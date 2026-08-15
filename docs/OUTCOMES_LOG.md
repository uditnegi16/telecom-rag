# OUTCOMES_LOG.md

What each change actually did to the numbers. This file becomes the **ablation table in your README** and the **centrepiece of your interview**.

**Rules**
1. **One variable per run.** Two changes at once produces an unattributable delta and wastes the run.
2. Log the run *before* you look at the result — write down what you expect. Being wrong about your own prediction is the interesting part, and interviewers love it.
3. **Log failures and reverts too.** "I tried X, it made things worse by 4 points, I reverted and here's why I think it failed" is a stronger answer than any success.
4. Same golden set, same seed, same τ across compared runs — otherwise you are not comparing anything.

**Template**
```
### RUN-0XX — <what changed>
- **Date / commit:**
- **Config delta from RUN-0XX:** exactly one thing
- **Hypothesis:** what you expect and why
- **Results:** (table below)
- **Interpretation:** why it moved / why it didn't
- **Verdict:** KEEP | REVERT | PARK
- **Related:** D-0XX, E-0XX
```

---

## Metric key
(full definitions in `EVALUATION_PLAN.md`)

| Metric | Set | Direction | Meaning |
|---|---|---|---|
| Recall@10 | answerable | ↑ | gold clause present in top-10 retrieved |
| MRR | answerable | ↑ | rank of the first gold clause |
| **Hallucination rate** | answerable | ↓ | % of claims not entailed by their cited chunk |
| Citation accuracy | answerable | ↑ | % of citations pointing at the correct clause |
| Answer correctness | answerable | ↑ | judged vs reference answer |
| **Abstention correctness** | adversarial | ↑ | % of unanswerable questions correctly refused |
| **False refusal rate** | answerable | ↓ | % of answerable questions wrongly refused |
| p95 latency | both | ↓ | end-to-end seconds |

**The two headline numbers are hallucination rate and abstention correctness. Everything else is supporting evidence.**

---

## What was actually executed

Two of the seven planned runs were completed. Recording that plainly, because
an ablation table with invented rows would be worse than an incomplete one.

| Run | Status | Result |
|---|---|---|
| RUN-001 | **executed** — full set, 70B generator | 17/47 answered · 30/47 abstained · recall@3 91.5% · 20/20 adversarial abstained |
| RUN-006 | **executed** — τ sweep, retrieval only, zero tokens | optimum τ=0.90 · J=0.939 · 46/47 answered · 2.1% false refusal · 96% abstention correctness |
| RUN-002…005, 007 | **not executed** | Ran out of budget and time. Each is a flag change to `eval/run_eval.py` and ~15 minutes. |

**RUN-001 is not comparable to current behaviour.** It was measured on
`llama-3.3-70b-versatile`, dropped afterwards for its 1000-requests/day cap
(D-027), and before six defects were fixed — most importantly E-016, where
correct citations were rejected because the model copied the square brackets
from the prompt's own source labels. That single bug caused the majority of
those 30 abstentions.

---

## RUN-001 — baseline (executed 14 Aug, 70B generator)

| Metric | Value |
|---|---|
| Answered | 17 / 47 |
| Abstained | 30 / 47 (64%) |
| Recall@3 (gold clause in context) | 43 / 47 = **91.5%** |
| Adversarial abstention | 20 / 20 = **100%** |
| Ungrounded-claim rate | unmeasured — run used `--no-verify` (E-012) |

**The finding that redirected the project.** Textbook naive RAG over-answers:
it invents responses to unanswerable questions and the work is driving
hallucination down. This did the opposite. Retrieval put the gold clause in
context 91.5% of the time and the system refused anyway, while abstaining on
100% of adversarial questions *before any abstention gate existed*.

Diagnosis took three attempts and two were wrong:

1. **Thought it was τ.** It was not — at the then-current τ=0.35 every
   answerable question passed the gate.
2. **Thought it was the prompt.** Partly: rules 1 and 5 told the model to
   refuse unless the sources were complete. Rebalanced in v3, which helped.
3. **It was E-016.** Citations were rejected as fabricated because the model
   returned `[TS28552_5.5.7.1.3]` — copying the bracket format from the
   prompt's own source labels — and the validator compared exactly. Under the
   fail-closed design that routes straight to abstention, so **a correct,
   well-grounded answer was silently discarded**.

---

## RUN-006 — τ sweep (executed 14 Aug, retrieval only, zero API tokens)

| τ | Answered (of 47) | False refusal | Correct abstention | Separation (J) |
|---|---|---|---|---|
| 0.35 | 47 | 0.0% | 76.0% | 0.760 |
| 0.50 | 46 | 2.1% | 84.0% | 0.819 |
| 0.75 | 46 | 2.1% | 92.0% | 0.899 |
| **0.90** | **46** | **2.1%** | **96.0%** | **0.939** |
| 0.95 | 43 | 8.5% | 96.0% | 0.875 |

Score distributions: answerable median **0.996**, adversarial median **0.029**.
Clean separation — better than expected from a cross-encoder trained on MS
MARCO web passages and applied to specification text.

**Operating point: τ = 0.90**, chosen deliberately. For a service-assurance
assistant a wrong answer about alarm semantics during an outage costs a NOC
engineer more than a refusal, so the system is tuned to fail closed and the
2.1% false-refusal cost is accepted.

**Five of 25 adversarial questions score above 0.6** — they use real-looking
identifiers such as an invented `TS 28.599`. No threshold catches those; they
are caught by citation validation and entailment verification. That is the
defence-in-depth argument with the overlap measured rather than asserted.

**The sequencing lesson.** This sweep is retrieval-only — embeddings, BM25 and
the cross-encoder all run locally — so it costs **zero API tokens** and about
two minutes. It was scheduled last, after the generation runs that consumed
the entire daily budget. The cheapest and most decisive measurement in the
project ran after the expensive ones. Order experiments by
information-per-cost, not by position in the pipeline.
| RUN-008 | + query rewrite / retry edge (D-008) | | | | | | | |

---

## Runs

### RUN-001 — Baseline (deliberately naive)
- **Date / commit:**
- **Config:** fixed 512-token chunks / 50 overlap · dense-only top-5 · no rerank · no gate · plain "answer from context" prompt · temp 0
- **Hypothesis:** hallucination rate 15–30% on answerable; near-0% abstention on adversarial (it will confidently answer questions with no answer). Both bad — that is the point.
- **Results:**

  | Metric | Value |
  |---|---|
  | Recall@10 | |
  | Hallucination rate | |
  | Citation accuracy | |
  | Answer correctness | |
  | Abstention correctness | |
  | False refusal rate | |
  | p95 latency | |

- **Interpretation:**
- **Failure taxonomy** (categorise ~10 failures by hand — do this properly, it directs everything after):

  | Failure mode | Count | Example Q |
  |---|---|---|
  | Retrieval miss (gold clause not in top-k) | | |
  | Retrieved but ignored (answered from memory) | | |
  | Chunk truncated mid-definition → model completed it | | |
  | Invented clause number | | |
  | Answered when corpus had no answer | | |
  | Release/version confusion | | |
  | Correct but uncited | | |

- **Verdict:** BASELINE — do not fix anything yet.

---

### RUN-002 — Clause-aware chunking
- **Config delta from RUN-001:** chunking only. Retrieval, prompt, k all unchanged.
- **Hypothesis:** biggest single gain of the project. "Chunk truncated mid-definition" failures should mostly disappear; citation accuracy should jump because clause IDs are now real.
- **Results:**
- **Interpretation:**
- **Verdict:**

---

### RUN-003 — Hybrid retrieval + RRF
- **Config delta:** add BM25 + RRF fusion.
- **Hypothesis:** large gain specifically on questions containing exact identifiers (`TS 28.552`, `5QI`, `NRCellDU`); little or no gain on paraphrased conceptual questions. **Segment the results by question type** — if the gain is uniform, something is wrong with your reasoning.
- **Results:**
- **Interpretation:**
- **Verdict:**

---

### RUN-004 — Cross-encoder reranking
- **Config delta:** rerank fused top-30 → top-5.
- **Hypothesis:** Recall@10 barely moves (same candidate pool); **MRR and hallucination improve markedly** because the right chunk moves into the small window the LLM actually sees. Latency worsens.
- **Results:**
- **Interpretation:**
- **Verdict:**

---

### RUN-005 — Citation-enforcing prompt + structured output
- **Config delta:** prompt + output schema only.
- **Hypothesis:** citation accuracy up sharply; hallucination down moderately (being forced to name a source suppresses unsupported claims). Watch for JSON parse failures.
- **Results:** (also record: parse-failure rate)
- **Interpretation:**
- **Verdict:**

---

### RUN-006 — Abstention gate (τ sweep)
- **Config delta:** add relevance threshold τ on top reranker score.
- **Hypothesis:** **the decisive run for this assignment.** Abstention correctness should go from near-0 to >90%. False refusals will appear — that is the cost, and quantifying it honestly is the point.
- **Threshold sweep:**

  | τ | Abstention ✓ (adversarial) | False refusal (answerable) | Halluc. rate |
  |---|---|---|---|
  | 0.1 | | | |
  | 0.2 | | | |
  | 0.3 | | | |
  | 0.4 | | | |
  | 0.5 | | | |
  | 0.6 | | | |

- **Chosen τ and justification:**
  > State the operating point as a deliberate product decision, e.g.: *"τ=0.35. For a service-assurance assistant, a wrong answer about an alarm definition costs an engineer far more than a refusal, so the system is tuned to fail closed."*
- **Verdict:**

---

### RUN-007 — Groundedness verifier
- **Config delta:** add post-generation claim/citation verification (D-010).
- **Hypothesis:** catches the residual "retrieved correctly but embellished" cases. Expect a small hallucination drop from an already-low number, plus a latency and cost increase. **Record how many claims were actually dropped** — if it is zero, say so; a verifier that never fires is still a finding, and reporting it is more honest than quietly keeping it.
- **Results:** (add: claims dropped, answers downgraded to abstention)
- **Interpretation:**
- **Verdict:**

---

### RUN-008 — Query rewrite + retry edge
- **Config delta:** LangGraph conditional retry on low-grade retrieval.
- **Hypothesis:** recovers a handful of false refusals caused by acronym/terminology mismatch, at ~2× latency on the affected subset. Modest.
- **Results:**
- **Verdict:**

---

## Final configuration (fill on 16 Aug, then freeze)

| Component | Final setting |
|---|---|
| Corpus | |
| Chunking | |
| Embedding model | |
| Retrieval | |
| Reranker | |
| k passed to LLM | |
| τ (abstention) | |
| Generator LLM | |
| Verifier | |

**Headline result:**
> Hallucination rate **__%** on N=__ answerable questions · abstention correctness **__%** on N=__ adversarial questions · false refusal rate **__%** · p95 latency **__s**.

**Known limitations (write these yourself — do not let the reviewer find them first):**
1.
2.
3.

---

## Note on baseline (added 13 Aug, after fork decision D-016)

RUN-001 is cheaper than planned. The fork base already implements
dense-only retrieval with fixed-size character chunking and a plain prompt —
which *is* the naive baseline. Point it at the 3GPP corpus and run the harness
before touching anything.

Do this **first**, before the clause chunker is wired in. It is the only
opportunity to measure the baseline, and once the chunker replaces it the
comparison is gone.
