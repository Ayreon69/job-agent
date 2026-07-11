"""Index the user profile into ChromaDB and expose similarity search over it.

Embeddings are generated locally via sentence-transformers, using a
multilingual model (paraphrase-multilingual-mpnet-base-v2) — no API key or
external call required. ChromaDB's own default embedding function
(all-MiniLM-L6-v2) was tried first but proved too weak on French job-offer
text and on distinguishing real matches from noise; see ROADMAP.md session 2
follow-up for the comparison.
"""

from __future__ import annotations

from pathlib import Path

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from scoring.embeddings.parser import Chunk, parse_profile_dir

PROFILE_DIR = Path(__file__).parent.parent / "profile"
CHROMA_PATH = Path(__file__).parent / "chroma"
COLLECTION_NAME = "profile"
EMBEDDING_MODEL = "paraphrase-multilingual-mpnet-base-v2"


def get_embedding_function() -> SentenceTransformerEmbeddingFunction:
    return SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)


def get_client() -> chromadb.ClientAPI:
    return chromadb.PersistentClient(path=str(CHROMA_PATH))


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
