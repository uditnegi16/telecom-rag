# REUSE_AUDIT.md

SDLC Phase 1. Documents the build-vs-reuse decision per component and defines
the disclosure that appears in the README.

## Audited sources

| Repo | Verdict | Notes |
|---|---|---|
| `production-rag` | **Fork base** | Groq + CPU-pinned torch + cross-encoder + confidence gate + cache + FastAPI + Docker + CI already present. Matches this project's constraints exactly. |
| `mednotes-rag` | Salvage one idea | `evaluations/metrics.py::faithfulness_prompt` seeded the entailment judge. Chunking (word-window) is weaker than the fork base — not reused. Note: its `keyword_recall` delegates to `keyword_precision`, so the two metrics were identical by construction; not carried forward. |
| `SupportIQ` | Not reused | Design document, no implementation. |

## Component-level decisions

| Component | Reuse / Build | Rationale |
|---|---|---|
| PDF parsing | **Reuse** (`parser.py`, swap pypdf → PyMuPDF) | Works; PyMuPDF keeps layout hints needed for clause detection |
| Chunking | **BUILD NEW** | Fixed-size character chunking, per-page, is the single largest hallucination source on spec text (DEF-03) |
| Embedding | Reuse, retarget model | `all-MiniLM-L6-v2` → `bge-small-en-v1.5`; stronger on technical English |
| Vector store | **Reuse** (ChromaDB) | Embedded, zero infra friction. Qdrant's hybrid support is attractive but BM25 is handled separately, so Chroma is sufficient — D-005 revised |
| Dense retrieval | Reuse | Interface was clean |
| Lexical retrieval | **BUILD NEW** | Did not exist; critical for 3GPP identifiers (FR-04) |
| Fusion | **BUILD NEW** | Did not exist |
| Reranker | **Reuse** | `ms-marco-MiniLM-L-6-v2` is the right CPU choice already |
| Abstention gate | Reuse, **redesign** | Concept existed; two untuned thresholds in two modules, filtering in the wrong place (DEF-04), arbitrary count term (DEF-06) |
| Prompt | **BUILD NEW** | v1 emitted one answer + one trailing SOURCE line; per-claim citations are required for claim-level verification |
| Citation validation | **BUILD NEW** | v1 silently substituted `chunks[0]` on unresolved citations (DEF-01) |
| Grounding check | **BUILD NEW** | v1 was bag-of-words overlap, unusable on normative spec language (DEF-02) |
| LLM client | **BUILD NEW** | No rate limiting, no cache, no token pacing — mandatory under Groq free tier (NFR-01) |
| Orchestration | **BUILD NEW** | Linear call path cannot express the abstain/verify/retry branches (D-008) |
| Eval harness | Reuse shape, **rebuild** | 10 keyword-coverage questions measured vocabulary, not grounding. No adversarial set existed at all |
| API / Docker / CI / sanitizer / logger | **Reuse** | Working, tested, not on the graded path |

## Time released

Reuse converted roughly three days of infrastructure work into configuration
work. That time was reallocated entirely to the graded components: clause-aware
chunking, the evaluation datasets, the verification chain, and threshold tuning.

## Disclosure text for the README

> **Reuse disclosure.** Ingestion scaffolding, the FastAPI layer, the
> cross-encoder reranker, the response cache, the prompt-injection sanitizer,
> the query logger, and the Docker/CI configuration were adapted from a prior
> personal project (`production-rag`). Written new for this assignment: the
> 3GPP clause-aware chunker, hybrid lexical+dense retrieval with RRF, the
> rate-limit-aware Groq client, the citation validator, the claim-level
> entailment verifier, the abstention gate redesign, the LangGraph answer
> pipeline, and both evaluation datasets. Six defects found in the reused code
> are documented in `docs/TRACEABILITY.md`.

Reusing one's own infrastructure is normal engineering. Presenting it as new
work is not — hence this section and the README paragraph.
