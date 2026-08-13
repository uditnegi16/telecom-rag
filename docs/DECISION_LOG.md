# DECISION_LOG.md

Every non-trivial choice in this project, with the alternatives that were rejected and why.

**How to use this file**
- Add an entry *before or while* you decide — never afterwards from memory.
- The **Rejected alternatives** field is the important one. A decision with no rejected alternative was not a decision.
- Status: `OPEN` → `DECIDED` → (`SUPERSEDED by D-0xx` if you change your mind; never delete an entry).
- If an eval run causes a reversal, link to the `OUTCOMES_LOG.md` run ID.

**Template**
```
### D-0XX — <short title>
- **Status:** OPEN | DECIDED | SUPERSEDED by D-0XX
- **Date:**
- **Context:** what forced a choice
- **Decision:** what you chose
- **Rationale:** why
- **Rejected alternatives:** X — because…; Y — because…
- **Consequences / cost:** what this makes harder later
- **Evidence:** OUTCOMES run ID, if measured
```

---

### D-001 — Corpus scope and version freeze
- **Status:** OPEN
- **Date:** 2026-08-13
- **Context:** 3GPP publishes thousands of specs across many Releases. Full ingestion is infeasible in 4 days, and mixing Releases makes two contradictory versions of the same clause retrievable at once — a hallucination source in itself.
- **Proposed decision:** Freeze a single Release (Rel-18). Ingest ~10 specs weighted toward fault management, KPIs and OAM: TS 28.545, 28.546, 28.552, 28.554, 28.532, 28.533, TS 23.501, 23.502, TS 32.111-2, TR 21.905.
- **Rationale:** (a) A narrow, deep corpus produces better retrieval than a broad shallow one at this scale. (b) The alarm/KPI/OAM weighting mirrors Mavenir's service-assurance domain rather than generic 5G trivia. (c) Version freeze eliminates a whole class of contradiction.
- **Rejected alternatives:** Full archive ingest — infeasible and would tank precision. Only TS 23.501 — too narrow to look like a real system. Multi-Release — introduces contradictory retrievals.
- **Consequences:** Out-of-Release questions must be handled by abstention, not by guessing. Record exact version strings (e.g. `TS 28.552 V18.5.0`) in the README.
- **Evidence:** —

---

### D-002 — Source file format and parser
- **Status:** OPEN
- **Date:** 2026-08-13
- **Context:** 3GPP ships specs as `.zip` containing legacy binary `.doc`. `python-docx` cannot read `.doc`; LibreOffice headless conversion is possible but slow and lossy on 3GPP's heavy table/figure usage. ETSI republishes the identical specs as PDFs.
- **Proposed decision:** Use ETSI PDFs, parsed with PyMuPDF.
- **Rationale:** Removes a whole conversion step from a 4-day budget. PDFs preserve clause numbering in the text stream, which the chunker depends on.
- **Rejected alternatives:** `.doc` → LibreOffice → `.docx` → python-docx — a day of work for equal or worse output. `unstructured` library — heavy install, unpredictable on 3GPP layouts. OCR — unnecessary, these PDFs have a text layer.
- **Consequences:** Multi-column and table content still needs handling; large tables will likely extract imperfectly → tag as `content_type: table` and list as a known limitation.
- **Evidence:** —

---

### D-003 — Chunking strategy (the core design choice)
- **Status:** OPEN
- **Date:** 2026-08-13
- **Context:** Fixed-size chunking splits 3GPP definitions and procedure steps mid-thought. When a chunk is truncated, the model completes the missing half from its parametric memory — this is the #1 mechanical cause of hallucination in spec RAG.
- **Proposed decision:** Clause-aware chunking. Detect the numbered clause hierarchy (`5`, `5.2`, `5.2.3`, `5.2.3.1`) with a regex over the text stream; make each leaf clause one chunk; sub-split oversized clauses (>800 tokens) recursively with 15% overlap, keeping the parent clause ID. Prepend a breadcrumb header to every chunk text: `TS 28.552 v18.5.0 › 5 Performance measurements › 5.1 NF measurements › 5.1.1.2 <title>`.
- **Rationale:** (a) Chunks become semantically complete units. (b) The breadcrumb is embedded, so retrieval benefits from hierarchical context. (c) Precise clause IDs make citations verifiable and enable citation-accuracy scoring against the golden set.
- **Rejected alternatives:** Fixed 512-token chunks — will be the *baseline*, kept deliberately so the ablation shows the delta. Semantic/embedding-based chunking — slower, non-deterministic, and it discards the free structure 3GPP already gives you. Whole-document chunks — destroys retrieval precision.
- **Consequences:** Regex is brittle against figure captions and annexes; needs manual eyeballing of ~10 sampled chunks (Gate G2).
- **Evidence:** —

---

### D-004 — Embedding model
- **Status:** OPEN
- **Date:** 2026-08-13
- **Proposed decision:** `BAAI/bge-small-en-v1.5` locally (upgrade to `bge-m3` if GPU available).
- **Rationale:** Free, no rate limits, no cost ceiling during repeated eval runs, runs on CPU, strong on technical English.
- **Rejected alternatives:** OpenAI `text-embedding-3-small` — better quality but adds cost and a network dependency to every eval run, and re-indexing during iteration would be slow. `all-MiniLM-L6-v2` — weaker on long technical text.
- **Consequences:** Re-indexing takes minutes, not seconds; embedding-model changes invalidate the index, so pin it early.
- **Evidence:** —

---

### D-005 — Vector store
- **Status:** OPEN
- **Proposed decision:** Qdrant via docker-compose. Fallback: ChromaDB if compose setup causes friction.
- **Rationale:** Native sparse+dense hybrid and payload filtering; a real service rather than an embedded library, which fits the containerised/cloud-native framing the JD asks for.
- **Rejected alternatives:** ChromaDB — simplest, but embedded and less impressive for a cloud-native role. FAISS — no metadata filtering out of the box. Elasticsearch — heavy for 4 days.
- **Consequences:** One more container to run; adds a failure mode on cold start.
- **Evidence:** —

---

### D-006 — Hybrid retrieval with Reciprocal Rank Fusion
- **Status:** OPEN
- **Proposed decision:** Run dense + BM25 in parallel, fuse with RRF (k=60), take top-30 into the reranker.
- **Rationale:** Dense retrieval is notoriously weak on exact identifiers — `TS 28.552`, `NRCellCU`, `gNB-DU`, `AMF`, `5QI` — which is exactly what telecom questions are made of. BM25 nails those. RRF needs no score normalisation and no tuning.
- **Rejected alternatives:** Dense only — the baseline; keep it for the ablation. Weighted score blending — requires normalising incomparable score scales and tuning a weight you cannot justify.
- **Consequences:** Two indices to keep in sync.
- **Evidence:** —

---

### D-007 — Cross-encoder reranking
- **Status:** OPEN
- **Proposed decision:** `BAAI/bge-reranker-v2-m3` over the fused top-30, pass top-5 to the LLM.
- **Rationale:** Usually the largest single jump in retrieval precision. Also produces a **calibrated relevance score**, which D-009's abstention gate depends on — this is the real reason it is in the design, not just quality.
- **Rejected alternatives:** No reranker — baseline. LLM-as-reranker — slower and more expensive per query.
- **Consequences:** CPU latency ~1–3s for 30 pairs. If p95 exceeds 3s, cut to top-15.
- **Evidence:** —

---

### D-008 — Orchestration: LangGraph state graph, not a linear chain
- **Status:** OPEN
- **Proposed decision:** Implement the answer path as a LangGraph graph: `rewrite → retrieve → grade → (retry|generate) → verify → (regenerate|abstain|answer)`, max 1 retry loop.
- **Rationale:** The design genuinely needs conditional branching and a bounded loop, which a linear chain cannot express. Also directly matches the JD (LangGraph, agentic, multi-agent) and the team's product framing ("Agentic Service Assurance Platform").
- **Rejected alternatives:** Plain LangChain LCEL chain — cannot express the retry edge cleanly. Hand-rolled control flow — fine engineering, but forfeits the framework signal the JD is explicitly asking for.
- **Consequences:** Extra dependency; graph state schema must be defined up front.
- **Evidence:** —

---

### D-009 — Abstention gate (the primary hallucination control)
- **Status:** OPEN
- **Proposed decision:** If the top reranker score < threshold τ, do not call the LLM at all. Return: *"I could not find this in the indexed 3GPP specifications."* Sweep τ empirically on the adversarial set and plot hallucination rate vs false-refusal rate.
- **Rationale:** The cheapest and most reliable hallucination control in the whole system — it removes the opportunity to hallucinate rather than trying to detect it afterwards. Fail closed.
- **Rejected alternatives:** Always answer with a confidence caveat — caveats do not stop invention, and users ignore them. LLM self-assessment of sufficiency — the model is a poor judge of its own ignorance.
- **Consequences:** Some answerable questions get refused. That trade-off must be quantified, not hidden.
- **Evidence:** —

---

### D-010 — Post-generation groundedness verification
- **Status:** OPEN
- **Proposed decision:** Generate structured output — a list of `{claim, citation_chunk_id}`. Then (a) check every `citation_chunk_id` exists in the retrieved set (cheap, deterministic, catches invented citations); (b) run an entailment check per claim against its cited chunk. Unsupported claims are dropped; if all claims fail, abstain.
- **Rationale:** Catches the residual case where retrieval was correct but the model embellished. Step (a) alone is nearly free and catches fabricated clause numbers, which is the most embarrassing failure mode for a spec assistant.
- **Rejected alternatives:** Trusting the prompt alone — measurable but insufficient. Full NLI model (`bge-reranker`/DeBERTa-NLI) — cheaper at inference but another model to wire; consider if LLM verifier cost becomes a problem.
- **Consequences:** Roughly doubles per-query LLM calls. Cache aggressively during eval.
- **Evidence:** —

---

### D-011 — LLM provider  ⚠️ **BLOCKING — decide before writing code**
- **Status:** OPEN
- **Context:** Generation and verification both need an LLM. Options differ in quality, cost, latency, and in the story they tell an on-prem-minded telecom vendor.
- **Options:**
  - **A. API model** (OpenAI / Azure OpenAI / Anthropic): best instruction-following and structured output, fastest to build. Costs money; rate limits during eval loops.
  - **B. Local** (Ollama + Llama-3.1-8B-Instruct / Qwen2.5-7B): free, unlimited eval runs, and a genuinely strong narrative for telecom operators who cannot send network data to a third-party API. Weaker at strict citation formatting; needs a GPU to be pleasant.
  - **C. Both** — API by default, local swappable via a provider abstraction.
- **Recommendation:** **C**, if you have API access. Build behind an `LLMProvider` interface, use the API model for quality, and demo the local path in the README. The sentence *"the whole stack can run air-gapped on-prem, which matters for operator data"* is worth real points with this employer.
- **Rejected alternatives:** Hard-coding a single provider — cheap now, but forfeits the on-prem story and makes the code look less considered.
- **Consequences:** ~1h to build the abstraction. Worth it.

---

### D-012 — Golden set construction method
- **Status:** OPEN
- **Proposed decision:** Sample chunks stratified across all 10 specs, have an LLM draft candidate Q/A pairs from each, then **manually verify and correct every single one**. Separately, hand-write ~25 adversarial questions in four families: (1) out-of-corpus topics, (2) false-premise questions, (3) invented entities (e.g. a non-existent NF `NSSAAF-X9`), (4) questions answerable only in a different Release.
- **Rationale:** LLM drafting gives volume; human verification gives validity. Documenting this method honestly is itself an evaluation-literacy signal.
- **Rejected alternatives:** Fully LLM-generated and unverified — the metrics would measure the generator, not the system; a reviewer will ask, and "I hand-checked all 60" is the only good answer. Fully hand-written — too slow for 4 days.
- **Consequences:** ~2.5h. Non-negotiable; it is the foundation every number rests on.
- **Evidence:** —

---

### D-013 — UI
- **Status:** OPEN
- **Proposed decision:** Streamlit. Must display: the answer, inline clause citations, an expander with the actual retrieved chunk text, the confidence/relevance score, and a visible abstention state.
- **Rationale:** The UI's job here is to *make the grounding visible*, not to look nice. Showing retrieved chunks next to the answer demonstrates the system is auditable.
- **Rejected alternatives:** React/Next.js — a day of work for zero additional marks on an AI role. CLI only — makes the demo video weak.
- **Consequences:** —

---

### D-014 — Packaging
- **Status:** OPEN
- **Proposed decision:** `docker-compose.yml` with app + Qdrant. Prebuilt index committed or rebuildable via `make ingest`. Stretch: K8s manifests.
- **Rationale:** JD names Docker, Kubernetes, OpenShift. A reviewer who can `docker compose up` and see it work will rate the submission far higher than one who fights a virtualenv.
- **Consequences:** Model weights make the image large; download at runtime into a mounted volume instead of baking them in.

---

### D-015 — <next decision>
- **Status:** OPEN

---

## Phase 1 addendum — fork & constraint decisions (13 Aug)

These supersede parts of D-004, D-005, D-007 and D-011 above, following the
reuse audit and the Groq free-tier constraint analysis.

### D-016 — Fork `production-rag` rather than build from scratch
- **Status:** DECIDED · 2026-08-13
- **Context:** ~1 day of build time. A prior personal project already provided Groq integration, CPU-pinned torch, a cross-encoder reranker, a confidence gate, response caching, FastAPI, Docker and CI.
- **Decision:** Fork it. Replace the graded components; keep the infrastructure. Component-level breakdown in `REUSE_AUDIT.md`.
- **Rationale:** Rebuilding working infrastructure would consume the entire schedule and leave nothing for the evaluation datasets and verification chain — the components actually being graded. Reuse converted ~3 days of infra work into configuration work.
- **Rejected alternatives:** From scratch — would guarantee an unfinished evaluation. Submit the old project retargeted — dishonest, and would not survive a code walkthrough.
- **Consequences:** Reuse must be disclosed in the README. Six defects inherited from the fork base, logged as DEF-01…DEF-06 in `TRACEABILITY.md`.

### D-017 — Reduce k and cap chunk size to fit the Groq token budget
- **Status:** DECIDED · 2026-08-13
- **Context:** Groq's free tier binds on ~6,000 **tokens** per minute, not requests. At 5 chunks × 800 tokens a query costs ~4,500 tokens → roughly one query per minute, so a full 85-question run with verification exceeds an hour of wall clock.
- **Decision:** `rerank_top_n = 3` (was 5); `max_chunk_tokens = 450`. Iterate on a 15-question smoke subset; full runs at phase gates only.
- **Rationale:** Turns a constraint into a defensible design choice — "lost in the middle" means more retrieved chunks is not better, and a strong reranker makes top-3 sufficient. Cuts per-query cost roughly 60%.
- **Rejected alternatives:** Keep k=5 and accept slow runs — would permit ~6 eval runs total, destroying the ablation. Pay for a higher tier — not available.
- **Consequences:** Recall now leans harder on the reranker. If Recall@3 lags Recall@10 badly in RUN-004, revisit.

### D-018 — Content-addressed response cache is mandatory, not optional
- **Status:** DECIDED · 2026-08-13
- **Decision:** On-disk cache keyed by `hash(model + prompt + params)`, plus a local token-bucket pacer and header-aware backoff (`app/llm/groq_client.py`).
- **Rationale:** Temperature is 0, so responses are deterministic and safely cacheable. Re-running an unchanged configuration then costs zero tokens — which is exactly what makes one-variable-at-a-time ablation affordable under this budget.
- **Consequences:** Cache must invalidate on prompt change; `prompt_version` is part of the config hash.

### D-019 — Two-tier model split
- **Status:** DECIDED · 2026-08-13
- **Decision:** `llama-3.3-70b-versatile` for generation, `llama-3.1-8b-instant` for entailment verification.
- **Rationale:** Verification is a narrow binary judgement over one claim and one passage — the small model is adequate, roughly 8× cheaper in tokens, and has a higher daily request allowance. Without this split, verification would roughly double the token cost of every run.
- **Rejected alternatives:** 70B for both — unaffordable per run. Local NLI cross-encoder — better long-term (see `RETROSPECTIVE.md`), but another model to wire on a one-day build.
- **Consequences:** Verifier quality must itself be validated; judge–human agreement on 20 hand-labelled items is reported.

### D-020 — Verification is a chain, cheapest stage first
- **Status:** DECIDED · 2026-08-13
- **Decision:** (1) deterministic citation-existence check → (2) lexical overlap pre-filter → (3) LLM entailment.
- **Rationale:** Stages 1 and 2 cost zero tokens and catch both the highest-embarrassment failure (fabricated clause numbers) and the most obvious ungroundedness. Only survivors reach the paid stage. Ordering by cost is what makes verification viable at 6,000 TPM.
- **Caveat recorded deliberately:** lexical overlap is used **only to reject**, never to accept. High overlap proves nothing on spec text — "shall" and "shall not" share ~95% of tokens (DEF-02).

### D-005 revised — ChromaDB, not Qdrant
- **Status:** SUPERSEDES D-005
- **Rationale:** BM25 is handled separately by `rank_bm25`, so Qdrant's native hybrid support — the main reason to prefer it — is no longer needed. Chroma already works in the fork base and adds no container to the compose stack. Simplicity wins on a one-day build.
- **Consequences:** Weaker "cloud-native" story than Qdrant. Accepted; Docker/K8s carries that instead.
