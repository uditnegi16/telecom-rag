"""API routes (FR-09, FR-12, FR-13, FR-14)."""

from __future__ import annotations

import logging
import re
import secrets
import shutil
import tempfile
import time
from pathlib import Path
from typing import List, Optional

from fastapi import (APIRouter, File, Form, HTTPException, Request, Response,
                     UploadFile)
from pydantic import BaseModel, Field

from app.config import CFG

router = APIRouter()
log = logging.getLogger("telecomrag")


# ---------------------------------------------------------------- models ---

class ChatRequest(BaseModel):
    # min_length=1, not 3: the intent classifier is what decides whether an
    # input is actionable, and it is designed to handle short input safely
    # ("hi" -> GREETING, "5QI" -> UNCLEAR). A stricter validator here rejected
    # the very inputs the greeting path exists to serve, with a 422 the UI
    # surfaced as a raw schema error (ERROR_LOG E-023).
    question: str = Field(..., min_length=1, max_length=1000)
    session_id: Optional[str] = None          # conversation id
    tau: Optional[float] = Field(None, ge=0.0, le=1.0)

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "question": "What is the unit of measurement for the number of "
                            "failed event exposure subscribe at the PCF?"
            }]
        }
    }


class ConversationSummary(BaseModel):
    id: str
    title: str
    turns: int
    created_at: float
    updated_at: float


class StoredTurn(BaseModel):
    role: str
    content: str
    abstained: bool = False
    abstain_reason: Optional[str] = None
    confidence: Optional[float] = None
    rewritten_query: Optional[str] = None
    citations: List[str] = []
    claims: List[Claim] = []
    latency_s: Optional[float] = None
    created_at: float


class Claim(BaseModel):
    claim: str
    citation: str


class Source(BaseModel):
    chunk_id: str
    spec_id: str
    spec_version: str
    clause_id: str
    clause_title: str
    heading_path: str
    page_start: int
    page_end: int
    reranker_score: float
    body: str


class ChatResponse(BaseModel):
    intent: str = "SPEC_QUESTION"
    answer: Optional[str]
    claims: List[Claim] = []
    citations: List[str] = []
    sources: List[Source] = []
    confidence: float
    abstained: bool
    abstain_reason: Optional[str] = None
    claims_dropped: int = 0
    latency_s: float
    rewritten_query: Optional[str] = None
    session_id: str
    questions_remaining: Optional[int] = None


class UploadResponse(BaseModel):
    spec_id: str
    spec_version: str
    pages: int
    chunks_added: int
    seconds: float
    warnings: List[str] = []
    session_id: str


# ----------------------------------------------------------------- utils ---

def _visitor_id(request: Request, response: Response) -> str:
    """Best-effort visitor identity for quota fairness.

    A cookie is trivially cleared, so this is fair-use accounting, NOT a
    security boundary. The global daily cap is the real backstop.
    """
    vid = request.cookies.get("demo_visitor")
    if not vid:
        vid = secrets.token_urlsafe(16)
        response.set_cookie("demo_visitor", vid, max_age=86400,
                            httponly=True, samesite="lax")
    return vid


def _src(c: dict) -> dict:
    return {
        "chunk_id": c.get("chunk_id", ""),
        "spec_id": c.get("spec_id", ""),
        "spec_version": c.get("spec_version", ""),
        "clause_id": c.get("clause_id", ""),
        "clause_title": c.get("clause_title", ""),
        "heading_path": c.get("heading_path", ""),
        "page_start": int(c.get("page_start", 0)),
        "page_end": int(c.get("page_end", 0)),
        "reranker_score": float(c.get("reranker_score", 0.0)),
        "body": (c.get("body") or "")[:2500],
    }


# ---------------------------------------------------------------- routes ---

@router.get("/health")
def health():
    from app.api.main import STATE
    from app.ingestion import vector_store as vs
    count = vs.count()
    return {
        "status": "ok" if (count and STATE["ready"]) else
                  ("warming_up" if count else "index_empty"),
        "ready": STATE["ready"],
        "warmup_s": STATE["warmup_s"],
        "chunks_indexed": count,
        "collection": CFG.collection,
        "embedding_model": CFG.embedding_model,
        "gen_model": CFG.gen_model,
        "verify_model": CFG.verify_model,
        "tau": CFG.tau_abstain,
        "prompt_version": CFG.prompt_version,
    }


@router.get("/corpus")
def corpus(session_id: Optional[str] = None):
    """What the system can answer from. Important context for reading an
    abstention: a refusal is only meaningful if you know the corpus scope."""
    import json
    from collections import Counter
    from pathlib import Path as P

    p = P("data/processed/chunks.json")
    base = {}
    total = 0
    if p.exists():
        chunks = json.loads(p.read_text(encoding="utf-8"))
        base = dict(Counter(f"{c['spec_id']} {c['spec_version']}" for c in chunks))
        total = len(chunks)

    user_docs: List[str] = []
    if session_id:
        from app.ingestion import vector_store as vs
        try:
            user_docs = sorted({
                f"{c.get('spec_id')} {c.get('spec_version')}"
                for c in vs.session_chunks(session_id)
            })
        except Exception:                          # noqa: BLE001
            user_docs = []

    return {"total_chunks": total, "specs": base, "user_documents": user_docs}


@router.get("/quota")
def quota_status(request: Request, response: Response):
    from app.security.quota import remaining_for, stats
    vid = _visitor_id(request, response)
    return {**stats(), "your_remaining": remaining_for(vid)}


@router.post("/quota/reset")
def quota_reset(request: Request, response: Response, all: bool = False):
    """Reset the demo quota.

    Deliberately unauthenticated and deliberately narrow: it can only clear a
    counter, never read or change anything else. The alternative during a
    live interview was SSH-ing into the box to delete a JSON file.
    Set DEMO_ALLOW_RESET=false in the environment to disable it.
    """
    import os
    if os.getenv("DEMO_ALLOW_RESET", "true").lower() != "true":
        raise HTTPException(403, "Reset is disabled on this deployment.")
    from app.security.quota import reset
    vid = _visitor_id(request, response)
    return reset(None if all else vid)


def _corpus_summary() -> str:
    import json
    from collections import Counter
    from pathlib import Path as P
    p = P("data/processed/chunks.json")
    if not p.exists():
        return "No corpus is currently indexed."
    chunks = json.loads(p.read_text(encoding="utf-8"))
    specs = Counter(f"{c['spec_id']} {c['spec_version']}" for c in chunks)
    lines = "\n".join(f"- **{k}** — {v} clauses" for k, v in specs.items())
    return (f"Indexed right now ({len(chunks):,} clauses total):\n{lines}\n\n"
            "Questions outside these specifications are declined by design.")



@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request, response: Response):
    from app.chat import intent as intent_mod
    from app.chat import store
    from app.security.quota import check, consume, remaining_for

    vid = _visitor_id(request, response)

    # ---- classify BEFORE anything else (FR-15, D-030, E-021) -------------
    # A greeting must never reach the follow-up rewriter, which would turn it
    # into the previous question and answer that instead - a fabricated
    # question presented with a real citation.
    conversation_id_probe = (
        req.session_id if req.session_id and store.exists(req.session_id, vid) else None
    )
    has_history = bool(conversation_id_probe and store.get_turns(conversation_id_probe))
    cls = intent_mod.classify(req.question, has_history)

    # Rules cannot enumerate conversational English. Anything they cannot
    # place gets one cheap LLM call rather than being pushed into retrieval,
    # where it produces a specification refusal that reads as a malfunction
    # (E-024).
    if cls.intent == intent_mod.Intent.AMBIGUOUS:
        try:
            from app.pipeline import _get_llm
            cls = intent_mod.resolve_ambiguous(req.question, llm=_get_llm())
        except Exception:                          # noqa: BLE001
            cls = intent_mod.resolve_ambiguous(req.question, llm=None)

    if not cls.billable:
        # Answered directly: no retrieval, no LLM call, no quota consumed.
        # Saying hello should not cost a visitor one of their eight questions.
        cid = conversation_id_probe or store.create_conversation(vid, req.question)
        summary = _corpus_summary()
        if cls.intent == intent_mod.Intent.GREETING:
            text = intent_mod.greeting_response(summary)
        elif cls.intent == intent_mod.Intent.META:
            # "what can you do" wants the capability explanation; "whats your
            # name" wants a short human reply. Both are META, so pick on
            # whether the user asked about capability.
            text = (
                intent_mod.meta_response(summary)
                if re.search(r"\b(can you do|how do you work|what is this|"
                             r"capabilit|what can i ask|which specs?|"
                             r"what specs?|what documents?)\b",
                             req.question, re.I)
                else intent_mod.conversational_response(summary)
            )
        else:
            text = intent_mod.unclear_response()
        store.add_turn(cid, "user", req.question)
        store.add_turn(cid, "assistant", text, confidence=0.0, latency_s=0.0)
        return ChatResponse(
            intent=cls.intent.value, answer=text, claims=[], citations=[],
            sources=[], confidence=0.0, abstained=False, abstain_reason=None,
            claims_dropped=0, latency_s=0.0, rewritten_query=None,
            session_id=cid, questions_remaining=remaining_for(vid),
        )

    allowed, _remaining, reason = check(vid)
    if not allowed:
        raise HTTPException(429, (
            "Demo limit reached: 8 questions per visitor. This runs on a "
            "shared free-tier API key, and the cap keeps the demo available "
            "for everyone. Clone the repo to run without limits."
        ) if reason == "visitor_limit" else (
            "The demo has reached its daily capacity. Please try tomorrow."
        ))

    conversation_id = conversation_id_probe or store.create_conversation(
        vid, req.question
    )

    history = store.history_for_prompt(conversation_id)
    store.add_turn(conversation_id, "user", req.question)

    t0 = time.time()
    try:
        from app.pipeline import get_answer_fn
        answer_fn = get_answer_fn(tau=req.tau, session_id=conversation_id)
        res = answer_fn(req.question, history=history)
    except Exception as exc:                       # noqa: BLE001
        log.exception("answer failed")
        raise HTTPException(500, f"Pipeline error: {exc}") from exc

    latency = round(time.time() - t0, 3)
    store.add_turn(
        conversation_id, "assistant", res.get("answer") or "",
        abstained=res.get("abstained"), abstain_reason=res.get("abstain_reason"),
        confidence=res.get("confidence"), rewritten_query=res.get("rewritten_query"),
        citations=res.get("citations", []), claims=res.get("claims", []),
        latency_s=latency,
    )
    remaining = consume(vid)

    log.info("query", extra={
        "question": req.question[:200], "abstained": res.get("abstained"),
        "confidence": res.get("confidence"), "latency_s": latency,
        "citations": res.get("citations", []),
    })

    return ChatResponse(
        answer=res.get("answer"),
        claims=[Claim(**c) for c in res.get("claims", [])],
        citations=res.get("citations", []),
        sources=[Source(**_src(s)) for s in res.get("source_chunks", [])],
        confidence=res.get("confidence", 0.0),
        abstained=res.get("abstained", False),
        abstain_reason=res.get("abstain_reason"),
        claims_dropped=res.get("claims_dropped", 0),
        latency_s=latency,
        rewritten_query=res.get("rewritten_query"),
        session_id=conversation_id,
        questions_remaining=remaining,
        intent=cls.intent.value,
    )


@router.get("/conversations", response_model=List[ConversationSummary])
def list_conversations(request: Request, response: Response):
    from app.chat import store
    vid = _visitor_id(request, response)
    return [ConversationSummary(**c) for c in store.list_conversations(vid)]


@router.get("/conversations/{conversation_id}", response_model=List[StoredTurn])
def get_conversation(conversation_id: str, request: Request, response: Response):
    from app.chat import store
    vid = _visitor_id(request, response)
    if not store.exists(conversation_id, vid):
        raise HTTPException(404, "Conversation not found.")
    return [StoredTurn(**t) for t in store.get_turns(conversation_id)]


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, request: Request, response: Response):
    from app.chat import store
    from app.ingestion import vector_store as vs
    vid = _visitor_id(request, response)
    if not store.delete_conversation(conversation_id, vid):
        raise HTTPException(404, "Conversation not found.")
    # Uploaded documents are scoped to the conversation, so they go with it.
    removed = vs.delete_session_chunks(conversation_id)
    return {"deleted": conversation_id, "removed_chunks": removed}


@router.post("/upload", response_model=UploadResponse)
async def upload(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
):
    """Ingest a user-supplied specification, scoped to this session (FR-14).

    Runs the same clause-aware chunker and embedding model as the shipped
    corpus, so an uploaded document is a first-class citizen in retrieval -
    not a second-rate path.
    """
    from app.chat import store
    from app.ingestion.upload import UploadError, ingest_upload
    from app.ingestion import vector_store as vs

    vid = _visitor_id(request, response)

    # MUST use the same conversation id the chat route uses (ERROR_LOG E-026).
    # This route previously used the old in-memory session store while /chat
    # had moved to SQLite, so uploads were tagged with one id and retrieval
    # filtered on another - the document indexed successfully and was then
    # invisible to every question.
    if session_id and store.exists(session_id, vid):
        conversation_id = session_id
    else:
        conversation_id = store.create_conversation(vid, "Uploaded document")

    try:
        existing = len({c.get("spec_id") for c in vs.session_chunks(conversation_id)})
    except Exception:                              # noqa: BLE001
        existing = 0

    tmp = Path(tempfile.gettempdir()) / f"upl_{secrets.token_hex(8)}.pdf"
    try:
        with tmp.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)
        result = ingest_upload(tmp, file.filename or "document.pdf",
                               conversation_id, existing_docs=existing)
    except UploadError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:                       # noqa: BLE001
        log.exception("upload failed")
        raise HTTPException(500, f"Could not process the document: {exc}") from exc
    finally:
        tmp.unlink(missing_ok=True)

    return UploadResponse(
        spec_id=result.spec_id, spec_version=result.spec_version,
        pages=result.pages, chunks_added=result.chunks_added,
        seconds=result.seconds, warnings=result.warnings,
        session_id=conversation_id,
    )


@router.delete("/session/{session_id}/documents")
def clear_documents(session_id: str):
    from app.ingestion import vector_store as vs
    removed = vs.delete_session_chunks(session_id)
    return {"removed_chunks": removed}
