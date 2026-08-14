"""
Per-visitor question quota for the public demo.

WHY (deployment constraint, not a product feature)
--------------------------------------------------
The live demo shares one Groq free-tier account: 1000 requests/day on the
generation model, and each question costs 1 generation call plus one
verification call per claim. An unlimited public endpoint drains the day's
quota in minutes, after which every visitor - including the person the link
was sent to - sees nothing but rate-limit errors.

A hard per-visitor cap is the honest engineering answer to a shared-quota
demo. It is enforced server-side, not in the browser, because a client-side
counter is a suggestion rather than a limit.

No authentication by design: the link must work on first click. Identity is
therefore best-effort (a signed browser-session cookie), which is adequate
for quota fairness and explicitly NOT a security boundary. Stated plainly
rather than dressed up.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

MAX_QUESTIONS_PER_VISITOR = int(os.getenv("DEMO_QUESTION_LIMIT", "8"))
GLOBAL_DAILY_CAP = int(os.getenv("DEMO_GLOBAL_DAILY_CAP", "300"))
STATE_PATH = Path(os.getenv("DEMO_QUOTA_PATH", "data/processed/quota.json"))

_lock = threading.Lock()


@dataclass
class QuotaState:
    day: str = ""
    global_used: int = 0
    visitors: Dict[str, int] = field(default_factory=dict)


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _load() -> QuotaState:
    if STATE_PATH.exists():
        try:
            raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            state = QuotaState(**raw)
            if state.day == _today():
                return state
        except Exception:                      # noqa: BLE001
            pass
    return QuotaState(day=_today())


def _save(state: QuotaState) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps({"day": state.day, "global_used": state.global_used,
                    "visitors": state.visitors}),
        encoding="utf-8",
    )


def check(visitor_id: str) -> tuple[bool, int, str]:
    """Returns (allowed, remaining, reason). Does NOT consume."""
    with _lock:
        state = _load()
        if state.global_used >= GLOBAL_DAILY_CAP:
            return False, 0, "global_daily_cap"
        used = state.visitors.get(visitor_id, 0)
        remaining = MAX_QUESTIONS_PER_VISITOR - used
        if remaining <= 0:
            return False, 0, "visitor_limit"
        return True, remaining, ""


def consume(visitor_id: str) -> int:
    """Records one question. Returns remaining for this visitor."""
    with _lock:
        state = _load()
        state.visitors[visitor_id] = state.visitors.get(visitor_id, 0) + 1
        state.global_used += 1
        _save(state)
        return max(0, MAX_QUESTIONS_PER_VISITOR - state.visitors[visitor_id])


def reset(visitor_id: str | None = None) -> dict:
    """Clear quota. Called by the admin endpoint before a live demo.

    Without this the only way to reset was deleting a file on the server and
    clearing browser cookies - impossible mid-interview (E-020).
    """
    with _lock:
        state = _load()
        if visitor_id:
            state.visitors.pop(visitor_id, None)
        else:
            state = QuotaState(day=_today())
        _save(state)
        return {"reset": visitor_id or "all", "day": state.day}


def remaining_for(visitor_id: str) -> int:
    with _lock:
        state = _load()
        return max(0, MAX_QUESTIONS_PER_VISITOR - state.visitors.get(visitor_id, 0))


def stats() -> dict:
    with _lock:
        state = _load()
        return {
            "day": state.day,
            "global_used": state.global_used,
            "global_cap": GLOBAL_DAILY_CAP,
            "per_visitor_limit": MAX_QUESTIONS_PER_VISITOR,
            "visitors_today": len(state.visitors),
        }
