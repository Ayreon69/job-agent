"""Entry point: run the orchestrator over a single offer or over every
offer currently at status='nouveau' in SQLite.

Usage:
    python -m orchestrator.run --offer-id 7
    python -m orchestrator.run
        (batch mode: every offer with status='nouveau')

Each processed offer produces, under --output-dir (default: orchestrator/runs/):
    analysis_<id>.md          - the markdown analysis, only on success
    trace_orchestrator_<id>.json  - the orchestrator's own decision trace
    trace_scoring_<id>.json       - session 3's decision trace
    trace_generation_<id>.json    - session 4's decision trace
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from orchestrator.agent import orchestrator_trace_to_json, process_offer
from storage.db import connect, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path(__file__).parent / "runs"


def load_offer(offer_id: int) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, title, location, description, company, url FROM jobs WHERE id = ?", (offer_id,)
        ).fetchone()
    if row is None:
        raise ValueError(f"No offer with id={offer_id}")
    return {"id": row[0], "title": row[1], "location": row[2], "description": row[3], "company": row[4], "url": row[5]}


def load_new_offers() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, title, location, description, company, url FROM jobs WHERE status = 'nouveau' ORDER BY id"
        ).fetchall()
    return [
        {"id": r[0], "title": r[1], "location": r[2], "description": r[3], "company": r[4], "url": r[5]}
        for r in rows
    ]


def write_outputs(output_dir: Path, offer_id: int, result) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / f"trace_orchestrator_{offer_id}.json").write_text(
        orchestrator_trace_to_json(result.trace), encoding="utf-8"
    )
    if result.analysis_markdown:
        (output_dir / f"analysis_{offer_id}.md").write_text(result.analysis_markdown, encoding="utf-8")
    if result.scoring_trace_json:
        (output_dir / f"trace_scoring_{offer_id}.json").write_text(result.scoring_trace_json, encoding="utf-8")
    if result.generation_trace_json:
        (output_dir / f"trace_generation_{offer_id}.json").write_text(result.generation_trace_json, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the orchestrator (scoring -> generation) on job offers")
    parser.add_argument("--offer-id", type=int, default=None, help="Process a single offer instead of the full batch")
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--delay-seconds", type=float, default=2.0,
        help="Pause between offers in batch mode, to avoid bursting the Mistral API rate limit (seen in practice: 13/30 offers failed with HTTP 429 when run back-to-back without delay)",
    )
    args = parser.parse_args()

    init_db()
    output_dir = Path(args.output_dir)

    offers = [load_offer(args.offer_id)] if args.offer_id is not None else load_new_offers()
    if not offers:
        logger.info("Aucune offre à traiter (statut 'nouveau' introuvable).")
        return

    logger.info("Traitement de %d offre(s)...", len(offers))

    summary = {"analyse": 0, "a_valider_geographie": 0, "echec": 0}
    for i, offer in enumerate(offers):
        if i > 0 and args.delay_seconds > 0:
            time.sleep(args.delay_seconds)
        logger.info("=== Offre %s: %s ===", offer["id"], offer["title"])
        result = process_offer(offer)
        summary[result.status] = summary.get(result.status, 0) + 1
        write_outputs(output_dir, offer["id"], result)
        logger.info("[offer %s] statut final: %s", offer["id"], result.status)

    print("\n=== Résumé du run ===")
    for status, count in summary.items():
        print(f"  {status}: {count}")
    print(f"Total: {len(offers)}")


if __name__ == "__main__":
    main()
