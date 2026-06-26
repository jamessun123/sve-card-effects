#!/usr/bin/env python3
"""Download judge batch results into judgments/."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from batch_utils import BATCHES_DIR, format_batch_errors, make_client, resolve_path
from download_batch import (
    download_file_content,
    load_metadata,
    parse_output_jsonl,
    print_batch_status,
    resolve_batch_id,
    save_jsonl,
)
from judge_utils import JUDGMENTS_DIR


def write_judgment_outputs(
    output_dir: Path,
    successes: list[dict],
    failures: list[dict],
    *,
    judgments_dir: Path | None = None,
) -> Path:
    judgments_root = resolve_path(judgments_dir) if judgments_dir else JUDGMENTS_DIR
    judgments_root.mkdir(parents=True, exist_ok=True)

    for item in successes:
        out_path = judgments_root / f"{item['custom_id']}.json"
        out_path.write_text(item["text"], encoding="utf-8")

    summary = {
        "success_count": len(successes),
        "failure_count": len(failures),
        "successes": [item["custom_id"] for item in successes],
        "failures": failures,
        "judgments_dir": str(judgments_root),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return judgments_root


def download_judge_batch(
    batch_id: str,
    *,
    output_dir: Path | None = None,
    judgments_dir: Path | None = None,
    metadata_path: Path | None = None,
) -> None:
    client = make_client()
    batch = client.batches.retrieve(batch_id)
    print_batch_status(batch)

    if batch.status != "completed":
        print()
        if batch.status == "failed":
            print("Batch validation or processing failed.")
        else:
            print(f"Batch is not complete yet (status={batch.status}).")
        print("Run this script again once the batch has finished.")
        return

    if not batch.output_file_id:
        raise RuntimeError(f"Batch {batch_id} is completed but has no output_file_id.")

    if output_dir is None:
        output_dir = BATCHES_DIR / "judge-output" / batch_id

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_output = download_file_content(client, batch.output_file_id)
    save_jsonl(output_dir / "batch_output.jsonl", raw_output)

    error_path = None
    if batch.error_file_id:
        error_content = download_file_content(client, batch.error_file_id)
        error_path = output_dir / "batch_errors.jsonl"
        save_jsonl(error_path, error_content)

    successes, failures = parse_output_jsonl(raw_output)
    judgments_root = write_judgment_outputs(
        output_dir,
        successes,
        failures,
        judgments_dir=judgments_dir,
    )

    if metadata_path and metadata_path.exists():
        info = load_metadata(metadata_path)
        info["status"] = batch.status
        info["output_file_id"] = batch.output_file_id
        info["error_file_id"] = batch.error_file_id
        info["local_output_dir"] = str(output_dir)
        info["local_judgments_dir"] = str(judgments_root)
        metadata_path.write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print()
    print("Download complete.")
    print(f"  output_dir:      {output_dir}")
    print(f"  raw_output:      {output_dir / 'batch_output.jsonl'}")
    if error_path:
        print(f"  raw_errors:      {error_path}")
    print(f"  judgments_dir:   {judgments_root}")
    print(f"  summary:         {output_dir / 'summary.json'}")
    print(f"  success_count:   {len(successes)}")
    print(f"  failure_count:   {len(failures)}")


def download_judge_manifest(
    manifest_path: Path,
    output_root: Path | None = None,
    *,
    judgments_dir: Path | None = None,
) -> None:
    manifest = load_metadata(manifest_path)
    batches = manifest.get("batches", [])
    if not batches:
        raise ValueError(f"No batches listed in manifest: {manifest_path}")

    print(f"Manifest: {manifest_path}")
    print(f"  chunk_count:   {manifest.get('chunk_count', len(batches))}")
    print(f"  request_count: {manifest.get('request_count', '-')}")
    print()

    for batch_info in batches:
        batch_id = batch_info["batch_id"]
        chunk_index = batch_info.get("chunk_index")
        chunk_label = f"part {chunk_index}" if chunk_index is not None else batch_id
        print(f"=== {chunk_label} ===")
        metadata_path = resolve_path(batch_info["local_metadata_path"])
        output_dir = None
        if output_root is not None:
            output_dir = output_root / batch_id
        download_judge_batch(
            batch_id,
            output_dir=output_dir,
            judgments_dir=judgments_dir,
            metadata_path=metadata_path,
        )
        print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download judge batch output into judgments/."
    )
    parser.add_argument(
        "batch_id",
        nargs="?",
        help="OpenAI batch id (for example batch_abc123).",
    )
    parser.add_argument(
        "--metadata",
        help="Path to a local .batch.json metadata file created by submit_judge_batches.py.",
    )
    parser.add_argument(
        "--manifest",
        help="Path to a judge-batches-*.manifest.json file.",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory for raw batch downloads (default: batches/judge-output/<batch_id>).",
    )
    parser.add_argument(
        "--judgments-dir",
        help="Directory for judgment JSON files (default: judgments/).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    judgments_dir = resolve_path(args.judgments_dir) if args.judgments_dir else None

    if args.manifest:
        manifest_path = resolve_path(args.manifest)
        output_root = resolve_path(args.output_dir) if args.output_dir else None
        download_judge_manifest(
            manifest_path,
            output_root=output_root,
            judgments_dir=judgments_dir,
        )
        return

    metadata_path = resolve_path(args.metadata) if args.metadata else None
    batch_id, metadata_path = resolve_batch_id(args.batch_id, metadata_path)
    output_dir = resolve_path(args.output_dir) if args.output_dir else None
    download_judge_batch(
        batch_id,
        output_dir=output_dir,
        judgments_dir=judgments_dir,
        metadata_path=metadata_path,
    )


if __name__ == "__main__":
    main()
