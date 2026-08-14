"""
SQLite-backed conversation persistence.

WHY SQLITE AND NOT POSTGRES (decision D-028)
--------------------------------------------
The in-memory SessionStore lost every conversation on restart, and the
frontend held session_id only in React state - so a page refresh started a
new conversation. For anything presented as production-shaped that reads as a
prototype.

SQLite over Postgres because the deployment is one API container on one host.
Postgres would add a service to run, back up and monitor in exchange for
multi-replica state sharing that this deployment cannot use. The schema below
is deliberately portable: no SQLite-specific types, so moving to Postgres is
a driver change if a second replica is ever needed.

The database file lives in the same mounted volume as the vector index, so
one volume carries all durable state.

WHAT IS STORED, AND WHAT IS NOT
-------------------------------
Turns, citations, confidence and abstention reasons are stored - they are the
audit trail, and being able to show WHY an answer was refused three days
later is the point of the system.

Retrieved chunk BODIES are not stored. They are reproducible from the index
by chunk_id, and duplicating spec text per turn would grow the database
without adding information.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import List, Optional

DB_PATH = Path("data/processed/conversations.db")
_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    visitor_id  TEXT,
    title       TEXT,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS turns (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    seq             INTEGER NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    created_at      REAL NOT NULL,
    abstained       INTEGER DEFAULT 0,
    abstain_reason  TEXT,
    confidence      REAL,
    rewritten_query TEXT,
    citations       TEXT,          -- JSON array
    claims          TEXT,          -- JSON array
    latency_s       REAL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE INDEX IF NOT EXISTS idx_turns_conv ON turns(conversation_id, seq);
CREATE INDEX IF NOT EXISTS idx_conv_visitor ON conversations(visitor_id, updated_at DESC);
"""


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: FastAPI runs sync handlers in a threadpool,
        # so the connection is touched from multiple threads. All writes go
        # through _lock, so serialisation is handled explicitly.
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
        _conn.commit()
    return _conn


def create_conversation(visitor_id: str, first_question: str = "") -> str:
    cid = uuid.uuid4().hex[:16]
    now = time.time()
    title = (first_question[:60] + "…") if len(first_question) > 60 else first_question
    with _lock:
        get_conn().execute(
            "INSERT INTO conversations (id, visitor_id, title, created_at, updated_at)"
            " VALUES (?,?,?,?,?)",
            (cid, visitor_id, title or "New conversation", now, now),
        )
        get_conn().commit()
    return cid


def add_turn(conversation_id: str, role: str, content: str, **meta) -> None:
    now = time.time()
    with _lock:
        conn = get_conn()
        seq = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM turns WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO turns (id, conversation_id, seq, role, content, created_at,"
            " abstained, abstain_reason, confidence, rewritten_query, citations,"
            " claims, latency_s) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                uuid.uuid4().hex[:16], conversation_id, seq, role, content, now,
                1 if meta.get("abstained") else 0,
                meta.get("abstain_reason"),
                meta.get("confidence"),
                meta.get("rewritten_query"),
                json.dumps(meta.get("citations", [])),
                json.dumps(meta.get("claims", [])),
                meta.get("latency_s"),
            ),
        )
        # Title the conversation from its first user turn.
        if role == "user" and seq == 1:
            title = (content[:60] + "…") if len(content) > 60 else content
            conn.execute("UPDATE conversations SET title = ? WHERE id = ?",
                         (title, conversation_id))
        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?",
                     (now, conversation_id))
        conn.commit()


def get_turns(conversation_id: str) -> List[dict]:
    rows = get_conn().execute(
        "SELECT * FROM turns WHERE conversation_id = ? ORDER BY seq", (conversation_id,)
    ).fetchall()
    out = []
    for r in rows:
        out.append({
            "role": r["role"], "content": r["content"],
            "abstained": bool(r["abstained"]),
            "abstain_reason": r["abstain_reason"],
            "confidence": r["confidence"],
            "rewritten_query": r["rewritten_query"],
            "citations": json.loads(r["citations"] or "[]"),
            "claims": json.loads(r["claims"] or "[]"),
            "latency_s": r["latency_s"],
            "created_at": r["created_at"],
        })
    return out


def history_for_prompt(conversation_id: str, max_turns: int = 8) -> List[dict]:
    """Reference-resolution context only — see D-025. Never generation context."""
    turns = get_turns(conversation_id)[-max_turns:]
    return [{"role": t["role"], "content": t["content"]} for t in turns]


def list_conversations(visitor_id: str, limit: int = 30) -> List[dict]:
    rows = get_conn().execute(
        "SELECT c.id, c.title, c.created_at, c.updated_at,"
        " (SELECT COUNT(*) FROM turns t WHERE t.conversation_id = c.id) AS turns"
        " FROM conversations c WHERE c.visitor_id = ?"
        " ORDER BY c.updated_at DESC LIMIT ?",
        (visitor_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_conversation(conversation_id: str, visitor_id: str) -> bool:
    with _lock:
        conn = get_conn()
        owner = conn.execute(
            "SELECT visitor_id FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        # Ownership check: a conversation id in a URL must not let one visitor
        # delete another's history.
        if not owner or owner["visitor_id"] != visitor_id:
            return False
        conn.execute("DELETE FROM turns WHERE conversation_id = ?", (conversation_id,))
        conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        conn.commit()
        return True


def exists(conversation_id: str, visitor_id: str) -> bool:
    row = get_conn().execute(
        "SELECT 1 FROM conversations WHERE id = ? AND visitor_id = ?",
        (conversation_id, visitor_id),
    ).fetchone()
    return row is not None
