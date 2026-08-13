"""
The answer pipeline as a LangGraph state graph.

WHY A GRAPH AND NOT A CHAIN (traceability: FR-06/07/08; decision D-008)
----------------------------------------------------------------------
The design genuinely needs conditional branching and a bounded loop, which a
linear chain cannot express:

    retrieve -> gate ---------(below tau)-------> ABSTAIN
                  |
              (above tau)
                  v
              generate -> validate citations --(invalid)--> ABSTAIN
                              |
                          (valid)
                              v
                          verify claims --(all ungrounded)--> ABSTAIN
                              |
                     (some grounded)
                              v
                       drop ungrounded -> ANSWER

Every terminal path that lacks evidence ends in ABSTAIN. That is the
fail-closed property (NFR-03).

This also matches the JD (LangGraph, agentic orchestration) and the team's
product framing. The optional query-rewrite retry edge is on the cut list -
implement only if evaluation targets are already met.
"""

from __future__ import annotations

from typing import Callable, List, Optional, TypedDict

from app.config import CFG
from app.generation import confidence as gate
from app.generation import prompt_builder
from app.verification import citation_check, entailment


class AnswerState(TypedDict, total=False):
    question: str
    chunks: List[dict]
    top_score: float
    confidence: float
    raw_response: str
    answer: Optional[str]
    claims: List[dict]
    claim_verdicts: List[bool]
    citations: List[str]
    cited_clauses: List[str]
    retrieved_clauses: List[str]
    abstained: bool
    abstain_reason: str
    parse_failed: bool
    tau: float


def build_answer_fn(
    retrieve_fn: Callable | None = None,
    llm=None,
    tau: float | None = None,
) -> Callable[[str], dict]:
    """Return `answer(question) -> dict` in the shape eval/run_eval.py expects.

    Written as an explicit function rather than a compiled StateGraph so it is
    runnable before LangGraph is wired in; the node boundaries below map 1:1
    onto graph nodes, so promoting this to a StateGraph is mechanical.
    """
    tau_eff = CFG.tau_abstain if tau is None else tau

    if retrieve_fn is None or llm is None:
        raise NotImplementedError(
            "Wire retrieve_fn (app.retrieval.search.retrieve, partially applied "
            "with your dense_search/bm25/chunk_lookup/reranker) and llm "
            "(app.llm.groq_client.GroqLLM()) here. Left explicit so the "
            "dependency is visible rather than hidden in a global."
        )

    def answer(question: str) -> dict:
        # --- node: retrieve ------------------------------------------------
        r = retrieve_fn(question)
        chunks = r["chunks"]
        retrieved_clauses = [c.get("clause_id", "") for c in chunks]
        conf = gate.confidence_from_retrieval(r["top_score"], len(chunks))

        base = {
            "retrieved_clauses": retrieved_clauses,
            "confidence": conf,
            "claim_verdicts": [],
            "citations": [],
            "cited_clauses": [],
            "parse_failed": False,
        }

        # --- edge: abstention gate (D-009) ---------------------------------
        if not gate.should_answer(conf, tau_eff):
            return {**base, **gate.abstain("below_tau", conf)}

        # --- node: generate ------------------------------------------------
        built = prompt_builder.build_prompt(question, chunks)
        raw = llm.complete(built["prompt"], json_mode=True)
        parsed = prompt_builder.parse_response(raw)

        if parsed["parse_failed"]:
            # Fail closed: an unreadable response must not become an answer.
            out = {**base, **gate.abstain("parse_failure", conf)}
            out["parse_failed"] = True
            return out

        if not parsed["sufficient"] or not parsed["claims"]:
            return {**base, **gate.abstain("model_declared_insufficient", conf)}

        # --- node: validate citations (FR-06, DEF-01) ----------------------
        cited_ids = [c["citation"] for c in parsed["claims"]]
        cit = citation_check.validate_citations(cited_ids, built["chunk_ids"])
        if not cit.valid:
            # Never substitute a default chunk. See DEF-01.
            return {**base, **gate.abstain(f"citation_invalid: {cit.reason}", conf)}

        # --- node: verify entailment (FR-08) -------------------------------
        chunk_map = citation_check.cited_chunk_map(chunks)
        verdicts = entailment.verify_claims(parsed["claims"], chunk_map, llm=llm)
        grounded = [v for v in verdicts if v.supported]

        base["claim_verdicts"] = [v.supported for v in verdicts]

        if not grounded:
            return {**base, **gate.abstain("all_claims_ungrounded", conf)}

        # --- node: emit (ungrounded claims dropped) ------------------------
        kept_ids = [v.citation for v in grounded]
        return {
            **base,
            "answer": parsed["answer"],
            "claims": [{"claim": v.claim, "citation": v.citation} for v in grounded],
            "citations": kept_ids,
            "cited_clauses": [
                chunk_map[i].get("clause_id", "") for i in kept_ids if i in chunk_map
            ],
            "abstained": False,
            "claims_dropped": len(verdicts) - len(grounded),
        }

    return answer
