"""
PDF parsing with layout-aware line reconstruction.

WHY NOT get_text("text")  (ERROR_LOG E-004)
-------------------------------------------
PyMuPDF's "text" mode emits each PDF text SPAN on its own line. ETSI documents
place a clause number and its title in separate spans at the same vertical
position (they are laid out with tab stops), so "text" mode yields:

    5.1.1.2
    RegistrationRequest counter

instead of "5.1.1.2  RegistrationRequest counter". No heading regex can match
that, and on TS 28.532 exactly 9 of 10,335 lines matched - clause detection
had effectively collapsed and the whole document fell through to the
window-splitting fallback.

Fix: extract with get_text("dict"), which carries a bbox per span, then group
spans into VISUAL lines by their y-coordinate and order them by x. This
reconstructs what a human sees on the page, which is what the clause structure
actually lives in.

Side benefit: table cells on one visual row rejoin into one line, so tables
stop exploding into hundreds of one-word lines.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

import fitz  # PyMuPDF

Y_TOLERANCE = 2.5      # points; spans within this y-distance are one visual line
GAP_FOR_TAB = 12.0     # x-gap wider than this becomes a double space (tab stop)

# Running headers/footers. NOTE these use `search`, not `match` (E-007):
# visual-line reconstruction joins the page header, the page number and the
# ETSI footer into ONE line, e.g.
#   "3GPP TS 28.532 version 18.7.0 Release 18  63  ETSI TS 128 532 V18.7.0 (2025-11)"
# An anchored ^...$ pattern misses these entirely and they end up embedded in
# the middle of clause bodies, polluting both retrieval and entailment checks.
NOISE_SEARCH = [
    re.compile(r"3GPP\s+T[SR]\s+\d+\.\d+\s+version\s+[\d.]+\s+Release\s+\d+", re.I),
    re.compile(r"ETSI\s+T[SR]\s+\d{3}\s+\d{3}\s+V[\d.]+", re.I),
]
NOISE_PATTERNS = [
    re.compile(r"^\s*ETSI\s*$", re.I),
    re.compile(r"^\s*3GPP\s*$", re.I),
    re.compile(r"^\s*Release\s+\d+\s*$", re.I),
    re.compile(r"^\s*\d{1,4}\s*$"),                     # bare page numbers
]

# Table-of-contents entries: "5.1.1 Something ......... 47"
TOC_LINE = re.compile(r"\.{4,}\s*\d+\s*$")


def parse_pdf(path: str | Path) -> List[dict]:
    """Return [{"page_number": int, "text": str}] with visual lines restored."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    doc = fitz.open(path)
    pages = []
    for i, page in enumerate(doc):
        lines = _visual_lines(page)
        cleaned = _clean(lines)
        if len(cleaned.strip()) < 20:
            continue
        pages.append({"page_number": i + 1, "text": cleaned})
    doc.close()

    if not pages:
        raise ValueError(f"No extractable text in {path.name} (scanned PDF?)")

    return _strip_front_matter(pages)


def _visual_lines(page) -> List[str]:
    """Group spans into visual lines by y-coordinate, ordered by x."""
    data = page.get_text("dict")
    rows: List[tuple] = []      # (y, x, text)

    for block in data.get("blocks", []):
        if block.get("type") != 0:          # 0 = text
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                txt = span.get("text", "")
                if not txt.strip():
                    continue
                x0, y0, _x1, y1 = span["bbox"]
                rows.append(((y0 + y1) / 2.0, x0, txt))

    if not rows:
        return []

    rows.sort(key=lambda r: (r[0], r[1]))

    out: List[str] = []
    current: List[tuple] = []
    current_y = rows[0][0]

    for y, x, txt in rows:
        if abs(y - current_y) <= Y_TOLERANCE:
            current.append((x, txt))
        else:
            out.append(_join(current))
            current = [(x, txt)]
            current_y = y
    if current:
        out.append(_join(current))

    return out


# PDF symbol fonts (Sigma, Delta, subscripts) extract as raw control bytes.
# They pollute embeddings, and Groq's JSON validator rejects any response that
# echoes them - which crashed golden-set drafting (ERROR_LOG E-010).
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]")


def _strip_control(text: str) -> str:
    return CONTROL_CHARS.sub(" ", text)


def _join(spans: List[tuple]) -> str:
    """Concatenate one visual line, inserting a double space across wide gaps.

    The double space matters: it is the separator the clause regex looks for,
    and it is what a tab stop between "5.1.1.2" and its title becomes.
    """
    spans.sort(key=lambda s: s[0])
    parts: List[str] = []
    prev_end = None

    for x, txt in spans:
        if prev_end is not None:
            gap = x - prev_end
            if gap > GAP_FOR_TAB:
                parts.append("  ")
            elif gap > 1.0 and parts and not parts[-1].endswith(" "):
                parts.append(" ")
        parts.append(txt)
        prev_end = x + len(txt) * 4.6      # rough advance estimate

    joined = _strip_control("".join(parts))
    return re.sub(r"[ \t]{3,}", "  ", joined).strip()


def _clean(lines: List[str]) -> str:
    out: List[str] = []
    for line in lines:
        if any(p.match(line) for p in NOISE_PATTERNS):
            continue
        # Strip a header/footer fragment wherever it appears in the line, then
        # drop the line if nothing meaningful survives.
        for pat in NOISE_SEARCH:
            line = pat.sub(" ", line)
        line = re.sub(r"\s{2,}", "  ", line).strip()
        if len(line) < 3 or re.fullmatch(r"[\d\s().-]+", line):
            continue
        if TOC_LINE.search(line):           # table-of-contents entry
            continue
        line = line.rstrip()
        if out and out[-1].endswith("-") and line[:1].islower():
            out[-1] = out[-1][:-1] + line.lstrip()
            continue
        if line:
            out.append(line)
    return "\n".join(out)


def _strip_front_matter(pages: List[dict]) -> List[dict]:
    """Drop everything before clause 1 (Scope).

    ETSI front matter - IPR notices, legal text, modal-verb terminology,
    foreword - contains no specification content but does contain prose that
    can be mistaken for headings. The ToC is already removed by dot-leader
    detection; this removes the rest.
    """
    start_re = re.compile(r"^1\s{1,}Scope\s*$", re.I)
    for idx, page in enumerate(pages):
        for line in page["text"].split("\n"):
            if start_re.match(line.strip()):
                return pages[idx:]
    return pages          # pattern not found: keep everything, do not guess


def spec_meta_from_filename(path: str | Path) -> tuple[str, str]:
    """Convention: TS_28552_v18.11.0.pdf -> ("TS 28.552", "V18.11.0")"""
    stem = Path(path).stem
    parts = stem.split("_")
    if len(parts) >= 3 and parts[1].isdigit():
        num = parts[1]
        return f"{parts[0]} {num[:2]}.{num[2:]}", parts[2].upper()
    if len(parts) >= 3:
        return f"{parts[0]} {parts[1]}", parts[2].upper()
    return stem, "UNKNOWN"
