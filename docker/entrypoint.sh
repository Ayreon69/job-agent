#!/bin/sh
# On a fresh named volume (first container start, or a volume that predates
# this app's index), scoring/embeddings/chroma/ is empty — search_profile()
# raises chromadb.errors.NotFoundError on the "profile" collection, which
# would send every single offer straight to status='echec' (session 5's
# catch-all decision 3) rather than failing loudly at startup where it's
# obvious what's wrong. Build the index once if it's missing, then start the
# API normally; if it's already there (persisted volume, most runs after the
# first), this is a fast no-op check, not a rebuild.
#
# API_MODE=readonly (Render deployment follow-up) skips this entirely: a
# readonly deployment never calls search_profile()/score_offer() (POST
# /analyze returns 503 there, see api/main.py), so building the index would
# spend CPU/time/RAM (chromadb + sentence-transformers + torch, the exact
# weight this mode exists to avoid) on an index that's never queried. Render
# also gives no persistent volume across deploys (container filesystem is
# rebuilt from scratch every time) — even in "full" mode there, this branch
# would always take the "absent, rebuild" path on every single deploy;
# that's expected there and not specific to this API_MODE check.
set -e

if [ "$API_MODE" = "readonly" ]; then
    echo "[entrypoint] API_MODE=readonly — index ChromaDB non construit (jamais interrogé dans ce mode)."
elif [ ! -d "/app/scoring/embeddings/chroma" ] || [ -z "$(ls -A /app/scoring/embeddings/chroma 2>/dev/null)" ]; then
    echo "[entrypoint] Index ChromaDB absent, construction depuis scoring/profile/*.md..."
    python -m scoring.embeddings.build
else
    echo "[entrypoint] Index ChromaDB déjà présent (volume persisté), pas de reconstruction."
fi

exec "$@"
