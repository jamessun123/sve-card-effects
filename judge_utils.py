#!/usr/bin/env python3
"""Helpers for LLM-as-judge card evaluation."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from batch_utils import (
    BATCHES_DIR,
    CARD_BATCHES_DIR,
    DEFAULT_MAX_ENQUEUED_TOKENS,
    DSL_BATCHES_DIR,
    MODEL,
    RESPONSES_ENDPOINT,
    batch_info_dict,
    build_batch_request_line,
    estimate_prompt_tokens,
    extract_response_text,
    make_client,
    resolve_path,
)

ROOT = Path(__file__).resolve().parent
JUDGE_PROMPT_FORMAT_PATH = ROOT / "judge_prompt_format.txt"
ABILITY_REFERENCE_PATH = ROOT / "ABILITY-REFERENCE.md"
JUDGMENTS_DIR = ROOT / "judgments"

_BATCH_STEM_RE = re.compile(r"^batch-(\d+)$", re.IGNORECASE)


@dataclass
class PairResult:
    pairs: list[dict[str, Any]]
    source_only: list[str]
    parsed_only: list[str]


def normalize_batch_stem(arg: str) -> str:
    """Accept 041, batch-041, or batch-041.json and return batch-041."""
    stem = Path(arg).stem
    if _BATCH_STEM_RE.match(stem):
        return stem.lower()
    if stem.isdigit():
        return f"batch-{int(stem):03d}"
    raise ValueError(
        f"Invalid batch identifier: {arg!r}. Expected 041, batch-041, or batch-041.json."
    )


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path}, got {type(data).__name__}.")
    return data


def resolve_dsl_batches_dir(dsl_dir: Path | None = None) -> Path:
    """Resolve the directory containing parsed batch-*.json DSL files."""
    resolved = resolve_path(dsl_dir) if dsl_dir else DSL_BATCHES_DIR
    if not resolved.is_dir():
        raise FileNotFoundError(
            f"DSL batches directory not found: {resolved}. "
            "Run download_batch.py first or pass --dsl-dir."
        )
    return resolved


def pair_batch_cards(source: dict[str, Any], parsed: dict[str, Any]) -> PairResult:
    source_names = set(source)
    parsed_names = set(parsed)
    common = sorted(source_names & parsed_names)

    pairs = [
        {"name": name, "source": source[name], "parsed": parsed[name]}
        for name in common
    ]
    return PairResult(
        pairs=pairs,
        source_only=sorted(source_names - parsed_names),
        parsed_only=sorted(parsed_names - source_names),
    )


def load_ability_reference() -> str:
    if not ABILITY_REFERENCE_PATH.exists():
        raise FileNotFoundError(f"Missing ability reference: {ABILITY_REFERENCE_PATH}")
    return ABILITY_REFERENCE_PATH.read_text(encoding="utf-8")


def build_judge_prompt(batch_stem: str, pairs: list[dict[str, Any]]) -> str:
    if not JUDGE_PROMPT_FORMAT_PATH.exists():
        raise FileNotFoundError(f"Missing judge prompt file: {JUDGE_PROMPT_FORMAT_PATH}")

    template = JUDGE_PROMPT_FORMAT_PATH.read_text(encoding="utf-8")
    if "{{ABILITY_REFERENCE}}" in template:
        ability_reference = load_ability_reference()
        template = template.replace("{{ABILITY_REFERENCE}}", ability_reference)

    batch_payload = {
        "batch": batch_stem,
        "cards": pairs,
    }
    batch_json = json.dumps(batch_payload, ensure_ascii=False, indent=2)
    return template + f"\n<JUDGE_BATCH>\n{batch_json}\n</JUDGE_BATCH>\n"


def list_dsl_batch_files(dsl_dir: Path | None = None) -> list[Path]:
    directory = resolve_dsl_batches_dir(dsl_dir)
    return sorted(directory.glob("batch-*.json"))


def judged_batch_stems(judgments_dir: Path | None = None) -> set[str]:
    directory = resolve_path(judgments_dir) if judgments_dir else JUDGMENTS_DIR
    if not directory.is_dir():
        return set()
    return {path.stem for path in directory.glob("batch-*.json")}


def build_judge_prompt_for_batch(
    batch_stem: str,
    *,
    dsl_dir: Path | None = None,
    source_dir: Path | None = None,
) -> str:
    source_path, parsed_path = resolve_batch_paths(
        batch_stem,
        dsl_dir=dsl_dir,
        source_dir=source_dir,
    )
    source = load_json(source_path)
    parsed = load_json(parsed_path)
    result = pair_batch_cards(source, parsed)
    if not result.pairs:
        raise RuntimeError(
            f"No matching cards between {source_path.name} and {parsed_path.name}."
        )
    return build_judge_prompt(batch_stem, result.pairs)


def estimate_judge_batch_tokens(
    dsl_batch_path: Path,
    *,
    dsl_dir: Path | None = None,
    source_dir: Path | None = None,
) -> int:
    batch_stem = dsl_batch_path.stem
    prompt = build_judge_prompt_for_batch(
        batch_stem,
        dsl_dir=dsl_dir,
        source_dir=source_dir,
    )
    return estimate_prompt_tokens(prompt)


def list_judge_batch_files(
    *,
    dsl_dir: Path | None = None,
    source_dir: Path | None = None,
    judgments_dir: Path | None = None,
    remaining_only: bool = True,
    batch_args: list[str] | None = None,
) -> list[Path]:
    source_root = resolve_path(source_dir) if source_dir else CARD_BATCHES_DIR
    dsl_root = resolve_dsl_batches_dir(dsl_dir)
    judged = judged_batch_stems(judgments_dir) if remaining_only else set()

    if batch_args:
        candidates = [dsl_root / f"{normalize_batch_stem(arg)}.json" for arg in batch_args]
    else:
        candidates = list_dsl_batch_files(dsl_root)

    selected: list[Path] = []
    skipped: list[str] = []
    for dsl_path in candidates:
        batch_stem = dsl_path.stem
        source_path = source_root / f"{batch_stem}.json"
        if not dsl_path.exists():
            raise FileNotFoundError(f"DSL batch not found: {dsl_path}")
        if not source_path.exists():
            continue
        if remaining_only and batch_stem in judged:
            continue
        try:
            load_json(dsl_path)
            load_json(source_path)
        except ValueError as exc:
            skipped.append(str(exc))
            continue
        selected.append(dsl_path)

    if skipped:
        print(f"Skipping {len(skipped)} batch file(s) with invalid JSON:", file=sys.stderr)
        for message in skipped:
            print(f"  {message}", file=sys.stderr)

    return selected


def chunk_judge_batch_files(
    judge_batch_files: list[Path],
    *,
    dsl_dir: Path | None = None,
    source_dir: Path | None = None,
    max_enqueued_tokens: int = DEFAULT_MAX_ENQUEUED_TOKENS,
) -> list[list[Path]]:
    chunks: list[list[Path]] = []
    current_chunk: list[Path] = []
    current_tokens = 0

    for dsl_batch_path in judge_batch_files:
        request_tokens = estimate_judge_batch_tokens(
            dsl_batch_path,
            dsl_dir=dsl_dir,
            source_dir=source_dir,
        )
        if request_tokens > max_enqueued_tokens:
            raise RuntimeError(
                f"{dsl_batch_path.name} alone exceeds the enqueued token budget "
                f"({request_tokens:,} estimated tokens > {max_enqueued_tokens:,})."
            )

        if current_chunk and current_tokens + request_tokens > max_enqueued_tokens:
            chunks.append(current_chunk)
            current_chunk = []
            current_tokens = 0

        current_chunk.append(dsl_batch_path)
        current_tokens += request_tokens

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def write_judge_chunk_input(
    judge_batch_files: list[Path],
    *,
    chunk_index: int,
    run_timestamp: str,
    run_label: str = "judge-batches",
    dsl_dir: Path | None = None,
    source_dir: Path | None = None,
) -> tuple[Path, list[str], list[str], int]:
    BATCHES_DIR.mkdir(parents=True, exist_ok=True)
    input_path = BATCHES_DIR / f"{run_label}-{run_timestamp}-part{chunk_index:03d}.jsonl"

    custom_ids: list[str] = []
    source_files: list[str] = []
    estimated_tokens = 0

    with input_path.open("w", encoding="utf-8") as f:
        for dsl_batch_path in judge_batch_files:
            batch_stem = dsl_batch_path.stem
            prompt = build_judge_prompt_for_batch(
                batch_stem,
                dsl_dir=dsl_dir,
                source_dir=source_dir,
            )
            request_line = build_batch_request_line(batch_stem, prompt)
            f.write(json.dumps(request_line, ensure_ascii=False) + "\n")
            custom_ids.append(batch_stem)
            source_files.append(str(dsl_batch_path))
            estimated_tokens += estimate_prompt_tokens(prompt)

    return input_path, custom_ids, source_files, estimated_tokens


def submit_judge_chunk(
    client,
    judge_batch_files: list[Path],
    *,
    chunk_index: int,
    chunk_count: int,
    run_timestamp: str,
    run_label: str = "judge-batches",
    dsl_dir: Path | None = None,
    source_dir: Path | None = None,
) -> dict[str, Any]:
    input_path, custom_ids, source_files, estimated_tokens = write_judge_chunk_input(
        judge_batch_files,
        chunk_index=chunk_index,
        run_timestamp=run_timestamp,
        run_label=run_label,
        dsl_dir=dsl_dir,
        source_dir=source_dir,
    )
    metadata_path = input_path.with_suffix(".batch.json")

    uploaded = client.files.create(file=input_path.open("rb"), purpose="batch")
    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint=RESPONSES_ENDPOINT,
        completion_window="24h",
        metadata={
            "source": "judge-batches",
            "request_count": str(len(custom_ids)),
            "chunk_index": str(chunk_index),
            "chunk_count": str(chunk_count),
        },
    )

    info = batch_info_dict(
        batch,
        input_path=input_path,
        metadata_path=metadata_path,
        custom_ids=custom_ids,
        source_files=source_files,
    )
    info["chunk_index"] = chunk_index
    info["chunk_count"] = chunk_count
    info["estimated_enqueued_tokens"] = estimated_tokens
    metadata_path.write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return info


def call_judge(prompt: str) -> str:
    client = make_client()
    response = client.responses.create(
        model=MODEL,
        input=[{"role": "user", "content": prompt}],
    )
    body = response.model_dump() if hasattr(response, "model_dump") else dict(response)
    text = extract_response_text(body)
    if text is None:
        output_text = getattr(response, "output_text", None)
        if output_text:
            return output_text
        raise RuntimeError("Judge response did not contain output text.")
    return text


def resolve_batch_paths(
    batch_stem: str,
    *,
    dsl_dir: Path | None = None,
    source_dir: Path | None = None,
) -> tuple[Path, Path]:
    source_root = resolve_path(source_dir) if source_dir else CARD_BATCHES_DIR
    dsl_root = resolve_dsl_batches_dir(dsl_dir)

    source_path = source_root / f"{batch_stem}.json"
    parsed_path = dsl_root / f"{batch_stem}.json"

    if not source_path.exists():
        raise FileNotFoundError(f"Source batch not found: {source_path}")
    if not parsed_path.exists():
        raise FileNotFoundError(f"Parsed batch not found: {parsed_path}")

    return source_path, parsed_path
