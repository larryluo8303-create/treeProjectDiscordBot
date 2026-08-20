"""Admin web panel — lightweight aiohttp dashboard for bot management.

Provides:
- GET  /admin/              — Single-page dashboard UI (HTML)
- GET  /admin/api/stats     — Bot stats JSON
- GET  /admin/api/config    — Current config snapshot
- GET  /admin/api/kb        — Knowledge base info (count, sample docs)
- GET  /admin/api/faq       — Current FAQ items
- POST /admin/api/faq/generate — Trigger FAQ generation
- GET  /admin/api/digest    — Latest digest data (last 24h summary)

Enable via ADMIN_ENABLED=true, set ADMIN_PORT and ADMIN_SECRET.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

import openai

from bot.config import (
    ADMIN_ENABLED,
    ADMIN_PORT,
    ADMIN_SECRET,
    CONFIDENCE_THRESHOLD,
    CONVERSATION_MEMORY_SIZE,
    CONVERSATION_MEMORY_TTL,
    EMBEDDING_MODEL,
    GLOBAL_MAX_PER_MINUTE,
    LLM_MODEL,
    OWNER_USER_ID,
    RESPOND_MODE,
    TARGET_CHANNEL_IDS,
    THREAD_AUTO_REPLY,
    THREAD_CONTEXT_MESSAGES,
    USER_COOLDOWN_SECONDS,
    VISION_MODEL,
)
from bot.health import uptime_seconds
from bot.stats import bot_stats

logger = logging.getLogger(__name__)

_DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Bot Admin Dashboard</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #0f172a; color: #e2e8f0; padding: 24px; }
  h1 { font-size: 1.5rem; margin-bottom: 20px; color: #38bdf8; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 16px; }
  .card { background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }
  .card h2 { font-size: 1rem; color: #94a3b8; margin-bottom: 12px; text-transform: uppercase;
             letter-spacing: 0.05em; }
  .stat { font-size: 2rem; font-weight: 700; color: #f1f5f9; }
  .stat-label { font-size: 0.85rem; color: #64748b; margin-top: 4px; }
  .stat-row { display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 8px; }
  .stat-item { flex: 1; min-width: 100px; }
  table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 0.85rem; }
  th, td { padding: 6px 8px; text-align: left; border-bottom: 1px solid #334155; }
  th { color: #94a3b8; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; }
  .badge-green { background: #065f46; color: #6ee7b7; }
  .badge-orange { background: #78350f; color: #fbbf24; }
  .btn { background: #2563eb; color: white; border: none; padding: 8px 16px; border-radius: 6px;
         cursor: pointer; font-size: 0.85rem; margin-top: 8px; }
  .btn:hover { background: #1d4ed8; }
  .btn:disabled { background: #475569; cursor: not-allowed; }
  pre { background: #0f172a; padding: 8px; border-radius: 6px; overflow-x: auto;
        font-size: 0.8rem; max-height: 300px; overflow-y: auto; }
  #faq-list { list-style: none; }
  #faq-list li { padding: 8px 0; border-bottom: 1px solid #334155; }
  .q { color: #38bdf8; font-weight: 600; }
  .a { color: #cbd5e1; margin-top: 4px; }
  .refresh-btn { float: right; background: #334155; border: none; color: #94a3b8;
                  padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 0.8rem; }
  .refresh-btn:hover { background: #475569; }
</style>
</head>
<body>
<h1>🤖 Bot Admin Dashboard
  <select id="range-select" onchange="loadStats()" style="margin-left:12px;padding:4px 8px;background:#1e293b;color:#e2e8f0;border:1px solid #334155;border-radius:6px;font-size:0.85rem;">
    <option value="24h">Last 24 Hours</option>
    <option value="7d">Last 7 Days</option>
    <option value="30d">Last 30 Days</option>
    <option value="90d">Last Quarter</option>
    <option value="365d">Last Year</option>
    <option value="all" selected>All Time</option>
  </select>
  <button class="refresh-btn" onclick="loadAll()">↻ Refresh</button>
</h1>
<div class="grid">
  <!-- Stats -->
  <div class="card">
    <h2>📊 Statistics</h2>
    <div class="stat-row">
      <div class="stat-item"><div class="stat" id="total-queries">-</div><div class="stat-label">Total Queries</div></div>
      <div class="stat-item"><div class="stat" id="auto-replies">-</div><div class="stat-label">Auto-Replies</div></div>
      <div class="stat-item"><div class="stat" id="forwards">-</div><div class="stat-label">Forwarded</div></div>
    </div>
    <div class="stat-row">
      <div class="stat-item"><div class="stat" id="avg-conf">-</div><div class="stat-label">Avg Confidence</div></div>
      <div class="stat-item"><div class="stat" id="avg-latency">-</div><div class="stat-label">Avg Latency (ms)</div></div>
      <div class="stat-item"><div class="stat" id="uptime">-</div><div class="stat-label">Uptime (min)</div></div>
    </div>
  </div>

  <!-- Config -->
  <div class="card">
    <h2>⚙️ Configuration</h2>
    <pre id="config-json">Loading...</pre>
  </div>

  <!-- KB -->
  <div class="card">
    <h2>📚 Knowledge Base</h2>
    <div class="stat-row">
      <div class="stat-item"><div class="stat" id="kb-count">-</div><div class="stat-label">Documents</div></div>
    </div>
    <h3 style="color:#94a3b8;font-size:0.85rem;margin-top:12px;">Recent Samples</h3>
    <table><thead><tr><th>ID</th><th>Type</th><th>Preview</th></tr></thead>
    <tbody id="kb-samples"></tbody></table>
  </div>

  <!-- Recent Queries -->
  <div class="card">
    <h2>❓ Recent Queries</h2>
    <table><thead><tr><th>Question</th><th>Conf</th><th>Action</th><th>Latency</th></tr></thead>
    <tbody id="recent-queries"></tbody></table>
  </div>

  <!-- FAQ -->
  <div class="card">
    <h2>📋 FAQ</h2>
    <ul id="faq-list"><li>Loading...</li></ul>
    <button class="btn" id="gen-faq-btn" onclick="generateFaq()">Generate FAQ</button>
  </div>
</div>

<script>
const SECRET = '';  // set if ADMIN_SECRET is used
const headers = SECRET ? {'X-Admin-Secret': SECRET} : {};

async function fetchJson(url) {
  const res = await fetch(url, {headers});
  return res.json();
}

async function loadStats() {
  const range = document.getElementById('range-select').value;
  const d = await fetchJson('/admin/api/stats?range=' + range);
  document.getElementById('total-queries').textContent = d.total_queries;
  document.getElementById('auto-replies').textContent = d.auto_replies;
  document.getElementById('forwards').textContent = d.forwards;
  document.getElementById('avg-conf').textContent = d.avg_confidence;
  document.getElementById('avg-latency').textContent = d.avg_latency_ms;
  document.getElementById('uptime').textContent = d.uptime_min;
  const tbody = document.getElementById('recent-queries');
  tbody.innerHTML = '';
  (d.recent || []).forEach(r => {
    const icon = r.action === 'auto_reply' ? '✅' : '📩';
    tbody.innerHTML += `<tr><td>${r.question.substring(0,60)}</td><td>${r.confidence}</td>
      <td>${icon}</td><td>${r.latency_ms}ms</td></tr>`;
  });
}

async function loadConfig() {
  const d = await fetchJson('/admin/api/config');
  document.getElementById('config-json').textContent = JSON.stringify(d, null, 2);
}

async function loadKB() {
  const d = await fetchJson('/admin/api/kb');
  document.getElementById('kb-count').textContent = d.count;
  const tbody = document.getElementById('kb-samples');
  tbody.innerHTML = '';
  (d.samples || []).forEach(s => {
    tbody.innerHTML += `<tr><td style="font-size:0.7rem">${s.id.substring(0,20)}</td>
      <td><span class="badge badge-green">${s.type||'—'}</span></td>
      <td>${(s.text||'').substring(0,80)}…</td></tr>`;
  });
}

async function loadFaq() {
  const d = await fetchJson('/admin/api/faq');
  const ul = document.getElementById('faq-list');
  if (!d.items || d.items.length === 0) {
    ul.innerHTML = '<li>No FAQ generated yet.</li>';
    return;
  }
  ul.innerHTML = '';
  d.items.forEach((f, i) => {
    ul.innerHTML += `<li><div class="q">${i+1}. ${f.q}</div><div class="a">${f.a}</div></li>`;
  });
}

async function generateFaq() {
  const btn = document.getElementById('gen-faq-btn');
  btn.disabled = true; btn.textContent = 'Generating...';
  try {
    const res = await fetch('/admin/api/faq/generate', {method:'POST', headers});
    const d = await res.json();
    if (d.status) alert(d.status);
    await loadFaq();
  } catch(e) {
    alert('FAQ generation request failed: ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = 'Generate FAQ';
  }
}

async function loadAll() {
  const btn = document.querySelector('.refresh-btn');
  if (btn) { btn.disabled = true; btn.textContent = '↻ Loading...'; }
  await Promise.allSettled([loadStats(), loadConfig(), loadKB(), loadFaq()]);
  if (btn) { btn.disabled = false; btn.textContent = '↻ Refresh'; }
}
loadAll();
setInterval(loadStats, 30000);
</script>
</body>
</html>
"""


class AdminServer:
    """Lightweight admin web panel using aiohttp."""

    def __init__(self, collection, openai_client: openai.AsyncOpenAI) -> None:
        self.collection = collection
        self.openai_client = openai_client
        self._runner = None

    async def start(self) -> None:
        try:
            from aiohttp import web
        except ImportError:
            logger.warning("aiohttp not installed — admin panel disabled. pip install aiohttp")
            return

        @web.middleware
        async def auth_middleware(request, handler):
            if ADMIN_SECRET:
                if request.path.startswith("/admin/api/"):
                    secret = request.headers.get("X-Admin-Secret", "")
                    if secret != ADMIN_SECRET:
                        return web.json_response({"error": "unauthorized"}, status=401)
            return await handler(request)

        app = web.Application(middlewares=[auth_middleware])
        app.router.add_get("/admin/", self._dashboard)
        app.router.add_get("/admin/api/stats", self._api_stats)
        app.router.add_get("/admin/api/config", self._api_config)
        app.router.add_get("/admin/api/kb", self._api_kb)
        app.router.add_get("/admin/api/faq", self._api_faq)
        app.router.add_post("/admin/api/faq/generate", self._api_faq_generate)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", ADMIN_PORT)
        await site.start()
        self._runner = runner
        logger.info("Admin panel started on port %d", ADMIN_PORT)

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    # ── Routes ────────────────────────────────────────────────────────────────

    async def _dashboard(self, request) -> "web.Response":
        from aiohttp import web
        return web.Response(text=_DASHBOARD_HTML, content_type="text/html")

    async def _api_stats(self, request) -> "web.Response":
        from aiohttp import web
        range_key = request.query.get("range", "all")
        snap = bot_stats.snapshot(range_key)
        snap["uptime_min"] = round(uptime_seconds() / 60, 1)
        snap["recent"] = bot_stats.top_questions(10, range_key)
        return web.json_response(snap)

    async def _api_config(self, request) -> "web.Response":
        from aiohttp import web
        config = {
            "respond_mode": RESPOND_MODE,
            "confidence_threshold": CONFIDENCE_THRESHOLD,
            "llm_model": LLM_MODEL,
            "embedding_model": EMBEDDING_MODEL,
            "vision_model": VISION_MODEL,
            "target_channel_ids": TARGET_CHANNEL_IDS,
            "owner_user_id": OWNER_USER_ID,
            "user_cooldown_seconds": USER_COOLDOWN_SECONDS,
            "global_max_per_minute": GLOBAL_MAX_PER_MINUTE,
            "conversation_memory_size": CONVERSATION_MEMORY_SIZE,
            "conversation_memory_ttl": CONVERSATION_MEMORY_TTL,
            "thread_auto_reply": THREAD_AUTO_REPLY,
            "thread_context_messages": THREAD_CONTEXT_MESSAGES,
        }
        return web.json_response(config)

    async def _api_kb(self, request) -> "web.Response":
        from aiohttp import web
        try:
            count = await self.collection.count()
        except Exception:
            count = -1

        samples = []
        try:
            result = await self.collection.get(
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
                        "text": text[:100],
                    })
        except Exception as exc:
            logger.warning("Failed to fetch KB samples: %s", exc)

        return web.json_response({"count": count, "samples": samples})

    async def _api_faq(self, request) -> "web.Response":
        from aiohttp import web
        from bot.faq import get_cached_faq, _load_faq
        data = _load_faq()
        return web.json_response(data if data else {"items": []})

    async def _api_faq_generate(self, request) -> "web.Response":
        from aiohttp import web
        from bot.faq import generate_faq
        items, status = await generate_faq(self.openai_client, return_status=True)
        return web.json_response({"items": items, "count": len(items), "status": status})
