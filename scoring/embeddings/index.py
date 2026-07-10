"""Index the user profile into ChromaDB and expose similarity search over it.

Embeddings are generated locally via ChromaDB's default embedding function
(sentence-transformers all-MiniLM-L6-v2, downloaded on first use) — no API
key or external call required.
"""

from __future__ import annotations

from pathlib import Path

import chromadb
from chromadb.api.models.Collection import Collection

from scoring.embeddings.parser import Chunk, parse_profile_dir

PROFILE_DIR = Path(__file__).parent.parent / "profile"
CHROMA_PATH = Path(__file__).parent / "chroma"
COLLECTION_NAME = "profile"


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
    collection = client.create_collection(COLLECTION_NAME)

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
    client = get_client()
    collection = client.get_collection(COLLECTION_NAME)

    results = collection.query(query_texts=[query], n_results=n_results)

    ids = results["ids"][0]
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]

    return [_chunk_from_result(i, d, m) for i, d, m in zip(ids, documents, metadatas)]
