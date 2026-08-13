# REQUIREMENTS.md

Baselined 13 Aug 2026. Every requirement has an ID, a source, and an acceptance criterion that is numeric or testable. A requirement with neither is not a requirement — it is a wish.

**Source column:** `BRIEF` = stated in the assignment email · `JD` = implied by the job description · `DERIVED` = engineering consequence of a BRIEF requirement.

---

## Functional requirements

| ID | Requirement | Source | Acceptance criterion |
|---|---|---|---|
| FR-01 | Ingest 3GPP specification documents as the primary knowledge source | BRIEF | ≥8 specs indexed; versions recorded |
| FR-02 | Answer natural-language questions over the indexed corpus | BRIEF | Golden-set answer correctness ≥ 0.8 (0–2 scale, normalised) |
| FR-03 | Chunks carry structural provenance: spec ID, version, clause ID, heading path | DERIVED | 100% of chunks populate all four fields |
| FR-04 | Retrieval combines lexical and semantic matching | DERIVED | BM25 and dense both contribute; fusion is deterministic |
| FR-05 | Retrieved candidates are reranked before entering the generation context | DERIVED | Reranker score present on every candidate |
| FR-06 | Every emitted claim carries a citation resolving to a real indexed chunk | BRIEF (reformulated) | Citation accuracy ≥ 90%; fabricated-citation rate = 0% |
| FR-07 | Where retrieved evidence is insufficient, the system abstains | BRIEF (reformulated) | Abstention correctness ≥ 90% on adversarial set |
| FR-08 | Claims not entailed by their cited passage are suppressed before output | BRIEF (reformulated) | Verifier drop count reported per run |
| FR-09 | Expose the system over a REST API | JD | `/chat`, `/health` respond per contract; integration test passes |
| FR-10 | Provide a user interface showing answer, citations, retrieved passages, confidence | DERIVED | Retrieved chunk text visible to the user for every answer |
| FR-11 | Reject or neutralise instruction-like text inside retrieved passages | DERIVED | Sanitizer unit test with injected instruction passes |
| FR-12 | Log every query with latency, confidence, token usage, and outcome | JD | Log row written per request |

## Non-functional requirements

| ID | Requirement | Source | Acceptance criterion |
|---|---|---|---|
| NFR-01 | Operate within Groq free-tier limits (~6,000 TPM, ~30 RPM) | DERIVED | No 429 aborts a full evaluation run; backoff verified |
| NFR-02 | Ungrounded-claim rate below target on a fixed benchmark | BRIEF (reformulated) | < 5% (stretch < 2%) on golden set |
| NFR-03 | Failure mode is closed — refusal, never a guess | BRIEF (reformulated) | Unsupported-answer rate < 10% on adversarial set |
| NFR-04 | Run on CPU-only hardware | DERIVED | No CUDA dependency; p95 latency measured on CPU |
| NFR-05 | p95 end-to-end latency | DERIVED | < 6 s (stretch < 3 s) |
| NFR-06 | Reproducible from a clean clone | JD | `make up` succeeds in a fresh environment |
| NFR-07 | Containerised, cloud-native deployable | JD | `docker compose up` works; K8s manifests if time permits |
| NFR-08 | Evaluation is reproducible | DERIVED | Temperature 0; datasets versioned; run records commit + config hash |
| NFR-09 | Design decisions are documented with rejected alternatives | BRIEF (graded on understanding) | `DECISION_LOG.md` complete |

## Explicit non-goals

Recorded so a reviewer does not mistake absence for oversight.

| ID | Non-goal | Reason |
|---|---|---|
| NG-01 | Fine-tuning any model | Retrieval, not training, is the right tool for a factual corpus; also infeasible on CPU |
| NG-02 | Full 3GPP corpus | Precision over breadth at this scale; scoped corpus stated in README |
| NG-03 | Multi-turn conversational memory | Orthogonal to the graded property; would dilute effort |
| NG-04 | Authentication, multi-tenancy, HA | Not a production deployment |
| NG-05 | Answering questions outside the indexed corpus | Deliberate: FR-07 requires abstention instead |

---

## Requirement → phase mapping

| Phase | Requirements addressed |
|---|---|
| 1 Feasibility | NFR-01, NFR-04 |
| 2 Architecture | FR-03, FR-04, FR-05 |
| 3 Detailed design | FR-06, FR-07, FR-08, NFR-08 |
| 4 Test infrastructure | NFR-02, NFR-03, NFR-08 |
| 5 Implementation | FR-01, FR-02, FR-09, FR-10, FR-11, FR-12 |
| 6 V&V | all acceptance criteria |
| 7 Tuning | FR-07, NFR-02, NFR-03 |
| 8 Release | NFR-06, NFR-07 |
