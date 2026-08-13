"""
Draft golden-set candidates for HAND VERIFICATION.

WHY THE HUMAN STEP IS NOT OPTIONAL (D-012)
------------------------------------------
This script produces DRAFTS, not a dataset. LLM-generated questions answered
by the same family of model measures the generator, not the system - the
metrics would be circular and a reviewer will ask about exactly this.

Every item must be read, checked against the actual clause text, corrected,
and marked verified_by_human: true before it counts. Budget ~2 minutes per
item. This is the highest-leverage work in the project: every headline number
rests on it.

Output: eval/datasets/golden_set_DRAFT.json
You then produce: eval/datasets/golden_set.json
"""

import json
import random
from pathlib import Path

from app.config import CFG
from app.llm.groq_client import GroqLLM

DRAFT_PROMPT = """You are helping build an evaluation set for a 3GPP specification assistant.

Below is one clause from a 3GPP specification.

Write ONE question that:
- is answerable ENTIRELY from this clause, with no outside knowledge
- a telecom operations engineer would plausibly ask
- is specific enough to have one correct answer

Also write the reference answer, drawn only from the clause.

CLAUSE {clause_id} - {clause_title}
SPEC: {spec_id} {spec_version}

TEXT:
{body}

Respond with JSON only:
{{"question": "...", "reference_answer": "...", "question_type": "definition|identifier_lookup|procedural|comparison|enumeration|cross_spec", "difficulty": "easy|medium|hard"}}"""

TARGET = 60


def main():
    chunks_path = Path("data/processed/chunks.json")
    if not chunks_path.exists():
        raise SystemExit("Run `make ingest` first to produce data/processed/chunks.json")

    chunks = json.loads(chunks_path.read_text())
    prose = [c for c in chunks if c.get("content_type") == "prose"
             and len(c.get("body", "")) > 300]

    # Stratify across specs so no single document dominates the benchmark.
    by_spec = {}
    for c in prose:
        by_spec.setdefault(c["spec_id"], []).append(c)

    per_spec = max(1, TARGET // max(len(by_spec), 1))
    sample = []
    for spec, items in by_spec.items():
        sample.extend(random.sample(items, min(per_spec, len(items))))
    random.shuffle(sample)
    sample = sample[:TARGET]

    llm = GroqLLM()
    drafts = []

    for i, c in enumerate(sample, 1):
        raw = llm.complete(
            DRAFT_PROMPT.format(
                clause_id=c["clause_id"], clause_title=c.get("clause_title", ""),
                spec_id=c["spec_id"], spec_version=c["spec_version"],
                body=c["body"][:3000],
            ),
            model=CFG.verify_model, max_tokens=400, json_mode=True,
        )
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            print(f"  [{i}] parse failed, skipping")
            continue

        drafts.append({
            "id": f"A-{i:03d}",
            "question": d.get("question", ""),
            "gold_spec": c["spec_id"],
            "gold_version": c["spec_version"],
            "gold_clause": c["clause_id"],
            "reference_answer": d.get("reference_answer", ""),
            "question_type": d.get("question_type", "definition"),
            "difficulty": d.get("difficulty", "medium"),
            "verified_by_human": False,          # <-- YOU set this to true
            "_source_body": c["body"][:1200],    # for your verification, strip after
        })
        print(f"  [{i}/{len(sample)}] {d.get('question','')[:70]}")

    out = Path("eval/datasets/golden_set_DRAFT.json")
    out.write_text(json.dumps(drafts, indent=2))

    print(f"\n{len(drafts)} drafts -> {out}")
    print(f"LLM stats: {llm.stats()}")
    print("\nNEXT (do not skip): read every item against _source_body, correct the")
    print("question and answer, set verified_by_human=true, delete _source_body,")
    print("and save as eval/datasets/golden_set.json. This is gate G3.")


if __name__ == "__main__":
    main()
