"""
Relabel question types and build the smoke subset.

WHY RELABEL (EVALUATION_PLAN 1.1)
---------------------------------
`question_type` is not decoration: RUN-003 must report the hybrid-retrieval
gain SEGMENTED by type, because the prediction is that BM25 helps
identifier-style questions sharply and barely moves definitional ones. If the
measured gain is uniform, the analysis is wrong and needs investigating.

The drafting model labelled 34/47 items "definition", including many that are
plainly identifier lookups ("What is the SS parameter type for
'heartbeatNtfPeriod'?"). The heuristics below retype on question SHAPE, then
print everything for a human glance. Labels are metadata about the benchmark,
not the benchmark itself, so heuristic assignment plus review is honest here -
unlike the question/answer content, which required item-by-item verification.

    python -m scripts.prep_eval
"""

import json
import random
import re
from pathlib import Path

GOLD = Path("eval/datasets/golden_set.json")
ADV = Path("eval/datasets/adversarial_set.json")
SMOKE = Path("eval/datasets/smoke_set.json")

# Telecom identifiers: NF names, measurement names, protocol params, 5QI, etc.
IDENTIFIER = re.compile(
    r"'[A-Za-z][A-Za-z0-9_.\-]*'|\"[A-Za-z][A-Za-z0-9_.\-]*\"|"
    r"\b[a-z]+[A-Z][A-Za-z]*\b|"                       # camelCase
    r"\b[A-Z]{2,}\.[A-Za-z]+|"                          # RACH.PreambleDed
    r"\bTS\s?\d{2}\.\d{3}\b|\b5QI\b|\bgNB[-A-Z]*\b|\bNRCell[A-Z]{2}\b"
)
ENUM = re.compile(r"\bwhat (values|types|methods|codes|options|fields)\b|"
                  r"\bwhich (values|types|methods|codes|parameters)\b|"
                  r"\blist\b", re.I)
PROCEDURAL = re.compile(r"\bhow is\b|\bhow does\b|\bhow are\b|\bwhat triggers\b|"
                        r"\bwhen is\b|\bwhat happens\b|\bformula\b|"
                        r"\bobtained\b|\bcalculated\b|\bmeasured\b|"
                        r"\bcondition for\b|\bprocedure\b", re.I)
COMPARISON = re.compile(r"\bdifference between\b|\bcompared to\b|\bversus\b|\bvs\b", re.I)


def classify(q: str) -> str:
    if COMPARISON.search(q):
        return "comparison"
    if ENUM.search(q):
        return "enumeration"
    if PROCEDURAL.search(q):
        return "procedural"
    if IDENTIFIER.search(q):
        return "identifier_lookup"
    return "definition"


def main():
    items = json.loads(GOLD.read_text(encoding="utf-8"))
    before = {}
    for it in items:
        old = it.get("question_type", "?")
        new = classify(it["question"])
        before[old] = before.get(old, 0) + 1
        it["question_type"] = new
        it["type_source"] = "heuristic"     # disclosed, not silently overwritten

    GOLD.write_text(json.dumps(items, indent=2), encoding="utf-8")

    from collections import Counter
    after = Counter(x["question_type"] for x in items)

    print(f"{len(items)} items relabelled\n")
    print("BEFORE:", dict(before))
    print("AFTER :", dict(after))
    print("\nSample per type (glance for obvious errors):")
    for t in after:
        ex = next(x["question"] for x in items if x["question_type"] == t)
        print(f"  {t:20s} {ex[:80]}")

    # --- smoke subset: 10 answerable + 5 adversarial, type-stratified -------
    random.seed(42)                     # NFR-08: reproducible
    by_type = {}
    for it in items:
        by_type.setdefault(it["question_type"], []).append(it)

    smoke = []
    for t, group in by_type.items():
        smoke.extend(random.sample(group, min(3, len(group))))
    smoke = smoke[:10]
    if len(smoke) < 10:
        rest = [x for x in items if x not in smoke]
        smoke.extend(random.sample(rest, 10 - len(smoke)))

    adv = json.loads(ADV.read_text(encoding="utf-8"))
    by_family = {}
    for a in adv:
        by_family.setdefault(a["family"], []).append(a)
    adv_smoke = [random.choice(v) for v in by_family.values()][:5]

    SMOKE.write_text(json.dumps(smoke, indent=2), encoding="utf-8")
    Path("eval/datasets/smoke_adversarial.json").write_text(
        json.dumps(adv_smoke, indent=2), encoding="utf-8"
    )

    print(f"\nsmoke set: {len(smoke)} answerable -> {SMOKE}")
    print(f"           {len(adv_smoke)} adversarial -> eval/datasets/smoke_adversarial.json")
    print(f"\nfull set : {len(items)} answerable + {len(adv)} adversarial")
    est = (len(items) + len(adv)) * 2700 / 6000
    print(f"est. full run at 6000 TPM with verifier: ~{est:.0f} min wall clock")


if __name__ == "__main__":
    main()
