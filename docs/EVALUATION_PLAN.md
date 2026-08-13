# EVALUATION_PLAN.md

The assignment is graded on hallucination. Hallucination is not a feeling — it is a rate on a fixed test set. This file defines that measurement precisely, **before** any optimisation happens.

---

## 1. Datasets

### 1.1 Answerable set — target N = 60
Questions whose answer exists in the indexed corpus.

Each item:
```json
{
  "id": "A-001",
  "question": "What is the definition of the perceivedSeverity field in an alarm notification?",
  "gold_spec": "TS 28.532",
  "gold_version": "V18.5.0",
  "gold_clause": "11.2.1.3",
  "reference_answer": "…",
  "question_type": "definition",
  "difficulty": "easy"
}
```

**Question types — aim for roughly:**
| Type | ~N | Tests |
|---|---|---|
| Definition ("what is X") | 15 | basic retrieval |
| Identifier lookup (exact spec/clause/field name) | 12 | BM25 / hybrid value |
| Procedural ("what happens when…") | 12 | multi-step, longer chunks |
| Comparison ("difference between X and Y") | 8 | multi-chunk synthesis |
| Enumeration ("which values can X take") | 8 | table extraction quality |
| Cross-spec | 5 | retrieval breadth |

**Construction (D-012):** stratified chunk sample → LLM drafts candidates → **you verify and correct all 60 by hand.** Record in the README that every item was manually verified. This is the honesty that survives an interview question.

### 1.2 Adversarial / unanswerable set — target N = 25
**This set is what actually proves "near-zero hallucination."** A system that answers everything correctly but also answers unanswerable questions is not a low-hallucination system.

| Family | ~N | Example |
|---|---|---|
| Out-of-corpus topic | 7 | "What are the LTE X2 handover procedures?" (not indexed) |
| False premise | 6 | "Why did 3GPP deprecate the AMF in Rel-18?" (it didn't) |
| Invented entity | 6 | "What is the role of the NSSAAF-X9 function?" (doesn't exist) |
| Wrong Release | 3 | asks for a Rel-15 clause not in the frozen corpus |
| Unanswerable-by-nature | 3 | "Which vendor's AMF performs best?" (not a spec question) |

**Correct behaviour for all 25: refuse.** Any confident answer counts as a hallucination.

### 1.3 Smoke subset — N = 15
A 15-item mixed subset for fast iteration. Full sets only at phase gates. Saves cost and time.

---

## 2. Metrics

### Retrieval
- **Recall@k** — fraction of questions where `gold_clause` appears in the top-k retrieved. Report k = 5, 10.
- **MRR** — mean of 1/(rank of first gold clause). Sensitive to ordering; the metric the reranker should move.
- **nDCG@10** — optional, only if you record graded relevance.

### Generation
- **Hallucination rate** *(headline)* — decompose each answer into atomic claims; a claim is **grounded** iff it is entailed by its cited chunk. `hallucination_rate = ungrounded_claims / total_claims`. Judged by LLM-as-judge with a strict rubric; **hand-verify a 20-item sample of the judgements** and report judge–human agreement. Reporting agreement is what separates a real evaluation from a decorative one.
- **Citation accuracy** — fraction of citations whose `chunk_id` (a) exists in the retrieved set and (b) contains the supporting text. Report the two failure types separately: *invented citation* vs *wrong-but-real citation*.
- **Answer correctness** — LLM-judged similarity to `reference_answer` on a 0–2 scale (wrong / partial / correct).

### Safety / abstention
- **Abstention correctness** *(headline)* = correctly refused adversarial / 25
- **False refusal rate** = wrongly refused answerable / 60
- **Unsupported-answer rate** = adversarial questions given a confident answer / 25 — the number that most directly contradicts "zero hallucination", so report it prominently rather than burying it.

### Operational
- p50 / p95 end-to-end latency; tokens per query; cost per query; JSON parse-failure rate.

---

## 3. Targets

| Metric | Baseline (expected) | Target | Stretch |
|---|---|---|---|
| Recall@10 | ~0.60 | ≥0.85 | ≥0.92 |
| Hallucination rate | 15–30% | **<5%** | **<2%** |
| Citation accuracy | n/a | ≥90% | ≥95% |
| Abstention correctness | ~0–20% | **>90%** | >96% |
| False refusal rate | 0% | <15% | <8% |
| p95 latency | — | <6s | <3s |

Note the baseline false-refusal rate is 0% *because the baseline never refuses anything*. That is not a virtue, and saying so out loud shows you understand the metric rather than just reporting it.

---

## 4. Judge protocol

- Judge model runs at temperature 0 with a fixed rubric prompt (version the prompt — a rubric change invalidates cross-run comparisons).
- Judge sees: question, answer claim, cited chunk text. **Not** the reference answer, when scoring groundedness — otherwise it scores correctness, not grounding.
- Binary entailment: does the cited chunk **state or directly imply** this claim? Plausible-but-absent = **not grounded**.
- Every full run writes `eval/results/RUN-0XX.json` with per-question rows so failures can be inspected individually.

**Judge validation:** hand-label 20 judgements and report agreement (e.g. "judge agreed with me on 18/20"). If an interviewer asks "how do you know your evaluator isn't hallucinating?" — this is the answer, and it is a question a good interviewer will ask.

---

## 5. Reproducibility

- Fixed seeds; temperature 0 everywhere including the judge.
- Datasets in `eval/datasets/` under version control, never regenerated between compared runs.
- Every run records: git commit, config hash, model names/versions, τ, timestamp.
- `make eval` reproduces the table from a clean clone.

---

## 6. Reporting

The README gets: the ablation table from `OUTCOMES_LOG.md`, the τ sweep curve (hallucination vs false refusal), the failure taxonomy from the baseline, and an explicit **Limitations** section.

Frame the headline like this, not as a bare percentage:
> "On a 60-question hand-verified benchmark the system produced **X% ungrounded claims**, and on 25 adversarial unanswerable questions it correctly abstained **Y%** of the time, at a cost of **Z%** false refusals on answerable questions. I would not claim zero hallucination in the general case — the system is designed to be *fail-closed and auditable* rather than provably correct."
