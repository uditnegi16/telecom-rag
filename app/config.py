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
    # MEASURED, not guessed (scripts/sweep_tau.py, RUN-006). On 47 answerable
    # and 25 adversarial questions: answerable median 0.996, adversarial
    # median 0.029. At 0.90 -> 46/47 answered, 2.1% false refusal, 96%
    # abstention correctness (Youden J = 0.939).
    #
    # This was reverted to a guessed 0.35 by a later patch that shipped the
    # whole file; at 0.35 the gate lets 24 of 25 adversarial questions through
    # and the fail-closed behaviour rests entirely on the second line of
    # defence (ERROR_LOG E-030).
    tau_abstain: float = 0.90

    # --- generation (D-011, D-019, D-027) ----------------------------------
    # Measured free-tier limits (from live x-ratelimit response headers):
    #   llama-3.3-70b-versatile : 12000 TPM /  1000 requests per DAY
    #   llama-3.1-8b-instant    :  6000 TPM / 14400 requests per DAY
    #
    # The 70B model's 1000/day cap is the binding constraint for a public
    # demo, not its token rate: at 3 calls per turn that is ~330 questions
    # across ALL visitors for the whole day, and development consumes it
    # before a recruiter ever clicks the link (D-027, E-019).
    #
    # 8b-instant gives 14x the daily headroom. The quality cost is real but
    # bounded, because the pipeline does not depend on the generator being
    # careful: citations are validated deterministically, claims are checked
    # by entailment, and anything unparseable fails closed. A weaker
    # generator degrades coverage, not correctness.
    gen_model: str = "llama-3.1-8b-instant"
    verify_model: str = "llama-3.1-8b-instant"
    temperature: float = 0.0                     # DEF-05
    max_output_tokens: int = 700
    prompt_version: str = "v5-complete-sentences"

    # --- rate limiting (NFR-01, D-018) -------------------------------------
    # Measured from live response headers, not guessed:
    #   llama-3.3-70b-versatile : 12000 TPM / 1000 RPD
    #   llama-3.1-8b-instant    :  6000 TPM / 14400 RPD
    # Configured to the GENERATION model's limit (E-013).
    tokens_per_minute: int = 6000     # 8b-instant limit
    requests_per_minute: int = 30
    cache_dir: str = "./data/processed/llm_cache"
    cache_enabled: bool = True
    max_pacer_wait_s: float = 45.0
    llm_request_timeout_s: float = 30.0
    # Total budget for one answer. Exceeding it returns a clear, honest
    # message instead of leaving the UI spinning forever (E-017).
    pipeline_budget_s: float = 75.0
    pacer_verbose: bool = True

    # --- verification (D-010) ----------------------------------------------
    overlap_prefilter: float = 0.10   # free pre-filter, NOT the real check
    require_entailment: bool = True

    def config_hash(self) -> str:
        blob = json.dumps(asdict(self), sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()[:12]


CFG = Config()
