"""
Clause-aware chunking for 3GPP specification documents.

WHY THIS MODULE EXISTS (traceability: FR-03, NFR-02; decision D-003)
--------------------------------------------------------------------
Fixed-size chunking splits 3GPP definitions and procedure steps mid-thought.
When a chunk ends halfway through a definition, the generator completes the
missing half from parametric memory. That is the single largest mechanical
cause of hallucination in specification RAG.

3GPP documents already carry a rigorous numbered clause hierarchy
(5 -> 5.2 -> 5.2.3 -> 5.2.3.1). This module uses that structure as the chunk
boundary, so each chunk is a semantically complete unit with an exact,
citable address.

Fixes DEF-03 from the forked codebase, which measured chunk size in
characters and chunked per page (3GPP clauses routinely span page breaks).

KEY DESIGN POINTS
-----------------
1. Clause detection is deliberately conservative. A naive `^\\d+(\\.\\d+)*`
   pattern also matches figure captions, table row labels and numbered list
   items. We require a title after the number, exclude caption keywords, and
   enforce hierarchy monotonicity (see `_is_plausible_successor`).
2. Text is concatenated across pages BEFORE clause splitting, with page
   markers retained so a chunk can still report its page span.
3. Oversized clauses (ASN.1 blocks in TS 38.331, large measurement tables in
   TS 28.552) are sub-split with overlap, keeping the parent clause ID.
4. Every chunk gets a breadcrumb prefix that is embedded along with the body.
   This is what lets a query like "alarm severity" retrieve a clause whose
   own text never repeats the word "alarm".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import List, Optional

# ---------------------------------------------------------------------------
# Tunables. Kept module-level so tests can override them explicitly.
# ---------------------------------------------------------------------------

MAX_CHUNK_TOKENS = 450          # D-017: kept small for the Groq 6k TPM budget
SUB_SPLIT_OVERLAP_TOKENS = 60
MIN_CHUNK_CHARS = 80            # below this a "clause" is a stub heading
CHARS_PER_TOKEN = 4             # cheap estimate; swap for tiktoken if desired

# A clause heading looks like:  "5.2.3.1<sep>Some Title Text"
# The separator is a tab, 2+ spaces, or a single space before a title-like
# token. Requiring a title is what rejects list numbering and cross-references.
#
# The camelCase lookahead `\s(?=[a-z]+[A-Z])` is load-bearing (ERROR_LOG E-003):
# 3GPP source uses TABS between number and title, but PDF text extraction
# collapses them to ONE SPACE. Combined with attribute-name titles like
# "6.1 perceivedSeverity", a single space before a lowercase letter is the
# normal case, not an anomaly. Without this, every camelCase clause in the
# alarm and KPI specs silently disappears from the index.
CLAUSE_RE = re.compile(
    r"^(?P<num>\d{1,2}(?:\.\d{1,3}){0,5})"
    r"(?:\s{2,}|\t+|\s(?=[A-Z])|\s(?=[a-z]+[A-Z]))"
    r"(?P<title>[^\n]{2,140})$"
)

ANNEX_RE = re.compile(
    r"^(?P<num>Annex\s+[A-Z])(?:\s*[:\-]?\s*)(?P<title>[^\n]{0,140})$",
    re.IGNORECASE,
)

# Annex SUB-clauses number with a letter prefix: "A.64", "B.2.1", "C.1.1".
# CLAUSE_RE requires a leading digit, so without this the whole of an annex
# collapsed into one giant blind-split blob - TS 28.552's informative Annex A
# alone produced 36+ fragments with no clause structure (ERROR_LOG E-008).
ANNEX_SUB_RE = re.compile(
    r"^(?P<num>[A-Z](?:\.\d{1,3}){1,4})"
    r"(?:\s{2,}|\t+|\s(?=[A-Z])|\s(?=[a-z]+[A-Z]))"
    r"(?P<title>[^\n]{2,140})$"
)

# Lines starting with these are captions or cross-references, never clauses.
CAPTION_PREFIXES = (
    "figure", "table", "note", "example", "editor's note", "void",
    "annex", "reference", "clause", "see ",
)

PAGE_MARKER_RE = re.compile(r"<<<PAGE:(\d+)>>>")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    """One retrievable unit. `chunk_id` is stable and human-readable so a
    citation printed to the user is also a valid lookup key."""

    chunk_id: str
    spec_id: str            # e.g. "TS 28.552"
    spec_version: str       # e.g. "V18.5.0"
    clause_id: str          # e.g. "5.1.1.2"  or  "Annex B"
    clause_title: str
    heading_path: str       # "5 Performance measurements > 5.1 NF > 5.1.1.2 ..."
    text: str               # breadcrumb + body, this is what gets embedded
    body: str               # body only, used for entailment checking
    page_start: int
    page_end: int
    token_estimate: int
    part_index: int = 0     # >0 when a long clause was sub-split
    part_total: int = 1
    content_type: str = "prose"   # prose | table | asn1
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class _Heading:
    num: str
    title: str
    line_index: int
    page: int


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def chunk_spec(
    pages: List[dict],
    spec_id: str,
    spec_version: str,
    max_tokens: int = MAX_CHUNK_TOKENS,
) -> List[Chunk]:
    """Turn a parsed spec into clause-level chunks.

    `pages` is the output of the PDF parser: a list of
    ``{"page_number": int, "text": str}`` in document order.

    Returns chunks in document order. Callers should sample and eyeball ~10 of
    these before indexing (SDLC gate G2) - clause regexes are brittle against
    unusual layouts and this is the cheapest place to catch it.
    """
    if not pages:
        raise ValueError("No pages supplied.")

    lines, line_pages = _flatten_pages(pages)
    headings = _detect_headings(lines, line_pages)

    if not headings:
        # Fall back rather than fail: some specs (short TRs) have unusual
        # front matter. Logged loudly because it silently degrades quality.
        return _fallback_window_chunks(
            lines, line_pages, spec_id, spec_version, max_tokens
        )

    chunks: List[Chunk] = []
    # A clause id can legitimately appear more than once (an annex heading
    # repeated in a running header, or a spec that reuses "Annex A" in its
    # change-history). Chroma requires globally unique ids, so we suffix
    # repeats rather than let ingestion crash (ERROR_LOG E-005).
    seen_clause: dict = {}
    for i, head in enumerate(headings):
        start = head.line_index + 1
        end = headings[i + 1].line_index if i + 1 < len(headings) else len(lines)
        body = "\n".join(lines[start:end]).strip()

        # Skip PARENT CONTAINER clauses: a heading whose only content is its
        # child clauses. Detected structurally (is the next heading my direct
        # child?) rather than by a length threshold. A length threshold alone
        # silently discarded short-but-real attribute definitions such as
        # "6.2 alarmType" - dropping corpus content is a worse failure than
        # keeping a short chunk. See ERROR_LOG E-002.
        next_head = headings[i + 1] if i + 1 < len(headings) else None
        is_container = (
            next_head is not None
            and _is_numeric(head.num)
            and _is_numeric(next_head.num)
            and next_head.num.startswith(head.num + ".")
        )
        if is_container and len(body) < MIN_CHUNK_CHARS:
            continue
        if not body:
            continue

        heading_path = _build_heading_path(headings, i)
        page_start = head.page
        page_end = line_pages[min(end - 1, len(line_pages) - 1)]

        occurrence = seen_clause.get(head.num, 0)
        seen_clause[head.num] = occurrence + 1

        chunks.extend(
            _emit(
                occurrence=occurrence,
                body=body,
                spec_id=spec_id,
                spec_version=spec_version,
                clause_id=head.num,
                clause_title=head.title,
                heading_path=heading_path,
                page_start=page_start,
                page_end=page_end,
                max_tokens=max_tokens,
            )
        )

    return chunks


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _flatten_pages(pages: List[dict]):
    """Concatenate pages into one line stream, tracking each line's page.

    Concatenating first is what lets a clause span a page break (DEF-03).
    """
    lines: List[str] = []
    line_pages: List[int] = []

    for page in pages:
        page_no = page.get("page_number", 0)
        raw = page.get("text") or ""
        for line in raw.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            lines.append(stripped)
            line_pages.append(page_no)

    return lines, line_pages


def _detect_headings(lines: List[str], line_pages: List[int]) -> List[_Heading]:
    """Find clause headings, rejecting captions and list numbering.

    The monotonicity check is the important part. A figure caption like
    "3.2 shows the reference model" will match the regex shape, but "3.2"
    is not a plausible successor to the last accepted heading "7.4.1", so it
    is rejected.
    """
    headings: List[_Heading] = []
    rejected_streak = 0

    for idx, line in enumerate(lines):
        lowered = line.lower()
        if lowered.startswith(CAPTION_PREFIXES) and not lowered.startswith("annex"):
            continue

        m = ANNEX_RE.match(line)
        if m:
            headings.append(
                _Heading(
                    num=m.group("num").title(),
                    title=(m.group("title") or "").strip(),
                    line_index=idx,
                    page=line_pages[idx],
                )
            )
            continue

        m = CLAUSE_RE.match(line)
        if not m:
            m = ANNEX_SUB_RE.match(line)
            if m and _looks_like_title(m.group("title").strip()):
                headings.append(
                    _Heading(num=m.group("num"), title=m.group("title").strip(),
                             line_index=idx, page=line_pages[idx])
                )
            continue

        num = m.group("num")
        title = m.group("title").strip()

        if not _looks_like_title(title):
            continue

        prev = headings[-1].num if headings and _is_numeric(headings[-1].num) else None
        if prev and not _is_plausible_successor(prev, num):
            # Do not lock on. A single bad anchor (a stray caption, or a
            # heading picked up out of order) previously caused every
            # subsequent heading to be rejected, silently collapsing the
            # whole document into the fallback splitter (ERROR_LOG E-004).
            # Track consecutive rejections and re-anchor after a few.
            rejected_streak += 1
            if rejected_streak < 3:
                continue
            rejected_streak = 0      # re-anchor on this heading
        else:
            rejected_streak = 0

        headings.append(
            _Heading(num=num, title=title, line_index=idx, page=line_pages[idx])
        )

    return headings


def _looks_like_title(title: str) -> bool:
    """A clause title is a noun phrase, not a sentence.

    Rejects prose that happens to follow a number, e.g.
    "5.2 is defined in TS 23.501 and applies to all NFs."
    """
    if title.endswith((".", ",", ";", ":")) and len(title.split()) > 8:
        return False
    if len(title.split()) > 18:
        return False
    if title[0].islower():
        # A lowercase start is USUALLY prose ("5.2 is defined in TS 23.501...").
        # But 3GPP clause titles are frequently bare attribute names in
        # camelCase: "perceivedSeverity", "alarmType", "gNBId". Rejecting
        # these loses exactly the clauses an alarm/KPI corpus is built for.
        # See ERROR_LOG E-001.
        is_identifier = (
            len(title.split()) <= 2
            and (any(ch.isupper() for ch in title[1:]) or "_" in title)
        )
        if not is_identifier:
            return False
    return True


def _is_numeric(num: str) -> bool:
    return bool(num) and num[0].isdigit()


def _is_plausible_successor(prev: str, cur: str) -> bool:
    """Is `cur` a plausible next clause after `prev` in document order?

    Accepts: a child (5.2 -> 5.2.1), a sibling increment (5.2 -> 5.3),
    or a jump back up to an ancestor's sibling (5.2.3 -> 5.3, 5.2.3 -> 6).
    Rejects arbitrary backward jumps, which is how captions get filtered.
    """
    p = [int(x) for x in prev.split(".")]
    c = [int(x) for x in cur.split(".")]

    # Child: same prefix, one level deeper, starting at 1.
    if len(c) == len(p) + 1 and c[:-1] == p and c[-1] == 1:
        return True

    # Sibling or later sibling at the same or any shallower depth.
    depth = min(len(p), len(c))
    for d in range(depth):
        if c[d] == p[d]:
            continue
        # First differing level must INCREASE. The magnitude limit is
        # deliberately generous: specs skip clause numbers, and `_looks_like_title`
        # is the primary filter for captions and prose. A tight limit here
        # rejected legitimate headings after any gap in numbering
        # (ERROR_LOG E-006).
        return 0 < (c[d] - p[d]) <= 20
    # Identical prefix but shallower - e.g. 5.2.3 -> 5.2 (a repeated heading
    # in a running header). Reject.
    return False


def _build_heading_path(headings: List[_Heading], i: int) -> str:
    """Breadcrumb from document root to this clause.

    Walk backwards collecting the nearest ancestor at each shallower depth.
    """
    cur = headings[i]
    if not _is_numeric(cur.num):
        return f"{cur.num} {cur.title}".strip()

    parts = [f"{cur.num} {cur.title}".strip()]
    depth = len(cur.num.split("."))

    for j in range(i - 1, -1, -1):
        cand = headings[j]
        if not _is_numeric(cand.num):
            continue
        cand_depth = len(cand.num.split("."))
        if cand_depth < depth and cur.num.startswith(cand.num + "."):
            parts.insert(0, f"{cand.num} {cand.title}".strip())
            depth = cand_depth
            if depth == 1:
                break

    return " > ".join(parts)


def _classify(body: str) -> str:
    """Tag content type so table-extraction quality can be reported as a
    known limitation rather than silently polluting the corpus."""
    if "::=" in body or "SEQUENCE {" in body:
        return "asn1"
    pipe_density = body.count("|") / max(len(body.split("\n")), 1)
    if pipe_density > 1.5 or body.lower().count("\t") > 10:
        return "table"
    return "prose"


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def _emit(
    occurrence: int,
    body: str,
    spec_id: str,
    spec_version: str,
    clause_id: str,
    clause_title: str,
    heading_path: str,
    page_start: int,
    page_end: int,
    max_tokens: int,
) -> List[Chunk]:
    """Build one chunk, or several if the clause is oversized."""
    body = PAGE_MARKER_RE.sub("", body).strip()
    content_type = _classify(body)
    breadcrumb = f"[{spec_id} {spec_version}] {heading_path}"

    if _estimate_tokens(body) <= max_tokens:
        parts = [body]
    else:
        parts = _sub_split(body, max_tokens, SUB_SPLIT_OVERLAP_TOKENS)

    out: List[Chunk] = []
    total = len(parts)
    occ = f"_occ{occurrence}" if occurrence else ""
    for k, part in enumerate(parts):
        suffix = (f"_p{k}" if total > 1 else "") + occ
        text = f"{breadcrumb}\n\n{part}"
        out.append(
            Chunk(
                chunk_id=f"{_slug(spec_id)}_{clause_id}{suffix}",
                spec_id=spec_id,
                spec_version=spec_version,
                clause_id=clause_id,
                clause_title=clause_title,
                heading_path=heading_path,
                text=text,
                body=part,
                page_start=page_start,
                page_end=page_end,
                token_estimate=_estimate_tokens(text),
                part_index=k,
                part_total=total,
                content_type=content_type,
            )
        )
    return out


def _sub_split(body: str, max_tokens: int, overlap_tokens: int) -> List[str]:
    """Split an oversized clause on sentence boundaries with overlap.

    Overlap matters here: the split point is arbitrary, so without it the
    boundary reintroduces exactly the truncation problem this module exists
    to prevent.
    """
    sentences = re.split(r"(?<=[.;:])\s+", body)
    max_chars = max_tokens * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN

    parts: List[str] = []
    cur: List[str] = []
    cur_len = 0

    for sent in sentences:
        if cur_len + len(sent) > max_chars and cur:
            parts.append(" ".join(cur).strip())
            tail, tail_len = [], 0
            for s in reversed(cur):
                if tail_len + len(s) > overlap_chars:
                    break
                tail.insert(0, s)
                tail_len += len(s)
            cur, cur_len = tail, tail_len
        cur.append(sent)
        cur_len += len(sent)

    if cur:
        parts.append(" ".join(cur).strip())

    # Sentence splitting cannot split text with no sentence punctuation -
    # measurement tables and ASN.1 blocks have none, so a "part" could still
    # be thousands of tokens. That is not cosmetic: at rerank_top_n=3, three
    # 2300-token chunks is ~7000 tokens in one request, which exceeds the
    # entire 6000 TPM Groq budget and guarantees a 429 (E-009, NFR-01).
    # Hard-split anything still over the cap.
    capped: List[str] = []
    for part in parts:
        if len(part) <= max_chars * 1.15:
            capped.append(part)
            continue
        step = max_chars - overlap_chars
        for start in range(0, len(part), max(step, 1)):
            piece = part[start : start + max_chars].strip()
            if piece:
                capped.append(piece)

    return [p for p in capped if p]


def _fallback_window_chunks(
    lines, line_pages, spec_id, spec_version, max_tokens
) -> List[Chunk]:
    """Used only when no clause headings were detected at all.

    Deliberately marked in `extra` so these chunks are identifiable in the
    index and can be excluded or reported. A silent fallback here would hide
    a parsing failure behind mediocre retrieval.
    """
    text = "\n".join(lines)
    parts = _sub_split(text, max_tokens, SUB_SPLIT_OVERLAP_TOKENS)
    out = []
    for k, part in enumerate(parts):
        out.append(
            Chunk(
                chunk_id=f"{_slug(spec_id)}_fallback_{k}",
                spec_id=spec_id,
                spec_version=spec_version,
                clause_id="UNKNOWN",
                clause_title="",
                heading_path=f"{spec_id} (no clause structure detected)",
                text=f"[{spec_id} {spec_version}]\n\n{part}",
                body=part,
                page_start=line_pages[0] if line_pages else 0,
                page_end=line_pages[-1] if line_pages else 0,
                token_estimate=_estimate_tokens(part),
                part_index=k,
                part_total=len(parts),
                extra={"fallback": True},
            )
        )
    return out


def _slug(spec_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", spec_id)


# ---------------------------------------------------------------------------
# Inspection helper for gate G2
# ---------------------------------------------------------------------------

def summarise(chunks: List[Chunk]) -> dict:
    """Stats to eyeball before indexing. Run this at gate G2."""
    if not chunks:
        return {"count": 0}
    tokens = [c.token_estimate for c in chunks]
    return {
        "count": len(chunks),
        "clauses": len({c.clause_id for c in chunks}),
        "fallback_chunks": sum(1 for c in chunks if c.extra.get("fallback")),
        "unknown_clause": sum(1 for c in chunks if c.clause_id == "UNKNOWN"),
        "content_types": {
            t: sum(1 for c in chunks if c.content_type == t)
            for t in {c.content_type for c in chunks}
        },
        "tokens_min": min(tokens),
        "tokens_mean": round(sum(tokens) / len(tokens), 1),
        "tokens_max": max(tokens),
        "sub_split_clauses": sum(1 for c in chunks if c.part_total > 1),
    }
