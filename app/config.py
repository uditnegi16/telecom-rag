"""
Central configuration. Every tunable lives here.

WHY (traceability: NFR-08, DEF-04)
-----------------------------------
The forked codebase had thresholds scattered across modules
(RELEVANCE_THRESHOLD in reranker.py, CONFIDENCE_THRESHOLD in confidence.py),
neither tuned, and the reranker filtered candidates before the gate could see
the score distribution. Centralising them makes the tau sweep (RUN-006)
possible and makes every run's config hashable for reproducibility.
"""

import hashlib
import json
import os
from dataclasses import dataclass, asdict
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # --- corpus (D-001) -----------------------------------------------------
    corpus_dir: str = "data/raw"
    release: str = "Rel-18"

    # --- chunking (D-003) ---------------------------------------------------
    max_chunk_tokens: int = 450
    sub_split_overlap_tokens: int = 60

    # --- embedding (D-004) --------------------------------------------------
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384

    # --- vector store (D-005) ----------------------------------------------
    chroma_path: str = os.getenv("CHROMA_PATH", "./data/processed/chroma")
    collection: str = "clauses_bge_small_v1"   # versioned: see E-000g

    # --- retrieval (D-006, D-007, D-017) ------------------------------------
    dense_top_k: int = 25
    bm25_top_k: int = 25
    rrf_k: int = 60
    rerank_top_n: int = 3          # D-017: small k, Groq 6k TPM budget
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # --- abstention (D-009) -- THE tuned parameter, swept in RUN-006 --------
    tau_abstain: float = 0.35

    # --- generation (D-011, D-019) -----------------------------------------
    gen_model: str = "llama-3.3-70b-versatile"
    verify_model: str = "llama-3.1-8b-instant"   # D-019: cheap verifier tier
    temperature: float = 0.0                     # DEF-05
    max_output_tokens: int = 700
    prompt_version: str = "v2-json-citations"

    # --- rate limiting (NFR-01, D-018) -------------------------------------
    tokens_per_minute: int = 6000
    requests_per_minute: int = 30
    cache_dir: str = "./data/processed/llm_cache"
    cache_enabled: bool = True

    # --- verification (D-010) ----------------------------------------------
    overlap_prefilter: float = 0.10   # free pre-filter, NOT the real check
    require_entailment: bool = True

    def config_hash(self) -> str:
        blob = json.dumps(asdict(self), sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()[:12]


CFG = Config()
