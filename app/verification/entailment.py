"""
Claim-level entailment verification.

WHY (traceability: FR-08, NFR-02, DEF-02; decision D-010)
---------------------------------------------------------
This replaces the forked codebase's hallucination check, which was bag-of-words
overlap with a 0.15 threshold. That heuristic is not merely weak on
specification text - it is actively dangerous there, because 3GPP's entire
content is normative language:

    "the AMF shall reject the request"
    "the AMF shall not reject the request"

These share ~95% of their tokens. The overlap check scores the inverted claim
as grounded. On a corpus whose meaning lives in shall/should/may/shall-not,
lexical overlap cannot distinguish a correct answer from its negation (DEF-02).

Design: two stages, cheap-first, because tokens are the binding constraint
(NFR-01).
  Stage 1  lexical overlap as a FREE PRE-FILTER only. Low overlap is strong
           evidence of ungroundedness and costs nothing to detect. High
           overlap proves nothing and is passed on to stage 2.
  Stage 2  LLM entailment on the small verifier model (D-019), one call per
           claim, judged ONLY against the chunk that claim actually cited.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import List, Optional

from app.config import CFG

VERIFY_PROMPT = """You are a strict verification system for telecom specification text.

Decide whether the CLAIM is supported by the SOURCE passage.

Rules:
- Answer SUPPORTED only if the SOURCE states or directly implies the CLAIM.
- Answer NOT_SUPPORTED if the CLAIM is plausible but absent from the SOURCE.
- Pay exact attention to normative words: shall, shall not, should, may, must.
  A claim that reverses or weakens a normative requirement is NOT_SUPPORTED.
- Pay exact attention to numbers, identifiers, and clause references.
- Do not use outside knowledge. Judge only against the SOURCE.

SOURCE:
{source}

CLAIM:
{claim}

Respond with JSON only:
{{"verdict": "SUPPORTED" or "NOT_SUPPORTED", "reason": "<one short sentence>"}}"""


@dataclass
class ClaimVerdict:
    claim: str
    citation: str
    supported: bool
    reason: str
    stage: str              # "prefilter" | "llm"


def lexical_overlap(claim: str, source: str) -> float:
    """Content-word overlap. A pre-filter, never the verdict on its own."""
    def words(t: str) -> set:
        return {w for w in re.findall(r"[a-z0-9]+", t.lower()) if len(w) > 2}

    c, s = words(claim), words(source)
    if not c:
        return 0.0
    return len(c & s) / len(c)


def verify_claims(
    claims: List[dict],           # [{"claim": str, "citation": chunk_id}]
    chunk_map: dict,              # chunk_id -> chunk dict
    llm=None,                     # GroqLLM, or None to run pre-filter only
) -> List[ClaimVerdict]:
    verdicts: List[ClaimVerdict] = []

    for item in claims:
        claim = (item.get("claim") or "").strip()
        citation = (item.get("citation") or "").strip()

        if not claim:
            continue

        chunk = chunk_map.get(citation)
        if chunk is None:
            verdicts.append(
                ClaimVerdict(claim, citation, False,
                             "citation does not resolve", "prefilter")
            )
            continue

        source = chunk.get("body") or chunk.get("text", "")

        # Stage 1 - free rejection of obviously ungrounded claims.
        if lexical_overlap(claim, source) < CFG.overlap_prefilter:
            verdicts.append(
                ClaimVerdict(claim, citation, False,
                             "negligible lexical overlap with cited source",
                             "prefilter")
            )
            continue

        # Stage 2 - the actual check.
        if llm is None or not CFG.require_entailment:
            verdicts.append(
                ClaimVerdict(claim, citation, True,
                             "prefilter only (entailment disabled)", "prefilter")
            )
            continue

        raw = llm.complete(
            VERIFY_PROMPT.format(source=source[:4000], claim=claim),
            model=CFG.verify_model,
            max_tokens=150,
            json_mode=True,
        )
        parsed = _parse_verdict(raw)
        verdicts.append(
            ClaimVerdict(
                claim, citation,
                parsed["verdict"] == "SUPPORTED",
                parsed.get("reason", ""),
                "llm",
            )
        )

    return verdicts


def _parse_verdict(raw: str) -> dict:
    """Tolerant parse. A parse failure is treated as NOT_SUPPORTED - failing
    closed is the whole point of the system (NFR-03), so an unreadable
    verifier response must not become an accepted claim."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    if "NOT_SUPPORTED" in raw.upper():
        return {"verdict": "NOT_SUPPORTED", "reason": "parsed from text"}
    return {"verdict": "NOT_SUPPORTED", "reason": "verifier response unparseable"}


def summarise(verdicts: List[ClaimVerdict]) -> dict:
    total = len(verdicts)
    ungrounded = [v for v in verdicts if not v.supported]
    return {
        "claims_total": total,
        "claims_ungrounded": len(ungrounded),
        "ungrounded_rate": round(len(ungrounded) / total, 4) if total else 0.0,
        "dropped_by_prefilter": sum(
            1 for v in ungrounded if v.stage == "prefilter"
        ),
        "dropped_by_llm": sum(1 for v in ungrounded if v.stage == "llm"),
    }
