# TODAY.md — the one-day build order

Work top to bottom. Each step names its gate. Do not skip the gates: both bugs
already in `ERROR_LOG.md` were silent failures that only surfaced by looking.

## Before anything (30 min)
- [ ] Unzip into your projects folder, `git init`, first commit
- [ ] `cp .env.example .env`, add `GROQ_API_KEY`
- [ ] `make install`
- [ ] Copy these files across from your `production-rag` repo — they are reused
      as-is and there is no reason to rewrite them:
      - `app/ingestion/embedder.py`  (retarget model to `bge-small-en-v1.5`)
      - `app/ingestion/vector_store.py` (add `embedding_model` + `dim` to
        collection metadata — see E-000g)
      - `app/retrieval/reranker.py` (**remove the internal threshold filter** —
        it must return everything scored and sorted; the gate decides. DEF-04)
      - `app/api/main.py`, `app/api/routes.py`
      - `app/monitoring/logger.py`, `app/cache/query_cache.py`
      - `.github/workflows/ci.yml`
- [ ] Download 10 spec PDFs → `data/raw/` (see `scripts/CORPUS.md`) — **G1**
- [ ] Fill `docs/CORPUS_MANIFEST.md` with exact versions

## Step 1 — chunking (45 min) — **G2**
- [ ] `make inspect` — read the 10 sampled chunks properly
- [ ] Fix any clause-detection misses you see; log them in `ERROR_LOG.md`
- [ ] `make ingest`

## Step 2 — baseline BEFORE optimising (30 min) — **G4**
- [ ] Run the eval with dense-only + old chunker → **RUN-001**
- [ ] Record the ugly numbers in `OUTCOMES_LOG.md`. Do not fix anything yet.
- [ ] Hand-categorise ~10 failures into the taxonomy table. This tells you what
      to build first, and it is the strongest interview material in the project.

## Step 3 — evaluation datasets (2–3 h) — **G3**
**The bottleneck, and the most important work. Do not compress it.**
- [ ] `make golden` → drafts
- [ ] Hand-verify every item against `_source_body`. ~2 min each.
- [ ] Adversarial set is already written (25 items) — read it, adjust any that
      do not fit your actual corpus (e.g. if you indexed TS 38.331, ADV-005
      is no longer unanswerable and must be replaced)
- [ ] Build `smoke_set.json`: 10 answerable + 5 adversarial

**If time runs short:** 30 answerable is an honest minimum. Say "N=30" in the
README. Never inflate the count with unverified items — that is the one thing
that would genuinely damage you in the interview.

## Step 4 — the ablation (2–3 h) — **G5**
One change, one run, one logged verdict. Use `make smoke` between gates.
- [ ] RUN-002 clause chunker
- [ ] RUN-003 + BM25 hybrid — **segment the gain by `question_type`**
- [ ] RUN-004 + reranker
- [ ] RUN-005 + per-claim citation prompt
- [ ] RUN-006 + abstention gate, `make sweep` for τ — **G6**
- [ ] RUN-007 + entailment verifier

## Step 5 — finish (1–2 h) — **G7, G8**
- [ ] Wire `build_answer_fn` in `app/graph/answer_graph.py` to your real
      retrieve/llm; promote to a LangGraph `StateGraph` if time allows
- [ ] Streamlit UI: answer, citations, **retrieved chunk text**, confidence
- [ ] Fill the README results and ablation tables
- [ ] `make up` from a clean clone
- [ ] Record a 3–5 min demo. **Show an abstention** — it is the most impressive
      thing in the submission and almost no candidate demos one.
- [ ] `docs/RETROSPECTIVE.md`, `docs/GATE_LOG.md`

## Cut list, in order
1. LangGraph promotion (keep the plain function — same logic)
2. K8s manifests
3. Query-rewrite retry edge
4. Streamlit polish
5. Reranker (keep hybrid)

**Never cut:** the adversarial set, the abstention gate, the baseline run, the logs.
