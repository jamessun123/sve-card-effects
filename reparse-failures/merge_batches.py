#!/usr/bin/env python3
"""Merge per-batch reparse input files into fewer API requests."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPARSE_DIR = Path(__file__).resolve().parent
ROOT = REPARSE_DIR.parent
for path in (str(ROOT), str(REPARSE_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from batch_utils import DEFAULT_MAX_REQUEST_TOKENS
from reparse_utils import (
    INPUT_BATCHES_DIR,
    MERGED_BATCHES_DIR,
    estimate_reparse_cards_tokens,
    list_per_batch_input_files,
    write_merged_input_batches,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Merge reparse-failures/input-batches/batch-*.json into fewer "
            "reparse-merge-*.json files by token budget."
        )
    )
    parser.add_argument(
        "--input-dir",
        default=str(INPUT_BATCHES_DIR),
        help="Directory with per-batch input files.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(MERGED_BATCHES_DIR),
        help="Directory for merged request files (default: input-batches/merged/).",
    )
    parser.add_argument(
        "--max-request-tokens",
        type=int,
        default=DEFAULT_MAX_REQUEST_TOKENS,
        help=(
            "Max estimated prompt tokens per merged API request "
            f"(default: {DEFAULT_MAX_REQUEST_TOKENS:,})."
        ),
    )
    args = parser.parse_args()

    try:
        batch_files = list_per_batch_input_files(Path(args.input_dir))
        out_dir, merged_paths, manifest = write_merged_input_batches(
            batch_files,
            output_dir=Path(args.output_dir),
            max_request_tokens=args.max_request_tokens,
        )

        print(
            f"Merged {manifest['source_batch_count']} source batch file(s) "
            f"({manifest['card_count']} cards) into {manifest['merged_request_count']} request(s)."
        )
        print(f"  output_dir: {out_dir}")
        print(f"  manifest:   {out_dir / 'merge-manifest.json'}")
        for request in manifest["requests"]:
            batches = ", ".join(request["source_batches"][:5])
            suffix = "..." if len(request["source_batches"]) > 5 else ""
            est_tokens = estimate_reparse_cards_tokens(request["cards"])
            print(
                f"  {request['custom_id']}: {request['card_count']} cards, "
                f"~{est_tokens:,} est tokens "
                f"from {len(request['source_batches'])} batch file(s) ({batches}{suffix})"
            )
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
