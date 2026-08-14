# TRACEABILITY.md

Every requirement traced to the decision that shaped it, the module that implements it, the test that verifies it, and the metric that measures it.

**Review rule:** a requirement with no test is an unverified claim. A module with no requirement is scope creep. Both are defects.

---

## Forward trace: requirement → implementation → evidence

| Req | Decision | Module | Test | Metric | Result |
|---|---|---|---|---|---|
| FR-01 Ingest 3GPP specs | D-001 corpus scope, D-002 PDF source | `app/ingestion/parser.py`, `ingestion_pipeline.py` | `tests/integration/test_ingestion.py` | specs indexed, chunk count | RUN-— |
| FR-02 Answer questions | D-011 Groq provider | `app/generation/generator.py` | `tests/integration/test_api.py` | answer correctness | RUN-— |
| FR-03 Structural provenance | **D-003 clause-aware chunking** | `app/ingestion/clause_chunker.py` | `tests/unit/test_clause_chunker.py` | % chunks with full metadata | RUN-002 |
| FR-04 Hybrid retrieval | D-006 BM25 + RRF | `app/retrieval/bm25_index.py`, `fusion.py` | `tests/unit/test_fusion.py` | Recall@10, MRR | RUN-003 |
| FR-05 Reranking | D-007 cross-encoder | `app/retrieval/reranker.py` | `tests/unit/test_reranker.py` | MRR | RUN-004 |
| FR-06 Valid citations | D-010 verification chain | `app/verification/citation_check.py` | `tests/unit/test_citation_check.py` | citation accuracy, fabricated-citation rate | RUN-005 |
| FR-07 Abstention | **D-009 relevance gate** | `app/generation/confidence.py` | `tests/unit/test_confidence.py` | abstention correctness, false-refusal rate | RUN-006 |
| FR-08 Suppress unentailed claims | D-010 entailment verifier | `app/verification/entailment.py` | `tests/unit/test_entailment.py` | ungrounded-claim rate, claims dropped | RUN-007 |
| FR-09 REST API | D-021 FastAPI (reused) | `app/api/routes.py` | `tests/integration/test_api.py` | contract test pass | — |
| FR-10 UI shows evidence | D-013 Streamlit | `ui/streamlit_app.py` | manual | — | — |
| FR-11 Injection defence | D-022 sanitizer (reused) | `app/security/sanitizer.py` | `tests/unit/test_sanitizer.py` | injection test pass | — |
| FR-12 Query logging | D-023 logger (reused) | `app/monitoring/logger.py` | `tests/unit/test_logger.py` | rows written | — |
| NFR-01 Groq limits | **D-017, D-018, D-019** | `app/llm/groq_client.py` | `tests/unit/test_token_budget.py` | 429 count, cache hit rate | all runs |
| NFR-02 Ungrounded rate | D-009 + D-010 | verification chain | eval harness | **ungrounded-claim rate** | RUN-007 |
| NFR-03 Fail closed | D-009 | `confidence.py` | adversarial set | **unsupported-answer rate** | RUN-006 |
| NFR-04 CPU-only | D-004, D-007 | `embedder.py`, `reranker.py` | — | p95 latency on CPU | all runs |
| NFR-05 Latency | D-017 reduced k | `search.py` | load test | p50 / p95 | all runs |
| NFR-06 Reproducible | D-014 packaging | `Dockerfile`, `Makefile` | clean-clone check | G7 pass | — |
| NFR-07 Containerised | D-014 | `docker-compose.yml` | CI build | build pass | — |
| NFR-08 Repro. evaluation | D-012, NFR-08 | `eval/run_eval.py` | — | run records commit + hash | all runs |
| NFR-09 Documented decisions | — | `docs/DECISION_LOG.md` | review | entries with rejected alternatives | — |

---

## Reverse trace: component → justifying requirement

Confirms no orphan components. Every entry must name a requirement, or be deleted.

| Module | Justified by | If removed, what breaks |
|---|---|---|
| `clause_chunker.py` | FR-03, NFR-02 | Definitions split mid-clause; citations lose clause granularity |
| `bm25_index.py` | FR-04 | Exact identifiers (`TS 28.552`, `5QI`, `gNB-DU`) become unretrievable |
| `fusion.py` | FR-04 | Two ranked lists cannot be combined without score normalisation |
| `reranker.py` | FR-05, FR-07 | Loss of the calibrated score that the abstention gate depends on |
| `confidence.py` | FR-07, NFR-03 | System answers when it has no evidence — primary hallucination path |
| `citation_check.py` | FR-06 | Fabricated clause references pass through undetected |
| `entailment.py` | FR-08, NFR-02 | Retrieval-correct-but-embellished answers pass through |
| `groq_client.py` | NFR-01 | Evaluation runs abort on rate limits |
| `sanitizer.py` | FR-11 | Instruction text in a spec passage could steer generation |

---

## Defect trace

Defects found in the forked codebase, with the requirement each violated. Kept because "what did you find and fix" is a direct interview question.

| ID | Defect | Requirement violated | Fix | Detected by |
|---|---|---|---|---|
| DEF-01 | `parse_llm_response` silently substituted `chunks[0]` when the model's cited chunk_id did not resolve — returning a real passage under a fabricated citation, and causing the grounding check to score against a passage that was never cited | **FR-06** | Unresolvable citation is now a hard failure routed to abstention; citation ID and source text can no longer disagree | Code review during Phase 1 reuse audit |
| DEF-02 | Hallucination check was bag-of-words overlap (`overlap < 0.15`). Inverted normative language (`shall` vs `shall not`) shares ~95% of tokens and scored as grounded — unusable on specification text | **FR-08, NFR-02** | Replaced with claim-level entailment; overlap retained only as a zero-cost pre-filter | Code review during Phase 1 |
| DEF-03 | `chunk_size=512` measured characters, not tokens, and chunking was per-page — 3GPP clauses span page breaks | **FR-03** | Clause-aware chunker with token-based sizing and cross-page clause continuation | Code review during Phase 1 |
| DEF-04 | Two untuned thresholds (`RELEVANCE_THRESHOLD=0.5`, `CONFIDENCE_THRESHOLD=0.4`); the reranker filtered candidates before confidence was computed, so the gate never saw the full distribution | **FR-07** | Single τ in `config.py`, swept empirically in RUN-006 | Code review during Phase 1 |
| DEF-05 | `temperature=0.1` in generation — non-deterministic, breaking run-to-run comparability | **NFR-08** | Set to 0 | Code review during Phase 1 |
| DEF-06 | Confidence formula rewarded retrieving *more* chunks (`count_factor`), which is not evidence of correctness | FR-07 | Simplified to top reranker score; count factor removed pending evidence it helps | Code review during Phase 1 |

---

## Coverage summary

| | Count | With test | With metric |
|---|---|---|---|
| Functional requirements | 12 | | |
| Non-functional requirements | 9 | | |
| Explicit non-goals | 5 | n/a | n/a |

Fill the columns at G6. Any requirement without a test at G6 must either get one or be reclassified as a non-goal — not quietly left unverified.
