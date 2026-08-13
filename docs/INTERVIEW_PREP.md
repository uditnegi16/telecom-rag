# INTERVIEW_PREP.md

The email says you are graded on three things: the project, **your understanding of the design and code**, and the technical interview. Points 2 and 3 are the majority. A modest system you can defend end-to-end beats an impressive one you cannot.

**Rule for the whole interview:** every claim you make should be traceable to a number in `OUTCOMES_LOG.md` or an entry in `DECISION_LOG.md`. That is why those files exist.

---

## A. The questions you will definitely get

### "Walk me through your architecture."
90 seconds, then stop and let them steer. Structure: corpus → ingestion → retrieval → generation → verification → abstention. For each block name **the specific failure it prevents**, not what it does. Anyone can describe a reranker; describing *why it is in your design* is the answer they want.

### "You were asked for zero hallucination. Did you achieve it?"
Do not say yes. Do not apologise either.
> "Not zero in the general case — I don't think that's provable for a generative model. What I did was reframe it as 'no unsupported claims emitted'. Every claim is verified against its cited chunk before it leaves the system, and anything unverifiable becomes a refusal. Measured: X% ungrounded claims on 60 hand-verified questions, Y% correct abstention on 25 adversarial ones, at Z% false refusals. The system is fail-closed and auditable rather than provably correct."

This is the single highest-leverage answer in the interview. Rehearse it aloud.

### "What was the biggest hallucination source you found?"
Answer from your baseline failure taxonomy, with counts. E.g. *"Chunk truncation. In the baseline, N of my failures were the model completing a definition that had been split mid-sentence. Clause-aware chunking removed most of that — RUN-002 took hallucination from A% to B%."*

### "Why hybrid retrieval instead of just embeddings?"
Exact identifiers. `TS 28.552`, `5QI`, `NRCellDU`, `gNB-CU-UP` are near-meaningless in embedding space but perfect BM25 matches. Cite your segmented RUN-003 result: gain concentrated on identifier questions, flat elsewhere. Segmented evidence sounds like measurement; a single global number sounds like a guess.

### "How do you know your evaluation is any good?"
- All 60 answerable items hand-verified (LLM-drafted, human-corrected — say this plainly).
- Adversarial set exists at all — most candidates only test answerable questions.
- Judge validated against 20 human labels; report agreement.
- Same set, same seed, one variable per run.

### "What would you do with two more weeks?"
Have three concrete answers ready, e.g.: expand corpus and measure whether precision degrades with scale; replace the LLM verifier with a fine-tuned NLI model to cut latency and cost; add multi-hop retrieval for cross-spec questions (currently the weakest category — *quote its score*); build a feedback loop that logs low-confidence queries for corpus gap analysis.

### "What's broken / what are you unhappy with?"
Answer honestly and specifically. Table extraction, multi-hop questions, latency under reranking, whatever your data says. **A candidate who cannot criticise their own system is the one interviewers worry about.** Have three real weaknesses ready, each with the evidence that revealed it.

---

## B. Code walkthrough — be ready to open these files

They will ask you to explain your own code. Know these cold:
1. **The chunker.** The regex, why it over-matches, how you constrained it (E-000b). This is where your real engineering is.
2. **The LangGraph state schema and edges.** Every node, every condition, the loop bound and why it's bounded.
3. **The abstention gate.** Where τ is applied and how you chose it.
4. **The verifier.** Exact prompt, what happens to a failed claim.
5. **The eval harness.** How a run produces a row in the table.

If you used code you cannot explain, **remove it before submitting.** Unexplainable code in a submission is worse than a missing feature.

---

## C. Fundamentals they may probe

Be ready to explain simply, ideally with a line from your own project:

**RAG:** why retrieval beats fine-tuning for a factual corpus (updatable, citable, no retraining, no knowledge baked into weights).
**Embeddings:** vectors where distance ≈ semantic similarity; why they fail on rare identifiers.
**Chunking trade-off:** small = precise retrieval, lost context; large = context kept, diluted embeddings and noisier prompts.
**Bi-encoder vs cross-encoder:** bi-encoder embeds independently (fast, pre-indexable), cross-encoder attends jointly (accurate, cannot pre-compute) → hence retrieve-then-rerank.
**RRF:** fuse ranked lists by summing 1/(k+rank); no score normalisation needed.
**Vector index:** HNSW as a navigable small-world graph; ANN trades exactness for speed.
**Why temperature 0** for a factual assistant.
**Context window / lost-in-the-middle:** why more retrieved chunks is not better.
**Prompt injection:** relevant here — a malicious document could carry instructions; your verifier and citation checks limit blast radius. Mention it unprompted; it shows security awareness.

---

## D. Domain — Mavenir-specific

They build **agentic service assurance**. Connect your project to their day job:
- **Alarms:** your corpus includes TS 28.545/28.546/32.111-2 — you can talk about alarm severity, probable cause, correlation.
- **KPIs:** TS 28.552/28.554 — performance measurements, E2E KPIs.
- **Why grounding matters operationally:** an assistant that invents an alarm's probable-cause semantics during an outage actively harms the NOC engineer. Refusal is strictly better than a plausible wrong answer at 3am. *This framing shows you understand their user, not just the technology.*
- **On-prem:** operators often cannot ship network telemetry to third-party APIs. Mention your local-model path (D-011).
- Skim their site and the two videos in Kanak's email — they were sent for a reason, and referencing something specific from them costs you 20 minutes and reads as genuine interest.

---

## E. Questions to ask them

Have four ready. Good ones:
- "How does MavAI OPS currently measure trust in agent-generated recommendations — do you have a groundedness metric in production?"
- "Where does the agentic layer sit relative to the existing OSS — does it act, or recommend to a human?"
- "What's the hardest failure mode you've hit taking LLM assistance into a live NOC?"
- "For a GET joining this team, what does the first six months look like?"

---

## F. Practical

- **Rehearse the demo.** Run it once end-to-end before the call. Show a good answer, then **show an abstention** — the refusal is the most impressive part of the whole submission and most candidates never demo one.
- **Have all four logs open** during the interview. Quoting your own decision log live is unusual and lands well.
- **Salary:** ₹8–10 LPA was stated up front. Nothing to negotiate before an offer; don't raise it first.
- If asked something you don't know: *"I don't know — my guess would be X, and I'd check it by Y."* Never bluff to an engineer about their own domain.

---

## G. Two-minute pitch (write your own version, then say it out loud until it's smooth)

> "I built a grounded assistant over ~10 3GPP specs, weighted toward fault management and KPIs because that's closest to service assurance. The design goal wasn't a clever answer — it was that the system never says anything it can't point at. Chunking follows the clause hierarchy so definitions stay intact; retrieval is hybrid because telecom questions are full of exact identifiers that embeddings miss; a cross-encoder reranks; and then two gates: if retrieval confidence is below threshold it refuses without calling the model at all, and after generation every claim is checked against its cited clause, with unsupported claims dropped. I built the evaluation harness first, shipped a deliberately naive baseline, and changed one thing at a time — the README has the full ablation. Final numbers: [X]% ungrounded claims on 60 hand-verified questions, [Y]% correct abstention on 25 adversarial ones, [Z]% false refusals. I wouldn't claim zero hallucination; I'd claim fail-closed and auditable."
