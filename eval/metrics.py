"""
Metric implementations.

WHY (traceability: NFR-02, NFR-03, NFR-08; EVALUATION_PLAN sections 2-3)
------------------------------------------------------------------------
Definitions are written here, in code, BEFORE any measurement exists. This is
deliberate: a metric defined after seeing results can always be shaped to
flatter them.
"""

from __future__ import annotations

from typing import Dict, List, Optional


# --- retrieval --------------------------------------------------------------

def recall_at_k(retrieved_clauses: List[str], gold_clause: str, k: int) -> int:
    return int(gold_clause in retrieved_clauses[:k])


def reciprocal_rank(retrieved_clauses: List[str], gold_clause: str) -> float:
    for i, c in enumerate(retrieved_clauses, start=1):
        if c == gold_clause:
            return 1.0 / i
    return 0.0


# --- generation -------------------------------------------------------------

def ungrounded_claim_rate(claim_verdicts: List[bool]) -> Optional[float]:
    """Headline metric. None when no claims were emitted (e.g. abstention) -
    NOT zero. Returning 0.0 for an abstention would let a system that refuses
    everything score a perfect hallucination rate, which is exactly the
    degenerate result the false-refusal metric exists to expose."""
    if not claim_verdicts:
        return None
    ungrounded = sum(1 for ok in claim_verdicts if not ok)
    return round(ungrounded / len(claim_verdicts), 4)


def citation_accuracy(
    cited_clauses: List[str], gold_clause: str
) -> Optional[float]:
    if not cited_clauses:
        return None
    hits = sum(1 for c in cited_clauses if c == gold_clause)
    return round(hits / len(cited_clauses), 4)


# --- safety / abstention ----------------------------------------------------

def abstention_correctness(results: List[dict]) -> float:
    """Fraction of adversarial questions correctly refused."""
    if not results:
        return 0.0
    correct = sum(1 for r in results if r.get("abstained"))
    return round(correct / len(results), 4)


def false_refusal_rate(results: List[dict]) -> float:
    """Fraction of ANSWERABLE questions wrongly refused. The cost of the gate.
    Reported alongside the headline number, never omitted - it is what stops
    'refuse everything' from looking like a good result."""
    if not results:
        return 0.0
    refused = sum(1 for r in results if r.get("abstained"))
    return round(refused / len(results), 4)


def unsupported_answer_rate(results: List[dict]) -> float:
    """Fraction of adversarial questions given a confident answer.
    The number that most directly contradicts a zero-hallucination claim, so
    it is reported prominently rather than buried."""
    if not results:
        return 0.0
    answered = sum(1 for r in results if not r.get("abstained"))
    return round(answered / len(results), 4)


# --- aggregation ------------------------------------------------------------

def aggregate(answerable: List[dict], adversarial: List[dict]) -> Dict:
    rates = [
        r["ungrounded_rate"] for r in answerable
        if r.get("ungrounded_rate") is not None
    ]
    recalls5 = [r.get("recall_at_5", 0) for r in answerable]
    recalls10 = [r.get("recall_at_10", 0) for r in answerable]
    rrs = [r.get("reciprocal_rank", 0.0) for r in answerable]
    cites = [
        r["citation_accuracy"] for r in answerable
        if r.get("citation_accuracy") is not None
    ]
    lats = [r.get("latency_s", 0.0) for r in answerable + adversarial]

    def mean(xs):
        return round(sum(xs) / len(xs), 4) if xs else 0.0

    def p95(xs):
        if not xs:
            return 0.0
        s = sorted(xs)
        return round(s[min(len(s) - 1, int(0.95 * len(s)))], 3)

    return {
        "n_answerable": len(answerable),
        "n_adversarial": len(adversarial),
        "recall_at_5": mean(recalls5),
        "recall_at_10": mean(recalls10),
        "mrr": mean(rrs),
        "ungrounded_claim_rate": mean(rates),
        "citation_accuracy": mean(cites),
        "answers_produced": sum(1 for r in answerable if not r.get("abstained")),
        "false_refusal_rate": false_refusal_rate(answerable),
        "abstention_correctness": abstention_correctness(adversarial),
        "unsupported_answer_rate": unsupported_answer_rate(adversarial),
        "parse_failure_rate": mean(
            [1 if r.get("parse_failed") else 0 for r in answerable + adversarial]
        ),
        "latency_p95_s": p95(lats),
    }


def per_family(adversarial: List[dict]) -> Dict[str, dict]:
    """Abstention broken out by adversarial family - different families are
    caught by different mechanisms, so the aggregate hides which one works."""
    out: Dict[str, dict] = {}
    for r in adversarial:
        fam = r.get("family", "unknown")
        bucket = out.setdefault(fam, {"n": 0, "abstained": 0})
        bucket["n"] += 1
        bucket["abstained"] += int(bool(r.get("abstained")))
    for fam, b in out.items():
        b["abstention_correctness"] = round(b["abstained"] / b["n"], 4)
    return out
