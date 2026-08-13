"""
Hybrid retrieval: dense + BM25 -> RRF -> cross-encoder rerank.

WHY (traceability: FR-04, FR-05, FR-07; decisions D-006, D-007, D-009)
----------------------------------------------------------------------
Two changes from the forked version:

1. Retrieval is hybrid, not dense-only.
2. The reranker NO LONGER filters candidates by threshold. Previously
   RELEVANCE_THRESHOLD=0.5 dropped candidates inside the reranker, so the
   abstention gate downstream never saw the real score distribution and the
   tau sweep would have been meaningless (DEF-04). Filtering is now a single
   explicit decision made in one place: the gate.
"""

from __future__ import annotations

from typing import List, Optional

from app.config import CFG


def retrieve(
    query: str,
    dense_search,          # callable(query, top_k) -> [(chunk_id, score)]
    bm25_index,            # BM25Index
    chunk_lookup,          # callable(chunk_id) -> dict
    reranker,              # callable(query, chunks) -> chunks with scores
    top_n: Optional[int] = None,
) -> dict:
    """Returns candidates ranked by reranker score, UNFILTERED.

    The caller applies tau. This separation is what makes the operating point
    a deliberate product decision instead of an accident of module defaults.
    """
    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")

    top_n = top_n or CFG.rerank_top_n

    dense_hits = dense_search(query, CFG.dense_top_k)
    bm25_hits = bm25_index.search(query, CFG.bm25_top_k)

    from app.retrieval.fusion import reciprocal_rank_fusion

    fused = reciprocal_rank_fusion([dense_hits, bm25_hits], k=CFG.rrf_k)
    candidate_ids = [cid for cid, _ in fused[: CFG.dense_top_k + CFG.bm25_top_k]]

    candidates = [c for c in (chunk_lookup(cid) for cid in candidate_ids) if c]

    if not candidates:
        return {
            "query": query,
            "chunks": [],
            "top_score": 0.0,
            "dense_hits": len(dense_hits),
            "bm25_hits": len(bm25_hits),
            "fused_candidates": 0,
        }

    reranked = reranker(query, candidates)          # sorted, scored, unfiltered
    selected = reranked[:top_n]

    return {
        "query": query,
        "chunks": selected,
        "top_score": max((c["reranker_score"] for c in selected), default=0.0),
        "dense_hits": len(dense_hits),
        "bm25_hits": len(bm25_hits),
        "fused_candidates": len(candidates),
        "score_distribution": [c["reranker_score"] for c in reranked[:10]],
    }
