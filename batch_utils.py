#!/usr/bin/env python3
"""Shared helpers for OpenAI Batch API scripts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI

ROOT = Path(__file__).resolve().parent
PROMPT_FORMAT_PATH = ROOT / "prompt_format.txt"
BATCHES_DIR = ROOT / "batches"
DSL_BATCHES_DIR = ROOT / "DSL_batches"
CARD_BATCHES_DIR = ROOT / "scraped-card-text" / "cards-by-name-batches"
SECRETS_PATH = ROOT / "secrets.json"
MODEL = "gpt-5.4"
RESPONSES_ENDPOINT = "/v1/responses"
# OpenAI enqueued prompt token limit per model/org (gpt-5.4-mini defaults to 2M).
DEFAULT_MAX_ENQUEUED_TOKENS = 850_000
_CHARS_PER_TOKEN_ESTIMATE = 4

_PROMPT_FORMAT_CACHE: str | None = None


def load_api_key() -> str:
    if not SECRETS_PATH.exists():
        raise FileNotFoundError(
            f"Missing {SECRETS_PATH.name}. Copy secrets.example.json to secrets.json "
            "and add your OpenAI API key."
        )

    with SECRETS_PATH.open(encoding="utf-8") as f:
        secrets = json.load(f)

    api_key = secrets.get("openai_api_key", "").strip()
    if not api_key or api_key == "your-api-key-here":
        raise ValueError("Set openai_api_key in secrets.json before running.")

    return api_key


def make_client() -> OpenAI:
    return OpenAI(api_key=load_api_key())


def resolve_path(path: str | Path) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = ROOT / resolved
    return resolved


def load_prompt_format() -> str:
    global _PROMPT_FORMAT_CACHE
    if _PROMPT_FORMAT_CACHE is None:
        if not PROMPT_FORMAT_PATH.exists():
            raise FileNotFoundError(f"Missing prompt context file: {PROMPT_FORMAT_PATH}")
        _PROMPT_FORMAT_CACHE = PROMPT_FORMAT_PATH.read_text(encoding="utf-8")
    return _PROMPT_FORMAT_CACHE


def load_prompt(prompt_body_filename: str | Path) -> str:
    prompt_body_path = resolve_path(prompt_body_filename)
    if not prompt_body_path.exists():
        raise FileNotFoundError(f"Prompt body file not found: {prompt_body_path}")

    prompt_context = load_prompt_format()
    prompt_body = prompt_body_path.read_text(encoding="utf-8")
    return prompt_context + "\n" + prompt_body


def build_prompt_from_card_batch(card_batch_path: Path) -> str:
    card_batch_json = card_batch_path.read_text(encoding="utf-8").strip()
    prompt_body = f"<INPUT_CARDS>\n{card_batch_json}\n</INPUT_CARDS>"
    return load_prompt_format() + "\n" + prompt_body


def estimate_prompt_tokens(prompt: str) -> int:
    return max(1, len(prompt) // _CHARS_PER_TOKEN_ESTIMATE)


def estimate_card_batch_tokens(card_batch_path: Path) -> int:
    return estimate_prompt_tokens(build_prompt_from_card_batch(card_batch_path))


def chunk_card_batch_files(
    card_batch_files: list[Path],
    max_enqueued_tokens: int = DEFAULT_MAX_ENQUEUED_TOKENS,
) -> list[list[Path]]:
    chunks: list[list[Path]] = []
    current_chunk: list[Path] = []
    current_tokens = 0

    for card_batch_path in card_batch_files:
        request_tokens = estimate_card_batch_tokens(card_batch_path)
        if request_tokens > max_enqueued_tokens:
            raise RuntimeError(
                f"{card_batch_path.name} alone exceeds the enqueued token budget "
                f"({request_tokens:,} estimated tokens > {max_enqueued_tokens:,})."
            )

        if current_chunk and current_tokens + request_tokens > max_enqueued_tokens:
            chunks.append(current_chunk)
            current_chunk = []
            current_tokens = 0

        current_chunk.append(card_batch_path)
        current_tokens += request_tokens

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def build_batch_request_line(custom_id: str, prompt: str) -> dict[str, Any]:
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": RESPONSES_ENDPOINT,
        "body": {
            "model": MODEL,
            "input": [{"role": "user", "content": prompt}],
        },
    }


def list_card_batch_files(batches_dir: Path | None = None) -> list[Path]:
    directory = batches_dir or CARD_BATCHES_DIR
    if not directory.exists():
        raise FileNotFoundError(f"Card batch directory not found: {directory}")
    return sorted(directory.glob("batch-*.json"))


def format_timestamp(unix_time: int | None) -> str:
    if unix_time is None:
        return "-"
    return datetime.fromtimestamp(unix_time, tz=timezone.utc).isoformat()


def batch_info_dict(
    batch: object,
    *,
    input_path: Path,
    metadata_path: Path,
    custom_ids: list[str] | None = None,
    source_files: list[str] | None = None,
) -> dict[str, Any]:
    request_counts = getattr(batch, "request_counts", None)
    counts: dict[str, Any] = {}
    if request_counts is not None:
        counts = {
            "total": getattr(request_counts, "total", None),
            "completed": getattr(request_counts, "completed", None),
            "failed": getattr(request_counts, "failed", None),
        }

    info: dict[str, Any] = {
        "batch_id": batch.id,
        "status": batch.status,
        "endpoint": batch.endpoint,
        "model": MODEL,
        "input_file_id": batch.input_file_id,
        "output_file_id": batch.output_file_id,
        "error_file_id": batch.error_file_id,
        "completion_window": batch.completion_window,
        "created_at": format_timestamp(batch.created_at),
        "in_progress_at": format_timestamp(batch.in_progress_at),
        "expires_at": format_timestamp(batch.expires_at),
        "completed_at": format_timestamp(batch.completed_at),
        "failed_at": format_timestamp(batch.failed_at),
        "request_counts": counts,
        "local_input_path": str(input_path),
        "local_metadata_path": str(metadata_path),
    }
    if custom_ids is not None:
        info["custom_ids"] = custom_ids
    if source_files is not None:
        info["source_files"] = source_files
    return info


def format_batch_errors(batch: object) -> str | None:
    errors = getattr(batch, "errors", None)
    if not errors:
        return None

    data = getattr(errors, "data", None) or []
    if not data:
        return None

    lines = []
    for item in data:
        code = getattr(item, "code", None) or item.get("code")
        message = getattr(item, "message", None) or item.get("message")
        line = getattr(item, "line", None) if hasattr(item, "line") else item.get("line")
        prefix = f"line {line}: " if line is not None else ""
        lines.append(f"{prefix}{code}: {message}")
    return "\n".join(lines)


def print_batch_info(info: dict[str, Any]) -> None:
    counts = info.get("request_counts", {})
    print("Batch submitted.")
    print(f"  batch_id:            {info['batch_id']}")
    print(f"  status:              {info['status']}")
    print(f"  endpoint:            {info['endpoint']}")
    print(f"  model:               {info['model']}")
    print(f"  input_file_id:       {info['input_file_id']}")
    print(f"  output_file_id:      {info.get('output_file_id') or '-'}")
    print(f"  error_file_id:       {info.get('error_file_id') or '-'}")
    print(f"  completion_window:   {info['completion_window']}")
    print(f"  created_at:          {info['created_at']}")
    print(f"  expires_at:          {info['expires_at']}")
    print(
        "  request_counts:      "
        f"total={counts.get('total', '-')}, "
        f"completed={counts.get('completed', '-')}, "
        f"failed={counts.get('failed', '-')}"
    )
    if info.get("source_files"):
        print(f"  source_files:        {len(info['source_files'])}")
    if info.get("custom_ids"):
        print(f"  custom_ids:          {len(info['custom_ids'])}")
    print(f"  local_input_path:    {info['local_input_path']}")
    print(f"  local_metadata_path: {info['local_metadata_path']}")
    if info.get("chunk_index") is not None and info.get("chunk_count") is not None:
        print(f"  chunk:               {info['chunk_index']} of {info['chunk_count']}")
    if info.get("estimated_enqueued_tokens") is not None:
        print(f"  estimated_tokens:    {info['estimated_enqueued_tokens']:,}")


def extract_response_text(response_body: dict[str, Any]) -> str | None:
    output_text = response_body.get("output_text")
    if output_text:
        return output_text

    for item in response_body.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                return content["text"]
    return None


TERMINAL_BATCH_STATUSES = frozenset({"completed", "failed", "expired", "cancelled"})


def write_combined_batch_input(
    card_batch_files: list[Path],
    *,
    chunk_index: int,
    run_timestamp: str,
    run_label: str = "all-card-batches",
) -> tuple[Path, list[str], list[str], int]:
    BATCHES_DIR.mkdir(parents=True, exist_ok=True)
    input_path = BATCHES_DIR / f"{run_label}-{run_timestamp}-part{chunk_index:03d}.jsonl"

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
    client: OpenAI,
    card_batch_files: list[Path],
    *,
    chunk_index: int,
    chunk_count: int,
    run_timestamp: str,
    run_label: str = "all-card-batches",
) -> dict[str, Any]:
    input_path, custom_ids, source_files, estimated_tokens = write_combined_batch_input(
        card_batch_files,
        chunk_index=chunk_index,
        run_timestamp=run_timestamp,
        run_label=run_label,
    )
    metadata_path = input_path.with_suffix(".batch.json")

    uploaded = client.files.create(file=input_path.open("rb"), purpose="batch")
    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint=RESPONSES_ENDPOINT,
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


def print_batch_progress(batch: object) -> None:
    request_counts = getattr(batch, "request_counts", None)
    counts = {}
    if request_counts is not None:
        counts = {
            "total": getattr(request_counts, "total", None),
            "completed": getattr(request_counts, "completed", None),
            "failed": getattr(request_counts, "failed", None),
        }

    print(
        f"  status={batch.status} "
        f"total={counts.get('total', '-')} "
        f"completed={counts.get('completed', '-')} "
        f"failed={counts.get('failed', '-')}"
    )

    error_text = format_batch_errors(batch)
    if error_text:
        print(f"  errors: {error_text}")


def wait_for_batch_completion(
    client: OpenAI,
    batch_id: str,
    *,
    poll_interval_seconds: int = 60,
) -> object:
    import time

    print(f"Waiting for batch {batch_id} to finish...")
    while True:
        batch = client.batches.retrieve(batch_id)
        print_batch_progress(batch)

        if batch.status in TERMINAL_BATCH_STATUSES:
            return batch

        time.sleep(poll_interval_seconds)
