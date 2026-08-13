"""
Full ingestion: PDFs -> clause chunks -> dense index + BM25 index.

Run once per corpus change:   python -m scripts.ingest
Gate G1 -> G2.

Writes:
  data/processed/chroma/       dense vectors
  data/processed/bm25.pkl      lexical index
  data/processed/chunks.json   chunk records (used by build_golden_set)
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from app.config import CFG
from app.ingestion.clause_chunker import chunk_spec, summarise
from app.ingestion.parser import parse_pdf, spec_meta_from_filename
from app.retrieval.bm25_index import BM25Index

CHUNKS_JSON = Path("data/processed/chunks.json")
BM25_PATH = "data/processed/bm25.pkl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="drop and rebuild index")
    ap.add_argument("--no-embed", action="store_true",
                    help="chunk + BM25 only; skip dense embedding")
    args = ap.parse_args()

    raw = Path(CFG.corpus_dir)
    pdfs = sorted(raw.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PDFs in {raw}/ - see scripts/CORPUS.md (gate G1)")

    t0 = time.time()
    all_chunks = []

    print(f"Parsing and chunking {len(pdfs)} specs...\n")
    for pdf in pdfs:
        spec_id, version = spec_meta_from_filename(pdf)
        pages = parse_pdf(pdf)
        chunks = chunk_spec(pages, spec_id, version, max_tokens=CFG.max_chunk_tokens)
        s = summarise(chunks)
        flag = ""
        if s.get("fallback_chunks") or s.get("unknown_clause"):
            flag = "   *** clause detection FAILED - investigate before indexing"
        print(f"  {spec_id:14s} {version:10s} {len(pages):4d}p -> "
              f"{s['count']:5d} chunks  (mean {s['tokens_mean']} tok){flag}")
        all_chunks.extend(c.to_dict() for c in chunks)

    if not all_chunks:
        raise SystemExit("No chunks produced. Check parsing.")

    print(f"\nTOTAL {len(all_chunks)} chunks")

    CHUNKS_JSON.parent.mkdir(parents=True, exist_ok=True)
    CHUNKS_JSON.write_text(json.dumps(all_chunks))
    print(f"  chunk records -> {CHUNKS_JSON}")

    # --- BM25 (fast, no model download) ------------------------------------
    print("\nBuilding BM25 index...")
    BM25Index().build(all_chunks).save(BM25_PATH)
    print(f"  -> {BM25_PATH}")

    if args.no_embed:
        print("\n--no-embed set; skipping dense index.")
        return

    # --- dense --------------------------------------------------------------
    from app.ingestion.embedder import embed_texts
    from app.ingestion import vector_store as vs

    if args.reset:
        print("\nResetting collection...")
        vs.reset_collection()

    print(f"\nEmbedding {len(all_chunks)} chunks on CPU "
          f"({CFG.embedding_model})... this takes a few minutes.")
    vectors = embed_texts([c["text"] for c in all_chunks])

    print("Writing to ChromaDB...")
    vs.store_chunks(all_chunks, vectors)

    print(f"\nDone in {time.time()-t0:.0f}s. Collection '{CFG.collection}' "
          f"holds {vs.count()} chunks.")
    print("\nNEXT: `python -m scripts.inspect_chunks` and READ the samples. "
          "That is gate G2.")


if __name__ == "__main__":
    main()
