# Evaluation dataset schema

Two datasets. They measure different things and must never be merged.

## `golden_set.json` — answerable

Questions whose answer exists in the indexed corpus. Measures whether the
system answers correctly and cites correctly.

```json
{
  "id": "A-001",
  "question": "What information does an alarm notification carry about severity?",
  "gold_spec": "TS 28.532",
  "gold_version": "V18.5.0",
  "gold_clause": "11.2.1.3",
  "reference_answer": "...",
  "question_type": "definition",
  "difficulty": "easy",
  "verified_by_human": true
}
```

`question_type` ∈ `definition` · `identifier_lookup` · `procedural` ·
`comparison` · `enumeration` · `cross_spec`

**`question_type` is not decoration.** RUN-003 must report the hybrid-retrieval
gain segmented by type. The prediction is that BM25 helps `identifier_lookup`
sharply and barely moves `definition`. If the measured gain is uniform, the
analysis is wrong and needs investigating before the result is trusted.

**`verified_by_human` must be `true` for every item.** Construction method
(D-012): stratified chunk sample → LLM drafts candidates → every item read,
checked against the actual clause, and corrected by hand. Disclosed in the
README so a reviewer can judge the metrics correctly.

Target: 60 items. Honest minimum at gate G3: 30.

## `adversarial_set.json` — unanswerable

**This is the dataset that makes the hallucination claim meaningful.** A system
evaluated only on answerable questions cannot demonstrate that it abstains.
Correct behaviour for every item is refusal; any confident answer is a
hallucination.

```json
{
  "id": "ADV-001",
  "family": "out_of_corpus",
  "question": "...",
  "why_unanswerable": "...",
  "expected": "abstain"
}
```

`family` ∈ `out_of_corpus` · `false_premise` · `invented_entity` ·
`wrong_release` · `not_a_spec_question`

Report abstention correctness **per family**. They fail for different reasons
and need different fixes: `invented_entity` is caught by the relevance gate,
whereas `false_premise` often retrieves genuinely relevant chunks with a high
score and must be caught by the entailment verifier instead. A single
aggregate number hides which mechanism is doing the work.

Shipped: 25 items, hand-written.

## `smoke_set.json` — iteration subset

15 mixed items (10 answerable, 5 adversarial) for fast iteration under the
Groq token budget. Full sets run only at phase gates. Never report headline
numbers from the smoke set.
