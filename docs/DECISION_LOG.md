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

### D-027 — Generation moved to `llama-3.1-8b-instant`
- **Status:** DECIDED · 2026-08-14
- **Context:** `llama-3.3-70b-versatile` returned 429 during UI testing. Live response headers showed the real limits: **1000 requests per DAY** on the 70B model versus **14400** on `8b-instant`. The binding constraint for a public demo is the daily request cap, not the token rate — at 3 calls per turn, 1000/day is roughly 330 questions across *all* visitors, and development had already consumed most of it before the link could be shared.
- **Decision:** Use `8b-instant` for generation as well as verification.
- **Rationale:** 14× the daily headroom. The quality cost is real but bounded, because the pipeline is explicitly designed not to depend on the generator being careful — citations are validated deterministically, every claim is checked by entailment against its cited clause, and unparseable output fails closed. **A weaker generator degrades coverage, not correctness.** That property was built for other reasons and turns out to make this swap safe.
- **Rejected alternatives:** Keep 70B and accept the demo dying mid-evaluation — unacceptable for a shared link. Pay for a higher tier — not available. Route generation to 70B and fall back to 8B on 429 — better, and the right answer with more time, but it makes measured results non-reproducible because the same question can be answered by different models.
- **Consequences:** Expect more JSON parse failures and weaker instruction-following from the smaller model. Both are measurable: parse-failure rate is already an eval metric. **Re-measure before quoting numbers** — the RUN-001 baseline was recorded on 70B and is not comparable.
- **Evidence:** measured from `x-ratelimit-*` headers, 2026-08-14.

### D-028 — SQLite for conversation persistence, not Postgres
- **Status:** DECIDED · 2026-08-14
- **Context:** Conversations lived in a Python dict and were lost on restart; the frontend held `session_id` only in React state, so a page refresh silently started a new conversation. For a system presented as production-shaped, that reads as a prototype.
- **Decision:** SQLite in the mounted `data/` volume, plus `session_id` in `localStorage` and a conversation list in the sidebar.
- **Rationale:** The deployment is one API container on one host. Postgres would add a service to run, back up and monitor in exchange for multi-replica state sharing this deployment cannot use. The schema avoids SQLite-specific types, so moving to Postgres is a driver change if a second replica is ever needed.
- **Rejected alternatives:** Postgres/Supabase — correct at multi-replica scale, unjustifiable infrastructure here. Redis — fast, but conversations are durable records, not cache. Keep in-memory — the behaviour being fixed.
- **What is stored, and what is not:** turns, citations, confidence and abstention reasons are stored, because being able to show *why* an answer was refused days later is the point of the system. Retrieved chunk **bodies** are not — they are reproducible from the index by `chunk_id`, and duplicating spec text per turn would grow the database without adding information.
- **Ownership:** conversation reads and deletes check the visitor cookie, so an id pasted into a URL cannot open someone else's history. This is fair-use scoping, not authentication.

### D-029 — Commit the built index to the repository
- **Status:** DECIDED · 2026-08-14
- **Context:** The deployed container needs a populated index to answer anything. Two options: ship the source PDFs and rebuild on the server, or commit the built artefacts.
- **Decision:** Commit `chroma/`, `chunks.json` and `bm25.pkl` (~20 MB). Source PDFs stay out — they are large and redistributable from ETSI.
- **Rationale:** Rebuilding on deploy means shipping PDFs, running a multi-minute CPU embedding job at boot, and accepting that any failure there yields a live site that silently retrieves nothing. Committing derived data is normally poor practice; here it buys a deterministic deploy, and the alternative failure mode is a broken demo in front of a recruiter.
- **Consequences:** The index must be rebuilt and re-committed when the corpus or embedding model changes. `CFG.collection` is versioned and the store raises on model mismatch (E-000g), so a stale index fails loudly rather than silently.

### D-030 — Classify intent before retrieval; non-questions are free
- **Status:** DECIDED · 2026-08-14
- **Context:** E-021 — a greeting was rewritten into the previous question and answered with a real citation. Separately, greetings were consuming the visitor's 8-question quota.
- **Decision:** A rule-based classifier runs before retrieval and routes GREETING, META and UNCLEAR to direct responses: no retrieval, no LLM call, no quota consumed. Only SPEC_QUESTION and FOLLOW_UP enter the pipeline.
- **Rationale:** Adapted from TravelMaster, where only `NEW_TRIP`/`MODIFY_TRIP` are billable turns. Rule-based rather than LLM-based because greetings are a small closed set of phrasings, and spending an LLM call to recognise "hi" would add latency and consume the very budget the classifier exists to protect.
- **Rejected alternatives:** LLM classifier — more robust on unusual phrasings, but adds a call to every turn including the ones it is meant to make free. Handle it in the prompt — too late; by then the rewriter has already fabricated the question. No classification — the status quo that produced E-021.
- **Consequences:** Rules will miss unusual greetings. The failure mode is safe: an unrecognised greeting is treated as a question and abstained on, rather than silently answered as something else. UNCLEAR deliberately asks the user to rephrase rather than guessing — inferring an unasked question is precisely the behaviour the system exists to prevent.

### D-031 — Delete superseded code rather than leave it importable
- **Status:** DECIDED · 2026-08-14
- **Context:** After the React frontend and SQLite conversation store shipped, their predecessors remained in the tree: `app/chat/session.py`, `ui/streamlit_app.py`, empty `app/cache/` and `app/monitoring/` packages, and a root `Dockerfile` superseded by `Dockerfile.api` and `Dockerfile.frontend`.
- **Decision:** Delete all of them. Update every reference in `Makefile`, `docker-compose.yml` and `docs/TRACEABILITY.md`, and migrate the two tests that depended on the old session store onto the new one.
- **Rationale:** E-026 was caused precisely by this — `/upload` still imported the superseded in-memory session store while `/chat` had moved to SQLite, so uploads were tagged with one identifier and retrieval filtered on another. The dead path compiled, imported and ran; it simply operated on a parallel universe of ids. **Code that is importable is code that can be imported by mistake.**
- **Rejected alternatives:** Keep for reference — that is what version control is for. Mark deprecated with a warning — warnings are ignored, and the failure mode here was silent rather than noisy.
- **Consequences:** The Streamlit prototype is gone. It served its purpose during development and its removal is recorded in `REUSE_AUDIT.md` rather than left as a puzzle in the tree.


### D-032 — HTTPS via Caddy and sslip.io rather than a purchased domain
- **Status:** DECIDED · 2026-08-15
- **Context:** The demo was served over plain HTTP on an EC2 IP. Browsers label that "Not secure", which is the first thing a reviewer sees. It also broke two features: `crypto.randomUUID` is unavailable outside a secure context (E-032), and the Web Speech API refuses microphone access.
- **Decision:** Caddy on the instance, terminating TLS for `15-206-59-248.sslip.io`. sslip.io resolves any dash-separated IP hostname to that IP, so no domain purchase was needed. Certificates are issued and renewed automatically by Let's Encrypt.
- **Rationale:** Fifteen minutes and zero cost, against an Application Load Balancer at roughly ₹1,400/month or the delay of registering and configuring a domain. The security-context features started working as a direct consequence.
- **Rejected alternatives:** ALB + ACM — costs more than the instance it fronts. Self-signed certificate — a browser warning is worse than no padlock. Buy a domain — better, and the right long-term answer, but not on a submission deadline.
- **Consequences:** The hostname is unmemorable and depends on a third-party DNS service. Because the hostname *embeds the IP*, an Elastic IP became mandatory — a changed address would invalidate the certificate. The web container was rebound to `127.0.0.1:8080` so nothing can bypass Caddy.

### D-033 — Onboarding: an overview modal, then a spotlight tour
- **Status:** DECIDED · 2026-08-15
- **Context:** A first-time visitor sees a chat box and must infer that the paperclip indexes their own specifications, that refusals are deliberate rather than broken, and that the evidence panel is the point of the interface. Those are exactly the things most likely to be misread as faults.
- **Decision:** Two sequential layers. A modal explains *what* the system does (verified claims, deliberate refusals, upload, visible query rewriting); a spotlight tour then shows *where* those controls are, highlighting real elements.
- **Rationale:** The two answer different questions and compete for attention if shown together. Separating them keeps each short.
- **Implementation notes worth keeping:** targets are located by `data-tour` attribute and measured with `getBoundingClientRect` at runtime, so the tour cannot drift out of sync with the layout. Targets that measure zero — the sidebar below the `lg` breakpoint — are **skipped**, not pointed at, so a phone does not get tooltips anchored to nothing. Both layers record dismissal in `localStorage`, and the sidebar carries a "Show me around again" control, because a one-time tour becomes unfindable the moment it is dismissed by accident.
