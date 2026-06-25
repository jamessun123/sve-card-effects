#!/usr/bin/env python3
"""Judge parsed card DSL against scraped source text via OpenAI Responses API."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from batch_utils import estimate_prompt_tokens
from judge_utils import (
    build_judge_prompt,
    call_judge,
    load_json,
    normalize_batch_stem,
    pair_batch_cards,
    resolve_batch_paths,
)


def judge_batch(
    batch_arg: str,
    *,
    dsl_dir: Path | None = None,
    source_dir: Path | None = None,
    dry_run: bool = False,
    output_path: Path | None = None,
) -> str:
    batch_stem = normalize_batch_stem(batch_arg)
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

    if result.source_only:
        print(
            f"Warning: {len(result.source_only)} card(s) in source only: "
            + ", ".join(result.source_only),
            file=sys.stderr,
        )
    if result.parsed_only:
        print(
            f"Warning: {len(result.parsed_only)} card(s) in parsed only: "
            + ", ".join(result.parsed_only),
            file=sys.stderr,
        )

    prompt = build_judge_prompt(batch_stem, result.pairs)
    estimated_tokens = estimate_prompt_tokens(prompt)
    print(
        f"Batch {batch_stem}: {len(result.pairs)} card(s), "
        f"~{estimated_tokens:,} estimated prompt tokens",
        file=sys.stderr,
    )

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
            "Judge parsed card DSL from DSL_batches/ "
            "against scraped-card-text/cards-by-name-batches source batches."
        )
    )
    parser.add_argument(
        "batch",
        help="Batch identifier (e.g. 041, batch-041, or batch-041.json).",
    )
    parser.add_argument(
        "--dsl-dir",
        help="Directory with parsed batch-*.json DSL files (default: DSL_batches/).",
    )
    parser.add_argument(
        "--source-dir",
        help="Directory with scraped batch-*.json files (default: scraped-card-text/cards-by-name-batches).",
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
    dsl_dir = Path(args.dsl_dir) if args.dsl_dir else None
    source_dir = Path(args.source_dir) if args.source_dir else None
    output_path = Path(args.output) if args.output else None

    content = judge_batch(
        args.batch,
        dsl_dir=dsl_dir,
        source_dir=source_dir,
        dry_run=args.dry_run,
        output_path=output_path,
    )
    print(content)


if __name__ == "__main__":
    main()
