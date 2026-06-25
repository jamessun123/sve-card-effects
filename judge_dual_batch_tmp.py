#!/usr/bin/env python3
"""Temporary: judge one batch against source + DSL_batches + gpt54_chunk7 encodings."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from batch_utils import CARD_BATCHES_DIR, DSL_BATCHES_DIR, estimate_prompt_tokens, resolve_path
from judge_utils import (
    JUDGE_PROMPT_FORMAT_PATH,
    call_judge,
    load_json,
    normalize_batch_stem,
)

ROOT = Path(__file__).resolve().parent
GPT54_CHUNK7_DIR = ROOT / "gpt54_chunk7"

_DUAL_INSTRUCTIONS = """
<DUAL_PARSE_NOTE>
Each card includes two parser outputs to judge independently against `source`:
- `parsedDSL_batches` — encoding from the DSL_batches pipeline
- `parsedGpt54Chunk7` — encoding from the gpt54_chunk7 pipeline

Judge each parsed object separately using the same criteria and verdict values.
</DUAL_PARSE_NOTE>

<DUAL_RESPONSE_FORMAT>
Return **only** valid JSON — no markdown fences, no commentary.

Top-level object with:
- `batchSummary` — object with keys `dslBatches` and `gpt54Chunk7`, each:
  `{ "pass": N, "fail": N, "engine-missing": N }`
- One key per card name (same keys as input), each value:
  ```json
  {
    "dslBatches": { "verdict": "pass", "issues": [] },
    "gpt54Chunk7": { "verdict": "fail", "issues": ["..."] }
  }
  ```
</DUAL_RESPONSE_FORMAT>
"""


def pair_dual_batch_cards(
    source: dict[str, Any],
    dsl_batches: dict[str, Any],
    gpt54_chunk7: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    common = sorted(set(source) & set(dsl_batches) & set(gpt54_chunk7))
    pairs = [
        {
            "name": name,
            "source": source[name],
            "parsedDSL_batches": dsl_batches[name],
            "parsedGpt54Chunk7": gpt54_chunk7[name],
        }
        for name in common
    ]
    warnings = {
        "source_only": sorted(set(source) - set(dsl_batches) - set(gpt54_chunk7)),
        "dsl_only": sorted(set(dsl_batches) - set(source)),
        "gpt54_only": sorted(set(gpt54_chunk7) - set(source)),
        "missing_dsl": sorted(set(source) & set(gpt54_chunk7) - set(dsl_batches)),
        "missing_gpt54": sorted(set(source) & set(dsl_batches) - set(gpt54_chunk7)),
    }
    return pairs, warnings


def build_dual_judge_prompt(batch_stem: str, pairs: list[dict[str, Any]]) -> str:
    if not JUDGE_PROMPT_FORMAT_PATH.exists():
        raise FileNotFoundError(f"Missing judge prompt file: {JUDGE_PROMPT_FORMAT_PATH}")

    base_prompt = JUDGE_PROMPT_FORMAT_PATH.read_text(encoding="utf-8")
    prompt = base_prompt.replace(
        "- `parsed` — encoded DSL JSON produced by a parser model",
        "- `parsedDSL_batches` and `parsedGpt54Chunk7` — two encoded DSL JSON outputs to judge separately",
    )
    prompt = prompt.replace("</JUDGE_INSTRUCTIONS>", _DUAL_INSTRUCTIONS + "\n</JUDGE_INSTRUCTIONS>")

    batch_payload = {
        "batch": batch_stem,
        "cards": pairs,
    }
    batch_json = json.dumps(batch_payload, ensure_ascii=False, indent=2)
    return prompt + f"\n<JUDGE_BATCH>\n{batch_json}\n</JUDGE_BATCH>\n"


def resolve_dual_batch_paths(
    batch_stem: str,
    *,
    source_dir: Path | None = None,
    dsl_dir: Path | None = None,
    gpt54_dir: Path | None = None,
) -> tuple[Path, Path, Path]:
    source_root = resolve_path(source_dir) if source_dir else CARD_BATCHES_DIR
    dsl_root = resolve_path(dsl_dir) if dsl_dir else DSL_BATCHES_DIR
    gpt54_root = resolve_path(gpt54_dir) if gpt54_dir else GPT54_CHUNK7_DIR

    source_path = source_root / f"{batch_stem}.json"
    dsl_path = dsl_root / f"{batch_stem}.json"
    gpt54_path = gpt54_root / f"{batch_stem}.json"

    missing: list[str] = []
    if not source_path.exists():
        missing.append(str(source_path))
    if not dsl_path.exists():
        missing.append(str(dsl_path))
    if not gpt54_path.exists():
        missing.append(str(gpt54_path))
    if missing:
        raise FileNotFoundError("Missing batch file(s):\n  " + "\n  ".join(missing))

    return source_path, dsl_path, gpt54_path


def judge_dual_batch(
    batch_arg: str,
    *,
    source_dir: Path | None = None,
    dsl_dir: Path | None = None,
    gpt54_dir: Path | None = None,
    dry_run: bool = False,
    output_path: Path | None = None,
) -> str:
    batch_stem = normalize_batch_stem(batch_arg)
    source_path, dsl_path, gpt54_path = resolve_dual_batch_paths(
        batch_stem,
        source_dir=source_dir,
        dsl_dir=dsl_dir,
        gpt54_dir=gpt54_dir,
    )

    source = load_json(source_path)
    dsl_batches = load_json(dsl_path)
    gpt54_chunk7 = load_json(gpt54_path)
    pairs, warnings = pair_dual_batch_cards(source, dsl_batches, gpt54_chunk7)

    if not pairs:
        raise RuntimeError(
            f"No cards in common across {source_path.name}, {dsl_path.name}, and {gpt54_path.name}."
        )

    for label, names in warnings.items():
        if names:
            print(f"Warning ({label}): {', '.join(names)}", file=sys.stderr)

    prompt = build_dual_judge_prompt(batch_stem, pairs)
    estimated_tokens = estimate_prompt_tokens(prompt)
    print(
        f"Batch {batch_stem}: {len(pairs)} card(s), "
        f"~{estimated_tokens:,} estimated prompt tokens",
        file=sys.stderr,
    )
    print(f"  source:       {source_path}", file=sys.stderr)
    print(f"  DSL_batches:  {dsl_path}", file=sys.stderr)
    print(f"  gpt54_chunk7: {gpt54_path}", file=sys.stderr)

    if dry_run:
        content = prompt
    else:
        print("Calling OpenAI judge...", file=sys.stderr)
        content = call_judge(prompt)

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        print(f"Wrote {output_path}", file=sys.stderr)

    return content


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Temporary: judge one batch using scraped source, DSL_batches, and gpt54_chunk7."
        )
    )
    parser.add_argument(
        "batch",
        help="Batch identifier (e.g. 257, batch-257).",
    )
    parser.add_argument(
        "--source-dir",
        help="Scraped source batches dir (default: scraped-card-text/cards-by-name-batches).",
    )
    parser.add_argument(
        "--dsl-dir",
        help="DSL_batches directory (default: DSL_batches/).",
    )
    parser.add_argument(
        "--gpt54-dir",
        help="gpt54_chunk7 directory (default: gpt54_chunk7/).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the composed judge prompt without calling the API.",
    )
    parser.add_argument(
        "--output",
        help="Write prompt (dry-run) or judge response to this file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        content = judge_dual_batch(
            args.batch,
            source_dir=Path(args.source_dir) if args.source_dir else None,
            dsl_dir=Path(args.dsl_dir) if args.dsl_dir else None,
            gpt54_dir=Path(args.gpt54_dir) if args.gpt54_dir else None,
            dry_run=args.dry_run,
            output_path=Path(args.output) if args.output else None,
        )
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
    print(content)


if __name__ == "__main__":
    main()
