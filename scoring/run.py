"""Entry point: score a job offer already stored in SQLite.

Usage:
    python -m scoring.run --offer-id 7
    python -m scoring.run --offer-id 7 --trace-file trace_7.json
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scoring.agent import score_offer, trace_to_json
from storage.db import connect

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def load_offer(offer_id: int) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, title, location, description FROM jobs WHERE id = ?", (offer_id,)
        ).fetchone()
    if row is None:
        raise ValueError(f"No offer with id={offer_id}")
    return {"id": row[0], "title": row[1], "location": row[2], "description": row[3]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Score a job offer from the SQLite store")
    parser.add_argument("--offer-id", type=int, required=True)
    parser.add_argument("--trace-file", type=str, default=None, help="Optional path to write the decision trace JSON")
    args = parser.parse_args()

    offer = load_offer(args.offer_id)
    result = score_offer(
        offer_id=offer["id"],
        title=offer["title"],
        location=offer["location"],
        description=offer["description"],
    )

    print(f"\n=== Offre {offer['id']} — {offer['title']} ({offer['location']}) ===")
    print(f"Score: {result.score}/100")
    print(f"Zone géographique: {result.geography_zone} (priority_rank={result.geography_priority_rank})")
    print(f"\nMatches ({len(result.matches)}):")
    for m in result.matches:
        print(f"  - {m}")
    print(f"\nGaps ({len(result.gaps)}):")
    for g in result.gaps:
        print(f"  - {g}")
    print(f"\nIncertains ({len(result.uncertain_flags)}): {result.uncertain_flags}")
    print(f"\nRésumé: {result.reasoning_summary}")

    if args.trace_file:
        Path(args.trace_file).write_text(trace_to_json(result.trace), encoding="utf-8")
        logger.info("Trace écrite dans %s", args.trace_file)


if __name__ == "__main__":
    main()
