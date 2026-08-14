"""
Conversation state for the chatbot.

DESIGN RULE: HISTORY IS NOT A SOURCE OF FACTS (decision D-025)
--------------------------------------------------------------
A conversational RAG system has a hallucination path that single-turn does
not: the model sees its own earlier answers in context and treats them as
established truth. By turn 5 it can be reasoning from something it inferred
in turn 2 that was never grounded in a clause - and the citation trail looks
clean, because the unsupported step happened in a previous turn.

This implementation forbids that:

  * History is used for ONE purpose - resolving references so a follow-up can
    be retrieved (see contextualizer.py).
  * Prior answers are NEVER placed in the generation context. Every turn
    retrieves from the corpus and generates only from retrieved chunks.
  * Every turn is independently verified. A claim in turn 5 is grounded in a
    clause retrieved for turn 5, not inherited from turn 2.

The cost is that the assistant cannot say "as I mentioned earlier". That is
the correct trade for a system whose entire proposition is that no claim
escapes without a citation.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

MAX_TURNS_KEPT = 12


@dataclass
class Turn:
    role: str                      # "user" | "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)
    # assistant turns only
    citations: List[str] = field(default_factory=list)
    abstained: bool = False
    confidence: float = 0.0
    rewritten_query: Optional[str] = None
    source_chunks: List[dict] = field(default_factory=list)

    def to_history(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class Session:
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    turns: List[Turn] = field(default_factory=list)
    created: float = field(default_factory=time.time)

    def add_user(self, text: str) -> None:
        self.turns.append(Turn("user", text))
        self._trim()

    def add_assistant(self, res: dict) -> Turn:
        turn = Turn(
            role="assistant",
            content=res.get("answer") or "",
            citations=res.get("citations", []),
            abstained=res.get("abstained", False),
            confidence=res.get("confidence", 0.0),
            rewritten_query=res.get("rewritten_query"),
            source_chunks=res.get("source_chunks", []),
        )
        self.turns.append(turn)
        self._trim()
        return turn

    def history(self) -> List[dict]:
        """Reference-resolution context only - never generation context."""
        return [t.to_history() for t in self.turns]

    def _trim(self) -> None:
        if len(self.turns) > MAX_TURNS_KEPT:
            self.turns = self.turns[-MAX_TURNS_KEPT:]


class SessionStore:
    """In-memory store. Adequate for a single-container demo; a real
    deployment would put this in Redis so it survives restarts and scales
    past one replica."""

    def __init__(self, ttl_s: float = 3600.0):
        self._sessions: Dict[str, Session] = {}
        self.ttl_s = ttl_s

    def get(self, session_id: Optional[str] = None) -> Session:
        self._expire()
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]
        s = Session() if not session_id else Session(session_id=session_id)
        self._sessions[s.session_id] = s
        return s

    def _expire(self) -> None:
        now = time.time()
        dead = [k for k, v in self._sessions.items() if now - v.created > self.ttl_s]
        for k in dead:
            self._sessions.pop(k, None)


STORE = SessionStore()
