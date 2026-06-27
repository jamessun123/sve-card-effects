#!/usr/bin/env python3
"""Download reparse batch results into reparse-failures/output/."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REPARSE_DIR = Path(__file__).resolve().parent
for path in (str(ROOT), str(REPARSE_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from batch_utils import BATCHES_DIR, make_client, resolve_path  # noqa: E402
from download_batch import (  # noqa: E402
    download_file_content,
    load_metadata,
    parse_output_jsonl,
    print_batch_status,
    resolve_batch_id,
    save_jsonl,
)

from reparse_utils import (  # noqa: E402
    MERGED_BATCHES_DIR,
    OUTPUT_DIR,
    load_merge_manifest,
    merge_manifest_for_custom_id,
    split_merged_response_to_batches,
)


def resolve_merge_manifest(
    metadata_path: Path | None,
    submit_manifest: dict | None,
) -> dict[str, Any] | None:
    if metadata_path and metadata_path.exists():
        info = load_metadata(metadata_path)
        manifest_path = info.get("merge_manifest_path")
        if manifest_path:
            return load_merge_manifest(Path(manifest_path))
        sidecar = Path(info.get("local_input_path", "")).with_suffix(".merge-manifest.json")
        if sidecar.exists():
            return load_merge_manifest(sidecar)
    if submit_manifest and submit_manifest.get("merge_manifest_path"):
        return load_merge_manifest(Path(submit_manifest["merge_manifest_path"]))
    default = MERGED_BATCHES_DIR / "merge-manifest.json"
    if default.exists():
        return load_merge_manifest(default)
    return None


def write_reparse_outputs(
    output_dir: Path,
    successes: list[dict],
    failures: list[dict],
    *,
    reparse_output_dir: Path | None = None,
    merge_manifest: dict[str, Any] | None = None,
) -> Path:
    parsed_dir = resolve_path(reparse_output_dir) if reparse_output_dir else OUTPUT_DIR
    parsed_dir.mkdir(parents=True, exist_ok=True)

    split_batch_stems: list[str] = []
    for item in successes:
        custom_id = item["custom_id"]
        request_meta = (
            merge_manifest_for_custom_id(merge_manifest, custom_id)
            if merge_manifest
            else None
        )
        if request_meta and request_meta.get("card_batches"):
            split_batch_stems.extend(
                split_merged_response_to_batches(
                    item["text"],
                    request_meta["card_batches"],
                    output_dir=parsed_dir,
                )
            )
            merged_raw = output_dir / f"{custom_id}.json"
            merged_raw.write_text(item["text"], encoding="utf-8")
        else:
            out_path = parsed_dir / f"{custom_id}.json"
            out_path.write_text(item["text"], encoding="utf-8")

    summary = {
        "success_count": len(successes),
        "failure_count": len(failures),
        "successes": [item["custom_id"] for item in successes],
        "failures": failures,
        "reparse_output_dir": str(parsed_dir),
        "split_batch_stems": sorted(set(split_batch_stems)),
        "merged": merge_manifest is not None,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return parsed_dir


def download_reparse_batch(
    batch_id: str,
    *,
    output_dir: Path | None = None,
    reparse_output_dir: Path | None = None,
    metadata_path: Path | None = None,
    submit_manifest: dict | None = None,
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
        output_dir = BATCHES_DIR / "reparse-output" / batch_id

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_output = download_file_content(client, batch.output_file_id)
    save_jsonl(output_dir / "batch_output.jsonl", raw_output)

    error_path = None
    if batch.error_file_id:
        error_content = download_file_content(client, batch.error_file_id)
        error_path = output_dir / "batch_errors.jsonl"
        save_jsonl(error_path, error_content)

    successes, failures = parse_output_jsonl(raw_output)
    merge_manifest = resolve_merge_manifest(metadata_path, submit_manifest)
    parsed_dir = write_reparse_outputs(
        output_dir,
        successes,
        failures,
        reparse_output_dir=reparse_output_dir,
        merge_manifest=merge_manifest,
    )

    if metadata_path and metadata_path.exists():
        info = load_metadata(metadata_path)
        info["status"] = batch.status
        info["output_file_id"] = batch.output_file_id
        info["error_file_id"] = batch.error_file_id
        info["local_output_dir"] = str(output_dir)
        info["local_reparse_output_dir"] = str(parsed_dir)
        metadata_path.write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print()
    print("Download complete.")
    print(f"  output_dir:           {output_dir}")
    print(f"  raw_output:           {output_dir / 'batch_output.jsonl'}")
    if error_path:
        print(f"  raw_errors:           {error_path}")
    print(f"  reparse_output_dir:   {parsed_dir}")
    print(f"  summary:              {output_dir / 'summary.json'}")
    print(f"  success_count:        {len(successes)}")
    print(f"  failure_count:        {len(failures)}")
    if merge_manifest:
        summary = load_metadata(output_dir / "summary.json")
        split_count = len(summary.get("split_batch_stems", []))
        print(f"  split_batch_files:    {split_count}")


def download_reparse_manifest(
    manifest_path: Path,
    output_root: Path | None = None,
    *,
    reparse_output_dir: Path | None = None,
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
        download_reparse_batch(
            batch_id,
            output_dir=output_dir,
            reparse_output_dir=reparse_output_dir,
            metadata_path=metadata_path,
            submit_manifest=manifest,
        )
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download reparse batch output into reparse-failures/output/."
    )
    parser.add_argument(
        "batch_id",
        nargs="?",
        help="OpenAI batch id.",
    )
    parser.add_argument(
        "--metadata",
        help="Path to a local .batch.json metadata file.",
    )
    parser.add_argument(
        "--manifest",
        help="Path to a reparse-failures-*.manifest.json file.",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory for raw batch downloads (default: batches/reparse-output/<batch_id>).",
    )
    parser.add_argument(
        "--reparse-output-dir",
        help="Directory for reparsed card JSON (default: reparse-failures/output/).",
    )
    args = parser.parse_args()

    reparse_output_dir = Path(args.reparse_output_dir) if args.reparse_output_dir else None

    if args.manifest:
        manifest_path = resolve_path(args.manifest)
        output_root = resolve_path(args.output_dir) if args.output_dir else None
        download_reparse_manifest(
            manifest_path,
            output_root=output_root,
            reparse_output_dir=reparse_output_dir,
        )
        return

    metadata_path = resolve_path(args.metadata) if args.metadata else None
    batch_id, metadata_path = resolve_batch_id(args.batch_id, metadata_path)
    output_dir = resolve_path(args.output_dir) if args.output_dir else None
    download_reparse_batch(
        batch_id,
        output_dir=output_dir,
        reparse_output_dir=reparse_output_dir,
        metadata_path=metadata_path,
    )


if __name__ == "__main__":
    main()
