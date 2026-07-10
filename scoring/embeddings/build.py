"""Entry point: (re)build the ChromaDB profile index from scoring/profile/*.md.

Usage:
    python -m scoring.embeddings.build
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scoring.embeddings.index import PROFILE_DIR, build_index

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    collection = build_index()
    logger.info("Indexed %d chunks from %s into collection %r", collection.count(), PROFILE_DIR, collection.name)


if __name__ == "__main__":
    main()
