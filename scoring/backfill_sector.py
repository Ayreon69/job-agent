"""One-off backfill: classify the business sector for offers scored before
scoring/agent.py's _extract_requirements started asking for it.

Deliberately NOT a full re-score: re-running score_offer() on every offer
would redo geography/RAG matching and the final LLM arbitrage, overwriting
analysis_<id>.md and the scoring/generation traces with a fresh (and
non-deterministic — see ROADMAP.md session 9 follow-up) LLM judgment call,
just to backfill one field. Instead this calls the same requirements
extraction _extract_requirements already makes (one Mistral call, no RAG),
keeps only its "sector" field, and patches ONLY that key into the existing
structured_analysis_<id>.json — matches/gaps/uncertain_flags, the markdown
analysis, and all three trace files are left untouched.

Idempotent / resumable: an offer whose structured_analysis_<id>.json already
has a non-null "sector" is skipped, so re-running after an interruption (or
a rate-limit failure) only processes what's still missing.

Usage:
    python -m scoring.backfill_sector [--delay-seconds 1.5]
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

from scoring.agent import _extract_requirements
from storage.db import connect, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

RUNS_DIR = Path(__file__).parent.parent / "orchestrator" / "runs"

# Same statuses the dashboard treats as "triageable" / analyzed — 'nouveau'
# has no description worth classifying yet, 'echec' has no
# structured_analysis_<id>.json to patch in the first place.
BACKFILL_STATUSES = ("analyse", "a_valider_geographie")


def _load_candidates() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            f"SELECT id, title, description FROM jobs WHERE status IN "
            f"({','.join('?' for _ in BACKFILL_STATUSES)}) ORDER BY id",
            BACKFILL_STATUSES,
        ).fetchall()
    return [{"id": r[0], "title": r[1], "description": r[2]} for r in rows]


def _needs_backfill(offer_id: int) -> bool:
    path = RUNS_DIR / f"structured_analysis_{offer_id}.json"
    if not path.exists():
        return False  # no structured analysis to patch — nothing this script can do
    data = json.loads(path.read_text(encoding="utf-8"))
    return not data.get("sector")


def _patch_sector(offer_id: int, sector: str | None) -> None:
    path = RUNS_DIR / f"structured_analysis_{offer_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["sector"] = sector
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill the 'sector' field for already-scored offers")
    parser.add_argument(
        "--delay-seconds", type=float, default=1.5,
        help="Pause between offers, same rate-limit precaution as orchestrator/run.py's own --delay-seconds",
    )
    args = parser.parse_args()

    init_db()
    candidates = [o for o in _load_candidates() if _needs_backfill(o["id"])]
    if not candidates:
        logger.info("Rien à backfiller — toutes les offres analysées ont déjà un secteur (ou aucune trace à patcher).")
        return

    logger.info("Backfill du secteur pour %d offre(s)...", len(candidates))
    done = 0
    failed = 0
    for i, offer in enumerate(candidates):
        if i > 0 and args.delay_seconds > 0:
            time.sleep(args.delay_seconds)
        try:
            requirements = _extract_requirements(offer["title"], offer["description"] or "")
            sector = requirements.get("sector")
            _patch_sector(offer["id"], sector)
            logger.info("[offer %s] secteur=%r", offer["id"], sector)
            done += 1
        except Exception:
            logger.exception("[offer %s] échec du backfill — offre laissée sans secteur, prochaine tentative au prochain run", offer["id"])
            failed += 1

    logger.info("Backfill terminé : %d offre(s) classée(s), %d échec(s).", done, failed)


if __name__ == "__main__":
    main()
