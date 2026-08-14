"""
Assembles the components into a runnable answer function.

WHY A SEPARATE MODULE
---------------------
`answer_graph.build_answer_fn` takes its dependencies explicitly rather than
reaching for globals, so the graph logic stays testable with fakes. This module
is the one place that knows about the real ChromaDB collection, the real BM25
index and the real Groq client - the composition root.

Usage:
    from app.pipeline import get_answer_fn
    answer = get_answer_fn()
    print(answer("What does the perceivedSeverity field indicate?"))
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Callable, Optional

from app.config import CFG

BM25_PATH = "data/processed/bm25.pkl"

_bm25 = None
_llm = None


def _get_bm25():
    global _bm25
    if _bm25 is None:
        from app.retrieval.bm25_index import BM25Index

        if not Path(BM25_PATH).exists():
            raise SystemExit(
                f"{BM25_PATH} missing. Run `python -m scripts.ingest` first."
            )
        _bm25 = BM25Index.load(BM25_PATH)
    return _bm25


def _get_llm():
    global _llm
    if _llm is None:
        from app.llm.groq_client import GroqLLM

        _llm = GroqLLM()
    return _llm


def build_retrieve_fn(
    use_bm25: bool = True,
    use_reranker: bool = True,
    top_n: Optional[int] = None,
    session_id: Optional[str] = None,
) -> Callable[[str], dict]:
    """Flags exist for the ablation. RUN-001 is dense-only, no reranker; each
    later run turns one on. Wiring them here means an ablation step is a
    parameter change, not a code edit - which is what keeps runs comparable."""
    from app.ingestion import vector_store as vs
    from app.retrieval.search import retrieve

    if not use_bm25:
        bm25 = _NullBM25()
    elif session_id:
        # Uploaded chunks are not in the prebuilt BM25 index, and rebuilding
        # it globally would leak one session's documents into everyone's
        # lexical search. A small per-session index over the uploads is
        # merged with the base index instead (D-026).
        bm25 = _SessionBM25(_get_bm25(), session_id)
    else:
        bm25 = _get_bm25()

    if use_reranker:
        from app.retrieval.reranker import rerank
    else:
        def rerank(query, chunks):
            # Preserve fusion order and synthesise a score so the abstention
            # gate still has something to threshold on.
            for i, c in enumerate(chunks):
                c["reranker_score"] = round(max(0.0, 1.0 - i * 0.05), 4)
            return chunks

    dense = functools.partial(vs.dense_search, session_id=session_id)

    return functools.partial(
        retrieve,
        dense_search=dense,
        bm25_index=bm25,
        chunk_lookup=vs.get_chunk,
        reranker=rerank,
        top_n=top_n,
    )


class _NullBM25:
    """Dense-only ablation: contributes an empty ranked list to the fusion."""

    def search(self, query: str, top_k: int):
        return []


class _SessionBM25:
    """Base index plus a session-local index over uploaded chunks."""

    def __init__(self, base, session_id: str):
        self.base = base
        self.session_id = session_id
        self._local = None

    def _get_local(self):
        if self._local is None:
            from app.ingestion import vector_store as vs
            from app.retrieval.bm25_index import BM25Index

            chunks = vs.session_chunks(self.session_id)
            self._local = BM25Index().build(chunks) if chunks else _NullBM25()
        return self._local

    def search(self, query: str, top_k: int):
        merged = self.base.search(query, top_k) + self._get_local().search(query, top_k)
        merged.sort(key=lambda x: x[1], reverse=True)
        return merged[:top_k]


def get_answer_fn(
    tau: Optional[float] = None,
    use_bm25: bool = True,
    use_reranker: bool = True,
    verify: bool = True,
    suppress: bool = True,
    session_id: Optional[str] = None,
) -> Callable[[str], dict]:
    from app.graph.answer_graph import build_answer_fn

    return build_answer_fn(
        retrieve_fn=build_retrieve_fn(use_bm25=use_bm25, use_reranker=use_reranker,
                                      session_id=session_id),
        llm=_get_llm(),
        tau=tau,
        verify=verify,
        suppress=suppress,
    )


def llm_stats() -> dict:
    return _llm.stats() if _llm else {}
