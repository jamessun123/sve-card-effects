#!/usr/bin/env python3
"""Minimal ChatGPT API caller. Set your API key in secrets.json and prompt below."""

import json
from pathlib import Path

from openai import OpenAI

# --- Fill this in ---
prompt_body_filename = "prompt_example_body.txt"

with open("prompt_format.txt", "r") as f:
    PROMPT_CONTEXT = f.read()

with open(prompt_body_filename, "r") as f:
    PROMPT_BODY = f.read()

# Optional settings
MODEL = "gpt-5.4-mini"

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
        input=[
            {"role": "user", "content": PROMPT_CONTEXT + "\n" + PROMPT_BODY}
        ]
    )

    with open("outputs/" + prompt_body_filename.replace(".txt", "_output.json"), "w") as f:
        json.dump(response.output_text, f)
    print(f"Output written to outputs/{prompt_body_filename.replace('.txt', '_output.json')}")


if __name__ == "__main__":
    main()
