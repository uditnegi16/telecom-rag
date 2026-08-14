"""
Diagnostic: what do real ETSI PDFs actually look like to the chunker?

Run:  python -m scripts.diagnose
Paste the entire output back.
"""
import re
from pathlib import Path

from app.config import CFG
from app.ingestion.parser import parse_pdf, spec_meta_from_filename
from app.ingestion.clause_chunker import CLAUSE_RE, ANNEX_RE, _looks_like_title

pdfs = sorted(Path(CFG.corpus_dir).glob("*.pdf"))
pdf = pdfs[0]
spec_id, version = spec_meta_from_filename(pdf)
pages = parse_pdf(pdf)
print(f"=== {spec_id} {version} | {len(pages)} pages ===\n")

lines, line_pages = [], []
for p in pages:
    for ln in p["text"].split("\n"):
        if ln.strip():
            lines.append(ln.strip())
            line_pages.append(p["page_number"])

print(f"total non-empty lines: {len(lines)}\n")

# 1. Raw lines from an early page (likely table of contents)
print("--- RAW LINES 40-70 (expect table of contents here) ---")
for i in range(40, min(70, len(lines))):
    print(f"  p{line_pages[i]:3d} | {lines[i][:100]!r}")

# 2. Raw lines from mid-document (expect real clause headings)
mid = len(lines) // 2
print(f"\n--- RAW LINES {mid}-{mid+30} (mid-document body) ---")
for i in range(mid, min(mid + 30, len(lines))):
    print(f"  p{line_pages[i]:3d} | {lines[i][:100]!r}")

# 3. Which lines match the regex at all
matches = []
for i, ln in enumerate(lines):
    m = CLAUSE_RE.match(ln) or ANNEX_RE.match(ln)
    if m:
        matches.append((i, line_pages[i], m.group("num"), m.group("title")[:60]))
print(f"\n--- REGEX MATCHED {len(matches)} lines ---")
print("first 25:")
for i, pg, num, title in matches[:25]:
    ok = _looks_like_title(title) if title else False
    print(f"  line{i:6d} p{pg:3d} | {num:12s} | title_ok={ok} | {title!r}")
print("last 10:")
for i, pg, num, title in matches[-10:]:
    print(f"  line{i:6d} p{pg:3d} | {num:12s} | {title!r}")

# 4. Table-of-contents detection: dot leaders
toc = [ln for ln in lines if re.search(r"\.{4,}\s*\d+\s*$", ln)]
print(f"\n--- lines ending in dot-leaders + page number (ToC): {len(toc)} ---")
for ln in toc[:8]:
    print(f"  {ln[:100]!r}")

# 5. How many 'Annex' headings and are they duplicated
annex = [(i, line_pages[i], ln) for i, ln in enumerate(lines) if ANNEX_RE.match(ln)]
print(f"\n--- ANNEX headings: {len(annex)} ---")
for i, pg, ln in annex[:15]:
    print(f"  line{i:6d} p{pg:3d} | {ln[:80]!r}")
