# ARCHITECTURE.md

## Design rule

Every component must be justifiable by naming **the specific hallucination
mode it eliminates**, not by describing what it does. A component that cannot
be justified this way is removed. This rule is why there is no query-expansion
step, no summarisation layer, and no conversational memory.

## Pipeline

```
OFFLINE — run once per corpus change
────────────────────────────────────
  3GPP PDFs (ETSI)
      │  PyMuPDF
      ▼
  pages[]  ──► clause_chunker ──► Chunk{spec_id, version, clause_id,
      │                                 heading_path, body, pages}
      ├──────────────► bge-small-en-v1.5 ──► ChromaDB (dense)
      └──────────────► BM25Okapi          ──► bm25.pkl (lexical)


ONLINE — per query
──────────────────
  question
      │
      ├─► dense search (k=25) ─┐
      │                        ├─► RRF (k=60) ─► top 50 ─► cross-encoder
      └─► BM25 search  (k=25) ─┘                            rerank
                                                               │
                                                    top_score  │  top-3
                                                               ▼
                                       ┌─────── τ gate (D-009) ────────┐
                                       │  score < τ  ─────────────────►│ ABSTAIN
                                       └───────────────┬───────────────┘
                                                       ▼
                                      Groq llama-3.3-70b, temp 0, JSON
                                       {answer, claims[{claim,citation}]}
                                                       │
                                       ┌───── citation validation ─────┐
                                       │  unresolvable ───────────────►│ ABSTAIN
                                       └───────────────┬───────────────┘
                                                       ▼
                                   ┌──── entailment verification ──────┐
                                   │  overlap pre-filter (free)        │
                                   │  llama-3.1-8b judge per claim     │
                                   │  all ungrounded ─────────────────►│ ABSTAIN
                                   └───────────────┬───────────────────┘
                                                   ▼
                              answer + surviving claims + clause citations
```

## Component justification

| Component | Hallucination mode eliminated | Req |
|---|---|---|
| Clause-aware chunking | Definition split mid-sentence; model completes from memory | FR-03 |
| Version in metadata + breadcrumb | Cross-Release blending of contradictory clause text | FR-03 |
| BM25 alongside dense | Dense misses `TS 28.552`, `5QI`, `gNB-CU-UP`, `perceivedSeverity` | FR-04 |
| RRF | Requires no score normalisation → one fewer unjustifiable constant | FR-04 |
| Cross-encoder rerank | Correct chunk in candidate pool but outside the LLM's window; also supplies the calibrated score τ depends on | FR-05 |
| **τ gate** | Corpus has no answer at all — removes the *opportunity* to invent | FR-07 |
| Per-claim JSON citations | Unfalsifiable claims; enables claim-level verification | FR-06 |
| Citation validation | Fabricated clause/spec numbers | FR-06 |
| Entailment verifier | Retrieval correct, generation embellished | FR-08 |
| Sanitizer | Instruction-like text inside a retrieved passage | FR-11 |

## Two-tier model split (D-019)

| Role | Model | Why |
|---|---|---|
| Generation | `llama-3.3-70b-versatile` | Instruction-following and strict JSON adherence matter most here |
| Verification | `llama-3.1-8b-instant` | One claim vs one passage is a narrow binary task; the small model is adequate and roughly 8× cheaper in tokens, which matters under a 6,000 TPM ceiling |

## Fail-closed property (NFR-03)

Five distinct paths terminate in abstention: below-τ, parse failure,
model-declared insufficiency, invalid citation, all-claims-ungrounded. There is
no path that emits an unverified claim. This is the property claimed at
delivery — *not* "zero hallucination".

## Known architectural limitations

State these before a reviewer finds them.

1. **Single-hop retrieval.** Cross-spec comparison questions need evidence from
   two clauses; the current design retrieves one set and does not decompose the
   question. Expect the `cross_spec` question type to score worst.
2. **Table extraction.** Large 3GPP measurement tables extract imperfectly from
   PDF. Tagged `content_type: table` so the effect is measurable, not fixed.
3. **Verifier is an LLM.** It can itself err; judge–human agreement on a
   hand-labelled sample is reported for exactly this reason.
4. **τ is tuned on this corpus.** The operating point does not transfer to a
   different corpus without re-sweeping.
