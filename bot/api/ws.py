"""WebSocket endpoint for real-time event push to clients."""

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from jose import JWTError, jwt

from bot.config import API_SECRET_KEY
from bot.api.auth import ALGORITHM

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts events."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.append(websocket)
        logger.info("WS client connected (total=%d)", len(self._connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)
        logger.info("WS client disconnected (total=%d)", len(self._connections))

    async def broadcast(self, event: dict[str, Any]) -> None:
        """Send an event dict to all connected clients."""
        if not self._connections:
            return
        data = json.dumps(event, ensure_ascii=False, default=str)
        async with self._lock:
            stale: list[WebSocket] = []
            for ws in self._connections:
                try:
                    await ws.send_text(data)
                except Exception:
                    stale.append(ws)
            for ws in stale:
                self._connections.remove(ws)

    @property
    def client_count(self) -> int:
        return len(self._connections)


# Singleton
ws_manager = ConnectionManager()


def _verify_ws_token(token: str) -> bool:
    """Verify a JWT token for WebSocket auth."""
    try:
        payload = jwt.decode(token, API_SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub") is not None
    except JWTError:
        return False


@router.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(default="")) -> None:
    """WebSocket endpoint. Authenticate via ?token=<jwt> query param."""
    if not _verify_ws_token(token):
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await ws_manager.connect(websocket)
    try:
        # Send initial heartbeat
        from bot.health import uptime_seconds
        await websocket.send_json({
            "type": "heartbeat",
            "uptime_seconds": round(uptime_seconds(), 1),
            "timestamp": time.time(),
        })
        # Keep alive — read messages to detect disconnect
        while True:
            # Client can send pings; we just read and discard
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await ws_manager.disconnect(websocket)
