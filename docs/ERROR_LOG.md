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

### E-014 — UI filename shadowed the application package
- **Date / phase:** 2026-08-14 / chat UI first launch
- **Symptom:** `ModuleNotFoundError: No module named 'app.chat'; 'app' is not a package`, raised from inside `ui/app.py` itself — the traceback showed the same file twice.
- **Root cause:** Streamlit places the running script's directory at the front of `sys.path`. With the UI at `ui/app.py`, the name `app` resolved to that script rather than to the `app/` package, so `import app.chat` looked for a `chat` submodule inside a plain module and failed. The error message is misleading: it reports the *symptom* (`app` is not a package) rather than the cause (the wrong `app` was found).
- **Fix:** Renamed to `ui/streamlit_app.py` and added an explicit `sys.path` guard inserting the project root ahead of the script directory, so the import order holds regardless of how the app is launched.
- **Time lost:** ~5 min
- **Prevention:** Never name an entry-point script after a top-level package in the same project. Applies equally to `main.py`, `test.py`, and any name matching a dependency.

### E-015 — τ hardcoded to a guess after documenting that it must be swept
- **Date / phase:** 2026-08-14 / demo testing
- **Symptom:** Nearly every question in the chat UI abstained.
- **Root cause:** `tau_abstain = 0.35` was invented, not measured — despite D-009 explicitly stating the threshold must be chosen empirically. The sweep, once run, showed the real separation point at **0.90**, and also showed that at 0.35 **all 47 answerable questions passed the gate**, so τ was not in fact causing the abstentions at all. A guessed parameter both was wrong and masked the real bug (E-016) by making the gate the obvious suspect.
- **Fix:** `scripts/sweep_tau.py`, τ set to 0.90 from measured data.
- **The sequencing error, which cost more than the bug:** the sweep is retrieval-only — embeddings, BM25 and the cross-encoder all run locally — so it costs **zero API tokens** and about two minutes of CPU. It was scheduled as RUN-006, *after* the generation runs that consumed the entire daily token budget. The cheapest and most decisive measurement in the project was sequenced last. Order experiments by information-per-cost, not by pipeline position.
- **Measured result:** answerable median 0.996 · adversarial median 0.029 · at τ=0.90, 46/47 answered, 2.1% false refusal, 96% correct abstention (J=0.939).
- **Related:** D-009, D-017

### E-016 — Correct citations rejected as fabricated because of square brackets
- **Date / phase:** 2026-08-14 / demo testing
- **Symptom:** `abstain reason: citation_invalid: fabricated citation(s): ['[TS28552_5.5.7.1.3]']` — with confidence 0.9996 and the gold clause retrieved at rank 1.
- **Root cause:** The prompt labelled each passage as `[TS28552_5.5.7.1.3] TS 28.552 …`. The model copied the id **including the brackets**, exactly as shown. `validate_citations` did an exact string comparison, so `[TS28552_5.5.7.1.3]` did not match `TS28552_5.5.7.1.3` and a perfectly correct citation was classified as fabricated. Under the fail-closed design that routes straight to abstention, so a correct, well-grounded answer was discarded.
- **Fix:** Two layers. Normalise citations (strip brackets, quotes, `SOURCE:` prefixes) before comparing, and relabel sources as `SOURCE_ID: <id>` so there is no decoration for the model to copy in the first place.
- **Impact:** this was the dominant cause of the 30/47 abstentions in RUN-001, not the relevance gate, not the prompt, and not retrieval — all of which were investigated first.
- **Wider point:** **a validator must not be stricter than the format its own prompt demonstrates.** The prompt showed one shape and the checker demanded another. Worth noting the failure was *safe* — it abstained rather than emitting a bad citation — but silently destroying correct answers is still a serious defect, and the fail-closed design made it look like a retrieval problem.
- **Related:** D-010, FR-06, DEF-01

### E-017 — A single chat turn hung for minutes with no output
- **Date / phase:** 2026-08-14 / React UI testing
- **Symptom:** The third turn of a conversation never returned. The uvicorn log showed no error and no new request completing; the UI spun indefinitely with no indication of why.
- **Root cause:** Three faults compounding.
  1. **Call amplification.** One turn had grown to **five sequential LLM calls** — query rewrite, generation, then one verification call *per claim*. A three-claim answer therefore cost five round trips.
  2. **Pacer sleeping silently.** Near the 12,000 TPM ceiling the token bucket sleeps up to 60 s per call, so five calls could stack into minutes. It logged with `print()`, which from a worker thread inside uvicorn does not reliably reach the console — so the wait produced *no output at all*.
  3. **No timeout anywhere.** Not in the Groq request, not in the pipeline, not in the frontend fetch. There was no path by which a slow turn could end in anything other than an indefinite spinner.
- **Fix:** Batch verification into a single call for all claims (5 calls → 3, accuracy unchanged since each claim is still judged only against its own cited passage); log pacer waits through the `logging` module; add a 30 s per-request timeout, a 75 s total pipeline budget, and an explicit timeout abstention with an honest message.
- **Design note:** the timeout path abstains rather than returning partial results. Emitting unverified claims to save time would violate the property the whole system exists to guarantee (NFR-03).
- **Wider point:** each feature added one more LLM call — the rewrite for multi-turn, the verifier for grounding — and nobody was counting. **Per-request call amplification needs a budget from the start**, in the same way token cost does.
- **Related:** D-018, D-019, D-024, NFR-01, E-013

### E-018 — Every first request after a restart timed out (cold model load)
- **Date / phase:** 2026-08-14 / React UI testing
- **Symptom:** First question after restarting the API took **102.3 s** and abstained with `timeout_before_generation` — while reporting confidence 1.000 and three correctly retrieved clauses. The message blamed rate limiting; no LLM call had been made.
- **Root cause:** `bge-small` and the cross-encoder load lazily on first use. On a cold process that is ~100 s of CPU, and it happened *inside* the request, so it consumed the 75 s pipeline budget before generation was reached. The timeout message then attributed the failure to the API provider — a misleading error for a cause that was entirely local.
- **Fix:** Warm the models in a FastAPI `lifespan` handler so loading happens at boot, where the container health check already allows for it (`start-period=45s`). `/health` now reports `ready` and `warmup_s` so the UI can distinguish "still warming" from "broken". The pipeline budget clock also restarts after retrieval, since it exists to bound LLM stalls, not local compute.
- **Why it mattered more than the delay:** on a deployed demo this is the **recruiter's first click**. A cold container would have shown a timeout blaming rate limits on a question the system answers perfectly.
- **Wider point:** lazy loading is invisible in development, where the process is already warm from a previous run. It only appears on a cold start, which is exactly the path a reviewer takes and the one least likely to be tested.
- **Related:** E-017, D-014, NFR-05

### E-019 — Demo model chosen on token rate, not daily request cap
- **Date / phase:** 2026-08-14 / UI testing
- **Symptom:** `429 Too Many Requests` on the second question of a session, after a fresh restart, with the token-per-minute budget nowhere near exhausted.
- **Root cause:** Model selection considered only TPM. The live headers show `llama-3.3-70b-versatile` has **12000 TPM but only 1000 requests per day**, while `llama-3.1-8b-instant` has **6000 TPM and 14400 per day**. The 70B model was chosen for quality on the basis of the *per-minute* figure; the *per-day* figure is what actually governs a shared public demo. At 3 calls per turn that is ~330 questions for every visitor combined, and a day of development consumes it before the link is ever shared.
- **Fix:** Generation moved to `8b-instant` (D-027).
- **Why the swap is safe, and why that is not luck:** the pipeline never trusts the generator. Citations are validated deterministically, claims are verified by entailment against the cited clause, and unparseable output fails closed. A weaker model produces more refusals, not more wrong answers. The property was built to contain hallucination and turns out to contain model downgrades too.
- **Wider point:** rate limits have more than one dimension. Reading only the one that matched the mental model (tokens, because chunk size dominated the design) meant the binding constraint went unnoticed until it fired in front of a working UI.
- **Related:** D-011, D-017, D-027, E-013

### E-020 — Small-model output quality, and an unresettable demo quota
- **Date / phase:** 2026-08-14 / after the D-027 model swap
- **Symptom (a):** `llama-3.1-8b-instant` answered "An integer value" where the 70B model had written a full sentence, and emitted a claim as `d) An integer value` — copying the 3GPP structural list marker verbatim. Correct, cited, and unreadable to anyone who has not seen the source clause.
- **Root cause (a):** The prompt asked for claims but never specified that they be self-contained sentences. The 70B model inferred it; the smaller model did not. Measurement clauses are laid out as `a) description  b) CC  d) An integer value`, so lifting the marker along with the content is a faithful reading of a badly-shaped instruction.
- **Fix (a):** Prompt now requires a complete sentence that restates the question, plus a regex marker strip at parse time — belt and braces, because a small model will not always comply.
- **Symptom (b):** After the swap, the input box locked at "0 of 8 questions remaining" after a single question.
- **Root cause (b):** Not a bug in the counter — the quota cookie had persisted across the whole day's testing, so the browser had genuinely used its 8. But the only way to reset was deleting a file on the server *and* clearing browser cookies, which is impossible mid-interview on a deployed box.
- **Fix (b):** `POST /api/v1/quota/reset`, and `GET /api/v1/quota` now reports the caller's own remaining count. Unauthenticated but deliberately narrow — it can only clear a counter — and disableable with `DEMO_ALLOW_RESET=false`.
- **Wider point:** a prompt tuned against a capable model encodes assumptions that only surface when the model is downgraded. Instructions that rely on the reader "knowing what is meant" are the first thing to break.
- **Related:** D-027, E-019

### E-021 — A greeting was answered as the previous question, with a real citation
- **Date / phase:** 2026-08-14 / voice input testing
- **Symptom:** The user said **"Hello, hello, hello."** The system replied *"The measurement is reported as an integer value"* with a verified claim and a valid clause citation — answering the question from two turns earlier.
- **Root cause:** `needs_rewrite()` treated any input of four words or fewer as a context-dependent follow-up. The rewriter dutifully resolved the "reference" into the previous question, and everything downstream then worked perfectly on a question the user never asked. Voice input made it common: dictation produces short, repeated utterances.
- **Fix:** Intent classification before anything else (`app/chat/intent.py`), following the pattern in TravelMaster's `chat_routes.py`. Greetings, meta questions and unclear input are answered directly with no retrieval, no LLM call and **no quota consumed**. `needs_rewrite` now requires a genuine dependency marker, not merely shortness.
- **Why this is the most serious defect found in the project:** every other control in the system verifies that the **answer** is supported by the sources. **None of them verify that the question was the one the user asked.** The citation was real, the claim was grounded, the confidence was 1.000 — and the entire response was to a fabricated question. A visitor typing "hi" would have received a confident, cited answer to something they never asked, and nothing in the pipeline would have flagged it.
- **Wider point:** grounding controls answer "is this claim supported?" They cannot answer "is this the right question?" Query transformation sits *upstream* of every safety mechanism, so a bug there is invisible to all of them. Any rewrite step needs its own guard — and it should fail toward asking the user rather than guessing.
- **Related:** D-024, D-030, FR-15

### E-022 — A helper function hijacked the /chat route
- **Date / phase:** 2026-08-14 / after adding the intent gate
- **Symptom:** `POST /api/v1/chat` returned 500 with `ResponseValidationError: Input should be a valid dictionary or object` — and the rejected input was the **corpus summary string**, not a chat response.
- **Root cause:** A patch inserted `_corpus_summary()` between `@router.post("/chat", response_model=ChatResponse)` and the `chat` function it was meant to decorate. Python applies a decorator to whatever function follows it, so the route was registered against `_corpus_summary`, which returns a string. FastAPI then tried to validate that string against `ChatResponse`.
- **Fix:** Moved the helper above the decorator. Added a test asserting that every route binds to its intended handler by name.
- **Why it was hard to read:** the traceback pointed at `serialize_response` and named `_corpus_summary` only as the *source of the input*, not as the handler. The error looked like a response-model mismatch rather than a routing bug.
- **Wider point:** this class of error is invisible to import checks, type checkers and `compileall` — the code is entirely valid Python and valid FastAPI. Only a request exercises it. Route-binding assertions are cheap and catch it at test time.

### E-023 — Input validation rejected the inputs the greeting path exists for
- **Date / phase:** 2026-08-14 / testing the intent gate
- **Symptom:** `POST /chat` with `{"question": "hi"}` returned **422** — `String should have at least 3 characters`.
- **Root cause:** `ChatRequest.question` carried `min_length=3` from the original single-turn design, when the shortest sensible input was a real question. The intent classifier added later is built precisely to handle one- and two-character inputs safely ("hi" → GREETING, "5QI" → UNCLEAR), but the request never reached it. Two layers held contradictory beliefs about what counts as valid input, and the stricter one won silently.
- **Fix:** `min_length=1`. The classifier, not the schema, decides whether input is actionable — and it is designed to fail toward asking the user rather than guessing.
- **Wider point:** a constraint that was correct when written became wrong when a new layer changed the assumptions beneath it. Nothing flagged the contradiction because each layer was individually reasonable. Tests now assert that anything the validator accepts, the classifier can classify — pinning the two together rather than leaving them to drift.
- **Related:** D-030, E-021

### E-024 — Rule-based intent classification cannot cover conversational English
- **Date / phase:** 2026-08-14 / intent gate testing
- **Symptom:** "so whats your name" was classified as a specification question, consumed a quota slot, retrieved three irrelevant clauses at confidence 0.001, and returned a specification refusal. To a user that reads as a broken system, not a careful one.
- **Root cause:** The classifier was a fixed regex list built from the greetings I happened to think of. It caught "hi" and "what can you do" but not "whats your name", "how are you", "who built you", or any of the unbounded set of ways people open a conversation. Rules can enumerate greetings; they cannot enumerate conversational English.
- **Fix:** Two stages. Rules still handle the common cases for free. Anything short with no telecom vocabulary is marked AMBIGUOUS and resolved by one cheap LLM call (~80 tokens on the small model) that decides CONVERSATIONAL vs TECHNICAL. It fires rarely, because real specification questions almost always contain domain terms.
- **Failure direction, chosen deliberately:** the fallback defaults to CONVERSATIONAL when the classifier is unavailable. Replying conversationally to a technical question is a mild annoyance; refusing a greeting with a specification disclaimer looks like a malfunction.
- **Wider point:** the earlier fix (E-021) was right about *where* the problem was and wrong about *how much* rules could carry. A closed-set solution to an open-set problem works exactly until someone phrases it differently — which, for a public demo, is the first visitor.
- **Related:** D-030, E-021

### E-025 — Upload required users to rename the file they had just downloaded
- **Date / phase:** 2026-08-14 / first real upload test
- **Symptom:** Uploading `ts_128554v180500p.pdf` — the exact filename etsi.org serves — produced the warning *"Filename did not match the TS_&lt;number&gt;_v&lt;version&gt;.pdf convention, so citations will show the filename instead of a spec number."* Every citation from that document then read `ts_128554v180500p` rather than `TS 28.554`.
- **Root cause:** `spec_meta_from_filename` only understood the convention *I* invented for my own corpus. ETSI's naming (`ts_128554v180500p`) is what a user actually has on disk, and ETSI numbers 3GPP specs with a leading 1 — `TS 128 554` is 3GPP `TS 28.554` — which the parser knew nothing about.
- **Fix:** Three-tier identity resolution, most reliable first: the running header printed inside the document (`3GPP TS 28.554 version 18.5.0 Release 18`), then the filename in either ETSI's format or mine, then the bare filename. Content wins because a file can be renamed and its header cannot.
- **Wider point:** the convention was fine for a corpus I curated and wrong the moment a user was involved. Anything that asks a user to reformat their input to suit an internal parser is a defect in the parser. The information was in the document all along — the code was reading the wrong source.
- **Related:** D-002, FR-14

### E-026 — Uploaded documents indexed successfully, then were invisible to every question
- **Date / phase:** 2026-08-14 / upload end-to-end test
- **Symptom:** Uploading TS 28.554 reported *"Indexed TS 28.554 — 140 clauses"*. Asking a question that only that document answers ("What is the KPI for NG-RAN handover success rate?", defined in its clause 6.6.1) retrieved three passages from the **base corpus** and abstained. Nothing in the logs indicated a problem — the upload succeeded and retrieval succeeded, they simply had nothing to do with each other.
- **Root cause:** Two session subsystems coexisting. `/chat` had been migrated to the SQLite `app.chat.store` (D-028), but `/upload` still used the superseded in-memory `app.chat.session.STORE`. Each minted its own identifier, so uploaded chunks were tagged `owner: <in-memory id>` while retrieval filtered on `owner: <sqlite conversation id>`. The filter worked perfectly and matched nothing.
- **Fix:** `/upload` now resolves the conversation through the same store as `/chat`. Added a test asserting `routes.py` no longer imports the superseded module.
- **Why it was invisible:** every individual component reported success. The upload confirmed a clause count, retrieval returned results, the abstention was correct given what it retrieved. Only an end-to-end test with a question answerable *solely* from the uploaded document could expose it — which is precisely the test that had never been run.
- **Wider point:** a migration that leaves the old subsystem importable leaves a trap. The dead code compiled, imported and ran; it just operated on a parallel universe of identifiers. Deleting or hard-failing the superseded path would have surfaced this at import time instead of as a silent retrieval miss.
- **Related:** D-026, D-028, FR-14

### E-028 — Docker build exhausted memory and hung the EC2 instance
- **Date / phase:** 2026-08-14 / first production deployment
- **Symptom:** During `docker compose up --build` on a t3.small (2 GB RAM + 2 GB swap), SSH dropped with `Connection closed by remote host`. Reconnection timed out, and `describe-instance-status` returned **empty** — the instance was unresponsive enough that even AWS's hypervisor checks stopped reporting. A reboot was required.
- **Root cause:** The API image installed the full `requirements.txt`, which still contained **streamlit** — and with it altair, pydeck, pandas and a large transitive tree — alongside torch, chromadb and transformers. None of the Streamlit path is used in production; the frontend is React and the Streamlit UI is a dev-only prototype. pip resolved and built all of it at once inside a 2 GB container and exhausted the host.
- **Fix:** A separate `requirements-api.txt` containing only what the API runs, plus `--no-compile` to skip bytecode generation during install. Dev tooling stays in `requirements.txt` for local work.
- **Second fault exposed:** the build ran attached to the SSH session, so losing the connection killed it. Long builds on a remote host must be detached (`nohup`, `tmux`, or `docker compose up -d --build` with logs tailed separately).
- **Wider point:** a dependency file that accumulated during development became a production liability. Nobody removed streamlit when the React frontend replaced it, because locally it cost nothing but disk. On a memory-constrained host the same unused dependency took the entire machine down. **Production images should install what they run, not what the repository happens to contain.**
- **Related:** D-013, D-014, NFR-07
