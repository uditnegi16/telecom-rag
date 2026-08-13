# RETROSPECTIVE.md

Complete after submission (SDLC phase 9). Three sections, all mandatory.

## 1. What the evidence showed

Fill from `OUTCOMES_LOG.md`. The point is what the *numbers* said, including
where they contradicted your prediction. A hypothesis you got wrong is the
most interesting content in this document.

- Largest single improvement:
- Change that surprised you:
- Change that was reverted, and why:

## 2. Three real weaknesses

Each with the evidence that revealed it. Not generic ("could be faster") —
specific and measured.

1.
2.
3.

## 3. What two more weeks would buy

Concrete and ordered. Have these ready for the interview question.

1. Expand the corpus and measure whether retrieval precision degrades with
   scale — currently unknown, and the honest answer is that 10 specs is small.
2. Replace the LLM entailment judge with a fine-tuned NLI cross-encoder to cut
   verification latency and remove the token cost from the critical path.
3. Multi-hop retrieval for cross-spec questions — the weakest measured
   category.
4. Log low-confidence queries to drive corpus gap analysis — turning
   abstentions into a feedback signal rather than a dead end.
