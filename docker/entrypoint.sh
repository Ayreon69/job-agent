#!/bin/sh
# On a fresh named volume (first container start, or a volume that predates
# this app's index), scoring/embeddings/chroma/ is empty — search_profile()
# raises chromadb.errors.NotFoundError on the "profile" collection, which
# would send every single offer straight to status='echec' (session 5's
# catch-all decision 3) rather than failing loudly at startup where it's
# obvious what's wrong. Build the index once if it's missing, then start the
# API normally; if it's already there (persisted volume, most runs after the
# first), this is a fast no-op check, not a rebuild.
set -e

if [ ! -d "/app/scoring/embeddings/chroma" ] || [ -z "$(ls -A /app/scoring/embeddings/chroma 2>/dev/null)" ]; then
    echo "[entrypoint] Index ChromaDB absent, construction depuis scoring/profile/*.md..."
    python -m scoring.embeddings.build
else
    echo "[entrypoint] Index ChromaDB déjà présent (volume persisté), pas de reconstruction."
fi

exec "$@"
