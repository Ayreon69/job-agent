"""Minimal LLM client wrapper for the scoring agent.

Uses the Mistral API (MISTRAL_API_KEY env var required). Kept to a single
pair of functions so the rest of the agent doesn't depend on the Mistral SDK
directly — swapping providers later only touches this file.
"""

from __future__ import annotations

import json
import os

from dotenv import load_dotenv

try:
    from mistralai import Mistral
except ImportError:
    # mistralai==2.6.0's top-level package is missing __init__.py exports
    # (installed wheel only has azure/client/extra/gcp submodules, no root
    # re-export of Mistral) — fall back to the internal path where the real
    # client class lives.
    from mistralai.client.sdk import Mistral

load_dotenv()

DEFAULT_MODEL = "mistral-large-latest"


def _get_client() -> Mistral:
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError(
            "MISTRAL_API_KEY is not set. Export it before running the scoring agent."
        )
    return Mistral(api_key=api_key)


def call_llm(system_prompt: str, user_prompt: str, model: str = DEFAULT_MODEL) -> str:
    """Send a single-turn prompt to the LLM and return the raw text response."""
    client = _get_client()
    response = client.chat.complete(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content


def call_llm_json(system_prompt: str, user_prompt: str, model: str = DEFAULT_MODEL) -> dict:
    """Like call_llm, but requests and parses a JSON object response."""
    client = _get_client()
    response = client.chat.complete(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)
