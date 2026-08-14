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

### E-004 — Clause detection collapsed on real ETSI PDFs (9 matches in 10,335 lines)
- **Date / phase:** 2026-08-13 / first ingest of real corpus
- **Symptom:** TS 28.532 (136 pages) produced only 167 chunks and TS 28.552 (383 pages) only 533, with mean chunk size (~460 tokens) sitting *above* the 450-token cap — meaning nearly every chunk was a fallback window-split fragment, not a detected clause. Diagnostics showed the heading regex matching **9 of 10,335 lines**.
- **Root cause:** `page.get_text("text")` emits every PDF text **span** on its own line. ETSI lays out a clause number and its title as separate spans at the same vertical position (tab-stop layout), so extraction produced:
  ```
  5.1.1.2
  RegistrationRequest counter
  ```
  No heading pattern can match a number with no title on its line. The single match found mid-document was a case where both happened to share one span. The table-of-contents dump made this unmistakable: entries read `'Scope ......'` and `'References ......'` with the clause numbers missing entirely.
- **Fix:** Rewrote the parser to use `get_text("dict")`, which carries a bbox per span, then group spans into **visual lines by y-coordinate** and order them by x, inserting a double space across wide x-gaps so tab stops become the separator the regex expects. Side benefit: table cells on one visual row now rejoin into one line instead of exploding into hundreds of one-word lines.
- **Time lost:** ~40 min, most of it in diagnosis
- **Prevention:** The lesson is about **diagnosing before fixing**. My first hypothesis was table-of-contents contamination poisoning the hierarchy anchor — plausible, and completely wrong. Dumping raw extracted lines took five minutes and pointed straight at the real cause. Guessing would have cost an hour and produced a fix for a problem that did not exist.
- **Wider point:** every synthetic test fixture had passed, because I generated those PDFs by writing whole heading lines in one call. The fixtures encoded my assumption about the input rather than the input's actual shape. Test data drawn from the real source is worth more than test data invented to match the code.
- **Related:** D-002, D-003, E-003

### E-005 — Duplicate chunk IDs crashed ChromaDB ingestion
- **Date / phase:** 2026-08-13 / first ingest
- **Symptom:** `chromadb.errors.DuplicateIDError: found 25 duplicated IDs: TS28552_Annex B_p11, TS28532_Annex C_p1, ...`
- **Root cause:** `chunk_id` was built as `{spec}_{clause_id}` plus a part suffix, on the assumption that a clause id occurs once per document. ETSI documents break that assumption: an annex heading appears both in its own section and again in the change-history annex. Each occurrence sub-split into `_p0`…`_p15`, so the part ids collided.
- **Fix:** Track occurrence counts per clause id during chunking and suffix repeats with `_occN`. Note the ingest crashed *after* 95 seconds of CPU embedding — the validation that would have caught it cheaply happens last.
- **Time lost:** ~10 min
- **Prevention:** Identifier uniqueness should be enforced where ids are minted, not discovered by the storage layer.
- **Related:** D-003, D-005

### E-006 — Hierarchy check rejected legitimate headings after a numbering gap
- **Date / phase:** 2026-08-13 / chunker hardening
- **Symptom:** After fixing E-004, clause `5.1` still vanished when the preceding accepted heading was `1 Scope`.
- **Root cause:** `_is_plausible_successor` required a sibling increment of at most 3, so a jump from `1` to `5.1` (gap 4) was rejected as implausible. Worse, once one heading was rejected the anchor never advanced, so **every subsequent heading was compared against the same stale anchor** and rejected too — one bad anchor silently collapsed the rest of the document.
- **Fix:** Two changes. Relaxed the gap limit to 20, since `_looks_like_title` is the primary filter for captions and prose and the hierarchy check is only a secondary guard. Added a consecutive-rejection counter that re-anchors after three rejections, so a single bad anchor can no longer poison the remainder of the document.
- **Time lost:** ~10 min
- **Prevention:** A filter that can enter an absorbing state needs a recovery path. Fail-safe defaults belong in ingestion as much as in generation.
- **Related:** D-003, E-004

### E-007 — Running headers embedded mid-clause after visual-line reconstruction
- **Date / phase:** 2026-08-13 / gate G2 chunk inspection
- **Symptom:** Sampled chunks contained `3GPP TS 28.532 version 18.7.0 Release 18  63  ETSI TS 128 532 V18.7.0 (2025-11)` in the middle of clause bodies.
- **Root cause:** A regression introduced by the E-004 fix. The noise filter used an anchored `^...Release \d+$` pattern, which worked when `get_text("text")` put the header on its own line. Visual-line reconstruction now joins the page header, page number and ETSI footer into a **single** line, so the anchored pattern no longer matched and every page's header survived into a chunk body.
- **Fix:** Switched to unanchored `search` patterns that strip the fragment wherever it occurs, then drop the line if only digits and punctuation remain.
- **Why it mattered:** the noise is embedded along with the clause text, degrading retrieval, and it is also handed to the entailment verifier as source material — the verifier would be judging claims partly against boilerplate.
- **Wider point:** fixing extraction changed the *shape* of the data downstream filters assumed. A fix in one stage can silently break a filter two stages later, and only reading actual output catches it.
- **Related:** E-004, D-002

### E-008 — Annex sub-clauses undetected, collapsing entire annexes
- **Date / phase:** 2026-08-13 / gate G2
- **Symptom:** A sampled chunk `TS28552_Annex A_p36_occ3` spanning pages 339-365 contained the text `A.64  Monitoring of RF performance` inside its body — a heading that should have started its own chunk.
- **Root cause:** `CLAUSE_RE` requires a leading digit. 3GPP annexes number their sub-clauses with a letter prefix (`A.64`, `B.2.1`, `C.1.1`), so no sub-clause inside any annex was ever detected. Each annex became one enormous blob, blind-split into 36+ fragments with no clause structure and a useless breadcrumb.
- **Fix:** Added `ANNEX_SUB_RE` for letter-prefixed clause numbers, reusing the same separator alternatives and title validation.
- **Impact:** TS 28.552's Annex A is a large informative section on measurement use cases. Recovering its structure adds genuinely retrievable, citable content that was previously unusable.
- **Related:** D-003, E-004

### E-009 — Token cap not enforced on text without sentence punctuation
- **Date / phase:** 2026-08-13 / gate G2
- **Symptom:** `tokens_max: 2331` against a configured cap of 450.
- **Root cause:** `_sub_split` splits on sentence boundaries (`(?<=[.;:])\s+`). Measurement tables and ASN.1 blocks contain no sentence punctuation, so there was nothing to split on and the "split" returned the original oversized text unchanged.
- **Fix:** Added a hard character-window split with overlap for any part still over the cap after sentence splitting.
- **Why this was the most serious of the three:** it is not a quality issue but a hard failure. At `rerank_top_n = 3`, three such chunks is roughly 7,000 tokens in one request — more than the entire 6,000 TPM Groq free-tier budget (NFR-01). Any query retrieving them would 429 and abort, and under the fail-closed design that surfaces as an abstention, so it would have looked like a *retrieval* problem while actually being a chunking problem.
- **Prevention:** `summarise()` reports `tokens_max`; treat any value above the cap as a gate-G2 failure, not a curiosity.
- **Related:** D-003, D-017, NFR-01

### E-010 — Control characters from PDF symbol fonts crashed generation, losing 27 drafts
- **Date / phase:** 2026-08-13 / golden-set drafting
- **Symptom:** `json_validate_failed` 400 from Groq at item 28 of 60. The failed generation contained `\x04\x05\x08\x07`. The run aborted and **all 27 completed drafts were lost**.
- **Root cause:** Three compounding faults.
  1. **Data:** PDF symbol fonts (Σ, Δ, subscripts) extract as raw control bytes. These sat in the chunks, went into the embeddings, and were echoed by the model into its JSON response, which the provider's validator then rejected.
  2. **Client:** `_send_with_backoff` retried the 400 five times. A 400 is deterministic — the same prompt fails identically every time — so this wasted ~30 s and buried the real cause behind a generic "failed after 5 attempts".
  3. **Script:** drafts were written only at the end, so one failure discarded everything before it.
- **Fix:** Strip control characters during parsing; raise a typed `LLMBadRequest` on 400 and never retry it; save drafts after every item and skip failures instead of aborting.
- **Time lost:** ~15 min plus 27 wasted drafts.
- **Wider point:** the retry policy was written for rate limits and silently applied to every error class. Backoff without classifying the error turns a fast, clear failure into a slow, opaque one.
- **Related:** D-018, NFR-01

### E-011 — Draft questions faithful to the source but useless as evaluation items
- **Date / phase:** 2026-08-13 / golden-set drafting
- **Symptom:** Drafts included "What is the status of the clause that cannot be deleted?", "What does this measurement provide?", "What is the format of tables 16.8.1?", "What is the purpose of Clause A.1.2 in TS 28.532 V18.7.0?"
- **Root cause:** Source chunks were sampled on length and `content_type` alone, so change-history annexes, mapping tables and stub clauses entered the pool. The drafting model then produced accurate questions about content that has no business in a benchmark. Separately, nothing in the prompt required questions to be self-contained, so "this measurement" phrasing passed through — a question that cannot be understood without already seeing the answer chunk measures nothing.
- **Fix:** Filter the source pool (exclude change-history and structural clauses, require sentence-bearing prose) and require self-contained phrasing in the drafting prompt.
- **Wider point:** this is why D-012 mandates hand-verification. The generator was not wrong; the *source selection* was. Bad inputs produce plausible outputs, which is the hardest failure mode to notice.
- **Related:** D-012
