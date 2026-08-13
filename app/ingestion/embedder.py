"""
Local CPU embeddings.

WHY LOCAL (decision D-004, NFR-01, NFR-04)
------------------------------------------
Groq provides no embedding endpoint, and paid embedding APIs would add a
network call plus cost to every re-index during iteration. bge-small-en-v1.5
is 33M parameters, runs comfortably on CPU, and is markedly stronger on
technical English than the fork base's all-MiniLM-L6-v2.

Retargeted from the fork base (all-MiniLM-L6-v2, 384-dim). Dimension happens
to match, which is a trap: swapping models without re-indexing produces
vectors in a DIFFERENT SPACE with no error raised. The collection name is
versioned and the model is recorded in collection metadata to prevent this
(E-000g).
"""

from __future__ import annotations

from typing import List

from sentence_transformers import SentenceTransformer

from app.config import CFG

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(CFG.embedding_model, device="cpu")
    return _model


def embed_texts(texts: List[str], batch_size: int = 32) -> List[List[float]]:
    model = get_model()
    vecs = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=len(texts) > 200,
        normalize_embeddings=True,      # cosine == dot product
        convert_to_numpy=True,
    )
    return vecs.tolist()


def embed_query(query: str) -> List[float]:
    """BGE models expect an instruction prefix on the QUERY side only.
    Omitting it costs a few points of retrieval quality - a silent
    degradation that is easy to miss."""
    prefix = "Represent this sentence for searching relevant passages: "
    return embed_texts([prefix + query])[0]
