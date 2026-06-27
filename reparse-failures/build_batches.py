#!/usr/bin/env python3
"""Build input batches for re-parsing cards that failed judgment."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPARSE_DIR = Path(__file__).resolve().parent
if str(REPARSE_DIR) not in sys.path:
    sys.path.insert(0, str(REPARSE_DIR))

from reparse_utils import (
    DEFAULT_FAILING_VERDICTS,
    INPUT_BATCHES_DIR,
    collect_failing_cards,
    write_input_batches,
)


def parse_verdicts(value: str) -> frozenset[str]:
    verdicts = {part.strip() for part in value.split(",") if part.strip()}
    if not verdicts:
        raise ValueError("Provide at least one verdict name.")
    return frozenset(verdicts)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Collect cards with failing judgments and write reparse input batches "
            "to reparse-failures/input-batches/."
        )
    )
    parser.add_argument(
        "--judgments-dir",
        help="Directory with judgment batch-*.json files (default: judgments/).",
    )
    parser.add_argument(
        "--source-dir",
        help="Scraped source batches directory.",
    )
    parser.add_argument(
        "--dsl-dir",
        help="Parsed DSL batches directory (default: DSL_batches/).",
    )
    parser.add_argument(
        "--output-dir",
        help="Where to write input batches (default: reparse-failures/input-batches/).",
    )
    parser.add_argument(
        "--verdicts",
        default="fail,engine-missing",
        help="Comma-separated verdicts to include (default: fail,engine-missing).",
    )
    args = parser.parse_args()

    try:
        failing_verdicts = parse_verdicts(args.verdicts)
        batch_records, warnings = collect_failing_cards(
            judgments_dir=Path(args.judgments_dir) if args.judgments_dir else None,
            source_dir=Path(args.source_dir) if args.source_dir else None,
            dsl_dir=Path(args.dsl_dir) if args.dsl_dir else None,
            failing_verdicts=failing_verdicts,
        )

        for warning in warnings:
            print(f"Warning: {warning}", file=sys.stderr)

        if not batch_records:
            print("No failing cards found to build batches.", file=sys.stderr)
            sys.exit(1)

        out_dir, written_paths, manifest = write_input_batches(
            batch_records,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )

        print(f"Wrote {len(written_paths)} input batch file(s) with {manifest['card_count']} card(s).")
        print(f"  output_dir: {out_dir}")
        print(f"  manifest:   {out_dir / 'manifest.json'}")
        print(f"  verdicts:   {', '.join(sorted(failing_verdicts))}")
        for verdict, count in sorted(manifest["verdict_counts"].items()):
            print(f"    {verdict}: {count}")
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
