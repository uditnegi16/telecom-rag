"""
Ask one question end-to-end. Smoke test before spending tokens on an eval run.

    python -m scripts.ask "What does the perceivedSeverity field indicate?"
    python -m scripts.ask --tau 0.2 "How is DAPS handover measured?"

Shows the full trace: retrieved clauses with scores, the gate decision, claims
with citations, and the verifier verdict per claim. If something is wrong,
this tells you WHICH stage - which a bare answer never does.
"""

import argparse
import json

from app.config import CFG


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="+")
    ap.add_argument("--tau", type=float, default=None)
    ap.add_argument("--no-bm25", action="store_true")
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()

    question = " ".join(args.question)

    from app.pipeline import get_answer_fn, llm_stats

    answer_fn = get_answer_fn(
        tau=args.tau,
        use_bm25=not args.no_bm25,
        use_reranker=not args.no_rerank,
        verify=not args.no_verify,
    )

    print(f"\nQ: {question}")
    print(f"tau={args.tau if args.tau is not None else CFG.tau_abstain}  "
          f"bm25={not args.no_bm25}  rerank={not args.no_rerank}  "
          f"verify={not args.no_verify}")
    print("-" * 72)

    res = answer_fn(question)

    print(f"confidence      : {res.get('confidence')}")
    print(f"abstained       : {res.get('abstained')}")
    if res.get("abstained"):
        print(f"abstain reason  : {res.get('abstain_reason')}")
    print(f"retrieved clauses: {res.get('retrieved_clauses')}")
    print(f"claim verdicts  : {res.get('claim_verdicts')}")
    if res.get("claims_dropped"):
        print(f"claims dropped  : {res['claims_dropped']}")

    print("\nANSWER:")
    print(f"  {res.get('answer')}")

    if res.get("claims"):
        print("\nCLAIMS:")
        for c in res["claims"]:
            print(f"  - {c['claim']}")
            print(f"    [{c['citation']}]")

    print(f"\nLLM: {json.dumps(llm_stats())}")


if __name__ == "__main__":
    main()
