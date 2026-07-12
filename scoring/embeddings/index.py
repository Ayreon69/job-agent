"""Index the user profile into ChromaDB and expose similarity search over it.

Embeddings are generated locally via sentence-transformers, using a
multilingual model (paraphrase-multilingual-mpnet-base-v2) — no API key or
external call required. ChromaDB's own default embedding function
(all-MiniLM-L6-v2) was tried first but proved too weak on French job-offer
text and on distinguishing real matches from noise; see ROADMAP.md session 2
follow-up for the comparison.

get_embedding_function()/get_client() are memoized at module level (session 6
follow-up): constructing SentenceTransformerEmbeddingFunction() the first
time triggers ~12s of HuggingFace Hub HEAD requests to verify the locally
cached model is current, even though the actual model weights are already
cached process-wide by chromadb's own SentenceTransformerEmbeddingFunction
(it keeps a class-level `models` dict keyed by model name). Constructing a
fresh instance per search_profile() call — which happened dozens of times per
offer before this fix — meant the FIRST call in a fresh process ate that 12s
penalty, then every call after was fast (~0.03s) in the same process.
orchestrator/run.py's batch mode already only pays this once (one process for
the whole batch), but api/main.py's long-lived server process makes the "pay
once, not per-call" guarantee an explicit, testable singleton instead of an
accidental side effect of never restarting the interpreter mid-request.
"""

from __future__ import annotations

import json
import logging
import statistics
import threading
from pathlib import Path

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from scoring.embeddings.parser import Chunk, parse_profile_dir

logger = logging.getLogger(__name__)

PROFILE_DIR = Path(__file__).parent.parent / "profile"
CHROMA_PATH = Path(__file__).parent / "chroma"
COLLECTION_NAME = "profile"
EMBEDDING_MODEL = "paraphrase-multilingual-mpnet-base-v2"

# Metadata file next to the ChromaDB index itself (not a ChromaDB collection):
# this is a single small scalar, not vector-searchable data, so a plain JSON
# file next to the index is simpler than adding a dedicated collection just
# to store one number. Lives alongside CHROMA_PATH so it travels with the
# index (same volume in Docker, same directory in git) and is trivially
# invalidated by deleting/rebuilding the index like everything else there.
NOISE_BASELINE_PATH = Path(__file__).parent / "chroma" / "noise_baseline.json"

# Off-topic reference queries used to measure this profile+model's actual
# noise floor at build time (session 2 follow-up correctif). Deliberately
# varied across unrelated domains (cooking, weather, sports, news, small
# talk) rather than one single probe — a single query risks accidentally
# landing close to profile vocabulary by chance; five independent domains
# make the resulting baseline a genuine floor, not a fluke of one query's
# wording. "recette de tarte aux pommes" is the original session-2 probe
# that first exposed the weak-embedding-model problem — kept as one of the
# five for continuity with that history, not because it's special.
NOISE_PROBE_QUERIES = [
    "recette de tarte aux pommes",
    "prévisions météo pour demain à Paris",
    "résultat du match de football d'hier soir",
    "les dernières actualités internationales",
    "comment planter des tomates au jardin",
]

# Safety margin applied below the measured noise baseline (see
# get_noise_threshold): the baseline is the noise FLOOR (distance where
# unrelated queries land), not the boundary between signal and noise — using
# it directly as the threshold would flag some genuine noise as "maybe a
# match" whenever a noise probe happens to score slightly better than
# average. 0.85 (accept only distances at or below 85% of the noise floor)
# mirrors the empirical gap already observed in session 2 between real
# matches (~0.33-0.65) and noise (~0.85): 0.75 / 0.85 ≈ 0.88 is close to
# this factor, so 0.85 reproduces roughly the same fixed threshold (0.75)
# on the current profile/model while remaining a genuine fraction of
# whatever baseline is measured on a future profile/model, rather than a
# number recalibrated by hand each time either changes.
NOISE_THRESHOLD_SAFETY_MARGIN = 0.85

# Hard-coded fallback (the original session-2 constant): used only if no
# baseline file exists yet (e.g. an index built before this feature existed
# and not yet rebuilt) or if it fails to parse — scoring must never crash
# for a missing metadata file, it should degrade to the previously-proven
# fixed value instead.
FALLBACK_NOISE_THRESHOLD = 0.75

_embedding_function: SentenceTransformerEmbeddingFunction | None = None
_client: chromadb.ClientAPI | None = None
_init_lock = threading.Lock()


def get_embedding_function() -> SentenceTransformerEmbeddingFunction:
    """Return the process-wide SentenceTransformerEmbeddingFunction singleton,
    constructing it on first call. Thread-safe: double-checked locking so
    concurrent requests (e.g. two overlapping API calls) can't race into
    building two instances, but the common case (already initialized) never
    pays lock overhead.

    Safe to call from multiple threads concurrently once initialized:
    sentence-transformers' SentenceTransformer.encode() does pure inference
    (no mutation of shared model state — weights are read-only at inference
    time), which is the standard thread-safety guarantee PyTorch's eval-mode
    modules provide for concurrent forward passes on CPU.
    """
    global _embedding_function
    if _embedding_function is None:
        with _init_lock:
            if _embedding_function is None:
                _embedding_function = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
    return _embedding_function


def get_client() -> chromadb.ClientAPI:
    """Return the process-wide PersistentClient singleton (same rationale as
    get_embedding_function: avoid redundant work on every call). ChromaDB's
    PersistentClient is documented as safe for concurrent reads from multiple
    threads within one process (the unsafe case is multiple *processes*
    writing to the same path at once, which doesn't apply here — this app
    only reads via collection.query() after indexing).
    """
    global _client
    if _client is None:
        with _init_lock:
            if _client is None:
                _client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return _client


def is_initialized() -> bool:
    """Report whether the embedding function + ChromaDB client singletons are
    already constructed, WITHOUT triggering construction if they aren't
    (session 7 follow-up: used by GET /health to report real readiness
    rather than lazily loading the model just to answer a health check —
    the API's lifespan hook is expected to have already called
    get_embedding_function()/get_client() at startup; this only reads the
    module-level state).
    """
    return _embedding_function is not None and _client is not None


def _compute_noise_baseline(collection: Collection) -> dict:
    """Query the freshly built collection with NOISE_PROBE_QUERIES (off-topic,
    unrelated to the profile by construction) and return each probe's best
    (lowest) distance, plus their median.

    Median rather than mean: with only 5 probes, a single query that happens
    to land close to profile vocabulary by chance (e.g. "football" sharing
    some surface similarity with an achievement mentioning team sports) would
    pull a mean baseline down and understate the real noise floor. The
    median is robust to exactly one such outlier among five samples, which a
    mean isn't.
    """
    per_query = []
    for query in NOISE_PROBE_QUERIES:
        results = collection.query(query_texts=[query], n_results=1)
        distances = results["distances"][0]
        best_distance = min(distances) if distances else 1.0
        per_query.append({"query": query, "best_distance": round(best_distance, 4)})

    median_distance = statistics.median(p["best_distance"] for p in per_query)
    return {
        "median_distance": round(median_distance, 4),
        "probes": per_query,
        "embedding_model": EMBEDDING_MODEL,
        "profile_chunk_count": collection.count(),
    }


def build_index(profile_dir: Path = PROFILE_DIR) -> Collection:
    """Parse the profile markdown files and (re)build the ChromaDB collection.

    Also recomputes and persists the noise baseline (session-2-correctif
    follow-up) every time the index is rebuilt, so the baseline always
    reflects the CURRENT profile size and embedding model — never a number
    calibrated once and left stale as the profile grows or the model
    changes. See get_noise_threshold() for how scoring/agent.py consumes it.
    """
    chunks = parse_profile_dir(profile_dir)
    if not chunks:
        raise ValueError(f"No chunks found in {profile_dir}")

    client = get_client()
    client.delete_collection(COLLECTION_NAME) if COLLECTION_NAME in {
        c.name for c in client.list_collections()
    } else None
    collection = client.create_collection(COLLECTION_NAME, embedding_function=get_embedding_function())

    collection.add(
        ids=[c.id for c in chunks],
        documents=[c.text for c in chunks],
        metadatas=[
            {
                "source_file": c.source_file,
                "tags": ", ".join(c.tags),
            }
            for c in chunks
        ],
    )

    baseline = _compute_noise_baseline(collection)
    NOISE_BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    NOISE_BASELINE_PATH.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(
        "Baseline de bruit recalculée: médiane=%.4f sur %d chunks (%s) -> %s",
        baseline["median_distance"], baseline["profile_chunk_count"], EMBEDDING_MODEL, NOISE_BASELINE_PATH,
    )

    return collection


def get_noise_threshold() -> float:
    """Return the noise threshold scoring/agent.py should use: the last
    computed baseline (median distance of off-topic probes) times
    NOISE_THRESHOLD_SAFETY_MARGIN, or FALLBACK_NOISE_THRESHOLD if no
    baseline is available yet (index built before this feature existed, or
    the file is missing/corrupt) — scoring must never crash for a missing
    metadata file.
    """
    try:
        baseline = json.loads(NOISE_BASELINE_PATH.read_text(encoding="utf-8"))
        median_distance = baseline["median_distance"]
        if not isinstance(median_distance, (int, float)):
            raise ValueError(f"median_distance is not numeric: {median_distance!r}")
        return round(median_distance * NOISE_THRESHOLD_SAFETY_MARGIN, 4)
    except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.warning(
            "Baseline de bruit indisponible (%s: %s) — repli sur le seuil fixe %.2f",
            type(exc).__name__, exc, FALLBACK_NOISE_THRESHOLD,
        )
        return FALLBACK_NOISE_THRESHOLD


def _chunk_from_result(id_: str, document: str, metadata: dict) -> Chunk:
    tags = [t.strip() for t in metadata.get("tags", "").split(",") if t.strip()]
    return Chunk(id=id_, source_file=metadata.get("source_file", ""), text=document, tags=tags)


def search_profile(query: str, n_results: int = 3) -> list[Chunk]:
    """Return the top-N profile chunks most relevant to a query, by embedding similarity."""
    return [chunk for chunk, _distance in search_profile_with_scores(query, n_results=n_results)]


def search_profile_with_scores(query: str, n_results: int = 3) -> list[tuple[Chunk, float]]:
    """Like search_profile, but also returns each chunk's cosine distance.

    Lower distance = more similar. Empirically (session 2 retest), real matches
    fall around ~0.33-0.65 and unrelated noise around ~0.85 with the current
    model — see ROADMAP.md for the full comparison. Used by the scoring agent to
    detect when nothing relevant was retrieved (flag_uncertain) instead of
    guessing from a weak match.
    """
    client = get_client()
    collection = client.get_collection(COLLECTION_NAME, embedding_function=get_embedding_function())

    results = collection.query(query_texts=[query], n_results=n_results)

    ids = results["ids"][0]
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    return [
        (_chunk_from_result(i, d, m), dist)
        for i, d, m, dist in zip(ids, documents, metadatas, distances)
    ]
