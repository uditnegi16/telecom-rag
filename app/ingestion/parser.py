"""
PDF parsing with PyMuPDF.

WHY PyMuPDF AND NOT pypdf (decision D-002)
------------------------------------------
The fork base used pypdf. Switched because the clause chunker depends on
line structure surviving extraction: pypdf's extract_text() collapses layout
aggressively, and the fork's _clean_text() then ran `re.sub(r'\\s+',' ')`,
flattening every newline. That destroys exactly the line boundaries the
clause regex needs.

PyMuPDF's get_text("text") preserves line breaks. We clean conservatively:
fix hyphenation and collapse runs of spaces WITHIN a line, but never across
lines.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

import fitz  # PyMuPDF

# 3GPP running headers/footers repeat on every page and pollute chunks.
NOISE_PATTERNS = [
    re.compile(r"^\s*3GPP\s+T[SR]\s+\d+\.\d+.*?\(\d{4}-\d{2}\)\s*$", re.I),
    re.compile(r"^\s*ETSI\s+T[SR]\s+\d+.*$", re.I),
    re.compile(r"^\s*Release\s+\d+\s*$", re.I),
    re.compile(r"^\s*\d+\s*$"),                       # bare page numbers
    re.compile(r"^\s*3GPP\s*$", re.I),
]


def parse_pdf(path: str | Path) -> List[dict]:
    """Return [{"page_number": int, "text": str}] preserving line structure."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    doc = fitz.open(path)
    pages = []
    for i, page in enumerate(doc):
        raw = page.get_text("text")
        cleaned = _clean(raw)
        if len(cleaned.strip()) < 20:
            continue
        pages.append({"page_number": i + 1, "text": cleaned})
    doc.close()

    if not pages:
        raise ValueError(f"No extractable text in {path.name} (scanned PDF?)")
    return pages


def _clean(text: str) -> str:
    out_lines = []
    for line in text.split("\n"):
        if any(p.match(line) for p in NOISE_PATTERNS):
            continue
        # Collapse spaces WITHIN the line only. Never touch newlines.
        line = re.sub(r"[ \t]+", " ", line).rstrip()
        # Repair hyphenation split across the line break.
        if out_lines and out_lines[-1].endswith("-") and line[:1].islower():
            out_lines[-1] = out_lines[-1][:-1] + line.lstrip()
            continue
        if line:
            out_lines.append(line)
    return "\n".join(out_lines)


def spec_meta_from_filename(path: str | Path) -> tuple[str, str]:
    """Convention: TS_28552_v18.5.0.pdf -> ("TS 28.552", "V18.5.0")"""
    stem = Path(path).stem
    parts = stem.split("_")
    if len(parts) >= 3 and parts[1].isdigit():
        num = parts[1]
        return f"{parts[0]} {num[:2]}.{num[2:]}", parts[2].upper()
    if len(parts) >= 3:
        return f"{parts[0]} {parts[1]}", parts[2].upper()
    return stem, "UNKNOWN"
