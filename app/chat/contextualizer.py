"""
Turn a context-dependent follow-up into a standalone retrievable query.

WHY THIS IS NEEDED (FR-13; decision D-024)
------------------------------------------
The brief asks for a CHATBOT, not single-turn Q&A. Multi-turn breaks
retrieval in a way single-turn never does:

    User: How is the RegistrationRequest counter incremented?
    User: What about for the SMF?          <-- unretrievable as written

"What about for the SMF?" has no embedding neighbourhood and no BM25 terms
worth matching. Sent to the retriever as-is it returns noise, the relevance
gate fires, and the system abstains on a question it could easily answer.
The failure looks like bad retrieval; the cause is a missing rewrite step.

WHY IT IS ALSO A HALLUCINATION CONTROL
--------------------------------------
The rewrite uses history to resolve references ONLY. It never carries facts
forward. Every turn re-retrieves and re-verifies against the corpus from
scratch, so an answer given in turn 3 cannot be built on an unverified claim
from turn 1. See `app/chat/session.py` for why that rule exists.

The rewritten query is returned and displayed, because a wrong rewrite
produces a confidently wrong retrieval, and the user needs to see what was
actually searched for.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from app.config import CFG

# Signals that a question depends on prior turns.
DEPENDENT = re.compile(
    r"^\s*(what about|how about|and (for|the|what)|what if|why|and\?|"
    r"same for|for (the )?[A-Z]{2,6}\??$)|"
    r"\b(it|its|that|those|these|they|them|this one|the same)\b",
    re.I,
)

REWRITE_PROMPT = """Rewrite the user's latest question as a standalone question \
that can be understood with no conversation history.

Rules:
- Resolve pronouns and references using the conversation below.
- Keep the user's terminology and any technical identifiers exactly.
- Do NOT answer the question. Do NOT add facts.
- If the question is already standalone, return it unchanged.

Conversation:
{history}

Latest question: {question}

Return JSON only: {{"standalone_question": "..."}}"""


def needs_rewrite(question: str, history: List[dict]) -> bool:
    if not history:
        return False
    q = question.strip()
    if len(q.split()) <= 4:
        return True
    return bool(DEPENDENT.search(q))


def contextualize(
    question: str,
    history: List[dict],
    llm=None,
    max_turns: int = 4,
) -> Tuple[str, bool]:
    """Returns (query_to_retrieve, was_rewritten)."""
    if not needs_rewrite(question, history) or llm is None:
        return question, False

    recent = history[-max_turns:]
    lines = []
    for turn in recent:
        role = "User" if turn["role"] == "user" else "Assistant"
        # Only the QUESTION text from prior turns, truncated. Assistant
        # answers are included for reference resolution but capped short, so
        # the rewriter cannot lift substantive content into the new query.
        lines.append(f"{role}: {turn['content'][:300]}")

    import json

    raw = llm.complete(
        REWRITE_PROMPT.format(history="\n".join(lines), question=question),
        model=CFG.verify_model,          # cheap model; this is a small task
        max_tokens=120,
        json_mode=True,
    )
    try:
        rewritten = (json.loads(raw).get("standalone_question") or "").strip()
    except json.JSONDecodeError:
        return question, False

    # Guard against a rewrite that invents content or collapses the question.
    if not rewritten or len(rewritten) > 400:
        return question, False
    return rewritten, rewritten.lower() != question.strip().lower()
