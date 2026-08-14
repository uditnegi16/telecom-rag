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

from app.config import CFG
from app.ingestion.clause_chunker import chunk_spec, summarise
# Import the REAL parser. This script previously carried its own copy using
# get_text("text"), which meant the gate-G2 inspection reported on different
# extraction than the pipeline actually used (ERROR_LOG E-004). An inspection
# tool that does not share the pipeline's code inspects a fiction.
from app.ingestion.parser import parse_pdf, spec_meta_from_filename as spec_meta


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

    # Clause-depth histogram: a healthy 3GPP spec has many deep clauses
    # (5.1.1.2.3). If almost everything is depth 1-2, detection is still
    # collapsing sub-clauses into their parents.
    from collections import Counter
    depths = Counter(
        len(c.clause_id.split(".")) if c.clause_id[0].isdigit() else 0
        for c in all_chunks
    )
    print("\nclause depth histogram (0 = annex/unknown):")
    for d in sorted(depths):
        print(f"   depth {d}: {depths[d]:5d}")

    print(f"\n{'='*70}\n10 RANDOM CHUNKS - READ THESE. This is gate G2.\n")
    for c in random.sample(all_chunks, min(10, len(all_chunks))):
        print(f"--- {c.chunk_id} | p{c.page_start}-{c.page_end} | "
              f"{c.token_estimate}tok | {c.content_type}")
        print(f"    path: {c.heading_path}")
        print(f"    body: {c.body[:240]}...\n")


if __name__ == "__main__":
    main()
