# PROJECT_PLAN.md
**Project:** 3GPP Spec Assistant — grounded RAG chatbot with measured near-zero hallucination
**For:** Mavenir GET (AI/LLM Engineer, MavAI OPS) — take-home assignment
**Deadline:** 17 Aug 2026 (submission). Plan written 13 Aug 2026.
**Owner:** Kanak

---

## 0. The lifecycle question (answer this in the interview)

You asked whether this is SDLC or AI lifecycle. The honest answer, and the one that will impress:

> **It is both, and the AI part cannot be run as a waterfall.**

- The **software wrapper** (ingestion service, FastAPI layer, UI, Docker packaging) follows a normal **SDLC**: requirements → design → implement → test → deploy.
- The **AI/RAG core** cannot follow SDLC, because "near-zero hallucination" is not a spec you implement — it is a *number you measure and then drive down*. That part follows the **LLMOps / eval-driven development loop** (the LLM-era descendant of CRISP-DM).

So the model for this project is a **hybrid: SDLC on the outside, an eval-driven spiral on the inside.**

```
                SDLC (outer shell)
  Requirements → Architecture → Build → Package → Deploy → Maintain
                                  │
                                  ▼
                  ┌──────── EVAL-DRIVEN INNER LOOP ────────┐
                  │  1. Build eval set + harness FIRST     │
                  │  2. Ship a deliberately dumb baseline  │
                  │  3. Measure (hallucination rate etc.)  │
                  │  4. Diagnose the dominant failure mode │
                  │  5. Change ONE thing                   │
                  │  6. Re-measure → keep or revert        │
                  └────────── repeat until frozen ─────────┘
```

**The single most important rule of this project:** the evaluation harness is built *before* the RAG is optimised. If you optimise first and evaluate later, you have no ablation story, and the ablation story is what you are actually being graded on.

### Interview one-liner
> "I treated it as eval-driven development. I built the golden set and the harness on day one, shipped a naive baseline, measured its hallucination rate, and then made one change at a time — structure-aware chunking, hybrid retrieval, reranking, an abstention gate, a groundedness verifier — logging the delta at each step. The final report is an ablation table, not a claim."

---

## 1. Problem statement & scope

**Build:** A chatbot that answers questions about 3GPP telecom specifications, where every factual claim is traceable to a specific clause of a specific spec, and where the system **refuses to answer** rather than guessing.

**In scope**
- Ingestion of a fixed, versioned corpus of 3GPP specs
- Hybrid retrieval + reranking over clause-level chunks
- Grounded generation with inline clause citations
- Post-generation verification + abstention
- Evaluation harness with an answerable set *and* an adversarial unanswerable set
- REST API + minimal UI + Docker packaging

**Out of scope (say this explicitly in your README — scoping is a senior signal)**
- Fine-tuning any model
- Full 3GPP corpus (thousands of documents)
- Multi-turn agentic tool use beyond retrieval
- Production auth, multi-tenancy, HA

---

## 2. Corpus selection — and why it matters for *this* employer

Do not grab random specs. Mavenir's MavAI OPS team does **agentic service assurance**: alarms, KPIs, fault management, root cause analysis. Pick a corpus that mirrors their day job. That alone is a differentiator.

**Recommended corpus (~10 documents):**

| Spec | Title | Why |
|---|---|---|
| TS 28.545 | Fault Supervision (FS) — concepts & requirements | **Alarms.** Directly matches the JD. |
| TS 28.546 | Fault Supervision — Stage 2/3 | Alarm data model, notifications |
| TS 28.552 | 5G performance measurements | **KPIs.** Directly matches the JD. |
| TS 28.554 | 5G end-to-end KPIs | Service assurance metrics |
| TS 28.532 | Management services (provisioning) | OSS/management plane |
| TS 28.533 | Architecture framework for management & orchestration | OSS architecture |
| TS 23.501 | System architecture for the 5G System | Canonical 5GC reference |
| TS 23.502 | Procedures for the 5G System | Call flows, procedures |
| TS 32.111-2 | Fault Management — Alarm IRP | Classic alarm semantics |
| TR 21.905 | Vocabulary for 3GPP specifications | Acronym/glossary queries |

**Freeze one Release** (e.g. Rel-18) and record exact version numbers. Mixing releases is a hallucination source in itself — the model will blend two versions of the same clause.

**Where to get them:** 3GPP publishes specs free at `3gpp.org/ftp/Specs/archive/` as `.zip` containing legacy `.doc`. ETSI mirrors the same specs as clean PDFs at `etsi.org/deliver/etsi_ts/`. **Prefer the ETSI PDFs** — parsing legacy `.doc` will cost you half a day you do not have. Log this as a decision (see `DECISION_LOG.md` D-002).

> Note: this sandbox's network cannot reach 3gpp.org or etsi.org. You must download the corpus on your own machine.

---

## 3. Target architecture

```
                    ┌─────────────────────────────────────────┐
 3GPP PDFs ────────▶│ INGESTION (offline, run once)           │
                    │  parse → clause-aware split → enrich    │
                    │  metadata → embed → index (dense+BM25)  │
                    └────────────────┬────────────────────────┘
                                     ▼
                            Vector store + BM25 index
                                     ▲
 User question ──▶ ┌─────────────────┴────────────────────────┐
                   │ ANSWER GRAPH (LangGraph)                 │
                   │                                          │
                   │  1. rewrite/expand query (acronyms)      │
                   │  2. hybrid retrieve (dense + BM25, RRF)  │
                   │  3. cross-encoder rerank → top-k         │
                   │  4. RELEVANCE GATE ──low?──▶ ABSTAIN     │
                   │  5. generate w/ mandatory citations      │
                   │  6. GROUNDEDNESS VERIFIER (claim⊑source) │
                   │  7. ungrounded? ──▶ retry once ─▶ ABSTAIN│
                   └──────────────────┬───────────────────────┘
                                      ▼
                   Answer + [TS 28.552 v18.5.0, cl. 5.1.1.2] + confidence
```

### Why each block exists (this is your design defence)

| Block | Hallucination it kills |
|---|---|
| Clause-aware chunking | Chunks that split a definition in half → model fills the gap |
| Metadata (spec, version, clause) | Model inventing clause numbers; version blending |
| Hybrid (BM25 + dense) | Dense misses exact identifiers like `TS 28.552`, `NRCellCU`, `gNB-DU` |
| Cross-encoder reranker | Right doc in top-50 but not in top-5 → model answers from a near-miss |
| **Relevance gate → abstain** | The biggest one. Corpus simply doesn't contain the answer |
| Mandatory citations | Makes every claim falsifiable by a human |
| **Groundedness verifier** | Model retrieved correctly but still embellished |
| Temperature 0 + structured output | Stylistic drift into invention |

### Agentic angle (free marks — the JD says LangGraph + agentic)
Implement the answer path as a **LangGraph state graph** with conditional edges, not a linear chain. The graph gives you: document grading, one query-rewrite retry, a verification node, and an abstain terminal state. That is textbook **Corrective RAG (CRAG)** and it maps 1:1 onto their "Agentic Service Assurance Platform" wording.

---

## 4. Recommended stack

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.11 | Mandatory per JD |
| Orchestration | **LangGraph** | Named in JD; gives real agentic control flow |
| Parsing | PyMuPDF (`fitz`) | Fast, keeps layout hints |
| Chunking | Custom clause-aware splitter + recursive sub-split | The core IP of this project |
| Embeddings | `BAAI/bge-m3` or `bge-small-en-v1.5` (local) | Free, strong, no rate limits |
| Vector store | **Qdrant** (docker) — fallback ChromaDB | Qdrant supports native hybrid; better story |
| Lexical | BM25 (`rank_bm25`) or Qdrant sparse vectors | Exact-identifier recall |
| Fusion | Reciprocal Rank Fusion | Simple, no tuning, defensible |
| Reranker | `BAAI/bge-reranker-v2-m3` | Biggest single retrieval quality jump |
| LLM | **OPEN — see D-011** | See open questions below |
| Verifier | LLM-as-judge (cheap model) or NLI cross-encoder | Cheap model is fine; log the choice |
| API | FastAPI + Pydantic | Named in JD |
| UI | Streamlit | 45 minutes vs 6 hours for React |
| Eval | Custom harness + RAGAS for cross-check | Custom = you can explain every number |
| Packaging | Docker + docker-compose | Named in JD |
| Stretch | K8s manifests / Helm chart | JD names Kubernetes + OpenShift |

---

## 5. Four-day schedule (13–17 Aug)

You have **~4 working days**. This is tight but very doable *if you do not gold-plate*. Timebox ruthlessly.

### Day 0 — Wed 13 Aug (evening, 3h)
- [ ] Repo scaffold, `.gitignore`, `pyproject.toml`/`requirements.txt`, `docs/` (these files)
- [ ] Download corpus (10 PDFs), record exact versions in `DECISION_LOG.md` D-001
- [ ] Confirm LLM provider + hardware → close D-011
- [ ] `git init`, first commit
- **Gate:** corpus on disk, versions logged, stack decided

### Day 1 — Thu 14 Aug
- **Morning:** ingestion pipeline — parse → clause-aware chunk → metadata → embed → index. Print chunk-count and a sample of 10 chunks and *eyeball them*. Bad chunks now = bad everything later.
- **Afternoon:** **evaluation harness + golden set.** 60 answerable Q/A with ground-truth clause IDs + 25 adversarial unanswerable questions. Generate drafts with an LLM from real chunks, then **hand-verify every single one**. Budget 2.5h; it is the highest-leverage work in the project.
- **Evening:** naive baseline (dense-only, top-5, plain prompt, no gate). Run eval. **Record the ugly numbers in `OUTCOMES_LOG.md`.** Do not be tempted to fix anything yet.
- **Gate:** baseline hallucination rate exists as a number

### Day 2 — Fri 15 Aug
- Iterate, **one change per run**, logging each in `OUTCOMES_LOG.md`:
  1. clause-aware chunking (vs naive fixed-size)
  2. + BM25 hybrid + RRF
  3. + cross-encoder reranker
  4. + relevance-score abstention gate (sweep the threshold!)
  5. + citation-enforcing prompt & structured output
  6. + groundedness verifier node
- Wire the whole path as a LangGraph graph with the retry edge.
- **Gate:** hallucination rate on the answerable set < 5%; abstention correctness on the adversarial set > 90%

### Day 3 — Sat 16 Aug
- **Morning:** threshold tuning — plot hallucination rate vs false-refusal rate. Choose an operating point *deliberately* and justify it.
- **Midday:** FastAPI endpoints (`/chat`, `/health`, `/eval/report`), Streamlit UI showing answer + citations + retrieved chunks + confidence.
- **Afternoon:** Dockerfile + docker-compose. Test cold start from clean clone.
- **Evening:** write `README.md`, finalise ablation table, architecture diagram.
- **Gate:** `docker compose up` works from a fresh clone

### Day 4 — Sun 17 Aug (morning only)
- [ ] Freeze code. No new features.
- [ ] 3–5 min screen-recorded demo (show a good answer, a cited answer, and **an abstention** — the abstention is the money shot)
- [ ] Final read-through of all four logs
- [ ] Submit before evening

### Cut list (drop in this order if time runs short)
1. K8s manifests → 2. RAGAS cross-check → 3. Streamlit polish → 4. Query rewrite node → 5. Reranker (keep hybrid).
**Never cut:** the eval harness, the abstention gate, the logs.

---

## 6. Phase gates / definition of done

| Gate | Criterion | Status |
|---|---|---|
| G1 Corpus | 10 specs, versions pinned & logged | ☐ |
| G2 Ingestion | Chunks carry `spec_id, version, clause_id, heading_path`; 10 sampled chunks manually verified | ☐ |
| G3 Eval | ≥60 answerable + ≥25 unanswerable Q, all hand-checked | ☐ |
| G4 Baseline | Baseline numbers recorded before any optimisation | ☐ |
| G5 Ablation | ≥5 logged experiments with one variable changed each | ☐ |
| G6 Target | Hallucination <5% answerable, abstention >90% adversarial, citation accuracy >90% | ☐ |
| G7 Reproducible | Fresh clone → `docker compose up` → working demo | ☐ |
| G8 Documented | README + 4 logs + ablation table + honest limitations section | ☐ |

---

## 7. Risks

| # | Risk | Likelihood | Mitigation |
|---|---|---|---|
| R1 | Legacy `.doc` parsing eats a day | High | Use ETSI PDFs; timebox parsing to 3h |
| R2 | Golden set built lazily → meaningless metrics | High | Hand-verify every item; document the method honestly |
| R3 | Reranker too slow on CPU | Med | Rerank only top-30; cache; drop to hybrid-only if >3s |
| R4 | API rate limits / cost mid-eval | Med | Local embeddings; cache LLM responses by prompt hash |
| R5 | Scope creep (agents, fine-tuning, fancy UI) | **High** | Follow the cut list. Depth beats breadth. |
| R6 | Overclaiming "0% hallucination" in the writeup | Med | Section 8 below. Be precise, not impressive. |
| R7 | Corpus tables/figures extract as garbage | Med | Detect and tag table chunks; note as known limitation |

---

## 8. On "zero hallucination" — your honest position

You are right to be suspicious. **You cannot prove zero hallucination for arbitrary input on a generative model.** Do not claim it. Claim this instead, and you will sound like an engineer rather than a candidate:

1. **Reframe the target.** The goal is not "the model never invents"; it is **"the system emits no unsupported claim."** Different problem, and this one is achievable, because you can *verify and suppress* after generation.
2. **Fail closed, not open.** Every path that lacks evidence terminates in abstention, not in a guess. Abstention is a correct answer.
3. **Make it measurable.** "Near-zero" is meaningless without a number and a test set. Report: *hallucination rate = X% on N=60 answerable questions; unsupported-answer rate = Y% on N=25 adversarial questions.*
4. **State the trade-off.** Driving hallucination to 0 raises false refusals. Show the curve. Name your operating point and why.
5. **State the residual risk.** Retrieval-correct-but-verifier-fooled cases; ambiguous clause language; table extraction. List them in the README's Limitations section.

**Interview line:**
> "I got measured hallucination to ~0 on my benchmark, but I would not claim zero in general — I'd claim the system is *fail-closed and auditable*. Every claim carries a clause citation, so a human can falsify any answer in ten seconds, and anything unsupported becomes a refusal instead of a guess. That's the property an operator actually needs in a service-assurance workflow."

---

## 9. Log discipline

Four living documents. Update them **as you work**, not at the end — the timestamps are part of the evidence.

| File | Rule |
|---|---|
| `DECISION_LOG.md` | Every non-obvious choice, *with the alternative you rejected* |
| `ERROR_LOG.md` | Every error that cost >10 minutes, with root cause |
| `OUTCOMES_LOG.md` | Every eval run: what changed, what moved, keep/revert |
| `EVALUATION_PLAN.md` | Metric definitions, dataset construction, thresholds |

Plus `INTERVIEW_PREP.md` for the questions coming after.

**Do not backfill these on the 17th.** Backfilled logs read as backfilled, and a Group Team Lead has seen a hundred of them.

---

## 10. Open questions blocking Day 0

- **D-011 LLM provider:** OpenAI/Azure key? Anthropic key? Or fully local (Ollama + Llama-3.1-8B)? Changes prompt strategy, verifier design, and cost handling.
- **Hardware:** GPU available, or CPU-only? Decides reranker feasibility and embedding model size.
- **Submission format:** GitHub repo link, or zip? (If unclear, ask Kanak — asking a precise clarifying question is itself a positive signal.)
