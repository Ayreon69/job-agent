"""Entry point: generate a candidacy analysis for a job offer already stored
in SQLite, chaining the session-3 scoring agent into the session-4
generation agent.

Usage:
    python -m generation.run --offer-id 7
    python -m generation.run --offer-id 7 --output analysis_7.md --trace-file trace_gen_7.json
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from generation.analysis import generate_analysis, trace_to_json
from scoring.agent import score_offer
from storage.db import connect

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def load_offer(offer_id: int) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, title, location, description, company FROM jobs WHERE id = ?", (offer_id,)
        ).fetchone()
    if row is None:
        raise ValueError(f"No offer with id={offer_id}")
    return {"id": row[0], "title": row[1], "location": row[2], "description": row[3], "company": row[4]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a candidacy analysis for a job offer")
    parser.add_argument("--offer-id", type=int, required=True)
    parser.add_argument("--output", type=str, default=None, help="Optional path to write the markdown analysis")
    parser.add_argument("--trace-file", type=str, default=None, help="Optional path to write the generation trace JSON")
    args = parser.parse_args()

    offer = load_offer(args.offer_id)
    scoring_result = score_offer(
        offer_id=offer["id"],
        title=offer["title"],
        location=offer["location"],
        description=offer["description"],
    )
    markdown, trace = generate_analysis(
        scoring_result,
        offer_title=offer["title"],
        offer_description=offer["description"] or "",
        company_name=offer.get("company"),
    )

    print(f"\n=== Analyse — offre {offer['id']} ({offer['title']}) ===\n")
    print(markdown)

    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
        logger.info("Analyse écrite dans %s", args.output)
    if args.trace_file:
        Path(args.trace_file).write_text(trace_to_json(trace), encoding="utf-8")
        logger.info("Trace de génération écrite dans %s", args.trace_file)


if __name__ == "__main__":
    main()
