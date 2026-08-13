"""
The abstention gate.

WHY (traceability: FR-07, NFR-03, DEF-04, DEF-06; decision D-009)
-----------------------------------------------------------------
This is the primary hallucination control in the system. It does not try to
DETECT invention after the fact - it removes the opportunity by never calling
the generator when the evidence is too weak.

Two changes from the forked version:
  * Single threshold. Previously two untuned thresholds existed in two modules
    (DEF-04); tau now lives in config.py and is swept empirically in RUN-006.
  * The count_factor term is gone (DEF-06). The old formula was
    0.7*top_score + 0.3*min(count/3,1), which rewarded retrieving MORE chunks.
    Retrieving more chunks is not evidence that any of them is correct; on a
    broad corpus it is weakly anti-correlated with precision. Removed until
    there is measured evidence it helps.
"""

from __future__ import annotations

from app.config import CFG

REFUSAL_MESSAGE = (
    "I could not find this in the indexed 3GPP specifications. "
    "Rather than guess, I am declining to answer. "
    "You may want to check a specification outside the indexed corpus."
)


def confidence_from_retrieval(top_score: float, chunk_count: int) -> float:
    """Confidence is the top reranker score, sigmoid-normalised upstream.

    Deliberately simple and monotone in one observable quantity, so the tau
    sweep in RUN-006 has a defensible interpretation.
    """
    if chunk_count == 0:
        return 0.0
    return round(float(top_score), 4)


def should_answer(confidence: float, tau: float | None = None) -> bool:
    return confidence >= (CFG.tau_abstain if tau is None else tau)


def abstain(reason: str, confidence: float = 0.0) -> dict:
    return {
        "answer": REFUSAL_MESSAGE,
        "claims": [],
        "citations": [],
        "confidence": confidence,
        "abstained": True,
        "abstain_reason": reason,
    }
