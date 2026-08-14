"""API routes (FR-09, FR-12)."""

from __future__ import annotations

import logging
import time
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import CFG

router = APIRouter()
log = logging.getLogger("telecomrag")

_answer_fn = None


def _get_answer_fn(tau: Optional[float] = None):
    global _answer_fn
    if _answer_fn is None or tau is not None:
        from app.pipeline import get_answer_fn

        fn = get_answer_fn(tau=tau)
        if tau is None:
            _answer_fn = fn
        return fn
    return _answer_fn


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)
    tau: Optional[float] = Field(None, ge=0.0, le=1.0)


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
    answer: Optional[str]
    claims: List[Claim] = []
    citations: List[str] = []
    sources: List[Source] = []
    confidence: float
    abstained: bool
    abstain_reason: Optional[str] = None
    claims_dropped: int = 0
    latency_s: float


@router.get("/health")
def health():
    from app.ingestion import vector_store as vs

    count = vs.count()
    return {
        "status": "ok" if count else "index_empty",
        "chunks_indexed": count,
        "collection": CFG.collection,
        "embedding_model": CFG.embedding_model,
        "gen_model": CFG.gen_model,
        "verify_model": CFG.verify_model,
        "tau": CFG.tau_abstain,
        "prompt_version": CFG.prompt_version,
    }


@router.get("/corpus")
def corpus():
    """What the system can and cannot answer from - important context for a
    user reading an abstention."""
    import json
    from collections import Counter
    from pathlib import Path

    path = Path("data/processed/chunks.json")
    if not path.exists():
        raise HTTPException(503, "Corpus not ingested.")
    chunks = json.loads(path.read_text(encoding="utf-8"))
    specs = Counter(f"{c['spec_id']} {c['spec_version']}" for c in chunks)
    return {"total_chunks": len(chunks), "specs": dict(specs)}


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    t0 = time.time()
    try:
        answer_fn = _get_answer_fn(req.tau)
        res = answer_fn(req.question)
    except Exception as exc:                       # noqa: BLE001
        log.exception("answer failed")
        raise HTTPException(500, f"Pipeline error: {exc}") from exc

    latency = round(time.time() - t0, 3)

    # FR-12: structured query log
    log.info(
        "query",
        extra={
            "question": req.question[:200],
            "abstained": res.get("abstained"),
            "confidence": res.get("confidence"),
            "latency_s": latency,
            "citations": res.get("citations", []),
        },
    )

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
    )


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
        "body": (c.get("body") or "")[:2000],
    }
