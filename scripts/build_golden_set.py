"""
Draft golden-set candidates for HAND VERIFICATION.

WHY THE HUMAN STEP IS NOT OPTIONAL (D-012)
------------------------------------------
This produces DRAFTS, not a dataset. LLM-generated questions answered by the
same family of model measures the generator, not the system - the metrics
would be circular, and a reviewer will ask about exactly this.

Every item must be read against its `_source_body`, corrected, and marked
verified_by_human: true before it counts.

HARDENING (ERROR_LOG E-010, E-011)
----------------------------------
* Drafts are saved after EVERY item. A crash at item 28 previously discarded
  all 27 completed drafts.
* A deterministic 400 skips that item instead of aborting the run.
* Source chunks are filtered before drafting. Change-history annexes, mapping
  tables and stub clauses produce questions like "What is the status of the
  clause that cannot be deleted?" - faithful to the source, useless as
  evaluation items. Filtering at the source is cheaper than discarding by hand.
"""

import json
import random
import re
from pathlib import Path

from app.config import CFG
from app.llm.groq_client import GroqLLM, LLMBadRequest

DRAFT_PROMPT = """You are helping build an evaluation set for a 3GPP specification assistant.

Below is one clause from a 3GPP specification.

Write ONE question that:
- is answerable ENTIRELY from this clause, with no outside knowledge
- a telecom operations engineer would plausibly ask
- is SELF-CONTAINED: it must make sense without seeing the clause, so never
  write "this measurement" or "this clause" - name the thing explicitly
- does not ask about clause numbering, table numbering, or document structure

Also write the reference answer, drawn only from the clause.

CLAUSE {clause_id} - {clause_title}
SPEC: {spec_id} {spec_version}

TEXT:
{body}

Respond with JSON only:
{{"question": "...", "reference_answer": "...", "question_type": "definition|identifier_lookup|procedural|comparison|enumeration|cross_spec", "difficulty": "easy|medium|hard"}}"""

TARGET = 60
OUT = Path("eval/datasets/golden_set_DRAFT.json")

# Clauses that produce poor evaluation questions.
BAD_TITLE = re.compile(
    r"change history|void|foreword|scope|references|abbreviations|"
    r"document structure|introduction$",
    re.I,
)
BAD_PATH = re.compile(r"Annex\s+[A-Z]\s*\(informative\):\s*$|change history", re.I)


def usable(c: dict) -> bool:
    body = c.get("body", "")
    if len(body) < 350 or len(body) > 6000:
        return False
    if c.get("content_type") != "prose":
        return False
    if BAD_TITLE.search(c.get("clause_title", "")):
        return False
    if BAD_PATH.search(c.get("heading_path", "")):
        return False
    # Mapping/spec tables: many short lines, few sentences.
    if body.count(".") < 3:
        return False
    # Change-history rows look like "2024-12 SA#106 SP-241643 0356 1 F Rel-18"
    if len(re.findall(r"\b(SA#\d+|SP-\d{6}|CR\s)\b", body)) > 2:
        return False
    return True


def main():
    chunks_path = Path("data/processed/chunks.json")
    if not chunks_path.exists():
        raise SystemExit("Run `python -m scripts.ingest` first.")

    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    pool = [c for c in chunks if usable(c)]
    print(f"{len(chunks)} chunks -> {len(pool)} usable as evaluation sources\n")

    by_spec = {}
    for c in pool:
        by_spec.setdefault(c["spec_id"], []).append(c)

    per_spec = max(1, TARGET // max(len(by_spec), 1))
    sample = []
    for spec, items in by_spec.items():
        sample.extend(random.sample(items, min(per_spec, len(items))))
    random.shuffle(sample)
    sample = sample[:TARGET]

    llm = GroqLLM()
    drafts, skipped = [], 0

    for i, c in enumerate(sample, 1):
        try:
            raw = llm.complete(
                DRAFT_PROMPT.format(
                    clause_id=c["clause_id"], clause_title=c.get("clause_title", ""),
                    spec_id=c["spec_id"], spec_version=c["spec_version"],
                    body=c["body"][:3000],
                ),
                model=CFG.verify_model, max_tokens=400, json_mode=True,
            )
            d = json.loads(raw)
        except LLMBadRequest:
            skipped += 1
            print(f"  [{i}] skipped (provider rejected generation)")
            continue
        except json.JSONDecodeError:
            skipped += 1
            print(f"  [{i}] skipped (unparseable)")
            continue

        drafts.append({
            "id": f"A-{len(drafts)+1:03d}",
            "question": d.get("question", ""),
            "gold_spec": c["spec_id"],
            "gold_version": c["spec_version"],
            "gold_clause": c["clause_id"],
            "gold_chunk_id": c["chunk_id"],
            "reference_answer": d.get("reference_answer", ""),
            "question_type": d.get("question_type", "definition"),
            "difficulty": d.get("difficulty", "medium"),
            "verified_by_human": False,
            "_source_body": c["body"][:1500],
        })
        # Save after EVERY item (E-010).
        OUT.write_text(json.dumps(drafts, indent=2), encoding="utf-8")
        print(f"  [{i}/{len(sample)}] {d.get('question','')[:72]}")

    print(f"\n{len(drafts)} drafts ({skipped} skipped) -> {OUT}")
    print(f"LLM: {llm.stats()}")
    print("\nNEXT (gate G3): read every item against _source_body, correct the")
    print("question and answer, set verified_by_human=true, delete _source_body,")
    print("save as eval/datasets/golden_set.json.")
    print("Delete any item that is vague, meta, or not self-contained.")


if __name__ == "__main__":
    main()
