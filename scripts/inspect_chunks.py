"""
Gate G2: inspect chunks BEFORE indexing.

WHY THIS IS A GATE AND NOT A NICETY
-----------------------------------
Clause regexes are brittle against unusual layouts, and a chunking failure is
SILENT - it degrades retrieval quality and looks like a model problem. Both
real bugs found during development (ERROR_LOG E-001, E-002) were silent drops
that only surfaced by looking at the output. Ten minutes here saves hours of
misattributed debugging later.

Look for:
  * unknown_clause / fallback_chunks > 0        -> clause detection failed
  * tokens_max at the cap for many chunks       -> sub-splitting dominating
  * tokens_min very small                       -> stub clauses leaking through
  * clause ids that look like figure numbers    -> regex over-matching
  * breadcrumbs that skip a level               -> hierarchy walk is wrong
"""

import random
import sys
from pathlib import Path

import fitz  # PyMuPDF

from app.config import CFG
from app.ingestion.clause_chunker import chunk_spec, summarise


def parse_pdf(path: Path):
    doc = fitz.open(path)
    return [
        {"page_number": i + 1, "text": page.get_text("text")}
        for i, page in enumerate(doc)
    ]


def spec_meta(path: Path):
    """Filename convention: TS_28552_v18.5.0.pdf"""
    stem = path.stem
    parts = stem.split("_")
    if len(parts) >= 3:
        num = parts[1]
        spec_id = f"{parts[0]} {num[:2]}.{num[2:]}" if num.isdigit() else f"{parts[0]} {num}"
        return spec_id, parts[2].upper()
    return stem, "UNKNOWN"


def main():
    raw = Path(CFG.corpus_dir)
    pdfs = sorted(raw.glob("*.pdf"))
    if not pdfs:
        sys.exit(f"No PDFs in {raw}. See scripts/CORPUS.md (gate G1).")

    all_chunks = []
    for pdf in pdfs:
        spec_id, version = spec_meta(pdf)
        pages = parse_pdf(pdf)
        chunks = chunk_spec(pages, spec_id, version)
        all_chunks.extend(chunks)
        s = summarise(chunks)
        print(f"\n{spec_id} {version}  ({len(pages)} pages)")
        print(f"  {s}")
        if s.get("fallback_chunks") or s.get("unknown_clause"):
            print("  *** WARNING: clause detection failed on this spec.")

    print(f"\n{'='*70}\nTOTAL: {len(all_chunks)} chunks across {len(pdfs)} specs")
    print(summarise(all_chunks))

    print(f"\n{'='*70}\n10 RANDOM CHUNKS - READ THESE. This is gate G2.\n")
    for c in random.sample(all_chunks, min(10, len(all_chunks))):
        print(f"--- {c.chunk_id} | p{c.page_start}-{c.page_end} | "
              f"{c.token_estimate}tok | {c.content_type}")
        print(f"    path: {c.heading_path}")
        print(f"    body: {c.body[:240]}...\n")


if __name__ == "__main__":
    main()
