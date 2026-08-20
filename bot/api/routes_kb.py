"""Knowledge base API routes — search, list, count."""

from fastapi import APIRouter, Depends, Query

from bot.api.auth import get_current_user
from bot.api.server import get_collection, get_openai_client

router = APIRouter(prefix="/api/kb", tags=["kb"])


@router.get("")
async def get_kb_info(_user: str = Depends(get_current_user)) -> dict:
    """Return KB document count and sample documents."""
    collection = get_collection()
    try:
        count = await collection.count()
    except Exception:
        count = -1

    samples = []
    try:
        result = await collection.get(
            include=["documents", "metadatas"],
            limit=10,
        )
        if result and result.get("ids"):
            for i, doc_id in enumerate(result["ids"]):
                meta = result["metadatas"][i] if result.get("metadatas") else {}
                text = result["documents"][i] if result.get("documents") else ""
                samples.append({
                    "id": doc_id,
                    "type": meta.get("type", "unknown"),
                    "text": text[:200],
                })
    except Exception:
        pass

    return {"count": count, "samples": samples}


@router.get("/search")
async def search_kb(
    q: str = Query(..., min_length=1, description="Search query"),
    top_k: int = Query(5, ge=1, le=20),
    _user: str = Depends(get_current_user),
) -> dict:
    """Semantic search over the knowledge base."""
    from bot.rag import retrieve_context

    collection = get_collection()
    openai_client = get_openai_client()

    chunks = await retrieve_context(
        question=q,
        collection=collection,
        openai_client=openai_client,
        top_k=top_k,
    )

    results = []
    for chunk in chunks:
        results.append({
            "text": chunk.get("text", ""),
            "distance": chunk.get("distance", 0),
            "metadata": chunk.get("metadata", {}),
        })

    return {"query": q, "count": len(results), "results": results}
