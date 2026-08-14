"""
Interactive reviewer for gate G3.

WHY THIS EXISTS
---------------
D-012 requires every golden-set item to be verified against its source clause
by a human. Doing that by hand-editing a 60-item JSON file is slow and
error-prone: you lose your place, you forget to clear _source_body, and the
temptation to skim is enormous - which defeats the entire purpose, because
the credibility of every headline metric rests on this dataset.

This shows one item at a time beside its source text and writes after every
decision, so the work is resumable and cannot be lost.

    python -m scripts.review_golden

Keys:
    k / Enter  keep as-is, mark verified
    e          edit the question
    a          edit the reference answer
    t          change question_type
    d          delete this item
    s          skip (leave unverified, revisit later)
    q          save and quit
"""

import json
import sys
from pathlib import Path

DRAFT = Path("eval/datasets/golden_set_DRAFT.json")
OUT = Path("eval/datasets/golden_set.json")

TYPES = ["definition", "identifier_lookup", "procedural",
         "comparison", "enumeration", "cross_spec"]


def save(items):
    DRAFT.write_text(json.dumps(items, indent=2), encoding="utf-8")
    verified = [
        {k: v for k, v in it.items() if k != "_source_body"}
        for it in items if it.get("verified_by_human")
    ]
    for i, it in enumerate(verified, 1):
        it["id"] = f"A-{i:03d}"
    OUT.write_text(json.dumps(verified, indent=2), encoding="utf-8")
    return len(verified)


def wrap(text, width=96, indent="    "):
    out, line = [], ""
    for word in (text or "").split():
        if len(line) + len(word) + 1 > width:
            out.append(indent + line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(indent + line)
    return "\n".join(out)


def main():
    if not DRAFT.exists():
        raise SystemExit("Run `python -m scripts.build_golden_set` first.")

    items = json.loads(DRAFT.read_text(encoding="utf-8"))
    todo = [i for i, it in enumerate(items) if not it.get("verified_by_human")]

    print(f"\n{len(items)} drafts, {len(todo)} awaiting review.")
    print("Target: 30 verified is an honest benchmark. 60 is better.\n")

    for n, idx in enumerate(todo, 1):
        it = items[idx]
        done = sum(1 for x in items if x.get("verified_by_human"))

        print("=" * 100)
        print(f"[{n}/{len(todo)}]  verified so far: {done}     "
              f"{it['gold_spec']} {it['gold_version']}  clause {it['gold_clause']}")
        print("=" * 100)
        print("\nSOURCE:")
        print(wrap(it.get("_source_body", "")[:1400]))
        print(f"\nQUESTION  ({it.get('question_type')}, {it.get('difficulty')}):")
        print(wrap(it.get("question", "")))
        print("\nREFERENCE ANSWER:")
        print(wrap(it.get("reference_answer", "")))
        print("\nIs the question answerable from the SOURCE above, self-contained,")
        print("and is the answer correct?")

        while True:
            try:
                choice = input("  [k]eep  [e]dit-q  [a]edit-ans  [t]ype  "
                               "[d]elete  [s]kip  [q]uit > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = "q"

            if choice in ("", "k"):
                it["verified_by_human"] = True
                break
            if choice == "e":
                new = input("  new question: ").strip()
                if new:
                    it["question"] = new
                continue
            if choice == "a":
                new = input("  new answer: ").strip()
                if new:
                    it["reference_answer"] = new
                continue
            if choice == "t":
                print("  " + "  ".join(f"{i}:{t}" for i, t in enumerate(TYPES)))
                sel = input("  type number: ").strip()
                if sel.isdigit() and int(sel) < len(TYPES):
                    it["question_type"] = TYPES[int(sel)]
                continue
            if choice == "d":
                it["_deleted"] = True
                it["verified_by_human"] = False
                break
            if choice == "s":
                break
            if choice == "q":
                items = [x for x in items if not x.get("_deleted")]
                count = save(items)
                print(f"\nSaved. {count} verified items in {OUT}")
                sys.exit(0)

        items = [x for x in items if not x.get("_deleted")]
        save(items)
        print()

    count = save([x for x in items if not x.get("_deleted")])
    print(f"\nReview complete. {count} verified items -> {OUT}")
    if count < 30:
        print(f"WARNING: {count} is below the honest minimum of 30 (gate G3).")
    print("\nReport the real N in the README. Never inflate it with unverified items.")


if __name__ == "__main__":
    main()
