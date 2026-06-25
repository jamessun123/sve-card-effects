#!/usr/bin/env python3
"""Re-submit specific card batches or token-budget chunks, waiting between each job."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from batch_utils import (
    BATCHES_DIR,
    CARD_BATCHES_DIR,
    DEFAULT_MAX_ENQUEUED_TOKENS,
    chunk_card_batch_files,
    format_batch_errors,
    format_timestamp,
    list_card_batch_files,
    make_client,
    print_batch_info,
    submit_chunk,
    wait_for_batch_completion,
)
from judge_utils import normalize_batch_stem


@dataclass
class SubmitJob:
    label: str
    files: list[Path]
    chunk_index: int
    chunk_count: int


def parse_comma_list(value: str | None) -> list[str]:
    if not value:
        return []
    items: list[str] = []
    for part in value.split(","):
        part = part.strip()
        if part:
            items.append(part)
    return items


def parse_int_list(value: str | None) -> list[int]:
    numbers: list[int] = []
    seen: set[int] = set()
    for part in parse_comma_list(value):
        number = int(part)
        if number in seen:
            continue
        seen.add(number)
        numbers.append(number)
    return numbers


def parse_batch_list(positional: list[str], batches_flag: str | None) -> list[str]:
    batch_args = list(positional)
    batch_args.extend(parse_comma_list(batches_flag))
    deduped: list[str] = []
    seen: set[str] = set()
    for arg in batch_args:
        stem = normalize_batch_stem(arg)
        if stem in seen:
            continue
        seen.add(stem)
        deduped.append(arg)
    return deduped


def resolve_batch_files(batches_dir: Path, batch_args: list[str]) -> list[Path]:
    files: list[Path] = []
    for arg in batch_args:
        stem = normalize_batch_stem(arg)
        path = batches_dir / f"{stem}.json"
        if not path.exists():
            raise FileNotFoundError(f"Batch file not found: {path}")
        files.append(path)
    return files


def build_chunk_jobs(
    card_batches_dir: Path,
    chunk_numbers: list[int],
    *,
    max_enqueued_tokens: int,
) -> list[SubmitJob]:
    card_batch_files = list_card_batch_files(card_batches_dir)
    if not card_batch_files:
        raise RuntimeError("No batch-*.json files found to chunk.")

    chunks = chunk_card_batch_files(card_batch_files, max_enqueued_tokens=max_enqueued_tokens)
    chunk_count = len(chunks)
    jobs: list[SubmitJob] = []

    for chunk_number in chunk_numbers:
        if chunk_number < 1 or chunk_number > chunk_count:
            raise ValueError(
                f"Chunk {chunk_number} out of range. Valid chunks: 1-{chunk_count}."
            )
        chunk_files = chunks[chunk_number - 1]
        jobs.append(
            SubmitJob(
                label=f"chunk {chunk_number}",
                files=chunk_files,
                chunk_index=chunk_number,
                chunk_count=chunk_count,
            )
        )
    return jobs


def build_batch_jobs(batch_files: list[Path]) -> list[SubmitJob]:
    jobs: list[SubmitJob] = []
    total = len(batch_files)
    for index, batch_file in enumerate(batch_files, start=1):
        jobs.append(
            SubmitJob(
                label=batch_file.stem,
                files=[batch_file],
                chunk_index=index,
                chunk_count=total,
            )
        )
    return jobs


def print_chunk_layout(
    card_batches_dir: Path,
    *,
    max_enqueued_tokens: int,
) -> None:
    card_batch_files = list_card_batch_files(card_batches_dir)
    if not card_batch_files:
        raise RuntimeError("No batch-*.json files found to chunk.")

    chunks = chunk_card_batch_files(card_batch_files, max_enqueued_tokens=max_enqueued_tokens)
    print(f"Chunk layout ({len(chunks)} chunk(s), max_enqueued_tokens={max_enqueued_tokens:,}):")
    for index, chunk_files in enumerate(chunks, start=1):
        names = ", ".join(path.stem for path in chunk_files)
        print(f"  chunk {index}: {len(chunk_files)} file(s) — {names}")


def submit_and_wait(
    client,
    jobs: list[SubmitJob],
    *,
    run_timestamp: str,
    poll_interval_seconds: int,
) -> list[dict]:
    submitted: list[dict] = []
    total = len(jobs)

    for run_index, job in enumerate(jobs, start=1):
        file_count = len(job.files)
        file_label = job.files[0].name if file_count == 1 else f"{file_count} files"
        print(f"Submitting {job.label} ({file_label}) [{run_index} of {total}]...")
        info = submit_chunk(
            client,
            job.files,
            chunk_index=job.chunk_index,
            chunk_count=job.chunk_count,
            run_timestamp=run_timestamp,
            run_label="resubmit-batches",
        )
        print_batch_info(info)
        print()

        batch = wait_for_batch_completion(
            client,
            info["batch_id"],
            poll_interval_seconds=poll_interval_seconds,
        )
        info["status"] = batch.status
        info["output_file_id"] = batch.output_file_id
        info["error_file_id"] = batch.error_file_id
        info["completed_at"] = format_timestamp(batch.completed_at)
        info["submit_label"] = job.label
        Path(info["local_metadata_path"]).write_text(
            json.dumps(info, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        submitted.append(info)

        if batch.status != "completed":
            error_text = format_batch_errors(batch)
            message = f"{job.label} ended with status={batch.status}."
            if error_text:
                message = f"{message}\n{error_text}"
            raise RuntimeError(message)

        print(f"{job.label} completed.")
        print()

    return submitted


def submit_selected(
    *,
    card_batches_dir: Path,
    chunk_numbers: list[int],
    batch_args: list[str],
    max_enqueued_tokens: int,
    poll_interval_seconds: int,
) -> None:
    if not chunk_numbers and not batch_args:
        raise ValueError(
            "Specify at least one --chunk/--chunks and/or batch id via positional args or --batches."
        )

    jobs: list[SubmitJob] = []
    jobs.extend(
        build_chunk_jobs(
            card_batches_dir,
            chunk_numbers,
            max_enqueued_tokens=max_enqueued_tokens,
        )
    )
    if batch_args:
        batch_files = resolve_batch_files(card_batches_dir, batch_args)
        jobs.extend(build_batch_jobs(batch_files))

    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    client = make_client()
    submitted = submit_and_wait(
        client,
        jobs,
        run_timestamp=run_timestamp,
        poll_interval_seconds=poll_interval_seconds,
    )

    manifest_path = BATCHES_DIR / f"resubmit-batches-{run_timestamp}.manifest.json"
    manifest = {
        "run_timestamp": run_timestamp,
        "model": submitted[0]["model"],
        "job_count": len(submitted),
        "request_count": sum(len(info["custom_ids"]) for info in submitted),
        "chunks": chunk_numbers,
        "batches": [normalize_batch_stem(arg) for arg in batch_args],
        "max_enqueued_tokens": max_enqueued_tokens,
        "poll_interval_seconds": poll_interval_seconds,
        "jobs": submitted,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Submitted {len(submitted)} OpenAI batch job(s).")
    print(f"  manifest: {manifest_path}")
    print()
    print("Download results when complete:")
    print(f"  python download_batch.py --manifest {manifest_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Re-submit selected cards-by-name batch files and/or token-budget chunks, "
            "waiting for each OpenAI batch job to finish before submitting the next."
        )
    )
    parser.add_argument(
        "batches",
        nargs="*",
        help="Batch id(s) to submit individually (e.g. 041, batch-041).",
    )
    parser.add_argument(
        "--batches",
        dest="batches_flag",
        help="Comma-separated batch ids (alternative to positional args).",
    )
    parser.add_argument(
        "--chunk",
        dest="chunks_flag",
        help="Chunk number(s) to submit (comma-separated, 1-based). Each chunk may contain multiple batch files.",
    )
    parser.add_argument(
        "--chunks",
        dest="chunks_flag_alias",
        help="Alias for --chunk.",
    )
    parser.add_argument(
        "--list-chunks",
        action="store_true",
        help="Print the token-budget chunk layout and exit.",
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
            "Maximum estimated enqueued prompt tokens per chunk "
            f"(default: {DEFAULT_MAX_ENQUEUED_TOKENS:,})."
        ),
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=60,
        help="Seconds between batch status checks while waiting (default: 60).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    card_batches_dir = Path(args.batches_dir)
    chunks_value = args.chunks_flag or args.chunks_flag_alias

    try:
        if args.list_chunks:
            print_chunk_layout(
                card_batches_dir,
                max_enqueued_tokens=args.max_enqueued_tokens,
            )
            return

        batch_args = parse_batch_list(args.batches, args.batches_flag)
        chunk_numbers = parse_int_list(chunks_value)
        submit_selected(
            card_batches_dir=card_batches_dir,
            chunk_numbers=chunk_numbers,
            batch_args=batch_args,
            max_enqueued_tokens=args.max_enqueued_tokens,
            poll_interval_seconds=args.poll_interval,
        )
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
