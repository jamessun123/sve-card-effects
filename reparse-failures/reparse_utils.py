#!/usr/bin/env python3
"""Helpers for re-parsing cards that failed judgment."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from batch_utils import (  # noqa: E402
    BATCHES_DIR,
    CARD_BATCHES_DIR,
    DEFAULT_MAX_ENQUEUED_TOKENS,
    DEFAULT_MAX_REQUEST_TOKENS,
    DSL_BATCHES_DIR,
    RESPONSES_ENDPOINT,
    batch_info_dict,
    build_batch_request_line,
    estimate_prompt_tokens,
    load_prompt_format,
    resolve_path,
)

REPARSE_DIR = Path(__file__).resolve().parent
REPARSE_PROMPT_PATH = REPARSE_DIR / "prompt_format.txt"
INPUT_BATCHES_DIR = REPARSE_DIR / "input-batches"
MERGED_BATCHES_DIR = INPUT_BATCHES_DIR / "merged"
OUTPUT_DIR = REPARSE_DIR / "output"
JUDGMENTS_DIR = ROOT / "judgments"

DEFAULT_FAILING_VERDICTS = frozenset({"fail", "engine-missing"})
DEFAULT_MERGE_PREFIX = "reparse-merge"
RUN_LABEL = "reparse-failures"

_PROMPT_CACHE: str | None = None


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path}, got {type(data).__name__}.")
    return data


def load_reparse_prompt_preamble() -> str:
    global _PROMPT_CACHE
    if _PROMPT_CACHE is None:
        if not REPARSE_PROMPT_PATH.exists():
            raise FileNotFoundError(f"Missing reparse prompt: {REPARSE_PROMPT_PATH}")
        _PROMPT_CACHE = REPARSE_PROMPT_PATH.read_text(encoding="utf-8")
    return _PROMPT_CACHE


def build_reparse_prompt(batch_payload: dict[str, Any]) -> str:
    preamble = load_reparse_prompt_preamble()
    base_prompt = load_prompt_format()
    batch_json = json.dumps(batch_payload, ensure_ascii=False, indent=2)
    return (
        preamble
        + "\n"
        + base_prompt
        + f"\n<REPARSE_BATCH>\n{batch_json}\n</REPARSE_BATCH>\n"
    )


def build_reparse_prompt_for_file(batch_path: Path) -> str:
    payload = load_json(batch_path)
    return build_reparse_prompt(payload)


def estimate_reparse_cards_tokens(cards: dict[str, Any]) -> int:
    return estimate_prompt_tokens(build_reparse_prompt(cards))


def estimate_reparse_batch_tokens(batch_path: Path) -> int:
    return estimate_reparse_cards_tokens(load_json(batch_path))


def list_per_batch_input_files(input_dir: Path | None = None) -> list[Path]:
    directory = resolve_path(input_dir) if input_dir else INPUT_BATCHES_DIR
    if not directory.is_dir():
        raise FileNotFoundError(f"Input batch directory not found: {directory}")

    manifest_path = directory / "manifest.json"
    if manifest_path.exists():
        manifest = load_json(manifest_path)
        paths = []
        for batch_info in manifest.get("batches", []):
            path = Path(batch_info["path"])
            if not path.is_absolute():
                path = directory / path.name
            if path.exists():
                paths.append(path)
        if paths:
            return sorted(paths, key=lambda p: p.name)

    files = sorted(path for path in directory.glob("batch-*.json") if path.is_file())
    if not files:
        raise RuntimeError(f"No batch-*.json files found in {directory}")
    return files


def list_merged_input_files(merged_dir: Path | None = None) -> list[Path]:
    directory = resolve_path(merged_dir) if merged_dir else MERGED_BATCHES_DIR
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob(f"{DEFAULT_MERGE_PREFIX}-*.json") if path.is_file())


def merge_input_batch_files(
    batch_files: list[Path],
    *,
    max_request_tokens: int = DEFAULT_MAX_REQUEST_TOKENS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Pack per-batch files into fewer merged API requests by per-request token budget."""
    merged_requests: list[dict[str, Any]] = []
    current_cards: dict[str, Any] = {}
    current_source_batches: list[str] = []
    current_card_batches: dict[str, str] = {}

    def flush() -> None:
        nonlocal current_cards, current_source_batches, current_card_batches
        if not current_cards:
            return
        merge_index = len(merged_requests) + 1
        custom_id = f"{merge_prefix}-{merge_index:03d}"
        merged_requests.append(
            {
                "custom_id": custom_id,
                "cards": dict(current_cards),
                "source_batches": list(current_source_batches),
                "card_batches": dict(current_card_batches),
                "card_count": len(current_cards),
            }
        )
        current_cards = {}
        current_source_batches = []
        current_card_batches = {}

    merge_prefix = DEFAULT_MERGE_PREFIX

    for batch_path in batch_files:
        batch_stem = batch_path.stem
        cards = load_json(batch_path)
        if not cards:
            continue

        single_tokens = estimate_reparse_cards_tokens(cards)
        if single_tokens > max_request_tokens:
            raise RuntimeError(
                f"{batch_path.name} alone exceeds the per-request token budget "
                f"({single_tokens:,} estimated tokens > {max_request_tokens:,}). "
                "Split cards across smaller input batches and rebuild."
            )

        if current_cards:
            trial_cards = {**current_cards, **cards}
            trial_tokens = estimate_reparse_cards_tokens(trial_cards)
            if trial_tokens > max_request_tokens:
                flush()

        current_cards.update(cards)
        current_source_batches.append(batch_stem)
        for card_name in cards:
            current_card_batches[card_name] = batch_stem

    flush()

    if not merged_requests:
        raise RuntimeError("No cards found to merge.")

    manifest = {
        "merge_prefix": merge_prefix,
        "source_batch_count": len(batch_files),
        "merged_request_count": len(merged_requests),
        "card_count": sum(item["card_count"] for item in merged_requests),
        "max_request_tokens": max_request_tokens,
        "requests": merged_requests,
    }
    return merged_requests, manifest


def write_merged_input_batches(
    batch_files: list[Path],
    *,
    output_dir: Path | None = None,
    max_request_tokens: int = DEFAULT_MAX_REQUEST_TOKENS,
) -> tuple[Path, list[Path], dict[str, Any]]:
    out_dir = resolve_path(output_dir) if output_dir else MERGED_BATCHES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    merged_requests, manifest = merge_input_batch_files(
        batch_files,
        max_request_tokens=max_request_tokens,
    )

    current_ids = {request["custom_id"] for request in merged_requests}
    for stale_path in out_dir.glob(f"{DEFAULT_MERGE_PREFIX}-*.json"):
        if stale_path.stem not in current_ids:
            stale_path.unlink()

    written_paths: list[Path] = []
    for request in merged_requests:
        out_path = out_dir / f"{request['custom_id']}.json"
        out_path.write_text(
            json.dumps(request["cards"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written_paths.append(out_path)

    manifest_path = out_dir / "merge-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_dir, written_paths, manifest


def load_merge_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest_path = path or (MERGED_BATCHES_DIR / "merge-manifest.json")
    manifest_path = resolve_path(manifest_path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Merge manifest not found: {manifest_path}")
    return load_json(manifest_path)


def merge_manifest_for_custom_id(manifest: dict[str, Any], custom_id: str) -> dict[str, Any] | None:
    for request in manifest.get("requests", []):
        if request.get("custom_id") == custom_id:
            return request
    return None


def split_merged_response_to_batches(
    response_text: str,
    card_batches: dict[str, str],
    *,
    output_dir: Path,
) -> list[str]:
    parsed = json.loads(response_text)
    if not isinstance(parsed, dict):
        raise ValueError("Merged reparse response must be a JSON object keyed by card name.")

    by_batch: dict[str, dict[str, Any]] = {}
    for card_name, card_def in parsed.items():
        batch_stem = card_batches.get(card_name)
        if batch_stem is None:
            continue
        by_batch.setdefault(batch_stem, {})[card_name] = card_def

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for batch_stem, cards in sorted(by_batch.items()):
        out_path = output_dir / f"{batch_stem}.json"
        out_path.write_text(json.dumps(cards, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(batch_stem)
    return written


def collect_failing_cards(
    *,
    judgments_dir: Path | None = None,
    source_dir: Path | None = None,
    dsl_dir: Path | None = None,
    failing_verdicts: frozenset[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return per-batch records and warning messages."""
    judgments_root = resolve_path(judgments_dir) if judgments_dir else JUDGMENTS_DIR
    source_root = resolve_path(source_dir) if source_dir else CARD_BATCHES_DIR
    dsl_root = resolve_path(dsl_dir) if dsl_dir else DSL_BATCHES_DIR
    verdicts = failing_verdicts or DEFAULT_FAILING_VERDICTS

    batch_records: list[dict[str, Any]] = []
    warnings: list[str] = []

    for judgment_path in sorted(judgments_root.glob("batch-*.json")):
        batch_stem = judgment_path.stem
        source_path = source_root / f"{batch_stem}.json"
        dsl_path = dsl_root / f"{batch_stem}.json"

        if not source_path.exists():
            warnings.append(f"Skipping {batch_stem}: missing source {source_path}")
            continue
        if not dsl_path.exists():
            warnings.append(f"Skipping {batch_stem}: missing DSL {dsl_path}")
            continue

        judgments = load_json(judgment_path)
        source_cards = load_json(source_path)
        parsed_cards = load_json(dsl_path)

        repair_cards: dict[str, Any] = {}
        for card_name, judgment in judgments.items():
            verdict = judgment.get("verdict")
            if verdict not in verdicts:
                continue
            if card_name not in source_cards:
                warnings.append(f"{batch_stem}: source missing card {card_name!r}")
                continue
            if card_name not in parsed_cards:
                warnings.append(f"{batch_stem}: DSL missing card {card_name!r}")
                continue
            repair_cards[card_name] = {
                "source": source_cards[card_name],
                "previousParsed": parsed_cards[card_name],
                "verdict": verdict,
                "issues": judgment.get("issues") or [],
            }

        if repair_cards:
            batch_records.append(
                {
                    "batch_stem": batch_stem,
                    "cards": repair_cards,
                    "card_count": len(repair_cards),
                    "judgment_path": str(judgment_path),
                    "source_path": str(source_path),
                    "dsl_path": str(dsl_path),
                }
            )

    return batch_records, warnings


def write_input_batches(
    batch_records: list[dict[str, Any]],
    *,
    output_dir: Path | None = None,
) -> tuple[Path, list[Path], dict[str, Any]]:
    out_dir = resolve_path(output_dir) if output_dir else INPUT_BATCHES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    current_stems = {record["batch_stem"] for record in batch_records}
    for stale_path in out_dir.glob("batch-*.json"):
        if stale_path.stem not in current_stems:
            stale_path.unlink()

    written_paths: list[Path] = []
    total_cards = 0
    verdict_counts: dict[str, int] = {}

    for record in batch_records:
        batch_stem = record["batch_stem"]
        cards = record["cards"]
        out_path = out_dir / f"{batch_stem}.json"
        out_path.write_text(json.dumps(cards, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written_paths.append(out_path)
        total_cards += len(cards)
        for card in cards.values():
            verdict = card.get("verdict", "unknown")
            verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1

    manifest = {
        "batch_count": len(written_paths),
        "card_count": total_cards,
        "verdict_counts": verdict_counts,
        "batches": [
            {
                "batch_stem": record["batch_stem"],
                "card_count": record["card_count"],
                "path": str(out_dir / f"{record['batch_stem']}.json"),
            }
            for record in batch_records
        ],
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_dir, written_paths, manifest


def chunk_reparse_batch_files(
    batch_files: list[Path],
    *,
    max_enqueued_tokens: int = DEFAULT_MAX_ENQUEUED_TOKENS,
) -> list[list[Path]]:
    chunks: list[list[Path]] = []
    current_chunk: list[Path] = []
    current_tokens = 0

    for batch_path in batch_files:
        request_tokens = estimate_reparse_batch_tokens(batch_path)
        if request_tokens > max_enqueued_tokens:
            raise RuntimeError(
                f"{batch_path.name} alone exceeds the enqueued token budget "
                f"({request_tokens:,} estimated tokens > {max_enqueued_tokens:,})."
            )

        if current_chunk and current_tokens + request_tokens > max_enqueued_tokens:
            chunks.append(current_chunk)
            current_chunk = []
            current_tokens = 0

        current_chunk.append(batch_path)
        current_tokens += request_tokens

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def write_reparse_chunk_input(
    batch_files: list[Path],
    *,
    chunk_index: int,
    run_timestamp: str,
    run_label: str = RUN_LABEL,
    merge_manifest_path: Path | None = None,
) -> tuple[Path, list[str], list[str], int]:
    BATCHES_DIR.mkdir(parents=True, exist_ok=True)
    input_path = BATCHES_DIR / f"{run_label}-{run_timestamp}-part{chunk_index:03d}.jsonl"

    custom_ids: list[str] = []
    source_files: list[str] = []
    estimated_tokens = 0

    with input_path.open("w", encoding="utf-8") as f:
        for batch_path in batch_files:
            custom_id = batch_path.stem
            prompt = build_reparse_prompt_for_file(batch_path)
            request_line = build_batch_request_line(custom_id, prompt)
            f.write(json.dumps(request_line, ensure_ascii=False) + "\n")
            custom_ids.append(custom_id)
            source_files.append(str(batch_path))
            estimated_tokens += estimate_prompt_tokens(prompt)

    if merge_manifest_path is not None:
        sidecar = input_path.with_suffix(".merge-manifest.json")
        sidecar.write_text(
            resolve_path(merge_manifest_path).read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    return input_path, custom_ids, source_files, estimated_tokens


def submit_reparse_chunk(
    client,
    batch_files: list[Path],
    *,
    chunk_index: int,
    chunk_count: int,
    run_timestamp: str,
    run_label: str = RUN_LABEL,
    merge_manifest_path: Path | None = None,
) -> dict[str, Any]:
    input_path, custom_ids, source_files, estimated_tokens = write_reparse_chunk_input(
        batch_files,
        chunk_index=chunk_index,
        run_timestamp=run_timestamp,
        run_label=run_label,
        merge_manifest_path=merge_manifest_path,
    )
    metadata_path = input_path.with_suffix(".batch.json")

    uploaded = client.files.create(file=input_path.open("rb"), purpose="batch")
    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint=RESPONSES_ENDPOINT,
        completion_window="24h",
        metadata={
            "source": RUN_LABEL,
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
    if merge_manifest_path is not None:
        info["merge_manifest_path"] = str(resolve_path(merge_manifest_path))
        info["merged_requests"] = True
    metadata_path.write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return info
