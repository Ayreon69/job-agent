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

import threading
from pathlib import Path

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from scoring.embeddings.parser import Chunk, parse_profile_dir

PROFILE_DIR = Path(__file__).parent.parent / "profile"
CHROMA_PATH = Path(__file__).parent / "chroma"
COLLECTION_NAME = "profile"
EMBEDDING_MODEL = "paraphrase-multilingual-mpnet-base-v2"

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


def build_index(profile_dir: Path = PROFILE_DIR) -> Collection:
    """Parse the profile markdown files and (re)build the ChromaDB collection."""
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
    return collection


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
