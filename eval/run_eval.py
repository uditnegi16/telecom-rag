"""
Evaluation harness.

WHY (traceability: NFR-02, NFR-03, NFR-08; SDLC phase 4)
--------------------------------------------------------
Built BEFORE the system is optimised. Every optimisation must produce a run
record here, or it does not count as evidence.

Each run writes eval/results/RUN-<id>.json containing the git commit, the
config hash, per-question rows, and aggregate metrics - so any number in the
final report can be traced back to a reproducible run.

Usage:
    python -m eval.run_eval --run-id 001 --note "baseline: dense only"
    python -m eval.run_eval --run-id 006 --tau 0.4 --smoke
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable, List

from app.config import CFG
from eval import metrics

DATASETS = Path("eval/datasets")
RESULTS = Path("eval/results")


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def load(name: str) -> List[dict]:
    path = DATASETS / name
    if not path.exists():
        return []
    return json.loads(path.read_text())


def evaluate(
    answer_fn: Callable[[str], dict],
    run_id: str,
    note: str,
    tau: float | None = None,
    smoke: bool = False,
) -> dict:
    """`answer_fn(question) -> dict` must return:
        answer, claims, citations, abstained, confidence,
        retrieved_clauses, claim_verdicts, parse_failed
    """
    if smoke:
        answerable = load("smoke_set.json")
        adversarial = load("smoke_adversarial.json")
    else:
        answerable = load("golden_set.json")
        adversarial = load("adversarial_set.json")

    if not answerable and not adversarial:
        raise SystemExit(
            "No datasets found. Build eval/datasets/golden_set.json first "
            "(gate G3) - the harness is useless without them."
        )

    ans_rows, adv_rows = [], []

    print(f"\nRUN-{run_id}  tau={tau if tau is not None else CFG.tau_abstain}  {note}")
    print("-" * 70)

    for item in answerable:
        t0 = time.time()
        res = answer_fn(item["question"])
        latency = time.time() - t0

        retrieved = res.get("retrieved_clauses", [])
        gold = item.get("gold_clause", "")
        verdicts = res.get("claim_verdicts", [])

        row = {
            **{k: item[k] for k in ("id", "question") if k in item},
            "question_type": item.get("question_type"),
            "gold_clause": gold,
            "abstained": res.get("abstained", False),
            "confidence": res.get("confidence"),
            "answer": res.get("answer"),
            "citations": res.get("citations", []),
            "recall_at_5": metrics.recall_at_k(retrieved, gold, 5),
            "recall_at_10": metrics.recall_at_k(retrieved, gold, 10),
            "reciprocal_rank": metrics.reciprocal_rank(retrieved, gold),
            "ungrounded_rate": metrics.ungrounded_claim_rate(verdicts),
            "citation_accuracy": metrics.citation_accuracy(
                res.get("cited_clauses", []), gold
            ),
            "parse_failed": res.get("parse_failed", False),
            "latency_s": round(latency, 3),
        }
        ans_rows.append(row)
        flag = "ABSTAIN" if row["abstained"] else "ANSWER "
        print(f"  [{item['id']}] {flag} r@10={row['recall_at_10']} "
              f"ungrounded={row['ungrounded_rate']}")

    for item in adversarial:
        t0 = time.time()
        res = answer_fn(item["question"])
        latency = time.time() - t0
        row = {
            "id": item["id"],
            "family": item.get("family"),
            "question": item["question"],
            "abstained": res.get("abstained", False),
            "confidence": res.get("confidence"),
            "answer": res.get("answer"),
            "latency_s": round(latency, 3),
        }
        adv_rows.append(row)
        # A confident answer here is a hallucination, so mark it loudly.
        flag = "ok (abstained)" if row["abstained"] else "*** ANSWERED - HALLUCINATION"
        print(f"  [{item['id']}] {flag}")

    agg = metrics.aggregate(ans_rows, adv_rows)
    fam = metrics.per_family(adv_rows)

    record = {
        "run_id": run_id,
        "note": note,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "git_commit": git_commit(),
        "config_hash": CFG.config_hash(),
        "config": asdict(CFG),
        "tau_used": tau if tau is not None else CFG.tau_abstain,
        "smoke": smoke,
        "aggregate": agg,
        "adversarial_by_family": fam,
        "answerable_rows": ans_rows,
        "adversarial_rows": adv_rows,
    }

    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"RUN-{run_id}.json"
    out.write_text(json.dumps(record, indent=2))

    print("-" * 70)
    for k, v in agg.items():
        print(f"  {k:28s} {v}")
    print(f"\n  adversarial by family: {json.dumps(fam)}")
    print(f"\n  written -> {out}")
    print("  Now paste these into docs/OUTCOMES_LOG.md with a KEEP/REVERT verdict.\n")

    return record


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--note", default="")
    ap.add_argument("--tau", type=float, default=None)
    ap.add_argument("--smoke", action="store_true")
    # Ablation switches (D-016..D-020). RUN-001 baseline is:
    #   --no-bm25 --no-rerank --no-verify
    ap.add_argument("--no-bm25", action="store_true")
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()

    from app.pipeline import get_answer_fn, llm_stats

    answer_fn = get_answer_fn(
        tau=args.tau,
        use_bm25=not args.no_bm25,
        use_reranker=not args.no_rerank,
        verify=not args.no_verify,
    )
    evaluate(answer_fn, args.run_id, args.note, tau=args.tau, smoke=args.smoke)
    print(f"  LLM: {llm_stats()}")


if __name__ == "__main__":
    main()
