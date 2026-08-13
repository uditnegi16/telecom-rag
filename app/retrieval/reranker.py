"""
Cross-encoder reranking.

CHANGE FROM THE FORK BASE (DEF-04) - IMPORTANT
----------------------------------------------
The original filtered candidates inside this module:

    filtered = [c for c in ranked if c["reranker_score"] >= RELEVANCE_THRESHOLD]

That is why the fork's confidence gate could never be tuned: by the time the
gate ran, low-scoring candidates were already gone, so the score distribution
it saw was truncated and the tau sweep would have been meaningless.

This module now SCORES AND SORTS ONLY. Filtering is one explicit decision made
in one place - the abstention gate. If you copy this file back into any other
project, keep that separation.
"""

from __future__ import annotations

from typing import List

import numpy as np
from sentence_transformers import CrossEncoder

from app.config import CFG

_reranker: CrossEncoder | None = None

# Long 3GPP chunks are truncated for SCORING ONLY - the full body is still
# what reaches the generator. Keeps CPU latency workable (E-000d).
MAX_RERANK_CHARS = 2000


def get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder(CFG.reranker_model, device="cpu")
    return _reranker


def rerank(query: str, chunks: List[dict]) -> List[dict]:
    """Score and sort. Returns ALL candidates - never filters."""
    if not chunks:
        return []
    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")

    model = get_reranker()
    pairs = [[query, (c.get("text") or "")[:MAX_RERANK_CHARS]] for c in chunks]
    logits = model.predict(pairs, batch_size=8, show_progress_bar=False)

    # ms-marco cross-encoders emit raw logits; sigmoid maps to 0-1 so tau has
    # a stable, interpretable scale across runs.
    scores = 1.0 / (1.0 + np.exp(-np.asarray(logits, dtype=float)))

    for c, s in zip(chunks, scores):
        c["reranker_score"] = round(float(s), 4)

    return sorted(chunks, key=lambda c: c["reranker_score"], reverse=True)
