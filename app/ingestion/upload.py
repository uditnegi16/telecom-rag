"""
Live ingestion of user-uploaded specifications.

WHY THIS EXISTS (FR-14, D-026)
------------------------------
A shipped two-spec corpus demonstrates the pipeline. It does not demonstrate
that the system is USABLE by an operator, who will want to point it at their
own documents. Upload closes that gap: the same clause-aware chunker, the same
embedding model, the same retrieval path - applied to a document the user
supplies at runtime.

Session scoping is not optional here. Uploaded specifications are routinely
confidential, and a shared demo instance where one visitor's document answers
another's questions would be disqualifying in any real evaluation.

Constraints enforced:
  * size cap - a 700-page spec takes minutes to embed on CPU
  * page cap - keeps a single upload from monopolising the container
  * PDF only - the parser is built for the ETSI PDF layout
  * per-session document cap
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

MAX_FILE_MB = 25
MAX_PAGES = 400
MAX_DOCS_PER_SESSION = 3


class UploadError(Exception):
    """User-facing, safe to surface verbatim."""


@dataclass
class UploadResult:
    spec_id: str
    spec_version: str
    pages: int
    chunks_added: int
    seconds: float
    warnings: List[str]


def ingest_upload(
    path: str | Path,
    original_name: str,
    session_id: str,
    existing_docs: int = 0,
) -> UploadResult:
    from app.config import CFG
    from app.ingestion.clause_chunker import chunk_spec, summarise
    from app.ingestion.embedder import embed_texts
    from app.ingestion.parser import (parse_pdf, spec_meta_from_content,
                                      spec_meta_from_filename)
    from app.ingestion import vector_store as vs

    path = Path(path)
    t0 = time.time()
    warnings: List[str] = []

    if existing_docs >= MAX_DOCS_PER_SESSION:
        raise UploadError(
            f"Limit of {MAX_DOCS_PER_SESSION} documents per session reached."
        )
    if not original_name.lower().endswith(".pdf"):
        raise UploadError("Only PDF files are supported.")

    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > MAX_FILE_MB:
        raise UploadError(f"File is {size_mb:.1f} MB; the limit is {MAX_FILE_MB} MB.")

    try:
        pages = parse_pdf(path)
    except Exception as exc:                      # noqa: BLE001
        raise UploadError(f"Could not read the PDF: {exc}") from exc

    if len(pages) > MAX_PAGES:
        warnings.append(
            f"Document has {len(pages)} pages; only the first {MAX_PAGES} "
            f"were indexed to keep processing time reasonable."
        )
        pages = pages[:MAX_PAGES]

    # Identity resolution, most reliable source first (E-025):
    #   1. the running header printed inside the document
    #   2. the filename, in either ETSI's format or ours
    #   3. the bare filename, as a last resort
    # Content wins because a file can be renamed and its header cannot.
    from_content = spec_meta_from_content(pages)
    if from_content:
        spec_id, version = from_content
    else:
        spec_id, version = spec_meta_from_filename(original_name)

    if version == "UNKNOWN":
        spec_id = Path(original_name).stem[:60]
        version = "uploaded"
        warnings.append(
            "This document does not identify itself as a 3GPP specification, "
            "so citations will show the filename. Retrieval still works."
        )

    chunks = chunk_spec(pages, spec_id, version, max_tokens=CFG.max_chunk_tokens)
    if not chunks:
        raise UploadError("No text could be extracted (is this a scanned PDF?).")

    stats = summarise(chunks)
    if stats.get("fallback_chunks"):
        warnings.append(
            f"{stats['fallback_chunks']} chunks had no detectable clause "
            f"structure; citations for those will be less precise."
        )

    records = [c.to_dict() for c in chunks]
    # Namespace ids so two sessions uploading the same file cannot collide.
    for r in records:
        r["chunk_id"] = f"{session_id[:8]}__{r['chunk_id']}"

    vectors = embed_texts([r["text"] for r in records])
    vs.store_chunks(records, vectors, session_id=session_id)

    return UploadResult(
        spec_id=spec_id, spec_version=version, pages=len(pages),
        chunks_added=len(records), seconds=round(time.time() - t0, 1),
        warnings=warnings,
    )
