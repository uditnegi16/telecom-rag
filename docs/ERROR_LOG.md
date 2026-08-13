# ERROR_LOG.md

Every error that cost more than ~10 minutes, with its **root cause** — not just the fix.

**Why this file exists:** in the interview you will be asked "what broke and how did you debug it?" A log of real, specific failures with correct root-cause attribution is far more convincing than a story about how everything went smoothly. Nobody believes the smooth story.

**Rule:** the *Root cause* field must explain the mechanism, not restate the symptom.
Bad: "Chroma threw an error." Good: "The persisted collection was written by chromadb 0.4.x; 0.5 changed the on-disk schema and does not migrate silently."

**Template**
```
### E-0XX — <one-line symptom>
- **Date / phase:**
- **Symptom:** exact error text or observed behaviour
- **Root cause:** the actual mechanism
- **Fix:**
- **Time lost:**
- **Prevention:** what stops this recurring
- **Related:** D-0XX / RUN-0XX
```

---

## Pre-seeded: failures likely on this stack

Delete any that do not occur; fill in the rest when they bite. They are listed here so you recognise them fast rather than losing an hour each.

### E-000a — 3GPP `.doc` files unreadable by python-docx
- **Expected phase:** ingestion
- **Symptom:** `docx.opc.exceptions.PackageNotFoundError` on files downloaded from 3gpp.org
- **Root cause:** 3GPP ships legacy binary Word 97-2003 `.doc` (an OLE compound file), not OOXML `.docx`. python-docx only reads OOXML.
- **Fix:** use ETSI PDF versions (see D-002), or `libreoffice --headless --convert-to docx`.
- **Prevention:** decided up front in D-002.

### E-000b — Clause-detection regex over-matches
- **Expected phase:** chunking
- **Symptom:** thousands of tiny chunks; chunk titles like `3.2` that are actually figure references or list numbering inside prose
- **Root cause:** the pattern `^\d+(\.\d+)*` also matches numbered list items, table row labels, and figure/table captions, which appear at line-start in the extracted text stream.
- **Fix:** require the number to be followed by a tab/multiple spaces and a capitalised title, exclude lines starting with `Figure`/`Table`/`Annex`, and enforce monotonic clause ordering (a clause number must be a plausible successor or child of the previous one).
- **Prevention:** Gate G2 — eyeball 10 sampled chunks before building anything on top.

### E-000c — Answers cite the wrong Release
- **Expected phase:** evaluation
- **Symptom:** answer is technically correct for Rel-16 but wrong for the indexed Rel-18 text
- **Root cause:** either two Releases got indexed (retrieval contradiction), or the model answered from parametric memory rather than context — the latter means your grounding prompt is too weak.
- **Fix:** version freeze (D-001); make version part of the chunk breadcrumb; harden the prompt to forbid outside knowledge; verify via D-010.
- **Prevention:** include Release-mismatch questions in the adversarial set (D-012 family 4).

### E-000d — Reranker slow / OOM on CPU
- **Expected phase:** retrieval
- **Symptom:** 5–15s per query, or the process is killed
- **Root cause:** cross-encoders score every (query, doc) pair through a full forward pass; 30 pairs × long 3GPP chunks × CPU is expensive, and batching long sequences spikes RAM.
- **Fix:** truncate chunks to 512 tokens for reranking only; batch size 8; rerank top-15 instead of top-30; switch to `bge-reranker-base`.
- **Prevention:** measure p95 latency as soon as the reranker lands, not on Day 3.

### E-000e — Streamlit reloads models on every interaction
- **Expected phase:** UI
- **Symptom:** every click takes 30s; RAM climbs
- **Root cause:** Streamlit re-executes the whole script top-to-bottom on each widget interaction, so unguarded model loads run again each time.
- **Fix:** wrap loaders in `@st.cache_resource`.

### E-000f — Structured output parse failures
- **Expected phase:** generation
- **Symptom:** `json.JSONDecodeError`; model wraps JSON in ``` fences or adds a preamble
- **Root cause:** the model is following its helpfulness prior over the format instruction; smaller/local models do this far more often.
- **Fix:** use native structured-output / tool-calling mode where available; otherwise strip fences, extract the outermost `{...}`, and retry once with the parse error fed back. Never silently drop a failed parse — count it as a failure in the eval.
- **Prevention:** log the parse-failure *rate* as a metric; it is a real quality signal.

### E-000g — Index/embedding-model mismatch after a swap
- **Expected phase:** iteration
- **Symptom:** retrieval quality collapses to near-random after changing the embedding model
- **Root cause:** the persisted vectors were produced by the old model; dimensions may still match, so no error is raised — the vectors are simply in a different space.
- **Fix:** store `embedding_model` + `dim` in collection metadata and refuse to query on mismatch. Version the collection name (`chunks_bge_small_v1`).
- **Prevention:** build the guard into the indexer on day 1.

### E-000h — API rate limit / cost spike during eval loops
- **Expected phase:** evaluation
- **Symptom:** `429`, or a surprising bill
- **Root cause:** each full eval run is 85 questions × (generate + verify) ≈ 170 calls, and you will run it a dozen times.
- **Fix:** cache responses keyed by `hash(model + prompt + params)`; add exponential backoff; run a 15-question smoke subset during iteration and the full set only at gates.
- **Prevention:** build the cache before the first full run.

---

## Actual errors

### E-001 —
- **Date / phase:**
- **Symptom:**
- **Root cause:**
- **Fix:**
- **Time lost:**
- **Prevention:**
- **Related:**

---

## Actual errors — build log

### E-001 — Clause titles in camelCase were silently dropped
- **Date / phase:** 2026-08-13 / chunker development
- **Symptom:** `6.1 perceivedSeverity` and `6.2 alarmType` produced no chunks, while `6.3 Alarm clearing procedure` worked. No error raised — the clauses simply vanished from the index.
- **Root cause:** `_looks_like_title()` rejected any title starting with a lowercase letter, as a heuristic against prose that happens to follow a number ("5.2 is defined in TS 23.501…"). But 3GPP clause titles are frequently bare attribute names in camelCase. The heuristic was correct in general and catastrophically wrong for exactly the alarm and KPI attribute clauses this corpus is built around.
- **Fix:** Allow a lowercase initial when the title is ≤2 words and contains an internal uppercase or underscore — i.e. looks like an identifier rather than prose.
- **Time lost:** ~15 min
- **Prevention:** Unit tests now assert both directions: `perceivedSeverity`/`gNBId` accepted, prose fragments rejected.
- **Why this matters beyond the bug:** a silent drop is worse than a crash. The system would have abstained on every `perceivedSeverity` question and looked like a retrieval-quality problem rather than an ingestion bug. Gate G2 (eyeball 10 chunks) exists for this class of failure.
- **Related:** D-003

### E-002 — Short attribute clauses discarded by a length filter
- **Date / phase:** 2026-08-13 / chunker development
- **Symptom:** `6.2 alarmType` still missing after E-001 was fixed.
- **Root cause:** `MIN_CHUNK_CHARS = 80` was intended to skip parent-container headings whose only content is their child clauses. It also discarded genuinely short attribute definitions — the body was 77 characters.
- **Fix:** Replaced the length heuristic with a structural test: skip a heading only if the *next* heading is its direct child. Parent containers are now detected by hierarchy, not by size.
- **Time lost:** ~10 min
- **Prevention:** Rule of thumb adopted — never discard corpus content on a size threshold alone; discard on structure.
- **Related:** D-003

### E-003 — Every camelCase clause vanished after real PDF extraction
- **Date / phase:** 2026-08-13 / ingestion pipeline integration test
- **Symptom:** Clause `6.1 perceivedSeverity` was detected correctly in unit tests but disappeared when the same content went through the actual PDF path. Its text was silently absorbed into parent clause `6`. No error, no warning.
- **Root cause:** Two things had to line up. 3GPP source documents separate the clause number from the title with a **tab**, and the detection regex required a tab, 2+ spaces, or a single space followed by an **uppercase** letter. But PDF text extraction collapses tabs to a **single space**, and 3GPP attribute-name clause titles are camelCase, so they start **lowercase**. `"6.1 perceivedSeverity"` therefore matched none of the three separator forms. Unit tests passed because the fixtures used literal `\t`, which the real pipeline never produces.
- **Fix:** Added a fourth separator alternative, `\s(?=[a-z]+[A-Z])` — a single space before a camelCase token. Prose is still rejected, because `"5.2 is defined in TS 23.501"` has no uppercase following the lowercase run.
- **Time lost:** ~20 min
- **Prevention:** Regression tests now use **space-separated** fixtures matching real extractor output, not idealised tab-separated source. Test fixtures must mirror what the pipeline actually receives.
- **Why this one matters most:** it would have removed nearly every attribute-definition clause from TS 28.545/28.546/28.532 — precisely the alarm and KPI clauses this corpus exists to serve. The system would have abstained on most alarm-field questions and it would have looked like a retrieval-tuning problem, not an ingestion bug. This is the third silent-drop failure in a row (E-001, E-002, E-003), which is why gate G2 requires reading sampled chunks rather than trusting the counts.
- **Related:** D-003, E-001, E-002
