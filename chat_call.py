#!/usr/bin/env python3
"""Minimal ChatGPT API caller. Set your API key in secrets.json and prompt below."""

import json
from pathlib import Path

from openai import OpenAI

# --- Fill this in ---
with open("prompt.txt", "r") as f:
    PROMPT = f.read()

# Optional settings
MODEL = "gpt-5.4-nano"

SECRETS_PATH = Path(__file__).resolve().parent / "secrets.json"


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


def main() -> None:
    client = OpenAI(api_key=load_api_key())

    response = client.responses.create(
        model=MODEL,
        messages=[
            {"role": "user", "content": PROMPT}
        ],
        text_format=json.load(open("card_schema.json", "r"))
    )

    print(response.output_parsed)


if __name__ == "__main__":
    main()
