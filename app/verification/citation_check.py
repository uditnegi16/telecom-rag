"""
Deterministic citation validation.

WHY (traceability: FR-06, DEF-01; decision D-010)
-------------------------------------------------
This is the cheapest hallucination control in the system: zero tokens, zero
latency, and it catches the most embarrassing failure mode for a spec
assistant - a confidently fabricated clause number.

It also fixes DEF-01, a real defect in the forked codebase:

    if not source_chunk and chunks:
        source_chunk = chunks[0]          # <-- silent substitution

When the model cited a chunk_id that did not resolve, the old code returned
chunks[0]'s TEXT while keeping the FABRICATED id. Two consequences:
  * the user saw a real passage under a citation that was never used;
  * the grounding check then compared the answer against a passage the model
    had not cited, so the evaluation graded the wrong document precisely in
    the cases that mattered most.

An unresolvable citation is now a hard failure. Never substitute.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class CitationResult:
    valid: bool
    reason: str
    fabricated: List[str]          # cited ids that do not exist at all
    out_of_context: List[str]      # ids that exist but were not retrieved


def validate_citations(
    cited_ids: List[str],
    retrieved_ids: List[str],
    known_ids: set | None = None,
) -> CitationResult:
    """Every cited id must be in the retrieved set.

    `known_ids` (the full corpus id set) is optional and only used to
    distinguish a fabricated id from a real-but-not-retrieved one. That
    distinction is worth reporting separately: the first is invention, the
    second means the model leaked prior context, and they need different fixes.
    """
    if not cited_ids:
        return CitationResult(False, "no citation supplied", [], [])

    retrieved = set(retrieved_ids)
    fabricated, out_of_context = [], []

    for cid in cited_ids:
        if cid in retrieved:
            continue
        if known_ids is not None and cid in known_ids:
            out_of_context.append(cid)
        else:
            fabricated.append(cid)

    if fabricated:
        return CitationResult(
            False, f"fabricated citation(s): {fabricated}", fabricated, out_of_context
        )
    if out_of_context:
        return CitationResult(
            False,
            f"cited chunk(s) not in retrieved context: {out_of_context}",
            fabricated,
            out_of_context,
        )
    return CitationResult(True, "all citations resolve to retrieved context", [], [])


def cited_chunk_map(chunks: List[dict]) -> Dict[str, dict]:
    return {c["chunk_id"]: c for c in chunks}
