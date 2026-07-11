"""Minimal LLM client wrapper for the scoring agent.

Uses the Mistral API (MISTRAL_API_KEY env var required). Kept to a single
pair of functions so the rest of the agent doesn't depend on the Mistral SDK
directly — swapping providers later only touches this file.
"""

from __future__ import annotations

import json
import logging
import os
import time

from dotenv import load_dotenv

try:
    from mistralai import Mistral
except ImportError:
    # mistralai==2.6.0's top-level package is missing __init__.py exports
    # (installed wheel only has azure/client/extra/gcp submodules, no root
    # re-export of Mistral) — fall back to the internal path where the real
    # client class lives.
    from mistralai.client.sdk import Mistral

from mistralai.client.errors.sdkerror import SDKError

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "mistral-large-latest"

# Retry/backoff for HTTP 429 (rate limit) specifically — not a catch-all for
# every SDKError. An auth failure or a malformed request should surface
# immediately rather than being retried 3 times for nothing. This is a
# complement to orchestrator/run.py's fixed --delay-seconds between offers
# (session 5 follow-up): the fixed delay reduces how often 429s happen in the
# first place, this retry absorbs the ones that still slip through.
RATE_LIMIT_STATUS_CODE = 429
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE_SECONDS = 2.0


def _get_client() -> Mistral:
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError(
            "MISTRAL_API_KEY is not set. Export it before running the scoring agent."
        )
    return Mistral(api_key=api_key)


def _call_with_retry(
    make_request,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS,
):
    """Run make_request(), retrying with exponential backoff only on HTTP 429.

    Any other exception (auth error, malformed request, etc.) propagates
    immediately on the first attempt — those aren't transient and retrying
    them identically would just waste time before the same failure. If every
    retry is also rate-limited, the last 429 propagates normally so the
    caller (orchestrator) handles it exactly as before: status 'echec',
    full log, batch continues.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            return make_request()
        except SDKError as exc:
            status_code = getattr(exc, "status_code", None)
            if status_code != RATE_LIMIT_STATUS_CODE or attempt > max_retries:
                raise
            delay = backoff_base_seconds * (2 ** (attempt - 1))
            logger.warning(
                "Rate limit Mistral (429) — tentative %d/%d, nouvel essai dans %.0fs",
                attempt, max_retries, delay,
            )
            time.sleep(delay)


def call_llm(system_prompt: str, user_prompt: str, model: str = DEFAULT_MODEL) -> str:
    """Send a single-turn prompt to the LLM and return the raw text response."""
    client = _get_client()

    def make_request():
        return client.chat.complete(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

    response = _call_with_retry(make_request)
    return response.choices[0].message.content


def call_llm_json(system_prompt: str, user_prompt: str, model: str = DEFAULT_MODEL) -> dict:
    """Like call_llm, but requests and parses a JSON object response."""
    client = _get_client()

    def make_request():
        return client.chat.complete(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )

    response = _call_with_retry(make_request)
    return json.loads(response.choices[0].message.content)
