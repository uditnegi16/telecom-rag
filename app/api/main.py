"""FastAPI application (FR-09)."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
log = logging.getLogger("telecomrag")

STATE = {"ready": False, "warmup_s": 0.0, "warmup_error": None}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Load models BEFORE serving traffic.

    WHY (ERROR_LOG E-018): the embedding model and cross-encoder load lazily
    on first use. Inside a request that cost ~100 s of CPU on a cold process
    - which then blew the 75 s pipeline budget, so the FIRST question after
    every restart timed out and looked like a rate limit. On a deployed demo
    that is the recruiter's first click.

    Warming up at startup moves the cost to boot, where the container health
    check already tolerates it, and keeps it out of the request budget.
    """
    t0 = time.time()
    log.info("warming up models…")
    try:
        from app.ingestion.embedder import get_model
        from app.retrieval.reranker import get_reranker

        get_model().encode(["warmup"])
        get_reranker().predict([["warmup", "warmup"]])

        from app.pipeline import _get_bm25
        _get_bm25()

        STATE["ready"] = True
        STATE["warmup_s"] = round(time.time() - t0, 1)
        log.info("ready in %.1fs", STATE["warmup_s"])
    except Exception as exc:                       # noqa: BLE001
        STATE["warmup_error"] = str(exc)
        log.exception("warmup failed - requests will be slow or fail")

    yield


app = FastAPI(
    title="TelecomRAG",
    description=(
        "Grounded question answering over 3GPP specifications. "
        "Every claim carries a clause citation; the system abstains rather "
        "than guessing when evidence is insufficient."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/")
def root():
    return {"service": "TelecomRAG", "docs": "/docs",
            "health": "/api/v1/health", "ready": STATE["ready"]}


@app.middleware("http")
async def add_timing(request, call_next):
    t0 = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{time.time() - t0:.3f}"
    return response
