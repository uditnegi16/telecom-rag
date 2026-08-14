"""
Empirical tau sweep. RETRIEVAL ONLY - zero Groq tokens.

WHY THIS RUNS FIRST, NOT LAST (D-009, ERROR_LOG E-015)
------------------------------------------------------
D-009 states that tau must be chosen by sweeping it against measured data.
It was then hardcoded to 0.35 - a guess - and shipped. Every abstention in
the demo traced back to that guess rather than to any design property.

Retrieval is entirely local: embeddings, BM25 and the cross-encoder all run
on CPU. So the sweep that chooses the single most consequential parameter in
the system costs NOTHING, while the generation runs that were prioritised
ahead of it cost the whole daily token budget. The cheap decisive measurement
was sequenced last. That ordering was the error.

Output: score distributions for answerable vs unanswerable questions, and the
false-refusal / correct-abstention trade-off at every threshold.

    python -m scripts.sweep_tau
"""

from __future__ import annotations

import json
import statistics as stats
from pathlib import Path

from app.config import CFG

GOLD = Path("eval/datasets/golden_set.json")
ADV = Path("eval/datasets/adversarial_set.json")
OUT = Path("eval/results/tau_sweep.json")


def percentiles(xs, ps=(5, 25, 50, 75, 95)):
    if not xs:
        return {}
    s = sorted(xs)
    return {f"p{p}": round(s[min(len(s) - 1, int(p / 100 * len(s)))], 4) for p in ps}


def main():
    from app.pipeline import build_retrieve_fn

    retrieve = build_retrieve_fn()

    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    adv = json.loads(ADV.read_text(encoding="utf-8"))

    print(f"Scoring {len(gold)} answerable + {len(adv)} adversarial "
          f"questions (no LLM calls)…\n")

    def score_all(items, label):
        rows = []
        for i, it in enumerate(items, 1):
            r = retrieve(it["question"])
            top = r["top_score"]
            got = [c.get("clause_id") for c in r["chunks"]]
            hit = it.get("gold_clause") in got if "gold_clause" in it else None
            rows.append({
                "id": it["id"], "top_score": top,
                "gold_clause": it.get("gold_clause"),
                "retrieved": got, "recall": hit,
            })
            flag = "" if hit is None else ("  hit" if hit else "  MISS")
            print(f"  [{label} {i}/{len(items)}] {top:.4f}{flag}")
        return rows

    gold_rows = score_all(gold, "A")
    print()
    adv_rows = score_all(adv, "ADV")

    g = [r["top_score"] for r in gold_rows]
    a = [r["top_score"] for r in adv_rows]

    print("\n" + "=" * 72)
    print("SCORE DISTRIBUTION")
    print("=" * 72)
    print(f"  answerable    n={len(g):3d}  mean={stats.mean(g):.4f}  "
          f"median={stats.median(g):.4f}")
    print(f"                {percentiles(g)}")
    print(f"  adversarial   n={len(a):3d}  mean={stats.mean(a):.4f}  "
          f"median={stats.median(a):.4f}")
    print(f"                {percentiles(a)}")

    # Recall against gold clause, independent of any threshold.
    hits = sum(1 for r in gold_rows if r["recall"])
    print(f"\n  recall@{CFG.rerank_top_n} (gold clause retrieved): "
          f"{hits}/{len(gold_rows)} = {hits/len(gold_rows):.1%}")

    print("\n" + "=" * 72)
    print("TAU SWEEP")
    print("=" * 72)
    print(f"  {'tau':>6} {'answered':>9} {'false-refuse':>13} "
          f"{'abstain-ok':>11} {'separation':>11}")
    print("  " + "-" * 62)

    sweep = []
    best = None
    for i in range(0, 21):
        tau = i / 20
        answered = sum(1 for x in g if x >= tau)
        false_ref = (len(g) - answered) / len(g)
        abstain_ok = sum(1 for x in a if x < tau) / len(a)
        # Youden's J: how well this threshold separates the two groups.
        sep = (answered / len(g)) + abstain_ok - 1
        sweep.append({"tau": tau, "answered": answered,
                      "false_refusal_rate": round(false_ref, 4),
                      "abstention_correctness": round(abstain_ok, 4),
                      "separation": round(sep, 4)})
        if best is None or sep > best["separation"]:
            best = sweep[-1]
        mark = ""
        if abs(tau - CFG.tau_abstain) < 0.001:
            mark = "  <- current"
        print(f"  {tau:6.2f} {answered:9d} {false_ref:12.1%} "
              f"{abstain_ok:10.1%} {sep:11.3f}{mark}")

    print("\n" + "=" * 72)
    print(f"  BEST SEPARATION at tau = {best['tau']:.2f}  "
          f"(J = {best['separation']:.3f})")
    print(f"    would answer {best['answered']}/{len(g)} answerable, "
          f"false-refusal {best['false_refusal_rate']:.1%}, "
          f"abstain-correct {best['abstention_correctness']:.1%}")

    overlap = sum(1 for x in a if x >= min(g)) if g else 0
    print(f"\n  DIAGNOSIS")
    if best["separation"] < 0.3:
        print("    Groups do NOT separate on this score. The cross-encoder is")
        print("    not a usable corpus-membership signal for this corpus - it")
        print("    is trained on MS MARCO web passages, far from 3GPP text.")
        print("    Recommendation: disable the score gate (tau=0.0) and rely")
        print("    on the model's sufficiency judgement plus the entailment")
        print("    verifier, which caught 20/20 adversarial in RUN-001 with")
        print("    no gate at all. Record this as a measured negative result.")
    else:
        print(f"    Usable separation. Set CFG.tau_abstain = {best['tau']:.2f}")
        print(f"    ({overlap} adversarial questions score above the lowest")
        print(f"    answerable score - the irreducible overlap.)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "config_hash": CFG.config_hash(),
        "reranker": CFG.reranker_model,
        "answerable": gold_rows, "adversarial": adv_rows,
        "distribution": {"answerable": percentiles(g), "adversarial": percentiles(a)},
        "sweep": sweep, "best": best,
    }, indent=2), encoding="utf-8")
    print(f"\n  written -> {OUT}")
    print("  Paste the sweep table into docs/OUTCOMES_LOG.md as RUN-006.")


if __name__ == "__main__":
    main()
