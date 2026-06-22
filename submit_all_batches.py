#!/usr/bin/env python3
"""Submit one OpenAI Batch job for every cards-by-name batch file."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from batch_utils import (
    BATCHES_DIR,
    CARD_BATCHES_DIR,
    build_batch_request_line,
    build_prompt_from_card_batch,
    batch_info_dict,
    list_card_batch_files,
    make_client,
    print_batch_info,
)


def write_combined_batch_input(
    card_batch_files: list[Path],
) -> tuple[Path, list[str], list[str]]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    BATCHES_DIR.mkdir(parents=True, exist_ok=True)
    input_path = BATCHES_DIR / f"all-card-batches-{timestamp}.jsonl"

    custom_ids: list[str] = []
    source_files: list[str] = []

    with input_path.open("w", encoding="utf-8") as f:
        for card_batch_path in card_batch_files:
            custom_id = card_batch_path.stem
            prompt = build_prompt_from_card_batch(card_batch_path)
            request_line = build_batch_request_line(custom_id, prompt)
            f.write(json.dumps(request_line, ensure_ascii=False) + "\n")
            custom_ids.append(custom_id)
            source_files.append(str(card_batch_path))

    return input_path, custom_ids, source_files


def submit_all(card_batches_dir: Path | None = None) -> None:
    card_batch_files = list_card_batch_files(card_batches_dir)
    if not card_batch_files:
        raise RuntimeError("No batch-*.json files found to submit.")

    input_path, custom_ids, source_files = write_combined_batch_input(card_batch_files)
    metadata_path = input_path.with_suffix(".batch.json")

    client = make_client()
    uploaded = client.files.create(file=input_path.open("rb"), purpose="batch")
    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint="/v1/responses",
        completion_window="24h",
        metadata={
            "source": "cards-by-name-batches",
            "request_count": str(len(custom_ids)),
        },
    )

    info = batch_info_dict(
        batch,
        input_path=input_path,
        metadata_path=metadata_path,
        custom_ids=custom_ids,
        source_files=source_files,
    )
    metadata_path.write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print_batch_info(info)
    print()
    print("Download results when complete:")
    print(f"  python download_batch.py {info['batch_id']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Submit all scraped-card-text/cards-by-name-batches/batch-*.json files "
            "as one OpenAI Batch job."
        )
    )
    parser.add_argument(
        "--batches-dir",
        default=str(CARD_BATCHES_DIR),
        help="Directory containing batch-*.json card input files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    submit_all(Path(args.batches_dir))


if __name__ == "__main__":
    main()
