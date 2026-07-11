"""Realistic, non-mocked reproduction of the session 5 rate-limit incident.

Session 5's 13 failures came from 30 offers hitting the Mistral API
back-to-back with --delay-seconds 0. When the same batch was re-run later
(this session, tests/test_llm_retry.py's sibling orchestrator run), 0 rate
limits occurred — the natural pacing from per-offer RAG/embedding work
(seconds of local computation between the two real LLM calls) was apparently
enough on its own this time, so the retry logic in scoring/llm.py was never
exercised end-to-end against a REAL 429.

This script removes that local-work spacing entirely: it fires real
call_llm() calls at the Mistral API in a tight loop, as fast as Python can
issue them, to reproduce genuine bursty conditions and prove the retry/
backoff in scoring/llm.py actually absorbs real 429s when they occur (not
just the mocked ones in test_llm_retry.py).

Not pytest: standalone script, run directly. Hits the real Mistral API and
costs real request quota — that is the point.
"""

from __future__ import annotations

import io
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from mistralai.client.errors.sdkerror import SDKError
from scoring.llm import call_llm

N_CALLS = 20


def main() -> None:
    successes = 0
    failures = 0
    retried_successes = 0

    for i in range(N_CALLS):
        try:
            import logging as _logging

            class _Counter(_logging.Handler):
                def __init__(self):
                    super().__init__()
                    self.count = 0

                def emit(self, record):
                    if "Rate limit Mistral" in record.getMessage():
                        self.count += 1

            counter = _Counter()
            _logging.getLogger("scoring.llm").addHandler(counter)

            result = call_llm("Réponds uniquement le mot 'ok'.", f"Requête de test numéro {i}.")
            _logging.getLogger("scoring.llm").removeHandler(counter)

            successes += 1
            if counter.count > 0:
                retried_successes += 1
            print(f"[{i}] OK (retries observés: {counter.count}) -> {result.strip()[:30]!r}")
        except SDKError as exc:
            failures += 1
            print(f"[{i}] ECHEC DEFINITIF après épuisement des tentatives: {exc}")

    print(f"\nRésumé: {successes}/{N_CALLS} succès, {failures}/{N_CALLS} échecs définitifs")
    print(f"Dont {retried_successes} succès obtenus APRES au moins un retry sur 429 (preuve que le backoff a absorbé un vrai rate limit)")


if __name__ == "__main__":
    main()
