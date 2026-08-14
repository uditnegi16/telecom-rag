# RETROSPECTIVE.md

## 1. What the evidence showed

**The abstention gate was not what made the system fail closed.** The design
assumed a relevance threshold would be the primary control. The measured
reality is that at the originally-guessed τ=0.35, *all 47* answerable questions
passed the gate and so did 24 of 25 adversarial ones — the refusals that
appeared to be working came from the model's own sufficiency judgement and the
citation validator. Only after sweeping τ to its measured optimum of 0.90 did
the gate start doing the work attributed to it.

**The baseline was over-refusing, not over-answering.** Textbook naive RAG
invents answers to unanswerable questions; the work is then driving
hallucination down. RUN-001 did the opposite — 30 of 47 answerable questions
were refused despite 91.5% retrieval recall. The remaining work was recovering
coverage without giving back the refusal correctness, which is the reverse of
the planned narrative.

**The most dangerous defect was upstream of every safety control.** E-021: a
greeting was rewritten into the previous question and answered with a real,
valid citation at confidence 1.000. Every grounding mechanism verifies that the
*answer* is supported by the sources. None verify that the *question* was the
one the user asked.

## 2. Three real weaknesses

**Answer completeness.** The generator under-uses retrieved content. Asked how
a measurement is obtained, it returns the measurement's description and pads
the claim list with `Valid for 5GS`-style boilerplate from the clause's trailer
fields, while skipping the trigger condition and formula that were in the same
chunk. Visible in the session-time question. The prompt asks for claims and
gets claim *count*.

**Single-hop retrieval.** Comparison and enumeration questions need evidence
from several clauses; the system retrieves one set and does not decompose. The
`cross_spec` and `comparison` categories are consequently the weakest, and the
benchmark under-represents them (1 procedural, 1 identifier_lookup out of 47
after relabelling) — so the weakness is under-measured as well as unfixed.

**Ungrounded-claim rate is instrumented but not benchmarked post-swap.** The
verifier runs on every response and reports claims removed, but the full
benchmark run after moving generation to `8b-instant` was never completed.
The number is therefore absent from the README rather than estimated.

## 3. What two more weeks would buy

1. **Complete the ablation.** RUN-002 through RUN-007 exist as a plan and a
   harness; only RUN-001 and the τ sweep were executed. Each remaining run is
   a flag change and 15 minutes.
2. **Expand and rebalance the benchmark.** 47 items skewed heavily toward
   `definition` limits what the segmented analysis can show. Deliberate
   sampling across question types would make RUN-003's hybrid-retrieval claim
   verifiable rather than plausible.
3. **Multi-hop retrieval** for comparison questions — decompose, retrieve per
   sub-question, verify each independently.
4. **Replace the LLM entailment judge with a fine-tuned NLI cross-encoder**,
   removing an API call from the critical path and roughly halving latency.
5. **Move the models behind hosted APIs** (embeddings and reranking) so the
   service becomes stateless and can scale to zero. The current EC2 deployment
   exists solely because two PyTorch models must stay resident.

## 4. What I would do differently

**Order experiments by information-per-cost, not by pipeline position.** The τ
sweep is retrieval-only, costs zero API tokens, runs in two minutes, and
determines the single most consequential parameter. It was scheduled last,
after the generation runs that consumed the entire daily token budget.

**Test the production build before deployment day.** Two failures (E-028
dependency bloat, E-029 Vite type declarations) were only discoverable under
`docker build` and `vite build`, neither of which had ever been run before the
deploy attempt. Both would have taken seconds to catch locally.

**Delete superseded code at migration time.** E-026 — uploads invisible to
retrieval — happened because an old session store remained importable after
its replacement shipped. The dead path compiled, imported and ran; it simply
operated on a parallel set of identifiers.
