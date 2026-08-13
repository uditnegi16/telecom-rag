"""
Neutralise instruction-like text inside retrieved passages.

WHY (traceability: FR-11)
-------------------------
Retrieved content is DATA, not commands. A specification passage - or a
maliciously crafted document in a real deployment - could contain text that
reads as an instruction to the model. This is a live concern for any RAG system
and worth raising unprompted in an interview: the citation check and entailment
verifier also limit the blast radius, since an injected instruction cannot
produce a claim that is entailed by a real cited clause.
"""

from __future__ import annotations

import re

PATTERNS = [
    (re.compile(r"ignore (?:all |any )?(?:previous|prior|above) instructions?", re.I),
     "[neutralised]"),
    (re.compile(r"disregard (?:the )?(?:above|previous|system)", re.I), "[neutralised]"),
    (re.compile(r"you are now\b", re.I), "[neutralised]"),
    (re.compile(r"^\s*system\s*:", re.I | re.M), "text:"),
    (re.compile(r"^\s*assistant\s*:", re.I | re.M), "text:"),
    (re.compile(r"</?(?:system|instruction)>", re.I), ""),
]


def sanitize_chunk(text: str) -> str:
    if not text:
        return ""
    out = text
    for pattern, replacement in PATTERNS:
        out = pattern.sub(replacement, out)
    return out
