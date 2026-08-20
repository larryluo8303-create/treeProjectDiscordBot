"""Embed preprocessed documents and store them in ChromaDB."""

import argparse
import logging
import os
import sys
import time
import uuid

import chromadb
import openai
import tiktoken
from tqdm import tqdm

# Allow running as `python -m ingestion.ingest`
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from bot.config import (
    CHROMADB_COLLECTION,
    CHROMADB_PATH,
    CHUNK_MAX_TOKENS,
    CHUNK_OVERLAP_TOKENS,
    EMBED_BATCH_SIZE,
    EMBEDDING_MODEL,
    EXPORT_DIR,
    OPENAI_API_KEY,
    OWNER_USER_ID,
)
from ingestion.preprocess import preprocess_all

logger = logging.getLogger(__name__)


def _get_chromadb_collection(db_path: str, collection_name: str) -> chromadb.Collection:
    client = chromadb.PersistentClient(path=db_path)
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )


# Cache the tiktoken encoding at module level to avoid recreating it on every call.
_ENC = tiktoken.get_encoding("cl100k_base")

EMBEDDING_MAX_TOKENS = 8191  # text-embedding-3-small hard limit


def _truncate_to_tokens(text: str, max_tokens: int = EMBEDDING_MAX_TOKENS) -> str:
    """Truncate text to fit within the embedding model's token limit."""
    tokens = _ENC.encode(text)
    if len(tokens) <= max_tokens:
        return text
    logger.warning("Truncating text from %d to %d tokens", len(tokens), max_tokens)
    return _ENC.decode(tokens[:max_tokens])


def embed_batch(texts: list[str], client: openai.OpenAI) -> list[list[float]]:
    """Embed a batch of texts using the configured embedding model."""
    safe_texts = [_truncate_to_tokens(t) for t in texts]
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=safe_texts)
    return [item.embedding for item in response.data]


def ingest_to_chromadb(
    documents: list[dict],
    collection: chromadb.Collection,
    openai_client: openai.OpenAI,
    batch_size: int = EMBED_BATCH_SIZE,
) -> int:
    """Embed and store all documents in ChromaDB.

    Parameters
    ----------
    documents : list[dict]
        Each dict has keys: ``id``, ``text``, ``metadata``.
    collection : chromadb.Collection
    openai_client : openai.OpenAI
    batch_size : int

    Returns
    -------
    int
        Number of documents inserted.
    """
    if not documents:
        logger.warning("No documents to ingest.")
        return 0

    # Check existing IDs to avoid duplicates
    existing_ids: set[str] = set()
    try:
        total_existing = collection.count()
        if total_existing > 0:
            # Fetch IDs in batches to avoid memory issues with very large collections
            batch_size_fetch = 10000
            for offset in range(0, total_existing, batch_size_fetch):
                result = collection.get(
                    include=[],
                    limit=batch_size_fetch,
                    offset=offset,
                )
                existing_ids.update(result["ids"])
            logger.info("Collection already has %d documents", len(existing_ids))
    except Exception:
        pass

    new_docs = [d for d in documents if d["id"] not in existing_ids]
    if not new_docs:
        logger.info("All documents already ingested — nothing to do.")
        return 0

    logger.info("Ingesting %d new documents (%d skipped as duplicates)",
                len(new_docs), len(documents) - len(new_docs))

    inserted = 0
    for start in tqdm(range(0, len(new_docs), batch_size), desc="Embedding & storing"):
        batch = new_docs[start : start + batch_size]
        texts = [d["text"] for d in batch]
        ids = [d["id"] for d in batch]

        # Ensure IDs are unique within the batch (append uuid suffix if needed)
        seen: set[str] = set()
        unique_ids: list[str] = []
        for doc_id in ids:
            if doc_id in seen:
                doc_id = f"{doc_id}_{uuid.uuid4().hex[:8]}"
            seen.add(doc_id)
            unique_ids.append(doc_id)

        # Sanitize metadata: ChromaDB only accepts str, int, float, bool
        metadatas = []
        for d in batch:
            clean_meta = {}
            for k, v in d["metadata"].items():
                if isinstance(v, (str, int, float, bool)):
                    clean_meta[k] = v
                else:
                    clean_meta[k] = str(v)
            metadatas.append(clean_meta)

        try:
            embeddings = embed_batch(texts, openai_client)
            collection.add(
                ids=unique_ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )
            inserted += len(batch)
        except openai.RateLimitError:
            logger.warning("Rate limited — waiting 30s before retrying batch")
            time.sleep(30)
            try:
                embeddings = embed_batch(texts, openai_client)
                collection.add(
                    ids=unique_ids,
                    embeddings=embeddings,
                    documents=texts,
                    metadatas=metadatas,
                )
                inserted += len(batch)
            except Exception as exc:
                logger.error("Failed batch starting at %d: %s", start, exc)
        except Exception as exc:
            logger.error("Failed batch starting at %d: %s", start, exc)

        # Small delay to stay within rate limits
        time.sleep(0.25)

    logger.info("Ingestion complete: %d documents stored in ChromaDB", inserted)
    return inserted


def run_ingestion(
    export_dir: str | None = None,
    owner_id: str | None = None,
    db_path: str | None = None,
    sample: int | None = None,
) -> None:
    """Main entry point: preprocess → embed → store."""
    export_dir = export_dir or EXPORT_DIR
    owner_id = owner_id or str(OWNER_USER_ID)
    db_path = db_path or CHROMADB_PATH

    logger.info("Starting ingestion pipeline")
    logger.info("  Export dir : %s", export_dir)
    logger.info("  Owner ID  : %s", owner_id)
    logger.info("  DB path   : %s", db_path)

    documents = preprocess_all(
        export_dir=export_dir,
        owner_id=owner_id,
        max_tokens=CHUNK_MAX_TOKENS,
        overlap=CHUNK_OVERLAP_TOKENS,
    )

    if sample:
        documents = documents[:sample]
        logger.info("Using sample of %d documents", sample)

    collection = _get_chromadb_collection(db_path, CHROMADB_COLLECTION)
    openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

    count = ingest_to_chromadb(documents, collection, openai_client)
    logger.info("Done — total documents in collection: %d", collection.count())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Discord exports into ChromaDB")
    parser.add_argument("--export-dir", type=str, default=None, help="Path to export JSON files")
    parser.add_argument("--owner-id", type=str, default=None, help="Discord user ID of the owner")
    parser.add_argument("--db-path", type=str, default=None, help="Path to ChromaDB persistent storage")
    parser.add_argument("--sample", type=int, default=None, help="Only ingest first N documents (for testing)")
    args = parser.parse_args()

    run_ingestion(
        export_dir=args.export_dir,
        owner_id=args.owner_id,
        db_path=args.db_path,
        sample=args.sample,
    )
