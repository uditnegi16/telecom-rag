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
    verify: bool = True,
    suppress: bool = True,
) -> Callable[[str], dict]:
    """Return `answer(question) -> dict` in the shape eval/run_eval.py expects.

    Written as an explicit function rather than a compiled StateGraph so it is
    runnable before LangGraph is wired in; the node boundaries below map 1:1
    onto graph nodes, so promoting this to a StateGraph is mechanical.
    """
    tau_eff = CFG.tau_abstain if tau is None else tau

    if retrieve_fn is None or llm is None:
        # Composition happens in app.pipeline - see get_answer_fn().
        from app.pipeline import build_retrieve_fn, _get_llm

        retrieve_fn = retrieve_fn or build_retrieve_fn()
        llm = llm or _get_llm()

    def answer(question: str, history: list | None = None) -> dict:
        # --- node: contextualise (FR-13, D-024) ----------------------------
        # A follow-up like "what about for the SMF?" is unretrievable as
        # written. History resolves the reference; it never supplies facts.
        from app.chat.contextualizer import contextualize

        search_query, rewritten = contextualize(question, history or [], llm=llm)

        # --- node: retrieve ------------------------------------------------
        r = retrieve_fn(search_query)
        chunks = r["chunks"]
        retrieved_clauses = [c.get("clause_id", "") for c in chunks]
        conf = gate.confidence_from_retrieval(r["top_score"], len(chunks))

        base = {
            "question": question,
            # Surfaced because a WRONG rewrite produces a confidently wrong
            # retrieval, and the user must be able to see what was searched.
            "rewritten_query": search_query if rewritten else None,
            # FR-10: the UI must show the evidence, not just the answer.
            # Exposed even on abstention - seeing WHAT was retrieved is how a
            # user judges whether a refusal was correct.
            "source_chunks": chunks,
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
        # Generation sees the SEARCH query and the retrieved chunks - never
        # the conversation history (D-025). Every turn is grounded from
        # scratch, so a turn-5 claim cannot rest on an unverified turn-2 one.
        built = prompt_builder.build_prompt(search_query, chunks)
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
        # The verifier has TWO roles and they must be controlled separately
        # (ERROR_LOG E-012):
        #   verify=True   -> run the entailment check, record verdicts. This is
        #                    the MEASUREMENT INSTRUMENT and must stay on for
        #                    every ablation run, or hallucination rate is
        #                    unmeasurable and the baseline scores a fake 0%.
        #   suppress=True -> act on the verdicts (drop ungrounded claims,
        #                    abstain if none survive). This is the SYSTEM
        #                    FEATURE being ablated.
        verdicts = entailment.verify_claims(
            parsed["claims"], chunk_map, llm=llm if verify else None
        )
        base["claim_verdicts"] = [v.supported for v in verdicts]

        grounded = [v for v in verdicts if v.supported]
        if suppress:
            if not grounded:
                return {**base, **gate.abstain("all_claims_ungrounded", conf)}
            emitted = grounded
        else:
            emitted = verdicts        # measured but not acted upon

        # --- node: emit (ungrounded claims dropped) ------------------------
        kept_ids = [v.citation for v in emitted]
        return {
            **base,
            "answer": parsed["answer"],
            "claims": [{"claim": v.claim, "citation": v.citation} for v in emitted],
            "citations": kept_ids,
            "cited_clauses": [
                chunk_map[i].get("clause_id", "") for i in kept_ids if i in chunk_map
            ],
            "abstained": False,
            "claims_dropped": (len(verdicts) - len(grounded)) if suppress else 0,
        }

    return answer
