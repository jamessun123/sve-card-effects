#!/usr/bin/env python3
"""Submit reparse-failure batches to the OpenAI Batch API."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPARSE_DIR = Path(__file__).resolve().parent
ROOT = REPARSE_DIR.parent
for path in (str(ROOT), str(REPARSE_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from batch_utils import BATCHES_DIR, DEFAULT_MAX_ENQUEUED_TOKENS, DEFAULT_MAX_REQUEST_TOKENS, make_client, print_batch_info

from reparse_utils import (
    INPUT_BATCHES_DIR,
    MERGED_BATCHES_DIR,
    RUN_LABEL,
    chunk_reparse_batch_files,
    estimate_reparse_batch_tokens,
    list_merged_input_files,
    list_per_batch_input_files,
    submit_reparse_chunk,
    write_merged_input_batches,
)


def parse_int_list(value: str | None) -> list[int]:
    if not value:
        return []
    numbers: list[int] = []
    seen: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        number = int(part)
        if number in seen:
            continue
        seen.add(number)
        numbers.append(number)
    return numbers


def select_chunks(
    all_chunks: list[list[Path]],
    chunk_numbers: list[int],
) -> list[tuple[int, list[Path]]]:
    selected: list[tuple[int, list[Path]]] = []
    for chunk_number in chunk_numbers:
        if chunk_number < 1 or chunk_number > len(all_chunks):
            raise ValueError(
                f"Chunk {chunk_number} out of range. Valid chunks: 1-{len(all_chunks)}."
            )
        selected.append((chunk_number, all_chunks[chunk_number - 1]))
    return selected


def resolve_request_files(
    *,
    input_dir: Path,
    merged_dir: Path,
    use_merge: bool,
    max_request_tokens: int,
) -> tuple[list[Path], Path | None, dict | None]:
    if use_merge:
        per_batch_files = list_per_batch_input_files(input_dir)
        _, merged_paths, manifest = write_merged_input_batches(
            per_batch_files,
            output_dir=merged_dir,
            max_request_tokens=max_request_tokens,
        )
        merge_manifest_path = merged_dir / "merge-manifest.json"
        return merged_paths, merge_manifest_path, manifest

    return list_per_batch_input_files(input_dir), None, None


def print_chunk_layout(
    request_files: list[Path],
    *,
    manifest: dict | None,
    max_enqueued_tokens: int,
    max_request_tokens: int | None = None,
) -> list[list[Path]]:
    chunks = chunk_reparse_batch_files(request_files, max_enqueued_tokens=max_enqueued_tokens)
    card_count = manifest["card_count"] if manifest else None
    request_limit_label = (
        f", max_request_tokens={max_request_tokens:,}"
        if max_request_tokens is not None
        else ""
    )
    print(
        f"Reparse chunk layout ({len(chunks)} OpenAI batch job(s), "
        f"{len(request_files)} API request(s)"
        + (f", {card_count} cards" if card_count is not None else "")
        + f", max_enqueued_tokens={max_enqueued_tokens:,}{request_limit_label}):"
    )
    for index, chunk_files in enumerate(chunks, start=1):
        request_names = ", ".join(path.stem for path in chunk_files)
        cards_in_chunk = None
        chunk_tokens = 0
        if manifest:
            request_map = {r["custom_id"]: r for r in manifest.get("requests", [])}
            cards_in_chunk = sum(
                request_map[path.stem]["card_count"]
                for path in chunk_files
                if path.stem in request_map
            )
        for path in chunk_files:
            chunk_tokens += estimate_reparse_batch_tokens(path)
        card_label = f", {cards_in_chunk} cards" if cards_in_chunk is not None else ""
        print(
            f"  chunk {index}: {len(chunk_files)} request(s){card_label}, "
            f"~{chunk_tokens:,} est tokens — {request_names}"
        )
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Submit reparse-failures input to the OpenAI Batch API."
    )
    parser.add_argument(
        "--input-dir",
        default=str(INPUT_BATCHES_DIR),
        help="Directory with per-batch input batch-*.json files.",
    )
    parser.add_argument(
        "--merged-dir",
        default=str(MERGED_BATCHES_DIR),
        help="Directory for merged reparse-merge-*.json files.",
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="Submit one API request per batch-*.json file (legacy behavior).",
    )
    parser.add_argument(
        "--chunk",
        dest="chunks_flag",
        help="OpenAI batch job chunk number(s) to submit (comma-separated, 1-based).",
    )
    parser.add_argument(
        "--chunks",
        dest="chunks_flag_alias",
        help="Alias for --chunk.",
    )
    parser.add_argument(
        "--list-chunks",
        action="store_true",
        help="Print chunk layout and exit.",
    )
    parser.add_argument(
        "--max-enqueued-tokens",
        type=int,
        default=DEFAULT_MAX_ENQUEUED_TOKENS,
        help=(
            "Max estimated prompt tokens enqueued per OpenAI batch job "
            f"(default: {DEFAULT_MAX_ENQUEUED_TOKENS:,})."
        ),
    )
    parser.add_argument(
        "--max-request-tokens",
        type=int,
        default=DEFAULT_MAX_REQUEST_TOKENS,
        help=(
            "Max estimated prompt tokens per merged API request / model context "
            f"(default: {DEFAULT_MAX_REQUEST_TOKENS:,})."
        ),
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    merged_dir = Path(args.merged_dir)
    chunks_value = args.chunks_flag or args.chunks_flag_alias
    chunk_numbers = parse_int_list(chunks_value) if chunks_value else None
    use_merge = not args.no_merge

    try:
        request_files, merge_manifest_path, manifest = resolve_request_files(
            input_dir=input_dir,
            merged_dir=merged_dir,
            use_merge=use_merge,
            max_request_tokens=args.max_request_tokens,
        )

        if args.list_chunks:
            print_chunk_layout(
                request_files,
                manifest=manifest,
                max_enqueued_tokens=args.max_enqueued_tokens,
                max_request_tokens=args.max_request_tokens if use_merge else None,
            )
            return

        all_chunks = chunk_reparse_batch_files(
            request_files,
            max_enqueued_tokens=args.max_enqueued_tokens,
        )
        chunks_to_submit = (
            select_chunks(all_chunks, chunk_numbers)
            if chunk_numbers
            else list(enumerate(all_chunks, start=1))
        )

        run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        client = make_client()
        submitted: list[dict] = []

        for chunk_index, chunk_files in chunks_to_submit:
            print(
                f"Submitting reparse chunk {chunk_index} of {len(all_chunks)} "
                f"({len(chunk_files)} request(s))...",
                file=sys.stderr,
            )
            info = submit_reparse_chunk(
                client,
                chunk_files,
                chunk_index=chunk_index,
                chunk_count=len(all_chunks),
                run_timestamp=run_timestamp,
                merge_manifest_path=merge_manifest_path if use_merge else None,
            )
            submitted.append(info)
            print_batch_info(info)
            print()

        manifest_path = BATCHES_DIR / f"{RUN_LABEL}-{run_timestamp}.manifest.json"
        submit_manifest = {
            "run_timestamp": run_timestamp,
            "model": submitted[0]["model"],
            "chunk_count": len(all_chunks),
            "submitted_chunk_count": len(submitted),
            "request_count": sum(len(info["custom_ids"]) for info in submitted),
            "merged": use_merge,
            "input_dir": str(input_dir),
            "merged_dir": str(merged_dir) if use_merge else None,
            "merge_manifest_path": str(merge_manifest_path) if merge_manifest_path else None,
            "output_dir": str(REPARSE_DIR / "output"),
            "max_enqueued_tokens": args.max_enqueued_tokens,
            "max_request_tokens": args.max_request_tokens if use_merge else None,
            "batches": submitted,
        }
        if manifest:
            submit_manifest["card_count"] = manifest.get("card_count")
            submit_manifest["source_batch_count"] = manifest.get("source_batch_count")
        manifest_path.write_text(
            json.dumps(submit_manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        print(f"Submitted {len(submitted)} reparse OpenAI batch job(s).")
        print(f"  manifest: {manifest_path}")
        print()
        print("Download results when complete:")
        print(f"  python reparse-failures/download_batch.py --manifest {manifest_path}")
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
