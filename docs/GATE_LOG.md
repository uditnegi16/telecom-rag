# GATE_LOG.md

Phase gates from `SDLC.md` §4, recorded as they were passed — including the
two that were not.

| Gate | Criterion | Status | Date | Evidence |
|---|---|---|---|---|
| G0 | Every requirement has an ID and a testable acceptance criterion | ✅ | 13 Aug | `REQUIREMENTS.md` — 12 FR, 9 NFR, 5 explicit non-goals |
| G1 | Corpus acquired; spec versions pinned | ✅ | 13 Aug | `CORPUS_MANIFEST.md` — TS 28.532 V18.7.0, TS 28.552 V18.11.0 |
| G2 | Chunk metadata complete; sampled chunks manually inspected | ✅ | 13 Aug | 1,275 chunks · 0 fallback · 0 unknown clause · depth mode 5. Inspection found E-001, E-002, E-003 |
| G3 | Golden set ≥30 + adversarial ≥15, hand-verified | ✅ | 14 Aug | 47 answerable (all `verified_by_human: true`) + 25 adversarial |
| G4 | Baseline measured **before** optimisation | ✅ | 14 Aug | RUN-001 — 17/47 answered, 91.5% recall@3 |
| G5 | ≥5 runs, one variable each | ❌ | — | **Not met.** 2 of 7 executed (RUN-001, RUN-006). Recorded rather than fabricated |
| G6 | Metric targets met | ⚠️ | 14 Aug | Abstention 96% ✅ · false refusal 2.1% ✅ · recall 91.5% ✅ · **ungrounded-claim rate not benchmarked post model-swap** |
| G7 | Clean clone reproduces the system | ✅ | 14 Aug | EC2: clone → `docker compose up` → serving. Index committed (D-029) |
| G8 | README + logs + limitations complete | ✅ | 15 Aug | 39 errors, 33 decisions, 8 limitations, live demo linked |

## Gate notes

### G2 — the gate that earned its place
"Read ten sampled chunks" took five minutes and found three defects, all
**silent drops**: camelCase clause titles rejected (E-001), short attribute
clauses discarded by a length filter (E-002), and — after the parser was fixed
— every camelCase clause vanishing because PDF extraction collapses tabs to
single spaces (E-003). None would have surfaced from the chunk counts alone.
Each would have looked like a retrieval-quality problem later.

### G5 — not met, and why that is stated rather than hidden
The plan called for seven single-variable runs. Two were executed. The Groq
free tier binds on **requests per day**, not just tokens per minute, and a day
of development exhausted it. Fabricating the remaining rows would have been
trivial and would have made the submission worse: an ablation table is
evidence, and evidence that was not gathered is not evidence.

### G6 — partially met
Three of four targets are measured and met. The ungrounded-claim rate is
instrumented and visible per response as *claims removed*, but a full
benchmark run after the D-027 model swap was never completed. It is therefore
absent from the README rather than estimated — quoting it would be precisely
the unsupported claim this system exists to prevent.
