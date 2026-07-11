"""Tests for the 429 retry/backoff logic in scoring/llm.py (session 5 follow-up).

Not pytest: standalone script in the same style as the other tests/ scripts.
Two layers of proof, per the task:
  1. A deterministic mock test — no real API calls, fast, proves the retry
     mechanics themselves (backoff timing, retry count, non-429 pass-through,
     exhaustion behavior) without depending on actually triggering a real
     rate limit.
  2. A realistic end-to-end test (see tests/test_orchestrator_retry.py) that
     replays the exact conditions that caused 13/30 offers to fail with 429
     in session 5 (--delay-seconds 0, back-to-back real Mistral calls).
"""

from __future__ import annotations

import io
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from mistralai.client.errors.sdkerror import SDKError
from scoring.llm import _call_with_retry


def _make_429() -> SDKError:
    response = httpx.Response(status_code=429, request=httpx.Request("POST", "http://test"), text="rate limited")
    return SDKError("Rate limit exceeded", response)


def _make_401() -> SDKError:
    response = httpx.Response(status_code=401, request=httpx.Request("POST", "http://test"), text="unauthorized")
    return SDKError("Unauthorized", response)


def test_succeeds_after_two_429s() -> bool:
    """3rd attempt succeeds -> should return normally, having slept twice."""
    calls = MagicMock(side_effect=[_make_429(), _make_429(), "ok"])
    sleeps = []
    start = time.monotonic()
    result = _call_with_retry(calls, max_retries=3, backoff_base_seconds=0.01)
    elapsed = time.monotonic() - start

    ok = result == "ok" and calls.call_count == 3
    print(f"[{'OK' if ok else 'FAIL'}] succeeds after two 429s: result={result!r}, call_count={calls.call_count}, elapsed={elapsed:.3f}s")
    return ok


def test_exhausts_retries_then_raises() -> bool:
    """Every attempt 429s -> should raise the last SDKError after max_retries."""
    calls = MagicMock(side_effect=[_make_429(), _make_429(), _make_429(), _make_429()])
    raised = None
    try:
        _call_with_retry(calls, max_retries=3, backoff_base_seconds=0.01)
    except SDKError as exc:
        raised = exc

    ok = raised is not None and raised.status_code == 429 and calls.call_count == 4
    print(f"[{'OK' if ok else 'FAIL'}] exhausts retries then raises: call_count={calls.call_count}, raised={raised!r}")
    return ok


def test_non_429_not_retried() -> bool:
    """A 401 (auth error) must propagate on the FIRST attempt, no retry."""
    calls = MagicMock(side_effect=[_make_401(), "should never be reached"])
    raised = None
    try:
        _call_with_retry(calls, max_retries=3, backoff_base_seconds=0.01)
    except SDKError as exc:
        raised = exc

    ok = raised is not None and raised.status_code == 401 and calls.call_count == 1
    print(f"[{'OK' if ok else 'FAIL'}] non-429 not retried: call_count={calls.call_count} (expected 1), raised={raised!r}")
    return ok


def test_exponential_backoff_timing() -> bool:
    """Delays should roughly double each retry: base, 2*base, 4*base..."""
    calls = MagicMock(side_effect=[_make_429(), _make_429(), _make_429(), "ok"])
    sleep_calls = []
    original_sleep = time.sleep
    time.sleep = lambda s: sleep_calls.append(s)
    try:
        _call_with_retry(calls, max_retries=3, backoff_base_seconds=1.0)
    finally:
        time.sleep = original_sleep

    expected = [1.0, 2.0, 4.0]
    ok = sleep_calls == expected
    print(f"[{'OK' if ok else 'FAIL'}] exponential backoff timing: sleeps={sleep_calls} (expected {expected})")
    return ok


def main() -> None:
    results = [
        test_succeeds_after_two_429s(),
        test_exhausts_retries_then_raises(),
        test_non_429_not_retried(),
        test_exponential_backoff_timing(),
    ]
    passed = sum(results)
    print(f"\n{passed}/{len(results)} cas passés")
    if passed != len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
