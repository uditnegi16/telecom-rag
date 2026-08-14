"""
Token-budget-aware Groq client.

WHY THIS MODULE EXISTS (traceability: NFR-01; decisions D-011, D-018, D-019)
---------------------------------------------------------------------------
Groq's free tier binds on TOKENS PER MINUTE (~6,000), not requests. At 3
chunks x ~450 tokens plus prompt, a single RAG call costs ~1,700 tokens, so
the ceiling is roughly 3 queries/minute. A naive eval loop over 85 questions
with a verifier pass would spend most of its wall clock in 429 backoff.

Three mitigations, all implemented here:
  1. On-disk response cache keyed by hash(model + prompt + params). Re-running
     an unchanged config costs ZERO tokens. This is what makes iterating on
     one component at a time affordable.
  2. A local token-bucket that paces requests BEFORE sending, so we mostly
     avoid 429s instead of reacting to them.
  3. Reactive backoff that reads Groq's rate-limit response headers
     (x-ratelimit-remaining-tokens, retry-after) rather than guessing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections import deque
from pathlib import Path
from typing import Optional

from groq import Groq

from app.config import CFG

log = logging.getLogger("telecomrag.llm")


class LLMBadRequest(Exception):
    """Deterministic 400 from the provider. Not retryable."""


class TokenBucket:
    """Sliding-window pacer for tokens/min and requests/min.

    THREE BUGS FIXED HERE (ERROR_LOG E-013), all found when a single query
    appeared to hang for ten minutes while the Groq account was in fact
    healthy with 944/1000 requests remaining:

    1. INFINITE LOOP. If `estimated_tokens` exceeded `self.tpm`, the exit
       condition could never be satisfied - not even with an empty window -
       so it slept 60s in a loop forever. A pacer must never be able to
       block a request that will never fit; that is a configuration error
       and should raise, not sleep.
    2. SILENT. It slept with no output, so a long legitimate wait was
       indistinguishable from a hang. Anything that can block for minutes
       must say so.
    3. NO CEILING. There was no bound on total wait. Now capped, and it
       raises rather than blocking indefinitely.
    """

    def __init__(self, tokens_per_min: int, requests_per_min: int,
                 max_wait_s: float = 90.0, verbose: bool = True):
        self.tpm = tokens_per_min
        self.rpm = requests_per_min
        self.max_wait_s = max_wait_s
        self.verbose = verbose
        self._events: deque = deque()   # (timestamp, tokens)

    def _prune(self, now: float) -> None:
        while self._events and now - self._events[0][0] > 60.0:
            self._events.popleft()

    def acquire(self, estimated_tokens: int) -> float:
        if estimated_tokens > self.tpm:
            raise ValueError(
                f"Single request estimated at {estimated_tokens} tokens exceeds "
                f"the {self.tpm} TPM budget - it can never be scheduled. "
                f"Reduce rerank_top_n or max_chunk_tokens in config.py."
            )

        waited = 0.0
        while True:
            now = time.time()
            self._prune(now)
            used = sum(t for _, t in self._events)
            if used + estimated_tokens <= self.tpm and len(self._events) < self.rpm:
                self._events.append((now, estimated_tokens))
                return waited

            if waited >= self.max_wait_s:
                raise RuntimeError(
                    f"Token pacer waited {waited:.0f}s without a slot "
                    f"({used}/{self.tpm} TPM used). Budget likely misconfigured."
                )

            oldest = self._events[0][0] if self._events else now
            sleep_for = min(max(0.5, 60.0 - (now - oldest) + 0.25),
                            self.max_wait_s - waited)
            if self.verbose:
                # logging, NOT print: print() from a worker thread inside
                # uvicorn does not reliably reach the console, so a minutes-
                # long pacer wait produced no output at all and looked like a
                # hang (ERROR_LOG E-017).
                log.warning("pacer: %d/%d TPM used, waiting %.1fs",
                            used, self.tpm, sleep_for)
            time.sleep(sleep_for)
            waited += sleep_for


class ResponseCache:
    """Content-addressed on-disk cache. Deterministic because temperature=0."""

    def __init__(self, directory: str):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(model: str, prompt: str, **params) -> str:
        blob = json.dumps(
            {"model": model, "prompt": prompt, **params}, sort_keys=True
        ).encode()
        return hashlib.sha256(blob).hexdigest()

    def get(self, key: str) -> Optional[str]:
        path = self.dir / f"{key}.json"
        if path.exists():
            self.hits += 1
            return json.loads(path.read_text())["response"]
        self.misses += 1
        return None

    def put(self, key: str, response: str) -> None:
        (self.dir / f"{key}.json").write_text(json.dumps({"response": response}))

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 3) if total else 0.0,
        }


class GroqLLM:
    """Thin wrapper. Deliberately provider-shaped so a local Ollama backend can
    be dropped in for the air-gapped on-prem story (D-011) without touching
    callers."""

    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.getenv("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY not set. Copy .env.example to .env")
        self.client = Groq(api_key=key)
        self.bucket = TokenBucket(
            CFG.tokens_per_minute, CFG.requests_per_minute,
            max_wait_s=CFG.max_pacer_wait_s, verbose=CFG.pacer_verbose,
        )
        self.cache = ResponseCache(CFG.cache_dir) if CFG.cache_enabled else None
        self.total_tokens = 0
        self.total_wait = 0.0
        self.rate_limit_hits = 0

    def complete(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        json_mode: bool = False,
    ) -> str:
        model = model or CFG.gen_model
        max_tokens = max_tokens or CFG.max_output_tokens
        temperature = CFG.temperature if temperature is None else temperature

        cache_key = None
        if self.cache:
            cache_key = ResponseCache.key(
                model, prompt, max_tokens=max_tokens,
                temperature=temperature, json_mode=json_mode,
            )
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        estimated = len(prompt) // 4 + max_tokens
        self.total_wait += self.bucket.acquire(estimated)

        kwargs = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": CFG.llm_request_timeout_s,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        text = self._send_with_backoff(kwargs)

        if self.cache and cache_key:
            self.cache.put(cache_key, text)
        return text

    def _send_with_backoff(self, kwargs: dict, attempts: int = 5) -> str:
        delay = 2.0
        last_err = None
        for _ in range(attempts):
            try:
                resp = self.client.chat.completions.create(**kwargs)
                if getattr(resp, "usage", None):
                    self.total_tokens += resp.usage.total_tokens
                return resp.choices[0].message.content or ""
            except Exception as exc:                     # noqa: BLE001
                last_err = exc
                msg = str(exc)
                if "429" in msg or "rate limit" in msg.lower():
                    self.rate_limit_hits += 1
                    time.sleep(self._retry_after(msg, delay))
                    delay = min(delay * 2, 60.0)
                    continue
                # A 400 is deterministic - the same prompt will fail the same
                # way every time. Retrying it 5 times wastes ~30s and buries
                # the real cause (E-010). Fail fast with a typed error so
                # callers can skip the item instead of aborting the run.
                if "400" in msg or "json_validate_failed" in msg:
                    raise LLMBadRequest(msg) from exc
                raise
        raise RuntimeError(f"Groq call failed after {attempts} attempts: {last_err}")

    @staticmethod
    def _retry_after(message: str, default: float) -> float:
        """Groq's 429 body states the wait explicitly, e.g. 'try again in
        6m11.52s'. Parsing it beats guessing."""
        import re
        m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", message)
        if m:
            minutes = int(m.group(1) or 0)
            return minutes * 60 + float(m.group(2)) + 0.5
        return default

    def stats(self) -> dict:
        out = {
            "total_tokens": self.total_tokens,
            "seconds_waited_on_budget": round(self.total_wait, 1),
            "rate_limit_hits": self.rate_limit_hits,
        }
        if self.cache:
            out["cache"] = self.cache.stats()
        return out
