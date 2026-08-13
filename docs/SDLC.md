# Software Development Life Cycle

**Project:** TelecomRAG — grounded question-answering over 3GPP specifications
**Assignment:** Mavenir GET (AI/LLM Engineer, MavAI OPS) technical submission
**Author:** Kanak
**Version:** 1.0 · 13 Aug 2026
**Submission deadline:** 17 Aug 2026

---

## 1. Purpose of this document

This document records the engineering process followed to build TelecomRAG: the lifecycle model chosen and why, the phases and their entry/exit criteria, the artifacts produced at each phase, and how every requirement traces to a design decision, a test, and a measured result.

It exists because the assignment is graded on *understanding of the solution design*, not only on the running system. A reviewer should be able to read this document and reconstruct why the system looks the way it does.

---

## 2. Lifecycle model selection

### 2.1 The problem with a single model

This system has two halves with incompatible development characteristics:

| | Software layer | AI/RAG layer |
|---|---|---|
| Components | Parser, API, vector store, UI, container | Chunking, retrieval, generation, verification |
| Correctness | Deterministic — a test passes or fails | Statistical — a metric improves or regresses |
| Specification | Can be written up front | Emerges from measurement |
| Failure mode | Exception, wrong output | Plausible but unsupported output |
| Verification | Unit / integration tests | Benchmark evaluation on a held dataset |

The requirement *"minimal to near-zero hallucinations"* cannot be implemented against a written spec. It is a **measured property of the assembled system**, so it can only be driven down by an iterative measure-diagnose-change-remeasure loop.

### 2.2 Model chosen: hybrid — V-Model shell, eval-driven spiral core

```
        ┌───────────────────── SOFTWARE LAYER (V-Model) ─────────────────────┐
        │                                                                    │
  Requirements ─────────────────────────────────────────► Acceptance testing │
        │                                                                    │
    Architecture ─────────────────────────────────► Integration testing      │
        │                                                                    │
      Module design ──────────────────────► Unit testing                     │
        │                                                                    │
        └──────────────── Implementation ────────────────┘                   │
                                │                                            │
                                ▼                                            │
        ┌────────────── AI LAYER (eval-driven spiral) ──────────────┐         │
        │                                                            │        │
        │   ① build eval harness + datasets    (BEFORE optimising)  │        │
        │   ② ship deliberately naive baseline                       │        │
        │   ③ measure → record in OUTCOMES_LOG                       │        │
        │   ④ diagnose dominant failure mode (failure taxonomy)      │        │
        │   ⑤ change exactly ONE variable                            │        │
        │   ⑥ re-measure → KEEP or REVERT (logged either way)        │        │
        │   ⑦ repeat until exit criteria met or time-box expires     │        │
        │                                                            │        │
        └────────────────────────────────────────────────────────────┘        │
        └────────────────────────────────────────────────────────────────────┘
```

### 2.3 Why not the alternatives

| Model | Rejected because |
|---|---|
| Waterfall | Hallucination rate is unknowable at design time; the design would be frozen before the first measurement existed. |
| Pure Agile / Scrum | Ceremony overhead has no payoff on a solo, 1-day-build project. The useful part (short feedback loops) is already inside the spiral core. |
| CRISP-DM | Written for predictive modelling on tabular data. Has no place for prompt design, retrieval quality, or grounding verification. |
| Pure MLOps | Assumes model training and retraining pipelines. This project trains nothing — it is a retrieval and orchestration problem. |
| **Hybrid V + spiral (chosen)** | The software layer genuinely benefits from up-front specification and a matching test level at each design level. The AI layer genuinely cannot be specified up front. Each half gets the discipline it actually needs. |

### 2.4 Governing principle

> **The evaluation harness is built before the system is optimised.**

If retrieval and prompting are tuned before a benchmark exists, there is no baseline, no attributable delta per change, and no evidence that any decision was correct. The ablation table in `OUTCOMES_LOG.md` is only possible because measurement precedes optimisation.

---

## 3. Phases

### Phase 0 — Inception & requirements elicitation
**Entry:** assignment brief received.
**Activities:** interpret the brief; separate explicit requirements from implied ones; identify the ambiguous requirement ("near-zero hallucination") and reformulate it as something measurable; define scope boundaries.
**Artifacts:** `REQUIREMENTS.md`, scope statement, `PROJECT_PLAN.md` §1.
**Exit:** every requirement has an ID and an acceptance criterion expressed as a number or a testable behaviour.

**Key output of this phase — requirement reformulation:**
> *"Near-zero hallucination"* is not verifiable as stated. Reformulated as three measurable requirements: **FR-06** (no claim emitted without a valid citation), **FR-07** (abstain rather than answer when evidence is insufficient), **NFR-02** (measured ungrounded-claim rate below threshold on a fixed benchmark). See `REQUIREMENTS.md` and §8 of this document.

---

### Phase 1 — Feasibility & reuse analysis
**Entry:** requirements baselined.
**Activities:** audit existing personal codebases for reusable components; assess constraints (Groq free tier, CPU-only hardware, 1-day build); decide build-vs-reuse per component.
**Artifacts:** `docs/REUSE_AUDIT.md`, decisions D-016 to D-020 in `DECISION_LOG.md`.
**Exit:** fork base selected; reuse boundary documented; constraint budget calculated.

**Finding:** a prior project (`production-rag`) already provided Groq integration, CPU-pinned inference, cross-encoder reranking, a confidence gate, caching, FastAPI, Docker and CI. Forking it converted approximately three days of infrastructure work into configuration work, releasing the entire schedule for the graded components. **The reuse boundary is disclosed in the README** — see §9, Ethics & disclosure.

**Constraint budget (Groq free tier):** ~6,000 tokens/min, ~30 req/min. At 5 chunks × 800 tokens this permits roughly one query per minute, so a full 85-question evaluation exceeds an hour of wall clock. This single number drove D-017 (reduce k, cap chunk size), D-018 (mandatory response caching), D-019 (two-tier model split), and the decision to iterate on a 15-question smoke subset with full runs only at phase gates.

---

### Phase 2 — Requirements analysis & architecture
**Entry:** fork base selected.
**Activities:** map each requirement to an architectural component; identify, for every component, the specific failure mode it prevents; define module interfaces and the state passed between pipeline stages.
**Artifacts:** `docs/ARCHITECTURE.md`, component diagram, `docs/TRACEABILITY.md`, decisions D-001 to D-015.
**Exit:** every requirement maps to at least one component; every component justified by at least one requirement. No orphans in either direction.

**Design rule applied:** each component in the pipeline must be justifiable by naming the hallucination mode it eliminates, not by describing what it does. A component that cannot be justified this way is removed.

| Component | Failure mode eliminated |
|---|---|
| Clause-aware chunking | Definition split mid-sentence; model completes it from parametric memory |
| Metadata (spec, version, clause) | Invented clause numbers; cross-Release blending |
| Hybrid retrieval (BM25 + dense) | Dense embeddings miss exact identifiers (`TS 28.552`, `5QI`, `gNB-DU`) |
| Cross-encoder reranking | Correct chunk present in candidate pool but outside the LLM's window |
| Relevance gate → abstention | Corpus does not contain the answer at all |
| Mandatory structured citations | Unfalsifiable claims |
| Citation existence check | Fabricated chunk / clause references |
| Entailment verification | Retrieval correct but generation embellished |

---

### Phase 3 — Detailed design
**Entry:** architecture baselined.
**Activities:** design the clause-detection algorithm; define the chunk schema and metadata contract; design the RRF fusion; specify the abstention policy and its two thresholds; design the verification chain; define the LangGraph state schema and conditional edges; design the evaluation datasets and metric definitions.
**Artifacts:** module docstrings, `EVALUATION_PLAN.md`, `eval/datasets/SCHEMA.md`.
**Exit:** metric definitions and thresholds are written down **before** any measurement, so they cannot be retrofitted to flatter the result.

---

### Phase 4 — Test & evaluation infrastructure (before implementation)
**Entry:** metric definitions frozen.
**Activities:** build the golden set (answerable, gold clause IDs, hand-verified); build the adversarial set (unanswerable — out-of-corpus, false premise, invented entity, wrong Release, non-spec); build the metric implementations, the judge protocol, and the run harness.
**Artifacts:** `eval/datasets/golden_set.json`, `eval/datasets/adversarial_set.json`, `eval/metrics.py`, `eval/run_eval.py`.
**Exit:** harness executes end-to-end and produces a results row against the naive baseline.

**This phase deliberately precedes Phase 5.** The adversarial set is the artifact that makes the hallucination claim meaningful — a system evaluated only on answerable questions cannot demonstrate that it abstains.

---

### Phase 5 — Implementation
**Entry:** harness operational; baseline measured and recorded.
**Activities:** implement components in the order dictated by the baseline failure taxonomy — highest-frequency failure mode first. One component per commit; one variable per evaluation run.
**Artifacts:** source modules, unit tests, `DECISION_LOG.md` and `ERROR_LOG.md` entries created as work proceeds.
**Exit:** all planned components implemented; every change has a corresponding logged run with a KEEP or REVERT verdict.

**Change discipline:** any change touching retrieval, prompting, or thresholds requires a new run ID in `OUTCOMES_LOG.md`. Reverted changes are logged with the reason, not deleted — a negative result is evidence.

---

### Phase 6 — Verification & validation

| Level | Method | Artifact |
|---|---|---|
| Unit | pytest — chunker boundaries, RRF ordering, threshold logic, citation validation | `tests/unit/` |
| Integration | pytest — ingestion pipeline end-to-end, API contract | `tests/integration/` |
| System | evaluation harness on golden set | `eval/results/RUN-*.json` |
| Safety | evaluation harness on adversarial set | abstention correctness |
| Judge validation | 20 judge decisions hand-labelled; agreement reported | `EVALUATION_PLAN.md` §4 |
| Non-functional | p50/p95 latency, tokens per query, cache hit rate | `OUTCOMES_LOG.md` |

**Validation vs verification, stated explicitly:** verification confirms the system was built as designed (tests pass). Validation confirms it solves the stated problem (benchmark metrics meet targets). Both are required; passing tests alone would not satisfy the assignment.

**Judge validation is itself part of V&V.** An LLM-based evaluator can hallucinate. Reporting judge–human agreement on a hand-labelled sample is what makes the headline metric credible rather than circular.

---

### Phase 7 — Tuning & operating-point selection
**Entry:** all components implemented and individually measured.
**Activities:** sweep the abstention threshold τ; plot ungrounded-claim rate against false-refusal rate; select and justify an operating point.
**Artifacts:** τ sweep table and curve in `OUTCOMES_LOG.md` RUN-006.
**Exit:** operating point chosen as an explicit product decision with a written rationale, not as a default value.

**Rationale recorded:** for a service-assurance assistant, an incorrect answer about alarm semantics during an outage costs a NOC engineer more than a refusal does. The system is therefore tuned to fail closed, accepting a measured false-refusal cost.

---

### Phase 8 — Packaging, documentation & release
**Entry:** operating point frozen; code freeze declared.
**Activities:** container build; clean-clone reproducibility check; README with ablation table, architecture diagram, honest limitations section, and reuse disclosure; demo recording that includes an abstention case.
**Artifacts:** `Dockerfile`, `docker-compose.yml`, `README.md`, demo recording.
**Exit:** fresh clone → `make up` → working system, verified on a clean environment.

---

### Phase 9 — Retrospective
**Entry:** submission complete.
**Activities:** review all four logs; identify what a longer schedule would have changed; list known defects and residual risks.
**Artifacts:** `docs/RETROSPECTIVE.md`, Limitations section of the README.
**Exit:** three concrete weaknesses documented with the evidence that revealed each.

---

## 4. Phase gates

No phase begins until the prior gate passes. Gates are recorded with a timestamp in `docs/GATE_LOG.md`.

| Gate | Criterion |
|---|---|
| G0 | Every requirement has an ID and a numeric or testable acceptance criterion |
| G1 | Corpus acquired; spec versions pinned and recorded |
| G2 | Chunk schema populated (`spec_id`, `version`, `clause_id`, `heading_path`); 10 sampled chunks manually inspected |
| G3 | Golden set ≥30 items and adversarial set ≥15 items, all hand-verified |
| G4 | Baseline metrics recorded **before** any optimisation |
| G5 | ≥5 logged runs, one variable changed per run |
| G6 | Ungrounded-claim rate, abstention correctness, and citation accuracy meet `EVALUATION_PLAN.md` targets |
| G7 | Clean clone reproduces the system |
| G8 | README, four logs, ablation table, and limitations section complete |

---

## 5. Configuration & change management

- **Version control:** git, one logical change per commit; commit messages reference the decision or run ID (`D-003`, `RUN-004`).
- **Datasets are versioned artifacts.** Golden and adversarial sets are committed and never regenerated between compared runs — regenerating them would invalidate every prior measurement.
- **Prompts are versioned.** `PROMPT_VERSION` is recorded with every run; a prompt change is a configuration change requiring a new run.
- **Index compatibility is enforced.** The embedding model name and dimension are stored in collection metadata and validated at query time, because a silent model swap produces vectors in a different space with no error raised (see `ERROR_LOG.md` E-000g).
- **Reproducibility:** temperature 0 everywhere including the judge; fixed seeds; each run records git commit, config hash, model identifiers, and τ.

---

## 6. Risk management

Maintained in `PROJECT_PLAN.md` §7. Top risks and their controls:

| Risk | Control |
|---|---|
| Groq token limit stalls evaluation | Response cache keyed by prompt hash; smoke subset for iteration; rate-limit-aware client reading `x-ratelimit-remaining-tokens` |
| Golden set built carelessly → meaningless metrics | Every item hand-verified; construction method disclosed |
| Clause regex over-matches figure and list numbering | Constrained pattern + monotonicity check + mandatory manual inspection at G2 |
| Scope creep | Documented cut list, executed in a fixed order |
| Overclaiming zero hallucination | Reformulated requirement (§8); limitations section mandatory before release |

---

## 7. Traceability

Full matrix in `docs/TRACEABILITY.md`. Every row links:

```
Requirement ID → Design decision (D-xxx) → Component/module → Test → Metric → Result (RUN-xxx)
```

A requirement with no test is an unverified claim. A component with no requirement is scope creep. Both are treated as defects in review.

---

## 8. Requirement reformulation: "near-zero hallucination"

Recorded here because it is the most consequential engineering judgement in the project.

**As stated:** *"minimal to near-zero hallucinations."*

**Problem:** not verifiable. For a generative model over open-ended input, zero hallucination is not provable, and "minimal" has no acceptance criterion.

**Reformulation.** The goal is restated from a property of the model to a property of the system:

> The system shall emit no claim that is not supported by a cited passage of the source corpus.

This is achievable, because unsupported claims can be **detected after generation and suppressed**, whereas model internals cannot be constrained directly. It decomposes into:

| ID | Requirement | Verification |
|---|---|---|
| FR-06 | Every claim carries a citation resolving to a real indexed chunk | Deterministic existence check; citation-accuracy metric |
| FR-07 | Where retrieved evidence is insufficient, the system abstains rather than answers | Abstention correctness on the adversarial set |
| FR-08 | Claims not entailed by their cited passage are suppressed before output | Entailment verification; ungrounded-claim rate |
| NFR-02 | Ungrounded-claim rate below target on a fixed, versioned benchmark | Evaluation harness |
| NFR-03 | Failure mode is closed (refusal), never open (guess) | Adversarial set; unsupported-answer rate |

**Accepted trade-off, stated up front:** driving unsupported output toward zero necessarily raises false refusals. This cost is measured, reported, and used to select the operating point rather than concealed.

**Claim made at delivery:** *not* "zero hallucination", but "**fail-closed and auditable**" — every claim is falsifiable against a named clause in seconds, and anything unverifiable becomes a refusal.

---

## 9. Ethics & disclosure

- **Code reuse is disclosed** in the README, naming which components were adapted from prior personal work and which were written for this assignment. Reusing one's own infrastructure is normal engineering practice; presenting it as new work is not.
- **Evaluation-set construction is disclosed:** candidate questions were LLM-drafted from real corpus chunks, then every item was manually verified and corrected. The method is stated so a reviewer can judge the metrics correctly.
- **Limitations are published by the author**, not left for the reviewer to discover.
- **Corpus provenance is recorded:** 3GPP specifications are publicly available; exact spec numbers and versions are cited in the README.

---

## 10. Deliverables index

| Artifact | Path | Phase |
|---|---|---|
| This document | `docs/SDLC.md` | 0 |
| Requirements | `docs/REQUIREMENTS.md` | 0 |
| Reuse audit | `docs/REUSE_AUDIT.md` | 1 |
| Project plan & risks | `docs/PROJECT_PLAN.md` | 0–1 |
| Architecture | `docs/ARCHITECTURE.md` | 2 |
| Traceability matrix | `docs/TRACEABILITY.md` | 2 |
| Decision log | `docs/DECISION_LOG.md` | all |
| Error log | `docs/ERROR_LOG.md` | 5 |
| Outcomes / ablation log | `docs/OUTCOMES_LOG.md` | 4–7 |
| Evaluation plan | `docs/EVALUATION_PLAN.md` | 3 |
| Gate log | `docs/GATE_LOG.md` | all |
| Retrospective | `docs/RETROSPECTIVE.md` | 9 |
| Interview preparation | `docs/INTERVIEW_PREP.md` | — |
