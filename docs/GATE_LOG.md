# GATE_LOG.md

Phase gates from `SDLC.md` §4. Sign each with a timestamp as you pass it.
Do not backfill — the timestamps are part of the evidence that the process
was followed rather than reconstructed.

| Gate | Criterion | Passed | Timestamp | Evidence |
|---|---|---|---|---|
| G0 | Every requirement has an ID and a testable acceptance criterion | ☐ | | `REQUIREMENTS.md` |
| G1 | Corpus acquired; spec versions pinned | ☐ | | `CORPUS_MANIFEST.md` |
| G2 | Chunk metadata complete; 10 chunks manually inspected | ☐ | | `make inspect` output |
| G3 | Golden set ≥30 + adversarial ≥15, hand-verified | ☐ | | `eval/datasets/` |
| G4 | Baseline measured **before** optimisation | ☐ | | `RUN-001.json` |
| G5 | ≥5 runs, one variable each | ☐ | | `OUTCOMES_LOG.md` |
| G6 | Metric targets met | ☐ | | `RUN-007.json` |
| G7 | Clean clone reproduces the system | ☐ | | fresh `make up` |
| G8 | README + logs + ablation + limitations complete | ☐ | | repo |

## Gate notes

Record anything that made a gate hard to pass — those notes become the
retrospective and the "what broke" interview answer.

### G2 —
### G3 —
### G4 —
