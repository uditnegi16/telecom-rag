"""FastAPI application (FR-09)."""

from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router

app = FastAPI(
    title="TelecomRAG",
    description=(
        "Grounded question answering over 3GPP specifications. "
        "Every claim carries a clause citation; the system abstains rather "
        "than guessing when evidence is insufficient."
    ),
    version="1.0.0",
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
    return {"service": "TelecomRAG", "docs": "/docs", "health": "/api/v1/health"}


@app.middleware("http")
async def add_timing(request, call_next):
    t0 = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{time.time() - t0:.3f}"
    return response
