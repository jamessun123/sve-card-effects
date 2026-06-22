#!/usr/bin/env python3
"""Submit a single card-parsing prompt via the OpenAI Batch API."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from batch_utils import (
    BATCHES_DIR,
    build_batch_request_line,
    batch_info_dict,
    load_prompt,
    make_client,
    print_batch_info,
)

ROOT = Path(__file__).resolve().parent


def write_batch_input_file(prompt_body_filename: str, prompt: str) -> tuple[Path, str]:
    stem = Path(prompt_body_filename).stem
    custom_id = stem.replace(" ", "-")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    BATCHES_DIR.mkdir(parents=True, exist_ok=True)
    input_path = BATCHES_DIR / f"{stem}-{timestamp}.jsonl"

    request_line = build_batch_request_line(custom_id, prompt)
    with input_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(request_line, ensure_ascii=False) + "\n")

    return input_path, custom_id


def submit_batch(prompt_body_filename: str) -> None:
    prompt = load_prompt(prompt_body_filename)
    input_path, custom_id = write_batch_input_file(prompt_body_filename, prompt)
    metadata_path = input_path.with_suffix(".batch.json")

    client = make_client()
    uploaded = client.files.create(file=input_path.open("rb"), purpose="batch")
    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint="/v1/responses",
        completion_window="24h",
        metadata={
            "prompt_body_filename": prompt_body_filename,
            "custom_id": custom_id,
        },
    )

    info = batch_info_dict(
        batch,
        input_path=input_path,
        metadata_path=metadata_path,
        custom_ids=[custom_id],
        source_files=[prompt_body_filename],
    )
    info["prompt_body_filename"] = prompt_body_filename
    info["custom_id"] = custom_id
    metadata_path.write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print_batch_info(info)
    print()
    print("Download results when complete:")
    print(f"  python download_batch.py {info['batch_id']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Submit a card-parsing prompt to the OpenAI Batch API."
    )
    parser.add_argument(
        "prompt_body_filename",
        help="Path to the prompt body file (for example prompt_example_body.txt).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    submit_batch(args.prompt_body_filename)


if __name__ == "__main__":
    main()
