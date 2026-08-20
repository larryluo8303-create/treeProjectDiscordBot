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

def _build_documents(
    pages: list[tuple[int, str]],
    pdf_path: str,
    source_label: str,
    max_tokens: int,
    overlap_tokens: int,
) -> list[dict]:
    """Convert extracted pages into overlapping chunks suitable for ChromaDB.

    Each document dict has keys: ``id``, ``text``, ``metadata``.
    The ID is a deterministic hash so re-running won't create duplicates.
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

            # Deterministic ID: hash of (filepath + page + chunk_index)
            id_seed = f"{pdf_path}::page{page_num}::chunk{chunk_idx}"
            doc_id = "pdf_" + hashlib.md5(id_seed.encode()).hexdigest()

            documents.append(
                {
                    "id": doc_id,
                    "text": chunk,
                    "metadata": {
                        "type": "book",
                        "source": source_label or filename,
                        "filename": filename,
                        "page": page_num,
                        "chunk_index": chunk_idx,
                    },
                }
            )

    return documents


# ── CLI ───────────────────────────────────────────────────────────────────────

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

    all_documents: list[dict] = []

    for pdf_path in args.files:
        if not os.path.isfile(pdf_path):
            logger.error("File not found: %s", pdf_path)
            continue

        label = args.source or os.path.splitext(os.path.basename(pdf_path))[0]
        logger.info("Processing: %s  (label=%r)", pdf_path, label)

        pages = _extract_text_from_pdf(pdf_path)
        if not pages:
            logger.warning("No readable text found in %s — is this a scanned image PDF?", pdf_path)
            logger.warning("Tip: use OCR software (e.g. Adobe Acrobat) to convert it first.")
            continue

        docs = _build_documents(
            pages=pages,
            pdf_path=pdf_path,
            source_label=label,
            max_tokens=CHUNK_MAX_TOKENS,
            overlap_tokens=CHUNK_OVERLAP_TOKENS,
        )
        logger.info("  → %d chunks generated from %d pages", len(docs), len(pages))
        all_documents.extend(docs)

    if not all_documents:
        logger.error("Nothing to ingest.")
        return

    logger.info("Total chunks across all PDFs: %d", len(all_documents))

    if args.dry_run:
        logger.info("Dry-run mode — not writing to ChromaDB.")
        # Print a sample
        for doc in all_documents[:3]:
            print(f"\n[{doc['metadata']['source']} p.{doc['metadata']['page']} chunk {doc['metadata']['chunk_index']}]")
            print(doc["text"][:300])
        return

    # Embed and store
    openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
    collection = _get_chromadb_collection(args.db_path, args.collection)
    inserted = ingest_to_chromadb(all_documents, collection, openai_client)
    logger.info("Done. Inserted %d new chunks into ChromaDB.", inserted)


if __name__ == "__main__":
    main()
