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

import re
from dataclasses import dataclass
from typing import Dict, List


def normalise(cid: str) -> str:
    """Strip decoration the model copies from the prompt's source labels.

    ERROR_LOG E-016: sources were labelled "[TS28552_5.5.7.1.3] TS 28.552 ...",
    so the model returned the id WITH the brackets. Exact string matching then
    rejected a perfectly correct citation as fabricated, and the answer was
    thrown away. This was the dominant cause of abstentions in RUN-001 - not
    the relevance gate, not the prompt, and not retrieval.

    A validator that is stricter than its own prompt's formatting will reject
    correct output. Normalise the shape, keep the identity check strict.
    """
    if not cid:
        return ""
    out = cid.strip()
    out = re.sub(r"^[\[\(<{'\"]+|[\]\)>}'\"]+$", "", out).strip()
    out = re.sub(r"^(source|chunk|id)\s*[:=]\s*", "", out, flags=re.I).strip()
    return out


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

    retrieved = {normalise(r) for r in retrieved_ids}
    known = {normalise(k) for k in known_ids} if known_ids is not None else None
    fabricated, out_of_context = [], []

    for raw in cited_ids:
        cid = normalise(raw)
        if cid in retrieved:
            continue
        if known is not None and cid in known:
            out_of_context.append(raw)
        else:
            fabricated.append(raw)

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
    """Keyed by BOTH raw and normalised id so downstream lookups (entailment
    verification) resolve a decorated citation too."""
    out: Dict[str, dict] = {}
    for c in chunks:
        out[c["chunk_id"]] = c
        out[normalise(c["chunk_id"])] = c
    return out
