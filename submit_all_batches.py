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
    build_batch_request_line,
    build_prompt_from_card_batch,
    batch_info_dict,
    chunk_card_batch_files,
    estimate_prompt_tokens,
    list_card_batch_files,
    make_client,
    print_batch_info,
)


def write_combined_batch_input(
    card_batch_files: list[Path],
    *,
    chunk_index: int,
    run_timestamp: str,
) -> tuple[Path, list[str], list[str], int]:
    BATCHES_DIR.mkdir(parents=True, exist_ok=True)
    input_path = BATCHES_DIR / f"all-card-batches-{run_timestamp}-part{chunk_index:03d}.jsonl"

    custom_ids: list[str] = []
    source_files: list[str] = []
    estimated_tokens = 0

    with input_path.open("w", encoding="utf-8") as f:
        for card_batch_path in card_batch_files:
            custom_id = card_batch_path.stem
            prompt = build_prompt_from_card_batch(card_batch_path)
            request_line = build_batch_request_line(custom_id, prompt)
            f.write(json.dumps(request_line, ensure_ascii=False) + "\n")
            custom_ids.append(custom_id)
            source_files.append(str(card_batch_path))
            estimated_tokens += estimate_prompt_tokens(prompt)

    return input_path, custom_ids, source_files, estimated_tokens


def submit_chunk(
    client,
    card_batch_files: list[Path],
    *,
    chunk_index: int,
    chunk_count: int,
    run_timestamp: str,
) -> dict:
    input_path, custom_ids, source_files, estimated_tokens = write_combined_batch_input(
        card_batch_files,
        chunk_index=chunk_index,
        run_timestamp=run_timestamp,
    )
    metadata_path = input_path.with_suffix(".batch.json")

    uploaded = client.files.create(file=input_path.open("rb"), purpose="batch")
    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint="/v1/responses",
        completion_window="24h",
        metadata={
            "source": "cards-by-name-batches",
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
