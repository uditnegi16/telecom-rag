# Corpus acquisition (gate G1)

**This sandbox cannot reach 3gpp.org or etsi.org — download on your own machine.**

## Which specs, and why these

Weighted deliberately toward fault management, KPIs and OAM, because Mavenir's
MavAI OPS team builds agentic **service assurance**. A corpus of alarm and KPI
specs demonstrates domain fit; a corpus of generic 5G architecture does not.

| Spec | Title | Why |
|---|---|---|
| TS 28.545 | Fault Supervision — concepts & requirements | **Alarms** |
| TS 28.546 | Fault Supervision — stage 2/3 | Alarm data model |
| TS 28.552 | 5G performance measurements | **KPIs** |
| TS 28.554 | 5G end-to-end KPIs | Service assurance metrics |
| TS 28.532 | Management services (provisioning) | OSS management plane |
| TS 28.533 | Architecture framework for management & orchestration | OSS architecture |
| TS 23.501 | System architecture for the 5G System | Canonical 5GC reference |
| TS 23.502 | Procedures for the 5G System | Call flows |
| TS 32.111-2 | Fault Management — Alarm IRP | Classic alarm semantics |
| TR 21.905 | Vocabulary for 3GPP specifications | Acronym / glossary queries |

## Where to get them

- 3GPP: `https://www.3gpp.org/ftp/Specs/archive/` — `.zip` of legacy binary `.doc`
- **ETSI (preferred): `https://www.etsi.org/deliver/etsi_ts/`** — clean PDFs

Use the ETSI PDFs. Parsing legacy `.doc` costs hours you don't have (D-002,
ERROR_LOG E-000a).

## Version freeze — mandatory

Pick **one Release** (Rel-18) and record the exact version string of every file
in `docs/CORPUS_MANIFEST.md`, e.g. `TS 28.552 V18.5.0`.

Mixing Releases makes two contradictory versions of the same clause
simultaneously retrievable, which is a hallucination source the retriever
cannot resolve. It also breaks the `wrong_release` adversarial family, which
exists precisely to test that the freeze holds.

Save PDFs to `data/raw/` named `TS_28552_v18.5.0.pdf`.
