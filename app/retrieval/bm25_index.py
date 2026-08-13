"""
BM25 lexical index.

WHY (traceability: FR-04; decision D-006)
-----------------------------------------
Dense embeddings are weak on rare exact identifiers, and 3GPP questions are
made almost entirely of them: "TS 28.552", "5QI", "gNB-CU-UP", "NRCellDU",
"perceivedSeverity". These tokens are near-meaningless in embedding space but
are perfect BM25 matches. Dense-only retrieval was the RUN-001 baseline; this
module is the RUN-003 delta, and the gain should be concentrated on
identifier-style questions. If the gain is uniform across question types,
something is wrong with the analysis.
"""

from __future__ import annotations

import pickle
import re
from pathlib import Path
from typing import List, Tuple

from rank_bm25 import BM25Okapi

# Keep alphanumeric-with-separators intact: "TS 28.552", "gNB-CU-UP", "5QI".
# A naive \w+ tokenizer shreds exactly the tokens BM25 is here to catch.
TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[.\-_][A-Za-z0-9]+)*")


def tokenize(text: str) -> List[str]:
    tokens = [t.lower() for t in TOKEN_RE.findall(text)]
    expanded: List[str] = []
    for t in tokens:
        expanded.append(t)
        # Also index the split parts so "28.552" matches a query for "28 552"
        # and "gnb-cu-up" matches "gnb cu up".
        if any(sep in t for sep in ".-_"):
            expanded.extend(p for p in re.split(r"[.\-_]", t) if p)
    return expanded


class BM25Index:
    def __init__(self):
        self.bm25: BM25Okapi | None = None
        self.chunk_ids: List[str] = []

    def build(self, chunks: List[dict]) -> "BM25Index":
        self.chunk_ids = [c["chunk_id"] for c in chunks]
        corpus = [tokenize(c["text"]) for c in chunks]
        self.bm25 = BM25Okapi(corpus)
        return self

    def search(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        if self.bm25 is None:
            raise RuntimeError("Index not built or loaded.")
        scores = self.bm25.get_scores(tokenize(query))
        ranked = sorted(
            zip(self.chunk_ids, scores), key=lambda x: x[1], reverse=True
        )
        return [(cid, float(s)) for cid, s in ranked[:top_k] if s > 0]

    def save(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump({"bm25": self.bm25, "chunk_ids": self.chunk_ids}, fh)

    @classmethod
    def load(cls, path: str) -> "BM25Index":
        obj = cls()
        with open(path, "rb") as fh:
            data = pickle.load(fh)
        obj.bm25 = data["bm25"]
        obj.chunk_ids = data["chunk_ids"]
        return obj
