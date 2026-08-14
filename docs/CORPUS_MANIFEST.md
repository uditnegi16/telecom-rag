# CORPUS_MANIFEST.md

The exact corpus the system can answer from. Cited by the README so a reviewer
knows precisely what is in scope — an abstention is only meaningful if the
boundary is stated.

## Indexed specifications

| Spec | Version | ETSI file | Pages indexed | Clauses |
|---|---|---|---|---|
| 3GPP TS 28.532 | V18.7.0 | `ts_128532v180700p.pdf` | 124 | 311 |
| 3GPP TS 28.552 | V18.11.0 | `ts_128552v181100p.pdf` | 359 | 964 |

**Total indexed:** 1,275 clause-level chunks
**Release:** Rel-18 (frozen — see D-001)
**Source:** ETSI (`etsi.org/deliver/etsi_ts/128500_128599/`)
**Acquired:** 13 August 2026
**Embedding model:** `BAAI/bge-small-en-v1.5`, 384 dimensions
**Collection:** `clauses_bge_small_v1`

## Chunk statistics

| | Value |
|---|---|
| Mean tokens per chunk | 253 |
| Max tokens per chunk | 538 (cap 450 + overlap; enforced, see E-009) |
| Chunks with no detected clause structure | 0 |
| Chunks with unknown clause id | 0 |
| Clause depth mode | 5 (e.g. `5.1.1.6.6`) |

Depth 5 is the expected mode: TS 28.552 defines measurements at that level, so
a shallower distribution would indicate sub-clauses being swallowed by parents.

## Scope, and what falls outside it

TS 28.532 covers management services; TS 28.552 covers 5G performance
measurements. Both were chosen for their relevance to service assurance —
counters, KPIs, measurement definitions, the management plane.

**Not indexed, and therefore correctly refused:**

- Fault supervision and alarms (TS 28.545 / 28.546) — so `perceivedSeverity`,
  `alarmType` and similar alarm attributes are genuinely out of corpus
- 5G system architecture and procedures (TS 23.501 / 23.502)
- Anything RAN-layer (TS 38.xxx), LTE, or pre-5G
- End-to-end KPIs (TS 28.554) — available for **upload** at runtime, not in the
  base index

The last point is worth noting: uploading TS 28.554 through the UI extends the
corpus for that conversation only, and citations then resolve against it.

## Reproducing this index

```bash
# Place the two PDFs in data/raw/ (any filename - identity is read from the
# document's own running header, see E-025)
python -m scripts.ingest --reset
python -m scripts.inspect_chunks     # gate G2: READ the sampled chunks
```

The built index is committed to the repository (D-029) so the deployed
container serves traffic on first boot without a re-ingestion step.
