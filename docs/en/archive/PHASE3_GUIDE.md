> **Archived**: Historical design/phase guide for reference only. See living docs under architecture/features/getting-started for current guidance.

# Phase 3: New Features User Guide

---

## Table of Contents

- [1. Overview](#1-overview)
- [2. Thread Auto-Reply (F1)](#2-thread-auto-reply-f1)
- [3. Daily Digest (F2)](#3-daily-digest-f2)
- [4. Voice Message Auto-Learning (F3)](#4-voice-message-auto-learning-f3)
- [5. Chart Comparative Analysis (F4)](#5-chart-comparative-analysis-f4)
- [6. FAQ Auto-Generation (F6)](#6-faq-auto-generation-f6)
- [7. Scheduled Data Ingestion (F7)](#7-scheduled-data-ingestion-f7)
- [8. Webhook Data Ingest (F8)](#8-webhook-data-ingest-f8)
- [9. Admin Dashboard (F10)](#9-admin-dashboard-f10)
- [10. Full Configuration Quick Reference](#10-full-configuration-quick-reference)
- [11. FAQ](#11-faq)

---

## 1. Overview

Phase 3 adds **8 feature modules**, all disabled by default (opt-in). Enable them in `.env` as needed. After upgrading, no config changes are required for existing features to keep working.

### Prerequisites

Before using Phase 3 features, confirm the environment is ready:

| Component | Requirement | Verify |
|-----------|-------------|--------|
| Python | 3.11+ | `python --version` |
| Virtual env | Created and activated | `.venv\Scripts\Activate.ps1` (PowerShell) |
| Python deps | Installed | `pip install -r requirements.txt` |
| `.env` config | Phase 1/2 already configured | Check `.env` exists and has required fields |
| ChromaDB | Data ingested | `python -c "import chromadb; c=chromadb.PersistentClient('./chromadb_store'); print(c.get_collection('bigtree_knowledge').count())"` |
| Discord Bot | Invited with permissions | Bot online in Discord server |
| FFmpeg | Required for voice transcription (F3) | `ffmpeg -version` |

> **Note:** If you are deploying from scratch, complete the full install flow in [`PHASE1_2_GUIDE.md`](./PHASE1_2_GUIDE.md) first.

### Environment Setup (if not done yet)

```powershell
# 1. Install Python 3.11+
winget install --id Python.Python.3.11 -e

# 2. Install FFmpeg (needed for voice transcription)
winget install --id Gyan.FFmpeg -e

# 3. Create virtual environment
cd C:\treeProjectDiscordBot
python -m venv .venv

# 4. Activate virtual environment
.venv\Scripts\Activate.ps1

# 5. Install Python dependencies
pip install -r requirements.txt
```

### Quick Start

```bash
# 1. Pull latest code
git pull

# 2. Activate virtual environment
.venv\Scripts\Activate.ps1    # PowerShell
# or source .venv/bin/activate  # Linux/macOS

# 3. Update dependencies
pip install -r requirements.txt

# 4. Add new config to .env as needed (see .env.example)

# 5. Start the bot
python -m bot.main
```

### Verify Successful Startup

After a normal start you should see:

```
[INFO] bot.main: OpenAI client initialized
[INFO] bot.main: ChromaDB collection loaded — XXXXX documents
[INFO] bot.main: Starting Discord bot...
[INFO] bot.listener: Bot is ready — starting message queue worker
```

If Phase 3 features are enabled, you will also see:

```
[INFO] Digest scheduler started (hour=22 UTC)
[INFO] Ingestion scheduler started (every 12.0h)
[INFO] Webhook server started on port 8081
[INFO] Admin panel started on port 8082
```

### Feature Switch Quick Reference

| Feature | Env Variable | Default |
|---------|--------------|---------|
| Thread replies | `THREAD_AUTO_REPLY` | `true` (already on) |
| Daily digest | `DIGEST_ENABLED` | `false` |
| Voice transcription | (automatic, no switch) | Always on |
| Chart comparison | (automatic, no switch) | Always on |
| FAQ generation | (on-demand slash command) | Always available |
| Scheduled ingest | `INGEST_INTERVAL_HOURS` | `0` (disabled) |
| Webhook | `WEBHOOK_ENABLED` | `false` |
| Admin panel | `ADMIN_ENABLED` | `false` |

---

## 2. Thread Auto-Reply (F1)

### What is it?

The bot can now auto-reply to user questions inside Discord Threads and keep Thread conversation context.

### How it works

1. A user creates a Thread in a target channel and asks a question
2. The bot detects that the Thread’s parent channel is in `TARGET_CHANNEL_IDS`
3. The bot loads recent Thread messages as conversation context
4. It generates a reply based on the full context

### Configuration

Add to `.env`:

```env
# Thread auto-reply (on by default)
THREAD_AUTO_REPLY=true

# Number of context messages to fetch from the Thread
THREAD_CONTEXT_MESSAGES=15
```

### Tips

- **Owner messages in Threads** are also auto-learned into the knowledge base
- To disable Thread replies: set `THREAD_AUTO_REPLY=false`
- `THREAD_CONTEXT_MESSAGES` controls how much Thread history the bot can “see”; 10–20 is recommended

---

## 3. Daily Digest (F2)

### What is it?

The bot sends a polished daily activity digest covering the last 24 hours of Q&A stats, top channels, recent questions, and forwarded/unanswered items that need attention.

### How to enable

Add to `.env`:

```env
DIGEST_ENABLED=true

# Send time (UTC hour, 0-23)
# 22 = 6:00 PM ET / 6:00 AM CST
DIGEST_HOUR=22

# Optional: also post to a channel (0 = Owner DM only)
DIGEST_CHANNEL_ID=0
```

### What the digest includes

Sent as a Discord Embed with these cards:

1. **📈 Overview** — total questions, auto-replies, forwards, avg confidence, avg latency
2. **📺 Top Channels** — top 5 most active channels
3. **❓ Recent Questions** — last 5 questions (✅ auto-reply / 🟠 forwarded)
4. **🔴 Forwarded / Unanswered** — items needing Owner attention
5. **💤 Quiet Day** — shown when there were no questions in 24h

### Tips

- Digest is DMed to the Owner and also posted to `DIGEST_CHANNEL_ID` (if set)
- If the Owner has DMs closed, the bot logs it but does not error
- Set `DIGEST_HOUR` to after your workday so you can review the day’s activity

---

## 4. Voice Message Auto-Learning (F3)

### What is it?

When the Owner sends a voice message in a target channel, the bot automatically:
1. Downloads the audio file
2. Transcribes it with OpenAI Whisper
3. Embeds the text and stores it in the ChromaDB knowledge base

### How to use

**No configuration required** — whenever the Owner sends a message with an audio attachment in `TARGET_CHANNEL_IDS`, the bot handles it automatically.

### Supported audio formats

- `.ogg` (Discord default voice format)
- `.mp3`
- `.m4a`
- `.wav`
- Any attachment with `audio/*` content type

### Processing details

- Transcription language defaults to Chinese (`zh`)
- Voice messages that transcribe to text that is too short (< 5 chars) are skipped
- Document ID `voice_{message_id}` provides automatic dedup
- Knowledge-base type is `owner_voice`, source is `discord_live_voice`

### Log examples

```
INFO - Auto-learn: detected owner voice message (id=1234, channel=5678)
INFO - Voice transcription complete (id=1234, len=156): ES looks strong today...
INFO - Auto-learned voice message 1234 (156 chars)
```

---

## 5. Chart Comparative Analysis (F4)

### What is it?

When a user sends a chart screenshot with text (e.g. “How’s ES looking”), the bot not only analyzes the chart with GPT-4o, but also retrieves the Owner’s past analyses of similar tickers from the knowledge base and injects them into the vision prompt.

### How it works

1. User sends image + text (e.g. “NQ 4H chart”)
2. Bot retrieves the top 3 related historical analyses from the knowledge base using the text
3. Historical analyses are injected into the GPT-4o vision prompt as reference context
4. GPT-4o produces an enhanced reply combining the chart and historical analysis

### Tips

- **RAG retrieval only triggers when image + text are both present**
- Image-only messages keep the original pure-vision behavior
- The more Owner analyses accumulate (via auto-learn, voice transcription, etc.), the better comparison works
- If RAG fails (network error, etc.), it automatically falls back to pure vision analysis

### What users notice

Before: GPT-4o analyzes based on the image alone  
After: GPT-4o also references the Owner’s historical style and views, so replies are more consistent

---

## 6. FAQ Auto-Generation (F6)

### What is it?

Based on recent high-frequency, high-confidence user questions, GPT clusters them into an FAQ list for self-service lookup.

### How to use

#### Users view FAQ

In Discord:

```
/faq
```

The bot shows the current FAQ list as an Embed (number + question + short answer).

#### Owner generates FAQ

In Discord:

```
/generate_faq
```

The bot will:
1. Extract auto-reply questions with confidence ≥ 7 from stats
2. Deduplicate + limit to the latest 50 unique questions
3. Call GPT to cluster/merge into at most 10 FAQ items
4. Save to `data/faq.json`
5. Return the generation result

### Advanced configuration

```env
# FAQ data file path (optional)
FAQ_FILE=data/faq.json

# Minimum confidence threshold (only replies at/above this score feed FAQ)
FAQ_MIN_CONFIDENCE=7

# Maximum FAQ items
FAQ_MAX_ITEMS=10
```

### Tips

- FAQ persists in `data/faq.json` and loads automatically after restart
- At least 3 high-confidence reply records are required to generate; otherwise cache is returned
- Let the bot run for a while and accumulate Q&A before using `/generate_faq`
- You can run `/generate_faq` multiple times; each run regenerates from the latest data

---

## 7. Scheduled Data Ingestion (F7)

### What is it?

Automatically runs knowledge-base ingest (`ingestion.ingest`) and style analysis (`ingestion.analyze_style`) on a schedule to keep the knowledge base in sync with the latest data.

### How to enable

Set intervals in `.env`:

```env
# Re-ingest every 12 hours
INGEST_INTERVAL_HOURS=12

# Re-analyze style every 24 hours
STYLE_INTERVAL_HOURS=24
```

Set to `0` = disabled (default).

### How it runs

- Ingest and style analysis run as **independent subprocesses** and do not block the bot’s main event loop
- Subprocesses run for at most 1 hour (auto-killed on timeout)
- On failure, the bot **DMs the Owner** with the error
- The first run starts after the first interval completes following bot startup

### Log examples

```
INFO - Ingestion scheduler started (every 12.0h)
INFO - Style re-analysis scheduler started (every 24.0h)
INFO - Scheduled ingestion starting...
INFO - Scheduled ingestion completed successfully
```

### Tips

- Ensure `EXPORT_DIR` contains ingest data (`.json` files), or ingest will fail
- If you only want automated style analysis (lighter), set only `STYLE_INTERVAL_HOURS` and keep `INGEST_INTERVAL_HOURS=0`

---

## 8. Webhook Data Ingest (F8)

### What is it?

Provides an HTTP endpoint that receives data from external systems (e.g. TradingView alerts, custom scripts), auto-embeds it, and stores it in the knowledge base.

### How to enable

Add to `.env`:

```env
WEBHOOK_ENABLED=true
WEBHOOK_PORT=8081

# Optional: HMAC signing secret (recommended in production)
WEBHOOK_SECRET=your_secret_key_here
```

### API Endpoints

#### Health check

```bash
GET http://localhost:8081/webhook/health
```

Response:
```json
{"status": "ok"}
```

#### Data ingest

```bash
POST http://localhost:8081/webhook/ingest
Content-Type: application/json
X-Webhook-Signature: <hmac-sha256-hex>  # required only when WEBHOOK_SECRET is set

{
  "text": "ES futures broke key resistance with significantly higher volume; short-term bias bullish...",
  "source": "tradingview",
  "type": "alert",
  "ticker": "ES",
  "timeframe": "4h",
  "alert_name": "Breakout signal"
}
```

#### Batch ingest

```bash
POST http://localhost:8081/webhook/ingest

[
  {"text": "NQ bounced off the 20-day MA...", "source": "tradingview", "ticker": "NQ"},
  {"text": "AAPL gap-up after earnings...", "source": "manual", "ticker": "AAPL"}
]
```

#### Response format

```json
{"ingested": 2, "total": 3}
```

- `ingested`: successfully stored count
- `total`: submitted total (difference = skipped: too short / already exists)

### JSON field reference

| Field | Required | Description |
|-------|----------|-------------|
| `text` | Yes | Text to store in the knowledge base (≥ 10 chars) |
| `source` | No | Source tag (default `"webhook"`) |
| `type` | No | Document type tag (default `"external_data"`) |
| `ticker` | No | Stock/futures symbol |
| `timeframe` | No | Timeframe (e.g. `"4h"`, `"1d"`) |
| `alert_name` | No | Alert name |

### HMAC signature verification

If `WEBHOOK_SECRET` is set, requests must include the signature header:

```python
import hashlib, hmac, json, requests

secret = "your_secret_key_here"
body = json.dumps({"text": "..."}).encode()
signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

requests.post(
    "http://localhost:8081/webhook/ingest",
    data=body,
    headers={
        "Content-Type": "application/json",
        "X-Webhook-Signature": signature,
    },
)
```

### TradingView integration example

1. Create an Alert in TradingView
2. Set Webhook URL: `http://your-server:8081/webhook/ingest`
3. Alert Message format:
```json
{
  "text": "{{exchange}}:{{ticker}} {{strategy.order.action}} @ {{close}} on {{interval}} chart. {{strategy.order.comment}}",
  "source": "tradingview",
  "type": "alert",
  "ticker": "{{ticker}}",
  "timeframe": "{{interval}}"
}
```

---

## 9. Admin Dashboard (F10)

### What is it?

A browser-based admin dashboard so the Owner can view bot status, knowledge base, query stats, and FAQ management on the web.

### How to enable

Add to `.env`:

```env
ADMIN_ENABLED=true
ADMIN_PORT=8082

# Optional: API access secret (recommended in production)
ADMIN_SECRET=your_admin_secret_here
```

### How to access

Open a browser:

```
http://localhost:8082/admin/
```

### Dashboard panels

1. **📊 Statistics** — total queries, auto-replies, forwards, avg confidence, avg latency, uptime
2. **⚙️ Configuration** — current bot config snapshot (JSON)
3. **📚 Knowledge Base** — total docs + last 10 document samples (ID, type, preview)
4. **❓ Recent Queries** — last 10 user queries (question, confidence, action, latency)
5. **📋 FAQ** — current FAQ list + “Generate FAQ” button

### Auto-refresh

- Stats refresh every 30 seconds
- Click **↻ Refresh** in the top-right to manually refresh all data

### REST API

For programmatic access (when `ADMIN_SECRET` is set, include header `X-Admin-Secret`):

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/api/stats` | Query stats |
| GET | `/admin/api/config` | Current config |
| GET | `/admin/api/kb` | Knowledge-base info |
| GET | `/admin/api/faq` | FAQ content |
| POST | `/admin/api/faq/generate` | Trigger FAQ generation |

```bash
# Example
curl -H "X-Admin-Secret: your_secret" http://localhost:8082/admin/api/stats
```

---

## 10. Full Configuration Quick Reference

All Phase 3 environment variables — add to `.env`:

```env
# ── Phase 3: New Features ──

# Thread support
THREAD_AUTO_REPLY=true
THREAD_CONTEXT_MESSAGES=15

# Daily digest
DIGEST_ENABLED=false
DIGEST_HOUR=22
DIGEST_CHANNEL_ID=0

# Scheduled ingest (0 = disabled)
INGEST_INTERVAL_HOURS=0
STYLE_INTERVAL_HOURS=0

# Webhook data ingest
WEBHOOK_ENABLED=false
WEBHOOK_PORT=8081
WEBHOOK_SECRET=

# Admin dashboard
ADMIN_ENABLED=false
ADMIN_PORT=8082
ADMIN_SECRET=
```

---

## 11. FAQ

### Q: Do I need to change config after upgrading to Phase 3?

**A:** No. All new features are off by default (except Thread replies, which default on). Your existing `.env` needs no changes to keep running normally.

### Q: Do I need new Python dependencies?

**A:** No. All Phase 3 features use existing dependencies (`aiohttp`, `openai`, `discord.py`, `chromadb`).

### Q: Can Webhook and Admin panel run at the same time?

**A:** Yes. They use different ports (defaults 8081 and 8082) and do not interfere.

### Q: What if Owner voice transcription fails?

**A:** The bot logs the error and keeps running. The message is not stored, and other features are unaffected.

### Q: How much Q&A data does FAQ generation need?

**A:** At least 3 auto-reply records with confidence ≥ 7. Running the bot for a week+ to accumulate data is recommended.

### Q: Can the daily digest use a non-hour time?

**A:** Currently only whole hours are supported (`DIGEST_HOUR` is an integer 0–23). The digest fires at :00 of that hour.

### Q: How do Thread replies differ from regular channel replies?

**A:** In Threads the bot reads Thread history as context (up to `THREAD_CONTEXT_MESSAGES`), while regular channels use per-channel conversation memory. Thread replies usually have better contextual consistency.

### Q: Is exposing the Webhook endpoint to the public internet safe?

**A:** Set `WEBHOOK_SECRET` and use HMAC signature verification. Without a secret, anyone can submit data. In production, prefer a reverse proxy (Nginx) + HTTPS + IP allowlist.

### Q: Can the Admin panel change configuration?

**A:** Currently view-only. Config changes still require editing `.env` and restarting the bot. Future versions may add hot-reload.

### Q: Will scheduled ingest conflict with manual ingest?

**A:** Scheduled ingest runs as an independent subprocess and does not interfere with the bot main process. Avoid triggering scheduled ingest while a manual ingest is running, which could cause ChromaDB concurrent-write issues.
