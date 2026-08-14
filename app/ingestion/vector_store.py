"""
ChromaDB dense store.

CHANGES FROM THE FORK BASE
--------------------------
1. Collection metadata now records embedding_model and dim, and a mismatch
   RAISES at query time (E-000g). Previously a model swap silently produced
   garbage retrieval because the dimensions happened to match.
2. Chunk metadata carries the full 3GPP provenance (spec_id, version,
   clause_id, heading_path, pages) required by FR-03.
"""

from __future__ import annotations

from typing import List, Optional

import chromadb
from chromadb.config import Settings

from app.config import CFG

_client = None
_collection = None


def get_client():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=CFG.chroma_path,
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def get_collection(create: bool = True):
    global _collection
    if _collection is not None:
        return _collection

    client = get_client()
    meta = {
        "hnsw:space": "cosine",
        "embedding_model": CFG.embedding_model,
        "embedding_dim": CFG.embedding_dim,
    }
    if create:
        _collection = client.get_or_create_collection(CFG.collection, metadata=meta)
    else:
        _collection = client.get_collection(CFG.collection)

    stored = _collection.metadata or {}
    if stored.get("embedding_model") not in (None, CFG.embedding_model):
        raise RuntimeError(
            f"Index/model mismatch (E-000g): collection '{CFG.collection}' was "
            f"built with {stored.get('embedding_model')}, config says "
            f"{CFG.embedding_model}. Vectors are in a different space. "
            f"Re-ingest, or bump CFG.collection."
        )
    return _collection


def reset_collection():
    global _collection
    try:
        get_client().delete_collection(CFG.collection)
    except Exception:
        pass
    _collection = None
    return get_collection()


def store_chunks(chunks: List[dict], embeddings: List[List[float]],
                 session_id: str | None = None) -> int:
    """Index chunks. `session_id` scopes user uploads (FR-14, D-026).

    Uploaded documents must NOT leak into other visitors' retrieval. Every
    chunk carries an `owner` field: "base" for the shipped corpus, or the
    session id for an upload. Retrieval filters on it. Without this, one
    person's document would answer everyone's questions - unacceptable for
    anything an operator would run internally, where uploaded material is
    routinely confidential.
    """
    if len(chunks) != len(embeddings):
        raise ValueError("chunks and embeddings length mismatch")

    col = get_collection()
    batch = 500
    for i in range(0, len(chunks), batch):
        part = chunks[i : i + batch]
        col.add(
            ids=[c["chunk_id"] for c in part],
            embeddings=embeddings[i : i + batch],
            documents=[c["text"] for c in part],
            metadatas=[
                {
                    "owner": session_id or "base",
                    "spec_id": c["spec_id"],
                    "spec_version": c["spec_version"],
                    "clause_id": c["clause_id"],
                    "clause_title": c.get("clause_title", ""),
                    "heading_path": c.get("heading_path", ""),
                    "page_start": c.get("page_start", 0),
                    "page_end": c.get("page_end", 0),
                    "content_type": c.get("content_type", "prose"),
                    "part_index": c.get("part_index", 0),
                    "part_total": c.get("part_total", 1),
                }
                for c in part
            ],
        )
    return len(chunks)


def dense_search(query: str, top_k: int,
                 session_id: str | None = None) -> List[tuple]:
    """Returns [(chunk_id, similarity)].

    Scope: the shipped corpus plus this session's uploads only. Other
    sessions' documents are invisible (D-026).
    """
    from app.ingestion.embedder import embed_query

    col = get_collection(create=False)
    owners = ["base"] + ([session_id] if session_id else [])
    res = col.query(
        query_embeddings=[embed_query(query)],
        n_results=top_k,
        where={"owner": {"$in": owners}},
    )
    ids = res["ids"][0]
    dists = res["distances"][0]
    return [(cid, 1.0 - d) for cid, d in zip(ids, dists)]


def delete_session_chunks(session_id: str) -> int:
    """Remove a session's uploads. Called on session expiry so a long-running
    demo container does not accumulate every visitor's documents."""
    col = get_collection(create=False)
    got = col.get(where={"owner": session_id})
    ids = got.get("ids", [])
    if ids:
        col.delete(ids=ids)
    return len(ids)


def session_chunks(session_id: str) -> List[dict]:
    col = get_collection(create=False)
    got = col.get(where={"owner": session_id},
                  include=["documents", "metadatas"])
    out = []
    for cid, doc, md in zip(got.get("ids", []), got.get("documents", []),
                            got.get("metadatas", [])):
        body = doc.split("\n\n", 1)[-1] if "\n\n" in doc else doc
        out.append({"chunk_id": cid, "text": doc, "body": body, **md})
    return out


def get_chunk(chunk_id: str) -> Optional[dict]:
    col = get_collection(create=False)
    res = col.get(ids=[chunk_id], include=["documents", "metadatas"])
    if not res["ids"]:
        return None
    md = res["metadatas"][0]
    text = res["documents"][0]
    # `body` strips the breadcrumb line the chunker prepended - entailment
    # must judge against source text, not against our own metadata header.
    body = text.split("\n\n", 1)[-1] if "\n\n" in text else text
    return {"chunk_id": chunk_id, "text": text, "body": body, **md}


def count() -> int:
    try:
        return get_collection(create=False).count()
    except Exception:
        return 0
