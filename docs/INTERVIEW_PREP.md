# INTERVIEW_PREP.md

The email grades three things: the project, **your understanding of the design
and code**, and the technical interview. Two of the three are you talking.

**One rule:** every claim traces to a number in `OUTCOMES_LOG.md` or an entry
in `DECISION_LOG.md` / `ERROR_LOG.md`. That is why those files exist.

---

## A. The question the brief invites

### "You were asked for zero hallucination. Did you achieve it?"

Do not say yes. Do not apologise either.

> "Not zero in the general case — I don't think that's provable for a
> generative model. So I reframed it: the goal isn't that the model never
> invents, it's that **the system emits no unsupported claim**. That's
> achievable, because you can verify after generation and suppress.
>
> Concretely: retrieval is hybrid dense plus BM25, reranked. Below a
> confidence threshold the system refuses without calling the model at all.
> Above it, generation must return per-claim citations; every citation is
> checked against the retrieved set, and every claim is checked for entailment
> against the clause it cites. Unsupported claims are dropped, and if none
> survive, it abstains.
>
> Measured: on a 47-question hand-verified benchmark and 25 adversarial
> questions, the operating point gives 96% correct abstention at a 2.1%
> false-refusal cost. I'd describe the system as **fail-closed and
> auditable**, not hallucination-free — every claim carries a clause citation
> a human can falsify in seconds."

Rehearse that aloud. It is the highest-leverage minute of the interview.

---

## B. Walk-through, 90 seconds

Corpus → ingestion → retrieval → generation → verification → abstention. For
each block name **the failure it prevents**, not what it does.

| Component | The hallucination it prevents |
|---|---|
| Clause-aware chunking | A definition split mid-sentence, which the model completes from memory |
| BM25 alongside embeddings | Dense retrieval misses `TS 28.552`, `5QI`, `gNB-CU-UP` |
| Cross-encoder rerank | Right clause retrieved but ranked outside the window the model sees |
| τ gate | Corpus has no answer — removes the *opportunity* to invent |
| Citation validation | Fabricated clause and spec numbers |
| Entailment verification | Retrieval correct, generation embellished |

Then stop and let them steer.

---

## C. The five stories worth telling

These are what separate this from a tutorial project. Each is a real defect
with a real diagnosis.

### 1. The greeting that was answered as the previous question (E-021)

A user typed "Hello, hello, hello." The system replied *"The measurement is
reported as an integer value"* — with a verified claim and a valid clause
citation, at confidence 1.000. It had answered the question from two turns
earlier.

The follow-up rewriter treated any short input as a context-dependent
reference and resolved it into the prior question. Everything downstream then
worked perfectly on a question the user never asked.

> **The point:** every grounding control verifies that the *answer* is
> supported by the sources. **None verify that the question was the one the
> user asked.** Query transformation sits upstream of every safety mechanism,
> so a bug there is invisible to all of them.

Fixed with intent classification before retrieval — greetings, meta questions
and unclear input answered directly, consuming no quota.

### 2. Correct citations rejected over square brackets (E-016)

Abstentions everywhere, at confidence 0.9996, with the gold clause retrieved
at rank 1. The reason: `fabricated citation(s): ['[TS28552_5.5.7.1.3]']`.

The prompt labelled sources as `[id]`. The model copied the brackets, exactly
as shown. The validator compared strings exactly.

> **The point:** a validator must not be stricter than the format its own
> prompt demonstrates. Note the failure was *safe* — it abstained rather than
> emitting a bad citation — but silently destroying correct answers is still a
> serious defect, and fail-closed design made it look like a retrieval problem.

This was the dominant cause of the RUN-001 baseline's 30/47 abstentions.

### 3. Clause detection collapsed on real ETSI PDFs (E-004)

136-page and 359-page specs produced 167 and 533 chunks, with mean chunk size
*above* the token cap — meaning almost everything was fallback window-splitting
rather than detected clauses. The heading regex matched **9 of 10,335 lines**.

`get_text("text")` emits each PDF text *span* on its own line. ETSI lays out a
clause number and its title as separate spans at the same vertical position,
so extraction gave `5.1.1.2` and `RegistrationRequest counter` on different
lines. No heading pattern can match that.

Fixed by extracting with `get_text("dict")` and reconstructing visual lines
from bbox y-coordinates.

> **The point worth making:** my first hypothesis was wrong. I assumed
> table-of-contents contamination was poisoning the hierarchy anchor.
> Plausible, completely wrong. Dumping raw extracted lines took five minutes
> and pointed straight at the cause. Diagnosing beat guessing.

### 4. Uploaded documents indexed, then invisible (E-026)

Upload reported "140 clauses indexed". Asking a question only that document
answered retrieved from the base corpus and abstained.

Two session subsystems coexisting: `/chat` had migrated to SQLite, `/upload`
still used the superseded in-memory store. Each minted its own id, so chunks
were tagged with one and retrieval filtered on the other. The filter worked
perfectly and matched nothing.

> **The point:** every component reported success. Upload confirmed a clause
> count, retrieval returned results, the abstention was correct *given what it
> retrieved*. Only an end-to-end test with a question answerable solely from
> the uploaded document could expose it — which is exactly the test that had
> never been run.

### 5. The measured threshold silently reverted (E-030)

τ was swept and set to 0.90. A later patch shipped the whole config file and
overwrote it back to a guessed 0.35. Nothing failed; the system just ran at a
worse operating point, and the fail-closed behaviour I was attributing to the
gate was actually coming from the second and third lines of defence.

> **The point:** correct behaviour for the wrong reason is harder to detect
> than outright failure. The operating point now has a regression test
> asserting it matches the recorded sweep.

---

## D. Questions you will get

### "How do you know your evaluation is any good?"
- 47 answerable items, **every one hand-verified** against its source clause.
  LLM-drafted, human-corrected — say that plainly, it's the honest method.
- A 25-item **adversarial set** exists at all. Most candidates test only
  answerable questions, which cannot demonstrate abstention.
- Same set, same seed, temperature 0, one variable per run.
- Be ready to concede: only 2 of 7 planned runs were executed. Say so.

### "Why hybrid retrieval instead of just embeddings?"
Exact identifiers. `TS 28.552`, `5QI`, `NRCellDU` are near-meaningless in
embedding space and perfect BM25 matches. Telecom questions are made of them.

### "What's your false-refusal rate, and is that acceptable?"
2.1% at τ=0.90. Acceptable **because of the use case**: for a service-assurance
assistant, a wrong answer about alarm semantics during an outage costs a NOC
engineer more than a refusal. Show the sweep table — the trade-off curve is
the answer, not the single number.

### "What would you do with two more weeks?"
1. Finish the ablation — 5 runs, each a flag change.
2. Rebalance the benchmark: 47 items skew heavily to `definition`, so the
   segmented analysis can't show what it was designed to show.
3. Multi-hop retrieval for comparison questions — currently the weakest
   category and structurally unsupported.
4. Replace the LLM entailment judge with a fine-tuned NLI cross-encoder —
   removes an API call from the critical path.
5. Move embedding and reranking behind hosted APIs so the service becomes
   stateless and scales to zero. The EC2 instance exists *only* because two
   PyTorch models must stay resident.

### "What's broken?"
Have three ready, with evidence:
- **Answer completeness.** The generator under-uses retrieved content — asked
  how a measurement is obtained, it returns the description and pads claims
  with `Valid for 5GS` boilerplate while skipping the trigger condition that
  was in the same chunk.
- **Follow-ups resolve against refusals.** Ask, get declined, then ask "what
  about for the AMF?" and it rewrites against the *declined* question. A
  refusal is a poor antecedent; the rewriter should skip abstained turns.
- **Single-hop retrieval.** Comparison questions need several clauses and the
  system doesn't decompose.

### "Why is it on EC2 and not Lambda?"
Two PyTorch models resident: `bge-small` for embedding, a cross-encoder for
reranking. ~150 MB of weights and a cold load. Lambda would work as a
container image, but cold starts run into API Gateway's 29-second ceiling, and
Chroma needs writable persistent storage. **The right fix is to stop doing the
ML locally** — hosted embedding and rerank APIs, pgvector for storage — and
then it's the same shape as my other services. That was a half-day migration I
didn't have before the deadline.

---

## E. Fundamentals they may probe

Answer with a line from your own project where possible.

**RAG vs fine-tuning** — updatable, citable, no retraining, knowledge not
baked into weights.
**Bi-encoder vs cross-encoder** — bi-encoder embeds independently (fast,
pre-indexable), cross-encoder attends jointly (accurate, cannot pre-compute),
hence retrieve-then-rerank.
**RRF** — fuse ranked lists by summing `1/(k+rank)`; no score normalisation, no
tuned weight to justify.
**Chunking trade-off** — small chunks retrieve precisely but lose context;
large chunks keep context but dilute the embedding.
**Why temperature 0** — reproducibility, and cacheable responses (which is what
made iterating under a 6,000 TPM budget affordable).
**Prompt injection** — retrieved content is data, not instructions. There's a
sanitizer, and the citation and entailment checks limit the blast radius:
injected text cannot produce a claim entailed by a real cited clause. Raise
this unprompted.

---

## F. Mavenir-specific

They build **agentic service assurance**. Connect to it:

- **Corpus choice was deliberate** — TS 28.552 (performance measurements) and
  TS 28.532 (management services). Counters, KPIs, the management plane. Not
  generic 5G architecture.
- **Why grounding matters operationally** — an assistant that invents an
  alarm's probable-cause semantics during an outage actively harms the NOC
  engineer. Refusal is strictly better than a plausible wrong answer at 3am.
  This framing shows you understand their user, not just the technology.
- **On-prem** — operators often cannot send network telemetry to a third-party
  API. The LLM sits behind a provider interface; the embedding and reranking
  models already run locally.
- Watch the two videos from Kanak's email and reference something specific.

---

## G. Practical

- **Rehearse the demo.** Show an answer with evidence expanded, then **show a
  refusal**. The refusal is the most impressive thing in the submission and
  almost nobody demos one.
- **Have `ERROR_LOG.md` open.** 39 logged defects with root causes is unusual.
  Quoting your own error log live lands well.
- **Know your numbers cold:** 1,275 chunks · 91.5% recall@3 · τ=0.90 ·
  96% abstention correctness · 2.1% false refusal · 47 + 25 benchmark.
- **Salary:** ₹8–10 LPA was stated up front. Nothing to negotiate pre-offer.
- If you don't know something: *"I don't know — my guess would be X, and I'd
  check it by Y."* Never bluff to an engineer about their own domain.

---

## H. Two-minute pitch

> "I built a grounded assistant over 3GPP specifications, weighted toward
> performance measurements and management services because that's closest to
> service assurance. The design goal wasn't a clever answer — it was that the
> system never says anything it can't point at.
>
> Chunking follows the clause hierarchy so definitions stay intact. Retrieval
> is hybrid, because telecom questions are full of exact identifiers that
> embeddings miss. A cross-encoder reranks. Then two gates: below a measured
> confidence threshold it refuses without calling the model at all, and after
> generation every claim is checked against its cited clause, with unsupported
> ones dropped.
>
> I built the evaluation harness before optimising anything, shipped a
> deliberately naive baseline, and measured. The threshold is swept, not
> guessed — 96% correct abstention at 2.1% false refusals on 47 hand-verified
> and 25 adversarial questions.
>
> I wouldn't claim zero hallucination. I'd claim fail-closed and auditable.
> And I'd point at the error log — 39 defects with root causes, including one
> where a greeting got answered as the previous question with a real citation,
> which taught me that grounding controls verify the answer but nothing was
> verifying the question."
