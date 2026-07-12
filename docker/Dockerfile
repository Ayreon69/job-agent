# job-agent API — packages sessions 3-6 (scoring, generation, orchestrator, FastAPI)
# as-is. No new business logic here, purely deployment plumbing.
#
# Base image: python:3.11-slim to match job-agent/.venv (Python 3.11.9 locally) —
# using the same minor version avoids any surprise from a Python version drift
# affecting wheel availability (torch/chromadb ship version-specific wheels).
FROM python:3.11-slim

WORKDIR /app

# System deps for: Playwright's Chromium (a long, well-known list of shared
# libs — see session notes in ROADMAP.md for what broke without them),
# plus build tools some Python wheels still need to compile on slim images.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libdbus-1-3 libxcb1 libxkbcommon0 libx11-6 libxcomposite1 libxdamage1 \
    libxext6 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 \
    libasound2 libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# CPU-only PyTorch, installed BEFORE the locked requirements below and from
# PyTorch's own CPU wheel index — found necessary after the first real build
# of this image landed at 13.2GB instead of the ~4-5GB expected (session 7
# real-build follow-up). Root cause: `pip freeze` in job-agent/.venv records
# "torch==2.13.0" with no variant info, and the local .venv happened to
# resolve the +cpu build, but a fresh `pip install` of that same pin inside
# this Debian slim image resolved the default CUDA build instead (~9GB of
# bundled NVIDIA libraries this project never uses — every embedding call
# runs on CPU). Pinning the CPU wheel index explicitly removes the ambiguity
# rather than relying on pip's default resolution matching what happened to
# get installed locally.
RUN pip install --no-cache-dir torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu

# Locked dependency set (session 7 follow-up on session 3's opentelemetry
# conflict between chromadb and mistralai): requirements.txt alone is
# unpinned (">=") and a fresh resolve inside the container could land on a
# different opentelemetry-semantic-conventions version than the one proven
# to work locally (0.60b1, discovered by trial in the job-agent/.venv — see
# ROADMAP.md session 3). docker/requirements-lock.txt is a full `pip freeze`
# of that known-working environment (minus torch, installed above from the
# CPU-only index instead of this list's default PyPI index), installed here
# instead of requirements.txt to make the container reproduce it exactly
# rather than re-discover it (or fail to).
COPY docker/requirements-lock.txt /app/docker/requirements-lock.txt
RUN pip install --no-cache-dir -r /app/docker/requirements-lock.txt

# mistralai's broken top-level import (mistralai/__init__.py missing the
# Mistral re-export — see scoring/llm.py's try/except fallback, session 3)
# is a packaging defect in the PyPI wheel itself, not an environment issue —
# the same try/except fallback in scoring/llm.py handles it identically
# here, unchanged. Nothing extra needed at the Docker layer for this one.

# Playwright browser binaries (needed for orchestrator's targeted re-scrape,
# session 5) — installed as its own step, not bundled in the lock file
# above, because `playwright install` downloads browser binaries outside of
# pip's dependency resolution.
RUN python -m playwright install --with-deps chromium

# Pre-download the sentence-transformers model at build time rather than at
# first container startup (see ROADMAP.md for the size/startup tradeoff this
# session made explicitly): adds ~1.1GB to the image, but the alternative
# (download on first use) means the very first /analyze after every fresh
# container start pays a slow download instead of ~12s of cache-check HTTP
# calls (session 6 follow-up already eliminated the *lazy re-construction*
# cost within a running process — this goes one step further and removes
# the network dependency from first startup entirely).
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-mpnet-base-v2')"

COPY . /app
RUN chmod +x /app/docker/entrypoint.sh

# storage/ (SQLite) and scoring/embeddings/chroma/ (the ChromaDB index) are
# meant to be Docker volumes (see docker-compose.yml) — not baked into the
# image, so offer/analysis data survives a container restart or rebuild. A
# fresh volume means an empty scoring/embeddings/chroma/, which would make
# every offer fail with 'echec' at scoring time (search_profile() raises on
# a missing collection) — the entrypoint builds the index once if it's not
# there yet, see docker/entrypoint.sh.

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
