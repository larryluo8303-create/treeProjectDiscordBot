"""Ingest a PDF book into ChromaDB for RAG retrieval.

Usage examples:

  # Single PDF
  python -m ingestion.ingest_pdf --files "path/to/book.pdf"

  # Multiple PDFs
  python -m ingestion.ingest_pdf --files "book1.pdf" "book2.pdf"

  # Specify a source label (shown in retrieved context)
  python -m ingestion.ingest_pdf --files "book.pdf" --source "股市操盤聖經"

  # Dry-run: show how many chunks would be created without writing to ChromaDB
  python -m ingestion.ingest_pdf --files "book.pdf" --dry-run
"""

import argparse
import hashlib
import logging
import os
import re
import sys

import fitz  # PyMuPDF

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bot.config import (
    CHROMADB_COLLECTION,
    CHROMADB_PATH,
    CHUNK_MAX_TOKENS,
    CHUNK_OVERLAP_TOKENS,
    OPENAI_API_KEY,
)
from ingestion.ingest import _get_chromadb_collection, ingest_to_chromadb
from ingestion.preprocess import chunk_text

import openai

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


# ── PDF extraction ────────────────────────────────────────────────────────────

def _extract_text_from_pdf(pdf_path: str) -> list[tuple[int, str]]:
    """Extract text from each page of a PDF.

    Returns
    -------
    list of (page_number, page_text) tuples.  Page numbers are 1-based.
    Blank pages are skipped.
    """
    pages: list[tuple[int, str]] = []
    doc = fitz.open(pdf_path)
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")  # plain text extraction
        # Normalize whitespace but keep paragraph breaks
        text = re.sub(r"[ \t]+", " ", text)         # collapse spaces/tabs
        text = re.sub(r"\n{3,}", "\n\n", text)      # max 2 consecutive newlines
        text = text.strip()
        if len(text) > 20:  # skip near-blank pages
            pages.append((page_num, text))
    doc.close()
    logger.info("Extracted %d non-blank pages from %s", len(pages), os.path.basename(pdf_path))
    return pages


def _clean_page_text(text: str) -> str:
    """Light cleanup: remove page headers/footers that are just numbers."""
    # Remove standalone page numbers at start/end of a page block
    text = re.sub(r"^\d+\s*\n", "", text)
    text = re.sub(r"\n\s*\d+\s*$", "", text)
    return text.strip()


# ── Chunking ──────────────────────────────────────────────────────────────────

def _file_content_hash(pdf_path: str) -> str:
    """Short hash of the file bytes — detects when a PDF was replaced."""
    h = hashlib.md5()
    with open(pdf_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _remove_stale_chunks(collection, filename: str, content_hash: str) -> int:
    """Delete chunks of *filename* whose content hash differs (file replaced).

    Also migrates chunks ingested by the old ID scheme (no content_hash in
    metadata) — they are treated as stale.
    """
    try:
        res = collection.get(where={"filename": filename}, include=["metadatas"])
    except Exception as exc:
        logger.warning("Could not query existing chunks for %s: %s", filename, exc)
        return 0
    stale = [
        doc_id
        for doc_id, meta in zip(res["ids"], res["metadatas"])
        if (meta or {}).get("content_hash") != content_hash
    ]
    if stale:
        try:
            collection.delete(ids=stale)
            logger.info("Removed %d stale chunk(s) for %s (file content changed)",
                        len(stale), filename)
        except Exception as exc:
            logger.warning("Could not delete stale chunks for %s: %s", filename, exc)
            return 0
    return len(stale)


def _build_documents(
    pages: list[tuple[int, str]],
    pdf_path: str,
    source_label: str,
    content_hash: str,
    max_tokens: int,
    overlap_tokens: int,
) -> list[dict]:
    """Convert extracted pages into overlapping chunks suitable for ChromaDB.

    Each document dict has keys: ``id``, ``text``, ``metadata``.
    The ID is a deterministic hash of (file content hash + page + chunk),
    so re-ingesting an unchanged file is a no-op, while a *replaced* file
    (same path, different bytes) yields new IDs — stale chunks are removed
    by :func:`_remove_stale_chunks`.
    """
    filename = os.path.basename(pdf_path)
    documents: list[dict] = []

    for page_num, raw_text in pages:
        text = _clean_page_text(raw_text)
        chunks = chunk_text(text, max_tokens=max_tokens, overlap=overlap_tokens)

        for chunk_idx, chunk in enumerate(chunks):
            chunk = chunk.strip()
            if not chunk:
                continue

            # Deterministic ID: content hash binds the ID to the actual bytes
            id_seed = f"{content_hash}::page{page_num}::chunk{chunk_idx}"
            doc_id = "pdf_" + hashlib.md5(id_seed.encode()).hexdigest()

            documents.append(
                {
                    "id": doc_id,
                    "text": chunk,
                    "metadata": {
                        "type": "book",
                        "source": source_label or filename,
                        "filename": filename,
                        "content_hash": content_hash,
                        "page": page_num,
                        "chunk_index": chunk_idx,
                    },
                }
            )

    return documents


# ── CLI ───────────────────────────────────────────────────────────────────────

def _ingest_single_pdf(
    pdf_path: str,
    source_label: str,
    collection,
    openai_client,
    max_tokens: int,
    overlap_tokens: int,
    dry_run: bool = False,
) -> int:
    """Extract, chunk and store one PDF.  Raises on failure — caller isolates.

    Each file is written to ChromaDB before the next one starts, so a crash
    or a bad file never loses the files that already succeeded (checkpoint).
    """
    label = source_label or os.path.splitext(os.path.basename(pdf_path))[0]
    logger.info("Processing: %s  (label=%r)", pdf_path, label)

    pages = _extract_text_from_pdf(pdf_path)
    if not pages:
        logger.warning("No readable text found in %s — is this a scanned image PDF?", pdf_path)
        logger.warning("Tip: use OCR software (e.g. Adobe Acrobat) to convert it first.")
        return 0

    content_hash = _file_content_hash(pdf_path)
    docs = _build_documents(
        pages=pages,
        pdf_path=pdf_path,
        source_label=label,
        content_hash=content_hash,
        max_tokens=max_tokens,
        overlap=overlap_tokens,
    )
    logger.info("  → %d chunks generated from %d pages", len(docs), len(pages))

    if dry_run:
        for doc in docs[:3]:
            print(f"\n[{doc['metadata']['source']} p.{doc['metadata']['page']} chunk {doc['metadata']['chunk_index']}]")
            print(doc["text"][:300])
        return 0

    _remove_stale_chunks(collection, os.path.basename(pdf_path), content_hash)
    return ingest_to_chromadb(docs, collection, openai_client)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest PDF files into ChromaDB")
    parser.add_argument(
        "--files",
        nargs="+",
        required=True,
        metavar="PDF",
        help="One or more PDF file paths to ingest",
    )
    parser.add_argument(
        "--source",
        default="",
        help="Human-readable source label (e.g. book title). Defaults to filename.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract & chunk without writing to ChromaDB",
    )
    parser.add_argument(
        "--db-path",
        default=CHROMADB_PATH,
        help="Path to ChromaDB persistent store",
    )
    parser.add_argument(
        "--collection",
        default=CHROMADB_COLLECTION,
        help="ChromaDB collection name",
    )
    args = parser.parse_args()

    openai_client = None if args.dry_run else openai.OpenAI(api_key=OPENAI_API_KEY)
    collection = None if args.dry_run else _get_chromadb_collection(args.db_path, args.collection)

    total_inserted = 0
    failed: list[str] = []
    succeeded = 0

    for pdf_path in args.files:
        if not os.path.isfile(pdf_path):
            logger.error("File not found: %s", pdf_path)
            failed.append(pdf_path)
            continue
        # Per-file isolation: one bad PDF must not kill the whole batch,
        # and each file is committed before the next starts (checkpoint).
        try:
            total_inserted += _ingest_single_pdf(
                pdf_path,
                args.source,
                collection,
                openai_client,
                CHUNK_MAX_TOKENS,
                CHUNK_OVERLAP_TOKENS,
                dry_run=args.dry_run,
            )
            succeeded += 1
        except Exception as exc:
            logger.error("Failed to ingest %s: %s", pdf_path, exc, exc_info=True)
            failed.append(pdf_path)

    logger.info("Done: %d file(s) ingested, %d chunk(s) stored, %d failed%s",
                succeeded, total_inserted, len(failed),
                f" ({', '.join(failed)})" if failed else "")


if __name__ == "__main__":
    main()
