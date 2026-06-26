#!/usr/bin/env python3
"""Submit OpenAI Batch jobs to judge DSL_batches against scraped source text."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from batch_utils import (
    BATCHES_DIR,
    CARD_BATCHES_DIR,
    DEFAULT_MAX_ENQUEUED_TOKENS,
    DSL_BATCHES_DIR,
    make_client,
    print_batch_info,
)
from judge_utils import (
    JUDGMENTS_DIR,
    chunk_judge_batch_files,
    judged_batch_stems,
    list_judge_batch_files,
    normalize_batch_stem,
    submit_judge_chunk,
)


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


def select_chunks(
    all_chunks: list[list[Path]],
    chunk_numbers: list[int],
) -> list[tuple[int, list[Path]]]:
    chunk_count = len(all_chunks)
    selected: list[tuple[int, list[Path]]] = []
    for chunk_number in chunk_numbers:
        if chunk_number < 1 or chunk_number > chunk_count:
            raise ValueError(
                f"Chunk {chunk_number} out of range. Valid chunks: 1-{chunk_count}."
            )
        selected.append((chunk_number, all_chunks[chunk_number - 1]))
    return selected


def print_chunk_layout(
    all_judge_batch_files: list[Path],
    *,
    dsl_dir: Path | None,
    source_dir: Path | None,
    max_enqueued_tokens: int,
) -> list[list[Path]]:
    chunks = chunk_judge_batch_files(
        all_judge_batch_files,
        dsl_dir=dsl_dir,
        source_dir=source_dir,
        max_enqueued_tokens=max_enqueued_tokens,
    )
    print(
        f"Judge chunk layout ({len(chunks)} chunk(s), "
        f"{len(all_judge_batch_files)} batch file(s), "
        f"max_enqueued_tokens={max_enqueued_tokens:,}):"
    )
    for index, chunk_files in enumerate(chunks, start=1):
        names = ", ".join(path.stem for path in chunk_files)
        print(f"  chunk {index}: {len(chunk_files)} file(s) — {names}")
    return chunks


def resolve_chunks_to_submit(
    all_judge_batch_files: list[Path],
    *,
    dsl_dir: Path | None,
    source_dir: Path | None,
    judgments_dir: Path | None,
    chunk_numbers: list[int] | None,
    remaining_only: bool,
    resubmit_chunks: bool,
    max_enqueued_tokens: int,
) -> tuple[list[tuple[int, list[Path]]], list[list[Path]]]:
    """Build stable chunks from the full judgeable set, then apply selection filters."""
    all_chunks = chunk_judge_batch_files(
        all_judge_batch_files,
        dsl_dir=dsl_dir,
        source_dir=source_dir,
        max_enqueued_tokens=max_enqueued_tokens,
    )

    if chunk_numbers:
        if resubmit_chunks:
            return select_chunks(all_chunks, chunk_numbers), all_chunks

        remaining_stems = {
            path.stem
            for path in list_judge_batch_files(
                dsl_dir=dsl_dir,
                source_dir=source_dir,
                judgments_dir=judgments_dir,
                remaining_only=True,
            )
        }
        selected: list[tuple[int, list[Path]]] = []
        for chunk_number, chunk_files in select_chunks(all_chunks, chunk_numbers):
            filtered = [path for path in chunk_files if path.stem in remaining_stems]
            if filtered:
                selected.append((chunk_number, filtered))
        return selected, all_chunks

    if remaining_only:
        remaining_stems = {
            path.stem
            for path in list_judge_batch_files(
                dsl_dir=dsl_dir,
                source_dir=source_dir,
                judgments_dir=judgments_dir,
                remaining_only=True,
            )
        }
        selected = []
        for chunk_number, chunk_files in enumerate(all_chunks, start=1):
            filtered = [path for path in chunk_files if path.stem in remaining_stems]
            if filtered:
                selected.append((chunk_number, filtered))
        return selected, all_chunks

    return list(enumerate(all_chunks, start=1)), all_chunks


def submit_judge_batches(
    *,
    dsl_dir: Path | None = None,
    source_dir: Path | None = None,
    judgments_dir: Path | None = None,
    batch_args: list[str] | None = None,
    chunk_numbers: list[int] | None = None,
    remaining_only: bool = True,
    resubmit_chunks: bool = True,
    max_enqueued_tokens: int = DEFAULT_MAX_ENQUEUED_TOKENS,
) -> None:
    all_judge_batch_files = list_judge_batch_files(
        dsl_dir=dsl_dir,
        source_dir=source_dir,
        judgments_dir=judgments_dir,
        remaining_only=False,
        batch_args=batch_args,
    )
    if not all_judge_batch_files:
        raise RuntimeError("No judge batch files found to submit.")

    chunks_to_submit, all_chunks = resolve_chunks_to_submit(
        all_judge_batch_files,
        dsl_dir=dsl_dir,
        source_dir=source_dir,
        judgments_dir=judgments_dir,
        chunk_numbers=chunk_numbers,
        remaining_only=remaining_only,
        resubmit_chunks=resubmit_chunks,
        max_enqueued_tokens=max_enqueued_tokens,
    )
    if not chunks_to_submit:
        judged = judged_batch_stems(judgments_dir)
        print(
            f"No batches to submit ({len(judged)} already in judgments/, "
            f"{len(all_judge_batch_files)} total judgeable). "
            "Use --chunks to resubmit a stable chunk or --all to resubmit everything.",
            file=sys.stderr,
        )
        return

    request_count = sum(len(chunk_files) for _, chunk_files in chunks_to_submit)
    judged_count = len(judged_batch_stems(judgments_dir))
    resubmitting = not remaining_only or bool(chunk_numbers and resubmit_chunks)
    print(
        f"Submitting {len(chunks_to_submit)} judge chunk(s) "
        f"for {request_count} batch file(s) "
        f"({judged_count} already judged, resubmit={'yes' if resubmitting else 'no'}).",
        file=sys.stderr,
    )

    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    client = make_client()
    submitted: list[dict] = []

    for chunk_index, chunk_files in chunks_to_submit:
        print(
            f"Submitting judge chunk {chunk_index} of {len(all_chunks)} "
            f"({len(chunk_files)} requests)...",
            file=sys.stderr,
        )
        info = submit_judge_chunk(
            client,
            chunk_files,
            chunk_index=chunk_index,
            chunk_count=len(all_chunks),
            run_timestamp=run_timestamp,
            dsl_dir=dsl_dir,
            source_dir=source_dir,
        )
        submitted.append(info)
        print_batch_info(info)
        print()

    manifest_path = BATCHES_DIR / f"judge-batches-{run_timestamp}.manifest.json"
    manifest = {
        "run_timestamp": run_timestamp,
        "model": submitted[0]["model"],
        "chunk_count": len(all_chunks),
        "submitted_chunk_count": len(submitted),
        "request_count": request_count,
        "remaining_only": remaining_only,
        "resubmit_chunks": resubmit_chunks,
        "chunk_numbers": chunk_numbers,
        "max_enqueued_tokens": max_enqueued_tokens,
        "judgments_dir": str(resolve_judgments_dir(judgments_dir)),
        "batches": submitted,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Submitted {len(submitted)} judge batch job(s) for {request_count} batch files.")
    print(f"  manifest: {manifest_path}")
    print()
    print("Download results when complete:")
    print(f"  python download_judge_batch.py --manifest {manifest_path}")


def resolve_judgments_dir(judgments_dir: Path | None) -> Path:
    return judgments_dir if judgments_dir is not None else JUDGMENTS_DIR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Submit OpenAI Batch jobs to judge DSL_batches encodings against "
            "scraped-card-text source batches."
        )
    )
    parser.add_argument(
        "batches",
        nargs="*",
        help="Optional batch id(s) to judge (e.g. 041, batch-041). Default: all remaining.",
    )
    parser.add_argument(
        "--batches",
        dest="batches_flag",
        help="Comma-separated batch ids (alternative to positional args).",
    )
    parser.add_argument(
        "--chunk",
        dest="chunks_flag",
        help=(
            "Chunk number(s) to submit (comma-separated, 1-based). "
            "Uses the stable full-batch chunk layout and resubmits already-judged batches."
        ),
    )
    parser.add_argument(
        "--chunks",
        dest="chunks_flag_alias",
        help="Alias for --chunk.",
    )
    parser.add_argument(
        "--list-chunks",
        action="store_true",
        help="Print the stable judge chunk layout for all judgeable batches and exit.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Resubmit all judgeable batches (all chunks).",
    )
    parser.add_argument(
        "--remaining-only",
        action="store_true",
        help=(
            "With --chunk/--chunks, submit only not-yet-judged batches from those chunks "
            "(default: resubmit the full stable chunk)."
        ),
    )
    parser.add_argument(
        "--dsl-dir",
        default=str(DSL_BATCHES_DIR),
        help="Directory with parsed batch-*.json DSL files (default: DSL_batches/).",
    )
    parser.add_argument(
        "--source-dir",
        default=str(CARD_BATCHES_DIR),
        help="Directory with scraped source batch-*.json files.",
    )
    parser.add_argument(
        "--judgments-dir",
        default=str(JUDGMENTS_DIR),
        help="Directory used to detect already-judged batches (default: judgments/).",
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
    dsl_dir = Path(args.dsl_dir)
    source_dir = Path(args.source_dir)
    judgments_dir = Path(args.judgments_dir)
    batch_args = parse_batch_list(args.batches, args.batches_flag)
    chunks_value = args.chunks_flag or args.chunks_flag_alias
    chunk_numbers = parse_int_list(chunks_value) if chunks_value else None
    remaining_only = not args.all
    resubmit_chunks = not args.remaining_only

    try:
        all_judge_batch_files = list_judge_batch_files(
            dsl_dir=dsl_dir,
            source_dir=source_dir,
            judgments_dir=judgments_dir,
            remaining_only=False,
            batch_args=batch_args or None,
        )

        if args.list_chunks:
            if not all_judge_batch_files:
                print("No judge batch files found.", file=sys.stderr)
                sys.exit(1)
            print_chunk_layout(
                all_judge_batch_files,
                dsl_dir=dsl_dir,
                source_dir=source_dir,
                max_enqueued_tokens=args.max_enqueued_tokens,
            )
            return

        submit_judge_batches(
            dsl_dir=dsl_dir,
            source_dir=source_dir,
            judgments_dir=judgments_dir,
            batch_args=batch_args or None,
            chunk_numbers=chunk_numbers,
            remaining_only=remaining_only,
            resubmit_chunks=resubmit_chunks,
            max_enqueued_tokens=args.max_enqueued_tokens,
        )
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
