"""
Reciprocal Rank Fusion.

WHY (traceability: FR-04; decision D-006)
-----------------------------------------
Dense cosine similarity and BM25 produce scores on incomparable scales.
Weighted score blending would require normalising both and tuning a weight
that cannot be justified from 60 eval questions. RRF ignores magnitudes and
uses only rank position, so it needs no normalisation and no tuning - one
fewer unjustifiable magic number in the system.

    score(d) = sum over lists of  1 / (k + rank(d))
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple


def reciprocal_rank_fusion(
    ranked_lists: Sequence[List[Tuple[str, float]]],
    k: int = 60,
    top_n: int | None = None,
) -> List[Tuple[str, float]]:
    """Fuse ranked (id, score) lists. Input scores are ignored by design -
    only rank position contributes."""
    fused: Dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, (doc_id, _score) in enumerate(ranked, start=1):
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank)

    out = sorted(fused.items(), key=lambda x: x[1], reverse=True)
    return out[:top_n] if top_n else out
