#!/usr/bin/env python3
"""Submit OpenAI Batch jobs for cards-by-name batch files."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from batch_utils import (
    BATCHES_DIR,
    CARD_BATCHES_DIR,
    DEFAULT_MAX_ENQUEUED_TOKENS,
    chunk_card_batch_files,
    list_card_batch_files,
    make_client,
    print_batch_info,
    submit_chunk,
)


def submit_all(
    card_batches_dir: Path | None = None,
    *,
    max_enqueued_tokens: int = DEFAULT_MAX_ENQUEUED_TOKENS,
) -> None:
    card_batch_files = list_card_batch_files(card_batches_dir)
    if not card_batch_files:
        raise RuntimeError("No batch-*.json files found to submit.")

    chunks = chunk_card_batch_files(card_batch_files, max_enqueued_tokens=max_enqueued_tokens)
    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    client = make_client()

    submitted: list[dict] = []
    for chunk_index, chunk_files in enumerate(chunks, start=1):
        info = submit_chunk(
            client,
            chunk_files,
            chunk_index=chunk_index,
            chunk_count=len(chunks),
            run_timestamp=run_timestamp,
        )
        submitted.append(info)
        print_batch_info(info)
        print()

    manifest_path = BATCHES_DIR / f"all-card-batches-{run_timestamp}.manifest.json"
    manifest = {
        "run_timestamp": run_timestamp,
        "model": submitted[0]["model"],
        "chunk_count": len(chunks),
        "request_count": len(card_batch_files),
        "max_enqueued_tokens": max_enqueued_tokens,
        "batches": submitted,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Submitted {len(submitted)} batch job(s) for {len(card_batch_files)} card batch files.")
    print(f"  manifest: {manifest_path}")
    print()
    print("Download results when complete:")
    print(f"  python download_batch.py --manifest {manifest_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Submit scraped-card-text/cards-by-name-batches/batch-*.json files "
            "as one or more OpenAI Batch jobs."
        )
    )
    parser.add_argument(
        "--batches-dir",
        default=str(CARD_BATCHES_DIR),
        help="Directory containing batch-*.json card input files.",
    )
    parser.add_argument(
        "--max-enqueued-tokens",
        type=int,
        default=DEFAULT_MAX_ENQUEUED_TOKENS,
        help=(
            "Maximum estimated enqueued prompt tokens per batch job "
            f"(default: {DEFAULT_MAX_ENQUEUED_TOKENS:,})."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    submit_all(Path(args.batches_dir), max_enqueued_tokens=args.max_enqueued_tokens)


if __name__ == "__main__":
    main()
