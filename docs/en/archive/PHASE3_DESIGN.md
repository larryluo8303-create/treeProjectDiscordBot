> **Archived**: Historical design/phase guide for reference only. See living docs under architecture/features/getting-started for current guidance.

# Phase 3: New Feature Development — Design Document

---

## Table of Contents

- [1. Background & Goals](#1-background--goals)
- [2. Feature Overview](#2-feature-overview)
- [3. System Architecture Changes](#3-system-architecture-changes)
- [4. Module Design](#4-module-design)
  - [4.1 F1: Thread Auto-Reply](#41-f1-thread-auto-reply)
  - [4.2 F2: Daily Digest](#42-f2-daily-digest)
  - [4.3 F3: Owner Voice Transcription & Auto-Learning](#43-f3-owner-voice-transcription--auto-learning)
  - [4.4 F4: Multimodal Chart Comparative Analysis](#44-f4-multimodal-chart-comparative-analysis)
  - [4.5 F6: FAQ Auto-Generation](#45-f6-faq-auto-generation)
  - [4.6 F7: Scheduled Data Ingestion](#46-f7-scheduled-data-ingestion)
  - [4.7 F8: Webhook External Data Ingest](#47-f8-webhook-external-data-ingest)
  - [4.8 F10: Admin Dashboard](#48-f10-admin-dashboard)
- [5. Data Flow Diagrams](#5-data-flow-diagrams)
- [6. Configuration Parameters](#6-configuration-parameters)
- [7. File Change List](#7-file-change-list)
- [8. Security Design](#8-security-design)
- [9. Dependencies & Compatibility](#9-dependencies--compatibility)

---

## 1. Background & Goals

### Background

The bot has completed Phase 1 (core RAG) and Phase 2 (enhancements), with capabilities including: auto-reply, confidence routing, owner review, negative-feedback learning, embedding cache, token-bucket rate limiting, graceful shutdown, i18n, stats tracking, and more.

### Goals

Phase 3 adds **8 feature modules** on top of the existing base to further improve automation, knowledge acquisition, and operations efficiency:

1. Support Discord Thread conversation context
2. Daily activity digest auto-push
3. Owner voice messages auto-transcribed and ingested
4. Chart analysis combined with historical knowledge comparison
5. High-frequency Q&A auto-generated into FAQ
6. Scheduled re-ingest / style analysis
7. External webhook data ingest
8. Web admin dashboard

---

## 2. Feature Overview

| ID | Feature | Priority | New Files | Modified Files |
|----|---------|----------|-----------|----------------|
| F1 | Thread auto-reply | High | — | listener.py, config.py |
| F2 | Daily digest | High | digest.py | main.py |
| F3 | Voice transcription & auto-learn | High | — | listener.py |
| F4 | Multimodal chart comparison | Medium | — | rag.py, listener.py |
| F6 | FAQ auto-generation | Medium | faq.py | commands.py |
| F7 | Scheduled data ingest | Medium | ingestion_scheduler.py | main.py, config.py |
| F8 | Webhook ingest | Low | webhook.py | main.py |
| F10 | Admin panel | Low | admin.py | main.py |

All new features are **opt-in** (disabled by default) and controlled by environment variables, without affecting existing behavior.

---

## 3. System Architecture Changes

### New Component Relationship Diagram

```
Discord
  │
  ├─ MessageListener (Cog)
  │    ├─ Thread support (F1) ─ _is_thread / _fetch_thread_context
  │    ├─ Voice transcription (F3) ─ _handle_voice_message → Whisper API → ChromaDB
  │    └─ Chart comparison (F4) ─ retrieve_context → analyze_image (with RAG context)
  │
  ├─ DigestCog (F2) ─ scheduled 24h digest embed → Owner DM / Channel
  │
  ├─ IngestionSchedulerCog (F7) ─ scheduled subprocess for ingest / analyze_style
  │
  ├─ BotCommands (Cog) ─ /faq, /generate_faq (F6)
  │
  ├─ WebhookServer (F8) ─ HTTP POST → embed → ChromaDB
  │    └─ aiohttp on port 8081
  │
  └─ AdminServer (F10) ─ HTML Dashboard + REST API
       └─ aiohttp on port 8082
```

### Entry Registration Order (main.py)

```python
# Cogs
MessageListener → PromotionCommands → BotCommands → SchedulerCog
→ HealthCog → IngestionSchedulerCog → DigestCog

# HTTP Servers (optional)
WebhookServer (port 8081)
AdminServer   (port 8082)
```

---

## 4. Module Design

### 4.1 F1: Thread Auto-Reply

**Purpose:** Support auto-replies inside Discord Threads while keeping conversation context consistent.

**Design points:**

- **Channel detection:** `_is_thread()` detects Thread messages; `_get_parent_channel_id()` gets the parent channel ID
- **Channel filtering:** `_should_skip()` accepts Threads whose parent channel is in `TARGET_CHANNEL_IDS`
- **Thread toggle:** Controlled by `THREAD_AUTO_REPLY` env var, on by default
- **Context fetch:** `_fetch_thread_context()` loads the last N Thread messages (`THREAD_CONTEXT_MESSAGES`) and formats them as conversation history
- **last_seen tracking:** Thread messages track via parent channel ID so offline backfill works correctly
- **Owner auto-learn:** Owner messages inside Threads are also auto-learned

**Modified files:**
- `bot/config.py` — add `THREAD_AUTO_REPLY`, `THREAD_CONTEXT_MESSAGES`
- `bot/listener.py` — add `_is_thread()`, `_get_parent_channel_id()`, `_fetch_thread_context()`; modify `_should_skip()`, `on_message()`, `_handle_message()`

### 4.2 F2: Daily Digest

**Purpose:** Send a daily activity digest to the Owner on a schedule to summarize bot operations.

**Design points:**

- **New file:** `bot/digest.py` implements `DigestCog`
- **Scheduling:** `_digest_loop()` computes seconds until the next `DIGEST_HOUR` (UTC), then `asyncio.sleep` and fire
- **Data source:** Filter `bot_stats.recent` for `QueryRecord`s in the last 24 hours
- **Digest contents:**
  - Total questions / auto-replies / forwards
  - Average confidence / average latency
  - Top 5 active channels
  - Last 5 questions (with reply-status icons)
  - Forwarded / unanswered question list
- **Delivery:** Discord Embed to `DIGEST_CHANNEL_ID` (optional) + Owner DM
- **Quiet day:** If no questions in 24h, show a "Quiet Day" notice

**Configuration:**
| Variable | Default | Description |
|----------|---------|-------------|
| `DIGEST_ENABLED` | `false` | Master switch |
| `DIGEST_HOUR` | `22` | UTC hour (0-23) |
| `DIGEST_CHANNEL_ID` | `0` | Publish channel (0 = DM only) |

### 4.3 F3: Owner Voice Transcription & Auto-Learning

**Purpose:** When the Owner sends a voice message, automatically transcribe via Whisper and ingest into ChromaDB to grow the knowledge base.

**Design points:**

- **Trigger:** In `on_message`, when an Owner message has no text but has an audio attachment
- **Audio formats:** `.ogg`, `.mp3`, `.m4a`, `.wav`, and `audio/*` content types
- **Flow:**
  1. Download audio attachment (`voice_att.read()`)
  2. Write temp file (keep original extension)
  3. Call `openai.audio.transcriptions.create(model="whisper-1", language="zh")`
  4. Clean up temp file (`finally` guaranteed)
  5. Filter text that is too short (< 5 chars)
  6. Embed and store in ChromaDB with metadata type `owner_voice`
- **Dedup:** Document ID `voice_{message.id}` prevents duplicates
- **Error handling:** Outer try/except for download/transcription errors; inner catch for storage errors

**Method:** `_handle_voice_message()` (listener.py, ~80 lines)

### 4.4 F4: Multimodal Chart Comparative Analysis

**Purpose:** When users upload charts, in addition to GPT-4o vision analysis, retrieve the Owner’s past analyses of similar tickers/patterns from the knowledge base and inject them into the vision prompt for comparison.

**Design points:**

- **Trigger:** Message contains image + text (ticker name / question)
- **RAG retrieval:** Call `retrieve_context(top_k=3)` on the accompanying user text for related historical analysis
- **Prompt injection:** Append to the vision prompt: “Below are the channel owner’s past analyses of similar tickers/patterns for reference comparison” + context block
- **Graceful fallback:** If RAG fails (exception / no results), fall back to pure vision analysis (no context)
- **No-text case:** If the user uploads only an image with no text, skip RAG and keep prior behavior

**Modified files:**
- `bot/rag.py` — `analyze_image()` gains `context_chunks` parameter
- `bot/listener.py` — vision branch in `_handle_message()` adds RAG retrieval

### 4.5 F6: FAQ Auto-Generation

**Purpose:** Automatically extract FAQ from high-frequency, high-confidence Q&A for user self-service.

**Design points:**

- **New file:** `bot/faq.py`
- **Generation logic (`generate_faq()`):**
  1. From `bot_stats.recent`, filter auto-reply records with confidence ≥ `FAQ_MIN_CONFIDENCE` (default 7)
  2. Deduplicate + cap at 50 unique questions
  3. Build a prompt for GPT to cluster/merge into a JSON array `[{"q": "...", "a": "..."}]`
  4. Parse JSON, validate structure, truncate to `FAQ_MAX_ITEMS`
  5. Persist to `data/faq.json` (with generation timestamp)
- **Cached read (`get_cached_faq()`):** Read the JSON file directly; no API call
- **Minimum threshold:** If high-confidence records < 3, return cache (do not regenerate)

**Slash Commands:**
| Command | Permission | Description |
|---------|------------|-------------|
| `/faq` | Everyone | View current FAQ (Discord Embed) |
| `/generate_faq` | Owner | Trigger FAQ regeneration immediately |

### 4.6 F7: Scheduled Data Ingestion

**Purpose:** Automatically re-run data ingest and style analysis on a schedule to keep the knowledge base fresh.

**Design points:**

- **New file:** `bot/ingestion_scheduler.py` implements `IngestionSchedulerCog`
- **Subprocess execution:** Run via `subprocess.run([sys.executable, "-m", module])` to avoid blocking the event loop
- **Two independent loops:**
  - `_ingest_loop()` — every `INGEST_INTERVAL_HOURS` hours run `ingestion.ingest`
  - `_style_loop()` — every `STYLE_INTERVAL_HOURS` hours run `ingestion.analyze_style`
- **Timeout protection:** Subprocess max 1 hour (`timeout=3600`)
- **Failure notification:** On failure, DM Owner with error info (last 500 chars)
- **Status tracking:** Record `_last_ingest` / `_last_style` timestamps; `status()` for external queries
- **Disabled by default:** Interval `0` means the loop does not start

**Configuration:**
| Variable | Default | Description |
|----------|---------|-------------|
| `INGEST_INTERVAL_HOURS` | `0` | Ingest interval (0 = disabled) |
| `STYLE_INTERVAL_HOURS` | `0` | Style analysis interval (0 = disabled) |

### 4.7 F8: Webhook External Data Ingest

**Purpose:** Provide an HTTP API to receive external data (e.g. TradingView alerts), auto-embed, and store in the knowledge base.

**Design points:**

- **New file:** `bot/webhook.py` implements `WebhookServer`
- **HTTP framework:** aiohttp (already a dependency; no new package)
- **Endpoints:**
  - `POST /webhook/ingest` — receive JSON and ingest
  - `GET /webhook/health` — health check

**Request format:**
```json
// Single item
{
  "text": "ES broke a key resistance with rising volume...",
  "source": "tradingview",
  "type": "alert",
  "ticker": "ES",
  "timeframe": "4h",
  "alert_name": "Breakout signal"
}

// Batch
[
  {"text": "...", "source": "..."},
  {"text": "...", "source": "..."}
]
```

**Security:**
- **HMAC-SHA256 signature verification:** When `WEBHOOK_SECRET` is set, requests must include `X-Webhook-Signature` header
- **Dedup:** Document ID `webhook_{md5(text)[:12]}`
- **Minimum length:** text < 10 chars is skipped

**Response format:**
```json
{"ingested": 2, "total": 3}
```

**Configuration:**
| Variable | Default | Description |
|----------|---------|-------------|
| `WEBHOOK_ENABLED` | `false` | Master switch |
| `WEBHOOK_PORT` | `8081` | HTTP port |
| `WEBHOOK_SECRET` | (empty) | HMAC secret; empty = no verification |

### 4.8 F10: Admin Dashboard

**Purpose:** Provide a web UI to view bot status, knowledge base, config, and FAQ management.

**Design points:**

- **New file:** `bot/admin.py` implements `AdminServer`
- **Stack:** aiohttp + inline HTML/CSS/JS single-page app (zero frontend dependencies)
- **UI style:** Dark theme (Slate palette), responsive grid, auto-refresh

**Routes:**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/` | HTML dashboard page |
| GET | `/admin/api/stats` | Query stats JSON |
| GET | `/admin/api/config` | Current config snapshot |
| GET | `/admin/api/kb` | Knowledge-base doc count + samples |
| GET | `/admin/api/faq` | Current FAQ content |
| POST | `/admin/api/faq/generate` | Trigger FAQ regeneration |

**Dashboard cards:**
1. **Statistics** — total queries, auto-replies, forwards, avg confidence, avg latency, uptime
2. **Configuration** — current config JSON
3. **Knowledge Base** — total docs + last 10 samples (ID, type, preview)
4. **Recent Queries** — last 10 queries (question, confidence, action, latency)
5. **FAQ** — current FAQ list + “Generate FAQ” button

**Security:**
- **API auth middleware:** When `ADMIN_SECRET` is set, `/admin/api/*` requests must include `X-Admin-Secret` header
- Dashboard HTML itself needs no auth (UI only; data via API)
- Stats auto-refresh every 30 seconds

**Configuration:**
| Variable | Default | Description |
|----------|---------|-------------|
| `ADMIN_ENABLED` | `false` | Master switch |
| `ADMIN_PORT` | `8082` | HTTP port |
| `ADMIN_SECRET` | (empty) | API secret; empty = no verification |

---

## 5. Data Flow Diagrams

### Owner Voice Message (F3)

```
Owner sends voice → on_message detects audio attachment
  → _handle_voice_message()
    → download attachment → write temp file
    → Whisper API transcription → text
    → filter (< 5 chars)
    → embed (text-embedding-3-small) → ChromaDB (type=owner_voice)
```

### Chart Comparative Analysis (F4)

```
User sends image + text ("How's ES looking")
  → _handle_message()
    → retrieve_context("How's ES looking", top_k=3) → [historical analysis chunks]
    → analyze_image(images, text, context_chunks=historical)
      → GPT-4o vision prompt includes historical comparison
    → generate enhanced reply
```

### Webhook Data Ingest (F8)

```
External system (TradingView/script)
  → POST /webhook/ingest (JSON + HMAC signature)
    → verify signature
    → parse JSON (single/batch)
    → each item: embed → ChromaDB (type=external_data)
    → return {"ingested": N}
```

---

## 6. Configuration Parameters

All Phase 3 environment variables:

```env
# F1: Thread support
THREAD_AUTO_REPLY=true            # Thread reply toggle
THREAD_CONTEXT_MESSAGES=15        # Thread history message count

# F2: Daily digest
DIGEST_ENABLED=false              # Master switch
DIGEST_HOUR=22                    # UTC hour
DIGEST_CHANNEL_ID=0               # Publish channel (0=DM only)

# F7: Scheduled ingest
INGEST_INTERVAL_HOURS=0           # Ingest interval (0=disabled)
STYLE_INTERVAL_HOURS=0            # Style analysis interval (0=disabled)

# F8: Webhook
WEBHOOK_ENABLED=false             # Master switch
WEBHOOK_PORT=8081                 # HTTP port
WEBHOOK_SECRET=                   # HMAC secret

# F10: Admin panel
ADMIN_ENABLED=false               # Master switch
ADMIN_PORT=8082                   # HTTP port
ADMIN_SECRET=                     # API secret
```

---

## 7. File Change List

### New Files (5)

| File | Lines | Feature |
|------|-------|---------|
| `bot/digest.py` | 190 | DigestCog — daily digest scheduling & Embed building |
| `bot/faq.py` | 125 | FAQ generation engine — GPT clustering + JSON persistence |
| `bot/ingestion_scheduler.py` | 136 | IngestionSchedulerCog — scheduled subprocess ingest |
| `bot/webhook.py` | 133 | WebhookServer — HTTP data ingest |
| `bot/admin.py` | 320 | AdminServer — web dashboard + REST API |

### Modified Files (5)

| File | Changes |
|------|---------|
| `bot/config.py` | Add `THREAD_AUTO_REPLY`, `THREAD_CONTEXT_MESSAGES` |
| `bot/listener.py` | F1: Thread support methods; F3: `_handle_voice_message()`; F4: vision RAG retrieval |
| `bot/rag.py` | F4: `analyze_image()` adds `context_chunks` parameter |
| `bot/commands.py` | F6: `/faq`, `/generate_faq` slash commands |
| `bot/main.py` | Register DigestCog, IngestionSchedulerCog; start WebhookServer, AdminServer |
| `.env.example` | Add all Phase 3 config variables |

---

## 8. Security Design

| Component | Security Measures |
|-----------|-------------------|
| Webhook | HMAC-SHA256 signature verification (`WEBHOOK_SECRET`) |
| Admin Panel | API key middleware (`ADMIN_SECRET`, protects API routes only) |
| Voice transcription | Owner messages only; temp files cleaned in `finally` |
| FAQ generation | `/generate_faq` is Owner-only |
| Scheduled ingest | Subprocess 1h timeout; failure DM to Owner |
| All new features | Disabled by default (opt-in); no impact on existing runtime |

---

## 9. Dependencies & Compatibility

- **No new dependencies:** All features use existing packages (`aiohttp`, `openai`, `discord.py`, `chromadb`)
- **Python version:** 3.11+ (uses `type | None` syntax)
- **Test compatibility:** All 139 existing tests pass; no breaking changes
- **Backward compatible:** All features default off; after upgrade, no `.env` changes required to keep current behavior
