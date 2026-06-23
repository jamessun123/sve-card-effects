#!/usr/bin/env python3
"""Download and extract results from a completed OpenAI Batch job."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from batch_utils import BATCHES_DIR, extract_response_text, format_batch_errors, make_client, resolve_path


def load_metadata(metadata_path: Path) -> dict:
    with metadata_path.open(encoding="utf-8") as f:
        return json.load(f)


def resolve_batch_id(batch_id: str | None, metadata: Path | None) -> tuple[str, Path | None]:
    if batch_id:
        return batch_id, metadata

    if metadata is None:
        raise ValueError("Provide batch_id or --metadata.")

    info = load_metadata(metadata)
    resolved_id = info.get("batch_id")
    if not resolved_id:
        raise ValueError(f"No batch_id found in metadata file: {metadata}")
    return resolved_id, metadata


def download_file_content(client, file_id: str) -> str:
    return client.files.content(file_id).text


def save_jsonl(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def parse_output_jsonl(raw_jsonl: str) -> tuple[list[dict], list[dict]]:
    successes: list[dict] = []
    failures: list[dict] = []

    for line_number, line in enumerate(raw_jsonl.splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        custom_id = record.get("custom_id", f"line-{line_number}")

        if record.get("error"):
            failures.append(
                {
                    "custom_id": custom_id,
                    "error": record["error"],
                }
            )
            continue

        response = record.get("response") or {}
        status_code = response.get("status_code")
        body = response.get("body") or {}

        if status_code != 200:
            failures.append(
                {
                    "custom_id": custom_id,
                    "status_code": status_code,
                    "body": body,
                }
            )
            continue

        text = extract_response_text(body)
        if text is None:
            failures.append(
                {
                    "custom_id": custom_id,
                    "error": "Response body did not contain output text.",
                    "body": body,
                }
            )
            continue

        successes.append(
            {
                "custom_id": custom_id,
                "text": text,
            }
        )

    return successes, failures


def write_extracted_outputs(
    output_dir: Path,
    successes: list[dict],
    failures: list[dict],
) -> None:
    extracted_dir = output_dir / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)

    for item in successes:
        out_path = extracted_dir / f"{item['custom_id']}.json"
        out_path.write_text(item["text"], encoding="utf-8")

    summary = {
        "success_count": len(successes),
        "failure_count": len(failures),
        "successes": [item["custom_id"] for item in successes],
        "failures": failures,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def print_batch_status(batch: object) -> None:
    request_counts = getattr(batch, "request_counts", None)
    counts = {}
    if request_counts is not None:
        counts = {
            "total": getattr(request_counts, "total", None),
            "completed": getattr(request_counts, "completed", None),
            "failed": getattr(request_counts, "failed", None),
        }

    print("Batch status.")
    print(f"  batch_id:       {batch.id}")
    print(f"  status:         {batch.status}")
    print(f"  output_file_id: {batch.output_file_id or '-'}")
    print(f"  error_file_id:  {batch.error_file_id or '-'}")
    print(
        "  request_counts: "
        f"total={counts.get('total', '-')}, "
        f"completed={counts.get('completed', '-')}, "
        f"failed={counts.get('failed', '-')}"
    )

    error_text = format_batch_errors(batch)
    if error_text:
        print("  errors:")
        for line in error_text.splitlines():
            print(f"    {line}")


def download_batch(
    batch_id: str,
    *,
    output_dir: Path | None = None,
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
        output_dir = BATCHES_DIR / "output" / batch_id

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_output = download_file_content(client, batch.output_file_id)
    save_jsonl(output_dir / "batch_output.jsonl", raw_output)

    error_path = None
    if batch.error_file_id:
        error_content = download_file_content(client, batch.error_file_id)
        error_path = output_dir / "batch_errors.jsonl"
        save_jsonl(error_path, error_content)

    successes, failures = parse_output_jsonl(raw_output)
    write_extracted_outputs(output_dir, successes, failures)

    if metadata_path and metadata_path.exists():
        info = load_metadata(metadata_path)
        info["status"] = batch.status
        info["output_file_id"] = batch.output_file_id
        info["error_file_id"] = batch.error_file_id
        info["local_output_dir"] = str(output_dir)
        metadata_path.write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print()
    print("Download complete.")
    print(f"  output_dir:      {output_dir}")
    print(f"  raw_output:      {output_dir / 'batch_output.jsonl'}")
    if error_path:
        print(f"  raw_errors:      {error_path}")
    print(f"  extracted_dir:   {output_dir / 'extracted'}")
    print(f"  summary:         {output_dir / 'summary.json'}")
    print(f"  success_count:   {len(successes)}")
    print(f"  failure_count:   {len(failures)}")


def download_manifest(manifest_path: Path, output_root: Path | None = None) -> None:
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
        download_batch(batch_id, output_dir=output_dir, metadata_path=metadata_path)
        print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download output from a completed OpenAI Batch job."
    )
    parser.add_argument(
        "batch_id",
        nargs="?",
        help="OpenAI batch id (for example batch_abc123).",
    )
    parser.add_argument(
        "--metadata",
        help="Path to a local .batch.json metadata file created by submit scripts.",
    )
    parser.add_argument(
        "--manifest",
        help="Path to a .manifest.json file created by submit_all_batches.py.",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory to write downloaded batch files (default: batches/output/<batch_id>).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.manifest:
        manifest_path = resolve_path(args.manifest)
        output_root = resolve_path(args.output_dir) if args.output_dir else None
        download_manifest(manifest_path, output_root=output_root)
        return

    metadata_path = resolve_path(args.metadata) if args.metadata else None
    batch_id, metadata_path = resolve_batch_id(args.batch_id, metadata_path)
    output_dir = resolve_path(args.output_dir) if args.output_dir else None
    download_batch(batch_id, output_dir=output_dir, metadata_path=metadata_path)


if __name__ == "__main__":
    main()
