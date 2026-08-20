"""Webhook integration — receive external data and ingest as knowledge.

Provides a lightweight HTTP endpoint that accepts JSON payloads (e.g. from
TradingView alerts, custom scripts) and stores them in ChromaDB so the bot
can reference them in future answers.

Enable via WEBHOOK_ENABLED=true and optionally set WEBHOOK_PORT and WEBHOOK_SECRET.
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

import openai

from bot.config import EMBEDDING_MODEL, WEBHOOK_ENABLED, WEBHOOK_PORT, WEBHOOK_SECRET

logger = logging.getLogger(__name__)


def _verify_signature(body: bytes, signature: str) -> bool:
    """Verify HMAC-SHA256 signature if WEBHOOK_SECRET is set."""
    if not WEBHOOK_SECRET:
        return True
    expected = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


class WebhookServer:
    """Async HTTP webhook server using aiohttp."""

    def __init__(self, collection, openai_client: openai.AsyncOpenAI) -> None:
        self.collection = collection
        self.openai_client = openai_client
        self._runner = None

    async def start(self) -> None:
        try:
            from aiohttp import web
        except ImportError:
            logger.warning("aiohttp not installed — webhook server disabled. pip install aiohttp")
            return

        app = web.Application()
        app.router.add_post("/webhook/ingest", self._handle_ingest)
        app.router.add_get("/webhook/health", self._handle_health)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", WEBHOOK_PORT)
        await site.start()
        self._runner = runner
        logger.info("Webhook server started on port %d", WEBHOOK_PORT)

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    async def _handle_health(self, request) -> "web.Response":
        from aiohttp import web
        return web.json_response({"status": "ok"})

    async def _handle_ingest(self, request) -> "web.Response":
        from aiohttp import web

        body = await request.read()

        # Verify signature
        sig = request.headers.get("X-Webhook-Signature", "")
        if WEBHOOK_SECRET and not _verify_signature(body, sig):
            return web.json_response({"error": "invalid signature"}, status=403)

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return web.json_response({"error": "invalid JSON"}, status=400)

        # Accept either a single item or a list
        items = data if isinstance(data, list) else [data]
        ingested = 0

        for item in items:
            text = item.get("text", "").strip()
            if not text or len(text) < 10:
                continue

            source = item.get("source", "webhook")
            doc_type = item.get("type", "external_data")
            doc_id = f"webhook_{hashlib.md5(text.encode()).hexdigest()[:12]}"

            try:
                existing = await self.collection.get(ids=[doc_id], include=[])
                if existing["ids"]:
                    continue

                response = await self.openai_client.embeddings.create(
                    model=EMBEDDING_MODEL,
                    input=[text],
                )
                embedding = response.data[0].embedding

                metadata = {
                    "type": doc_type,
                    "source": source,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                # Include extra metadata fields from payload
                for key in ("ticker", "timeframe", "alert_name"):
                    if key in item:
                        metadata[key] = str(item[key])

                await self.collection.add(
                    ids=[doc_id],
                    embeddings=[embedding],
                    documents=[text],
                    metadatas=[metadata],
                )
                ingested += 1
                logger.info("Webhook ingested: %s (source=%s, len=%d)", doc_id, source, len(text))
            except Exception as exc:
                logger.warning("Webhook ingest failed for item: %s", exc)

        return web.json_response({"ingested": ingested, "total": len(items)})
