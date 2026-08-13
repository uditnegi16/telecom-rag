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

## Ablation summary (fill as you go — this table goes in the README)

| Run | Change | Recall@10 | Halluc. ↓ | Citation ✓ | Abstain ✓ | False refuse ↓ | p95 | Verdict |
|---|---|---|---|---|---|---|---|---|
| RUN-001 | Baseline: fixed 512 chunks, dense-only, plain prompt | | | | | | | — |
| RUN-002 | + clause-aware chunking (D-003) | | | | | | | |
| RUN-003 | + BM25 hybrid, RRF (D-006) | | | | | | | |
| RUN-004 | + cross-encoder rerank (D-007) | | | | | | | |
| RUN-005 | + citation-enforcing prompt & structured output | | | | | | | |
| RUN-006 | + abstention gate, τ swept (D-009) | | | | | | | |
| RUN-007 | + groundedness verifier (D-010) | | | | | | | |
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
