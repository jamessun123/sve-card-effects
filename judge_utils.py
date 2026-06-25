#!/usr/bin/env python3
"""Helpers for LLM-as-judge card evaluation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from batch_utils import (
    CARD_BATCHES_DIR,
    DSL_BATCHES_DIR,
    MODEL,
    extract_response_text,
    make_client,
    resolve_path,
)

ROOT = Path(__file__).resolve().parent
JUDGE_PROMPT_FORMAT_PATH = ROOT / "judge_prompt_format.txt"
ABILITY_REFERENCE_PATH = ROOT / "ABILITY-REFERENCE.md"

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
        data = json.load(f)
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
    ability_reference = load_ability_reference()
    prompt = template.replace("{{ABILITY_REFERENCE}}", ability_reference)

    batch_payload = {
        "batch": batch_stem,
        "cards": pairs,
    }
    batch_json = json.dumps(batch_payload, ensure_ascii=False, indent=2)
    return prompt + f"\n<JUDGE_BATCH>\n{batch_json}\n</JUDGE_BATCH>\n"


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
