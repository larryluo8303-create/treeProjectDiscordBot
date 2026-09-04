> **Archived**: Historical design/phase guide for reference only. See living docs under architecture/features/getting-started for current guidance.

# Phase 1 & Phase 2: Core Features & Enhancements — Design Document

---

## Table of Contents

- [1. Background & Goals](#1-background--goals)
- [2. System Architecture](#2-system-architecture)
- [3. Tech Stack](#3-tech-stack)
- [4. Phase 1 — Core Feature Design](#4-phase-1--core-feature-design)
  - [4.1 Config Layer (config.py)](#41-config-layer-configpy)
  - [4.2 Data Ingestion Layer (ingestion/)](#42-data-ingestion-layer-ingestion)
  - [4.3 RAG Core Engine (rag.py)](#43-rag-core-engine-ragpy)
  - [4.4 Confidence Routing (confidence.py)](#44-confidence-routing-confidencepy)
  - [4.5 Message Listener (listener.py)](#45-message-listener-listenerpy)
  - [4.6 Owner Review UI (review.py)](#46-owner-review-ui-reviewpy)
  - [4.7 ChromaDB Async Wrapper (chromadb_async.py)](#47-chromadb-async-wrapper-chromadb_asyncpy)
  - [4.8 Bot Entry Point (main.py)](#48-bot-entry-point-mainpy)
- [5. Phase 2 — Enhancement Design](#5-phase-2--enhancement-design)
  - [5.1 E1: Slash Commands (commands.py)](#51-e1-slash-commands-commandspy)
  - [5.2 E2: Stats Tracking (stats.py)](#52-e2-stats-tracking-statspy)
  - [5.3 E3: Negative Feedback Learning](#53-e3-negative-feedback-learning)
  - [5.4 E4: Embedding Cache (cache.py)](#54-e4-embedding-cache-cachepy)
  - [5.5 E5: Token Bucket Rate Limiting](#55-e5-token-bucket-rate-limiting)
  - [5.6 E7: Graceful Shutdown](#56-e7-graceful-shutdown)
  - [5.7 E8: Multilingual Support (i18n)](#57-e8-multilingual-support-i18n)
  - [5.8 E10: Test Coverage Improvements](#58-e10-test-coverage-improvements)
  - [5.9 BigTreeSignal Promotion System](#59-bigtreesignal-promotion-system)
  - [5.10 Offline Backfill](#510-offline-backfill)
  - [5.11 Multi-Source Ingestion (YouTube / PDF)](#511-multi-source-ingestion-youtube--pdf)
  - [5.12 Vision Image Analysis](#512-vision-image-analysis)
  - [5.13 Health Checks (health.py)](#513-health-checks-healthpy)
- [6. Data Flow Architecture](#6-data-flow-architecture)
- [7. File Inventory](#7-file-inventory)
- [8. Configuration Parameter Reference](#8-configuration-parameter-reference)
- [9. Security Design](#9-security-design)
- [10. Dependency List](#10-dependency-list)

---

## 1. Background & Goals

### Background

Operate a Discord stock/investing channel with 5000+ members. The channel owner cannot reply to every question 24/7. An AI assistant is needed that:
- Auto-replies in the owner's own tone and knowledge
- Forwards uncertain questions to the owner for human review
- Never fabricates investment advice

### Phase 1 Goals — Core RAG Auto-Reply

1. Ingest 200K+ historical Discord messages as a knowledge base
2. Build vector retrieval with OpenAI embeddings + ChromaDB
3. Generate replies that mimic the owner's style with GPT-4o-mini
4. Confidence routing: high-confidence auto-reply, low-confidence human review
5. Owner DM review UI (Approve / Edit / Reject)

### Phase 2 Goals — Enhancements & Operations

1. Slash Commands (`/ask`, `/status`, `/stats`)
2. Stats tracking and persistence
3. Negative feedback loop (rejected replies as counterexamples)
4. Embedding cache to reduce API calls
5. Token Bucket advanced rate limiting
6. Graceful shutdown (signal handling + state save)
7. Multilingual support (Chinese / English)
8. BigTreeSignal promotion system
9. Offline backfill (answer missed questions after downtime)
10. Multi-source data ingestion (YouTube videos, PDF books)
11. GPT-4o Vision image analysis
12. Health check endpoint
13. Test coverage improvements (96 → 139 tests)

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Offline Data Ingestion Layer              │
│  ingestion/preprocess.py → ingestion/ingest.py → ChromaDB   │
│  ingestion/analyze_style.py → data/style_profile.txt        │
│  ingestion/ingest_youtube.py → ChromaDB                     │
│  ingestion/ingest_pdf.py → ChromaDB                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    Bot Runtime Layer (main.py)               │
│                                                              │
│  MessageListener (Cog)                                       │
│  ├─ on_message → filter → rate limit → queue → _handle_message│
│  ├─ RAG Pipeline: retrieve_context → generate_answer         │
│  ├─ Confidence Router: route_answer                          │
│  ├─ Auto-reply OR send_for_review (Owner DM)                │
│  ├─ Vision: analyze_image (GPT-4o)                          │
│  ├─ Auto-learn: _learn_owner_message → ChromaDB             │
│  ├─ Offline backfill: _backfill_offline_messages            │
│  └─ Promotion: CTA / Signal query / Welcome / Testimonial   │
│                                                              │
│  BotCommands (Cog) — /ask, /status, /stats, /faq            │
│  PromotionCommands (Cog) — /signal, /schedule_promo, ...    │
│  SchedulerCog (Cog) — scheduled promo posts                  │
│  HealthCog (Cog) — Heartbeat + HTTP /health                 │
│                                                              │
│  Support modules:                                            │
│  ├─ stats.py — BotStats stats singleton                       │
│  ├─ cache.py — EmbeddingCache LRU                           │
│  ├─ review.py — ReviewView (Approve/Edit/Reject)            │
│  ├─ confidence.py — routing decisions + signal detection     │
│  ├─ promo_config.py — promotion helper functions              │
│  ├─ testimonials.py — user testimonial collection            │
│  └─ chromadb_async.py — AsyncCollection wrapper              │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Tech Stack

| Component | Choice | Notes |
|------|------|------|
| Language | Python 3.11+ | Uses `type \| None` syntax |
| Discord | discord.py 2.3+ | Cog architecture, Slash Commands, UI Views |
| LLM | OpenAI GPT-4o-mini | Generate replies (~$0.15/1M input tokens) |
| Vision | OpenAI GPT-4o | Image analysis |
| Embeddings | text-embedding-3-small | Vectorization (~$0.02/1M tokens) |
| Vector DB | ChromaDB (local persistent) | Zero deployment cost |
| Tokenizer | tiktoken (cl100k_base) | Chunk sizing |
| HTTP | aiohttp | Health check endpoint |
| Config | python-dotenv | `.env` file management |
| Audio/Video | yt-dlp + Whisper API | YouTube video ingestion |
| PDF | PyMuPDF (fitz) | PDF book ingestion |

**Monthly operating cost:** ~$30-50 (1000 questions/day), one-time ingestion ~$1-3 (200K posts)

---

## 4. Phase 1 — Core Feature Design

### 4.1 Config Layer (config.py)

**Responsibility:** Centralize all configuration parameters, loaded from the `.env` file.

**Design points:**

- Use `python-dotenv`'s `load_dotenv()` to read `.env` at module load time
- All config variables are module-level constants with type annotations and defaults
- `TARGET_CHANNEL_IDS` / `PROMO_CHANNEL_IDS` parsed as `list[int]`
- System Prompt template (`SYSTEM_PROMPT_TEMPLATE`) embeds Chinese investing-domain rules:
  - Price-level redaction (forbid outputting specific price numbers)
  - Style matching (mimic the owner's concise, direct tone)
  - Don't answer when uncertain (low confidence scores 1-3)
  - Strict scoring standard (CONFIDENCE: 1-10)
- `LOCALE` dictionary supports `zh` / `en`
- Logging: RotatingFileHandler (10MB × 5 backups) + StreamHandler

**Key config items:** 55+ environment variables (see Section 8 for the full table)

### 4.2 Data Ingestion Layer (ingestion/)

#### 4.2.1 Data Preprocessing (preprocess.py)

**Responsibility:** Convert DiscordChatExporter JSON into embeddable document chunks.

**Processing flow:**

```
load_exports() → build_qa_pairs() + group_consecutive()
       ↓                    ↓
  filter_owner_messages    Q&A pairing (question + reply)
       ↓                    ↓
  clean_message()          Merge consecutive messages (2-minute window)
       ↓                    ↓
  chunk_text()             Output: [{id, text, metadata}]
```

**Core functions:**

- `load_exports(dir)` — Load all `.json` files, extract messages and user info
- `build_qa_pairs(msgs, owner_id)` — Build `Q: ... A: ...` format from Owner replies to user questions
- `group_consecutive(msgs, owner_id, window=120s)` — Merge messages posted consecutively within 2 minutes
- `clean_message(content, users)` — Resolve `<@USER_ID>` mentions, clean custom emoji
- `chunk_text(text, max_tokens=500, overlap=50)` — Chunk at paragraph/sentence boundaries with 50-token overlap
- `filter_owner_messages(msgs, owner_id)` — Keep only Owner messages
- `preprocess_all(dir, owner_id)` — Full pipeline

**Output document format:**
```python
{
    "id": "msg_123456",
    "text": "做ES的话主要看4小时图...",
    "metadata": {
        "type": "qa_pair" | "standalone" | "grouped",
        "source_message_id": "123456",
        "timestamp": "2023-01-15T10:30:00",
        "channel_id": "...",
        "chunk_index": 0,
        "total_chunks": 1,
    }
}
```

#### 4.2.2 Vector Storage (ingest.py)

**Responsibility:** Embed preprocessed documents and store them in ChromaDB.

**Design points:**

- **ChromaDB persistence:** `PersistentClient(path="./chromadb_store")`, cosine similarity space
- **Incremental ingestion:** Query existing IDs, skip already-ingested documents
- **Batch processing:** 100 documents per batch (`EMBED_BATCH_SIZE`)
- **Token truncation:** Auto-truncate text over 8191 tokens (embedding model hard limit)
- **Rate protection:** 0.25s delay between batches; 30s backoff retry on `RateLimitError`
- **Progress display:** tqdm progress bar
- **CLI args:** `--sample N` (test sample), `--export-dir`, `--owner-id`, `--db-path`

#### 4.2.3 Style Analysis (analyze_style.py)

**Responsibility:** Analyze writing-style features from Owner historical messages.

**Analysis dimensions:**
- Average reply length (chars/words)
- High-frequency phrases (bigram / trigram)
- Emoji usage patterns
- Message length distribution
- Common opening words
- Typical message samples near median length

**Output:** `data/style_profile.txt`, automatically loaded into the system prompt during RAG generation.

### 4.3 RAG Core Engine (rag.py)

**Responsibility:** Full RAG pipeline — retrieve → generate → post-process.

#### Retrieval Stage (`retrieve_context`)

```python
async def retrieve_context(question, collection, openai_client,
                           top_k=8, max_distance=0.6) -> list[dict]:
```

1. **Embed query:** Call `text-embedding-3-small` on the question text (with LRU cache)
2. **Vector search:** ChromaDB `query(n_results=top_k)`
3. **Distance filter:** Discard results with cosine distance > `RAG_MAX_DISTANCE`
4. **Dedup:** Remove near-duplicates via head/tail text hash
5. **Return:** `[{text, score, distance, metadata}]` sorted by relevance

#### Generation Stage (`generate_answer`)

1. **Load style guide:** Prefer `data/style_profile.txt`, 5-minute cache TTL
2. **Build System Prompt:** Template + style + negative-feedback guidance
3. **Build User Prompt:** Retrieved context (distinguish Q&A pairs vs standalone posts) + conversation history + question
4. **Call GPT-4o-mini:** `temperature=0.5`, `max_tokens=500`
5. **Parse confidence:** Regex extract `CONFIDENCE: X`; default to 3 on parse failure
6. **Price redaction:** Regex-replace specific price numbers leaked in the reply

#### Price Redaction (`_redact_price_levels`)

Even when prompt rules forbid mentioning prices, the LLM occasionally still leaks them. The post-processing layer uses 10+ regex rules as a safety net:

- `支撑 3900` → `支撑附近`
- `突破 18000` → `突破关键位`
- `目标价 250` → `目标位`
- `止损 3850` → `止损位`
- `区间 3900-3950` → `对应区间`
- Keep indicator parameters (EMA13, MA200, RSI 70) and percentages

#### Retry Mechanism (`_openai_chat_with_retry`)

- Auto-retry once on `APITimeoutError` / `APIConnectionError`
- On second failure return `None`; upper layer degrades to "unable to reply"

#### Vision Analysis (`analyze_image`)

```python
async def analyze_image(image_urls, user_text, openai_client,
                        conversation_history="", context_chunks=None):
```

- Use GPT-4o Vision to analyze chart screenshots
- Support up to 4 images (GPT-4o limit)
- Vision-specific system prompt includes technical-analysis guidance
- Same price-redaction post-processing applied

### 4.4 Confidence Routing (confidence.py)

**Responsibility:** Decide whether each reply is auto-sent or forwarded to Owner for review.

**Routing matrix:**

| Condition | Action | Reason |
|------|------|------|
| Signal/trade query (`is_signal_query`) | Forward to Owner | Needs live market confirmation |
| "Uncertain, wait for owner" reply (`is_fallback_answer`) | Auto-reply | Safe fallback reply |
| No relevant context (`context_count == 0`) | Forward to Owner | Knowledge base has no coverage |
| Context distance too high (`best_distance > 0.95`) | Forward to Owner | Poor match quality |
| Confidence below threshold (`confidence < threshold`) | Forward to Owner | LLM is uncertain |
| None of the above | Auto-reply | High confidence + high-quality context |

**Signal query detection (`is_signal_query`):**

Multi-pattern regex matching for trade-related questions (Simplified/Traditional Chinese), including:
- Buy/sell/long/short/open/close/entry/exit
- Signal / 信号 / 讯号 + question words
- Entry/exit/stop points
- Variants like "can I buy now", "should I go long"

### 4.5 Message Listener (listener.py)

**Responsibility:** Discord on_message handling, filtering, rate limiting, queueing, and full reply flow.

**Architecture:** `MessageListener(commands.Cog)` — ~1000+ line core module

#### Message Filter Chain (`_should_skip`)

```
Message enters
  ├─ Bot message? → skip
  ├─ Owner message (not @bot)? → skip (route to auto-learn instead)
  ├─ Channel not in TARGET_CHANNEL_IDS? → skip
  ├─ Thread and THREAD_AUTO_REPLY=false? → skip
  ├─ Empty message (no text, no images)? → skip
  ├─ Spam/ad keywords? → skip
  ├─ Polite/thanks message? → skip
  └─ Non-question / chat (RESPOND_MODE gate)? → skip
```

#### Response Trigger Judgment (`_is_response_warranted`)

| Condition | Always respond |
|------|----------|
| Message contains images | ✅ |
| @mention Bot | ✅ |
| Reply to Bot's message | ✅ |
| Contains question mark / question words (questions mode) | ✅ |
| Pure chat (mention_only mode) | ❌ |

#### Rate Limiting

- **Per-user Token Bucket:** 1 token / `USER_COOLDOWN_SECONDS` (default 30s), burst=1
- **Global Token Bucket:** `GLOBAL_MAX_PER_MINUTE` tokens/min (default 10), refill_rate = N/60 per sec
- After a reply, consume one token from each bucket

#### Conversation Memory (`_channel_memory`)

- **Per-channel rolling window:** `{channel_id: [(timestamp, role, text), ...]}`
- Keep at most `CONVERSATION_MEMORY_SIZE` entries (default 10), TTL `CONVERSATION_MEMORY_TTL` seconds (default 1800)
- Truncate each message to 500 characters
- Auto-clean expired channels (triggered when more than 50 channels)

#### Message Processing Queue

- `asyncio.Queue` with a single worker for sequential processing (avoid concurrent API calls)
- On shutdown, best-effort drain remaining messages
- Update `_last_seen` after each message is processed

#### Auto-Learning (`_learn_owner_message`)

Owner messages in target channels are automatically embedded and stored:
- Skip short messages (<10 chars) and pure emoji
- If replying to a user question, build Q&A pair format
- Use `live_{message_id}` as document ID (dedup)
- Async fire-and-forget; does not block the main flow

#### Full Handling Flow (`_handle_message`)

```
Dequeue message → build conversation history
  ├─ Thread? → _fetch_thread_context()
  └─ Regular channel? → _format_memory()
  ↓
  Detect images
  ├─ Has images? → analyze_image() (Vision)
  └─ Text only? → run_rag_pipeline() (RAG)
  ↓
  route_answer() → {action, answer, confidence, reason}
  ↓
  record_query() → BotStats
  ↓
  Structured log (JSON)
  ↓
  ├─ auto_reply → message.reply()
  │    ├─ Promo channel? → append CTA (every N times)
  │    ├─ Discord 2000-char truncation
  │    ├─ Record in conversation memory
  │    └─ DM Owner notification
  └─ forward → send_for_review()
       └─ Signal query + promo channel? → send CTA Embed
```

### 4.6 Owner Review UI (review.py)

**Responsibility:** DM review flow for low-confidence replies.

#### ReviewView (discord.ui.View)

Three buttons:

| Button | Behavior |
|------|------|
| ✅ Approve | Post draft to original channel → auto-learn Q&A → stop View |
| ✏️ Edit | Open Modal (prefilled draft, 4000-char limit) → post edited version → auto-learn |
| ❌ Reject | Do not post → store negative sample → stop View |

**Review DM Embed includes:**
- Channel, asker, confidence
- Original question text
- Draft reply
- Top 3 retrieved context summaries
- Jump link to original message

**Auto-learn (`_learn_qa`):** After Approve/Edit, embed the Q&A pair into ChromaDB (type=`qa_pair`, source=`owner_review`)

**Negative sample storage (`_store_negative_sample`):** On Reject, store the rejected Q&A in `data/negative_samples.json` (keep at most the latest 50)

**Timeout:** Silently expires after 1 hour of no action

**Auto-reply notification (`notify_owner_auto_reply`):** When the bot auto-replies, also DM the Owner a notification (FYI only, no action required)

### 4.7 ChromaDB Async Wrapper (chromadb_async.py)

**Responsibility:** Wrap ChromaDB's sync API as async.

The ChromaDB Python client is synchronous; calling it directly in async code blocks the event loop. `AsyncCollection` proxies all calls via `asyncio.to_thread`:

```python
class AsyncCollection:
    async def query(**kwargs) → dict
    async def get(**kwargs) → dict
    async def count() → int
    async def add(**kwargs)
    async def upsert(**kwargs)
    async def delete(**kwargs)
    async def update(**kwargs)
```

### 4.8 Bot Entry Point (main.py)

**Responsibility:** Initialize all components, register Cogs, start the Bot.

**Startup order:**
1. Validate config (`DISCORD_BOT_TOKEN`, `OPENAI_API_KEY`)
2. Create OpenAI AsyncClient (timeout=60s, retries=0)
3. Load/create ChromaDB collection → wrap with AsyncCollection
4. Create Discord Bot (intents: message_content + members)
5. Register Cogs: MessageListener → PromotionCommands → BotCommands → SchedulerCog → HealthCog → ...
6. Start optional HTTP services (WebhookServer, AdminServer)
7. Register signal handlers (SIGINT/SIGTERM, Windows-compatible)
8. `asyncio.wait` until Bot runs or shutdown signal

**Shutdown flow:**
1. Receive signal → set `shutdown_event`
2. Stop HTTP services
3. Unload Cogs one by one (each `cog_unload` saves state)
4. Close Bot connection

---

## 5. Phase 2 — Enhancement Design

### 5.1 E1: Slash Commands (commands.py)

**New file:** `bot/commands.py`

**BotCommands Cog — general commands:**

| Command | Permission | Description |
|------|------|------|
| `/ask <question>` | Everyone | Start a RAG query via Slash Command |
| `/status` | Everyone | Show Bot uptime, queue depth, knowledge-base document count |
| `/stats` | Owner | Query stats (total, auto-reply rate, avg confidence, top questions) |

**PromotionCommands Cog — promotion commands (see Section 5.9)**

### 5.2 E2: Stats Tracking (stats.py)

**New file:** `bot/stats.py`

**BotStats class — module-level singleton:**

**Tracked metrics:**
- `total_queries` — total query count
- `auto_replies` / `forwards` — auto-reply / forward counts
- `total_confidence` / `total_latency_ms` — cumulative confidence / latency
- `channel_counts` — per-channel stats `{channel_id: count}`
- `recent` — latest 200 `QueryRecord` entries (deque)

**QueryRecord dataclass:**
```python
@dataclass
class QueryRecord:
    question: str
    channel_id: int
    confidence: int
    action: str          # "auto_reply" or "forward"
    latency_ms: int
    timestamp: float
```

**Persistence:**
- Async save to `data/stats.json` every 60 seconds (dirty-flag optimization)
- Atomic write: write `.tmp` then `os.replace`
- Auto-load on startup

**API:**
- `record_query(...)` — record one query
- `snapshot()` → `dict` — JSON-serializable stats snapshot
- `top_questions(limit)` → `list[dict]` — recent popular questions
- `start_periodic_save()` / `stop()` — lifecycle management

### 5.3 E3: Negative Feedback Learning

**Modified files:** `bot/review.py`, `bot/rag.py`

**Flow:**
1. Owner clicks ❌ Reject → `_store_negative_sample(question, bad_answer)` → `data/negative_samples.json`
2. On next generation: `_build_negative_guidance()` takes the latest 5 negative samples
3. Inject into System Prompt: `【以下是被频道主拒绝的回答示例，请避免类似的回答方式：】`
4. LLM uses these counterexamples to avoid repeating the same mistakes

**Storage format:** JSON array, each entry `{question, bad_answer, timestamp}`, max 50 entries

### 5.4 E4: Embedding Cache (cache.py)

**New file:** `bot/cache.py`

**EmbeddingCache — module-level singleton:**

- **LRU policy:** `OrderedDict`, max 256 entries (`_DEFAULT_MAX_SIZE`)
- **TTL expiry:** 10 minutes (`_DEFAULT_TTL`), timed with `time.monotonic`
- **Key generation:** `SHA-256(text.strip().lower())`
- **Integration point:** `retrieve_context` in `rag.py` checks cache before calling the embedding API
- **Stats:** `hits` / `misses` / `hit_rate` — shown by `/status`

### 5.5 E5: Token Bucket Rate Limiting

**Modified file:** `bot/listener.py`

Replace the previous simple cooldown timer with a dual Token Bucket:

**Per-user Bucket:**
- Capacity 1 token, refill rate = 1 / `USER_COOLDOWN_SECONDS`
- On each message, check whether tokens ≥ 1; if not, rate-limit

**Global Bucket:**
- Capacity `GLOBAL_MAX_PER_MINUTE` tokens
- Refill rate = `GLOBAL_MAX_PER_MINUTE` / 60 per second
- Shared by all users

A message is processed only when both buckets allow it; after a reply, consume 1 token from each.

### 5.6 E7: Graceful Shutdown

**Modified file:** `bot/main.py`

**Signal handling:**
- SIGINT / SIGTERM → set `shutdown_event` → `asyncio.wait` returns
- Windows compatibility: `signal.signal` fallback (no `add_signal_handler` support)

**Shutdown flow:**
1. Stop HTTP servers (WebhookServer, AdminServer)
2. Unload Cogs one by one → trigger `cog_unload()`:
   - `MessageListener.cog_unload()` → cancel worker/save task → save `last_seen` → `bot_stats.stop()`
   - `SchedulerCog.cog_unload()` → stop scheduler loop
   - `HealthCog.cog_unload()` → stop heartbeat → clean up HTTP runner
3. Close Bot connection

### 5.7 E8: Multilingual Support (i18n)

**Modified file:** `bot/config.py`

**Implementation:**
- `BOT_LANGUAGE` env var (`zh` / `en`)
- `LOCALE` dictionary: `{lang: {key: string}}`
- `get_locale(key)` with fallback to `zh`

**Translated strings:**
- Rate-limit hints, unable-to-reply, uncertain replies
- Owner-only hints, channel-disabled hints
- Promotion-related hints
- Review button results
- Conversation labels ("成员" / "Member")

### 5.8 E10: Test Coverage Improvements

**New files:** `tests/test_stats.py`, `tests/test_cache.py`, `tests/test_listener.py`, `tests/test_review.py`

| Test file | Covers module | Notes |
|----------|----------|------|
| `test_ingestion.py` | preprocess.py | Message cleaning, chunking, Q&A pairing |
| `test_rag.py` | rag.py | Retrieval, generation, price redaction |
| `test_confidence.py` | confidence.py | Routing decisions, signal detection, confidence parsing |
| `test_promotion.py` | promo_config.py | CTA generation, channel checks |
| `test_stats.py` | stats.py | Recording, snapshots, persistence |
| `test_cache.py` | cache.py | LRU, TTL, hit rate |
| `test_listener.py` | listener.py | Filter chain, rate limiting, queue |
| `test_review.py` | review.py | Review flow, negative feedback |

**Total:** 139 test cases, all passing

### 5.9 BigTreeSignal Promotion System

**New files:** `bot/promo_config.py`, `bot/commands.py` (PromotionCommands), `bot/scheduler.py`, `bot/testimonials.py`

**Design principle:** Promotion behavior is fully isolated to `PROMO_CHANNEL_IDS` and does not affect Q&A in `TARGET_CHANNEL_IDS`. `PROMO_ENABLED` is the master switch.

#### Promotion Helpers (promo_config.py)

- `is_promo_channel(channel_id)` — whether the channel is in the promo list
- `get_signal_cta_embed()` — signal-query CTA Embed
- `get_auto_reply_cta()` — CTA text appended to auto-replies
- `should_append_cta(counter)` — append CTA every N replies (`CTA_FREQUENCY`)
- `get_welcome_embed(member)` — new-member welcome Embed
- `get_signal_product_embed()` — `/signal` product info Embed

#### Promotion Slash Commands

| Command | Permission | Description |
|------|------|------|
| `/signal` | Everyone | Show BigTreeSignal product info |
| `/schedule_promo` | Owner | Schedule a promo post |
| `/list_promos` | Owner | List scheduled promos |
| `/cancel_promo` | Owner | Cancel a scheduled promo |
| `/post_promo` | Owner | Post a promo immediately |
| `/schedule_trial` | Owner | Schedule free-trial promotion |
| `/schedule_lesson` | Owner | Schedule a lesson post (supports repeat) |
| `/list_lessons` | Owner | List lesson schedule |
| `/cancel_lesson` | Owner | Cancel a lesson schedule |
| `/testimonials` | Everyone | Show user testimonials |

#### Scheduled Posts (scheduler.py)

- `SchedulerCog` — 60-second loop checking `data/promos.json` and `data/lessons.json`
- On due time, auto-send Embed to the target channel
- Lesson posts support repeat (`repeat_days`); after posting, auto-schedule the next one
- CRUD helpers: `add_promo/list_promos/cancel_promo` + `add_lesson/list_lessons/cancel_lesson`

#### User Testimonials (testimonials.py)

- Auto-detect profit/copy-trading messages from users (`_TESTIMONIAL_PATTERNS`)
- DM Owner for review (Approve / Reject)
- On Approve, forward to `TESTIMONIAL_CHANNEL_ID`
- Persist to `data/testimonials.json`

#### CTA Trigger Timing

| Scenario | Behavior |
|------|------|
| Auto-reply (promo channel) | Append CTA text every `CTA_FREQUENCY` replies |
| Signal-query forward (promo channel) | Send Signal CTA Embed |
| New member join (guild containing promo channels) | DM welcome Embed |

### 5.10 Offline Backfill

**Modified file:** `bot/listener.py`

**Purpose:** After bot downtime/restart, automatically scan target channels, find unanswered questions from the offline period, and catch up.

**Flow:**

1. `on_ready` → `_backfill_offline_messages()` (with asyncio.Lock to prevent duplicates)
2. Determine scan start:
   - Has `last_seen[channel_id]`? → start after that message ID
   - First run? → look back `OFFLINE_BACKFILL_LOOKBACK_HOURS` hours
3. Fetch message history (max `OFFLINE_BACKFILL_MAX_PER_CHANNEL` per channel)
4. Mark already-answered questions:
   - Method 1: Discord explicit reply (message reference)
   - Method 2: Owner posted within N minutes after the question (`OWNER_REPLY_WINDOW_MINUTES` heuristic)
5. Enqueue unanswered questions for processing
6. Owner offline messages go through auto-learn ingestion

**State persistence:** `data/last_seen.json` — periodic save every 30 seconds + save on shutdown

### 5.11 Multi-Source Ingestion (YouTube / PDF)

#### YouTube Video Ingestion (ingest_youtube.py)

**Flow:**
```
Video URL → try fetch captions (youtube_transcript_api)
  ├─ Has captions → use directly (free, instant)
  └─ No captions → download audio (yt-dlp, 32K mono MP3)
       ├─ < 24MB → Whisper API transcription directly
       └─ > 24MB → 10-minute segments → transcribe each → merge
  ↓
  chunk → embed → ChromaDB (incremental; already-ingested skipped)
```

**CLI:** `--urls "URL1" "URL2"` / `--url-file list.txt` / `--whisper-lang zh` / `--no-whisper`

**Cost:** Whisper ~$0.006/10 minutes

#### PDF Book Ingestion (ingest_pdf.py)

**Flow:**
```
PDF file → PyMuPDF extract text page by page
  → clean (strip headers/footers, merge hyphenated line breaks)
  → chunk → embed → ChromaDB
```

**CLI:** `--files "book.pdf"` / `--source "书名"` / `--dry-run`

**Features:** MD5 hash for document IDs; supports incremental ingestion

### 5.12 Vision Image Analysis

**Integrated in:** `bot/rag.py` + `bot/listener.py`

- Detect image attachments and Embed images in messages (up to 4)
- Analyze with GPT-4o Vision
- Vision-specific system prompt (technical-analysis oriented)
- Same price redaction applied
- Included in the confidence routing flow

### 5.13 Health Checks (health.py)

**New file:** `bot/health.py`

**HealthCog provides:**

1. **Heartbeat logs:** Every 5 minutes output uptime, guild count, WebSocket latency
2. **HTTP /health endpoint (optional):** Enabled when `HEALTH_PORT` is set
   - `GET /health` → `{status, uptime_seconds, guilds, ws_latency_ms}`
   - 200 = ready, 503 = not ready
   - For Docker / k8s health checks

---

## 6. Data Flow Architecture

### Full Message Processing Flow

```
User sends message
  ↓
  on_message()
  ├─ Owner message? → _learn_owner_message() → ChromaDB
  ├─ Owner voice? → _handle_voice_message() → Whisper → ChromaDB
  ├─ User testimonial? → _handle_testimonial() → DM Owner review
  ├─ _should_skip()? → discard
  └─ _is_rate_limited()? → discard
  ↓
  _queue.put(message)
  ↓
  _process_queue() → _handle_message()
  ├─ Build conversation history (Thread / Channel memory)
  ├─ Detect images
  │  ├─ Has images → analyze_image() (GPT-4o Vision)
  │  └─ Text only → run_rag_pipeline()
  │       ├─ retrieve_context() → ChromaDB
  │       └─ generate_answer() → GPT-4o-mini
  ├─ route_answer() → auto_reply / forward_to_owner
  ├─ bot_stats.record_query()
  ├─ Structured JSON log
  └─ Send reply / DM for review
```

### Knowledge Base Growth Paths

```
1. Offline ingestion (one-time)
   Discord JSON → preprocess → ingest → ChromaDB

2. YouTube ingestion (one-time)
   Video → transcript/whisper → chunk → ingest → ChromaDB

3. PDF ingestion (one-time)
   PDF → PyMuPDF → chunk → ingest → ChromaDB

4. Real-time auto-learning (continuous)
   Owner text messages → embed → ChromaDB (type=owner_post / qa_pair)
   Owner voice messages → Whisper → embed → ChromaDB (type=owner_voice)

5. Review learning (continuous)
   Approve/Edit → embed Q&A pair → ChromaDB (type=qa_pair, source=owner_review)
```

---

## 7. File Inventory

### Bot Runtime Layer (`bot/`)

| File | Lines | Description |
|------|------|------|
| `main.py` | 175 | Bot entry: init, Cog registration, signal handling, graceful shutdown |
| `config.py` | 265 | All config, System Prompt template, Locale dictionary |
| `listener.py` | 1038 | Message listening: filter, rate limit, queue, RAG flow, auto-learn, backfill |
| `rag.py` | 457 | RAG core: retrieve, generate, Vision, price redaction |
| `confidence.py` | 134 | Confidence routing, signal-query detection |
| `review.py` | 395 | Owner DM review (Approve/Edit/Reject), negative-sample storage |
| `commands.py` | 624 | Slash Commands (general + promotion + FAQ) |
| `stats.py` | 183 | BotStats singleton, persistence |
| `cache.py` | 73 | EmbeddingCache LRU + TTL |
| `chromadb_async.py` | 44 | ChromaDB async wrapper |
| `health.py` | 101 | Heartbeat logs + HTTP /health |
| `promo_config.py` | 144 | Promotion helper functions |
| `scheduler.py` | 287 | Scheduled promo/lesson post scheduling |
| `testimonials.py` | 244 | User testimonial collection and review |

### Data Ingestion Layer (`ingestion/`)

| File | Lines | Description |
|------|------|------|
| `preprocess.py` | 335 | Message preprocessing: load, Q&A pairing, grouping, cleaning, chunking |
| `ingest.py` | 221 | Embed + ChromaDB storage (batch, incremental) |
| `analyze_style.py` | 147 | Style feature analysis |
| `ingest_youtube.py` | 530 | YouTube video ingestion (captions + Whisper) |
| `ingest_pdf.py` | 210 | PDF book ingestion |

### Tests (`tests/`)

| File | Description |
|------|------|
| `test_ingestion.py` | Preprocessing logic tests |
| `test_rag.py` | RAG pipeline tests |
| `test_confidence.py` | Routing decision tests |
| `test_promotion.py` | Promotion feature tests |
| `test_stats.py` | Stats module tests |
| `test_cache.py` | Cache module tests |
| `test_listener.py` | Listener filter/rate-limit tests |
| `test_review.py` | Review flow tests |

---

## 8. Configuration Parameter Reference

### Required

| Variable | Description |
|------|------|
| `DISCORD_BOT_TOKEN` | Discord Bot Token |
| `OPENAI_API_KEY` | OpenAI API Key |
| `OWNER_USER_ID` | Channel owner Discord user ID |
| `TARGET_CHANNEL_IDS` | Monitored channel IDs (comma-separated) |

### OpenAI Models

| Variable | Default | Description |
|------|--------|------|
| `LLM_MODEL` | `gpt-4o-mini` | Generation model |
| `VISION_MODEL` | `gpt-4o` | Vision model |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `LLM_MAX_TOKENS` | `500` | Max generation tokens |
| `LLM_TEMPERATURE` | `0.5` | Generation temperature |

### RAG

| Variable | Default | Description |
|------|--------|------|
| `RAG_TOP_K` | `8` | Number of retrieval results |
| `RAG_MAX_DISTANCE` | `0.6` | Max cosine distance |
| `CONFIDENCE_THRESHOLD` | `7` | Minimum confidence for auto-reply |

### Conversation & Rate Limiting

| Variable | Default | Description |
|------|--------|------|
| `CONVERSATION_MEMORY_SIZE` | `10` | Conversation memory size |
| `CONVERSATION_MEMORY_TTL` | `1800` | Conversation memory TTL (seconds) |
| `USER_COOLDOWN_SECONDS` | `30` | Per-user cooldown seconds |
| `GLOBAL_MAX_PER_MINUTE` | `10` | Global max replies per minute |
| `RESPOND_MODE` | `questions` | Response mode (questions/mention_only/all) |

### Offline Backfill

| Variable | Default | Description |
|------|--------|------|
| `OFFLINE_BACKFILL_ENABLED` | `true` | Master switch |
| `OFFLINE_BACKFILL_LOOKBACK_HOURS` | `24` | First-run lookback hours |
| `OFFLINE_BACKFILL_MAX_PER_CHANNEL` | `100` | Max messages scanned per channel |
| `OFFLINE_BACKFILL_OWNER_REPLY_WINDOW_MINUTES` | `10` | Owner reply window (minutes) |
| `OFFLINE_LAST_SEEN_FILE` | `data/last_seen.json` | State persistence file |

### Data Ingestion

| Variable | Default | Description |
|------|--------|------|
| `CHROMADB_PATH` | `./chromadb_store` | ChromaDB storage path |
| `EXPORT_DIR` | `./data/exports` | Export file directory |
| `CHUNK_MAX_TOKENS` | `500` | Max tokens per chunk |
| `CHUNK_OVERLAP_TOKENS` | `50` | Chunk overlap tokens |
| `EMBED_BATCH_SIZE` | `100` | Embedding batch size |

### Promotion

| Variable | Default | Description |
|------|--------|------|
| `PROMO_ENABLED` | `true` | Promotion master switch |
| `PROMO_CHANNEL_IDS` | (empty) | Promo channel ID list |
| `SIGNAL_PRODUCT_NAME` | `BigTreeSignal` | Product name |
| `SIGNAL_PRODUCT_URL` | (empty) | Product URL |
| `SIGNAL_CTA_TEXT` | 想获取实时交易信号？... | CTA text |
| `AUTO_REPLY_CTA_TEXT` | 想获取实时交易信号？... | Auto-reply CTA |
| `CTA_FREQUENCY` | `5` | Append CTA every N replies |
| `FREE_TRIAL_ENABLED` | `false` | Free-trial switch |
| `FREE_TRIAL_URL` | (empty) | Trial URL |
| `WELCOME_MESSAGE` | 欢迎加入！... | New-member welcome text |
| `TESTIMONIAL_CHANNEL_ID` | `0` | Testimonial channel ID |
| `TESTIMONIAL_DETECTION_ENABLED` | `true` | Auto-detect testimonials |

### Other

| Variable | Default | Description |
|------|--------|------|
| `BOT_LANGUAGE` | `zh` | UI language (zh/en) |
| `LOG_LEVEL` | `INFO` | Log level |
| `HEALTH_PORT` | `0` | Health-check port (0=disabled) |

---

## 9. Security Design

| Layer | Measure |
|------|------|
| API keys | Managed via `.env`, excluded by `.gitignore`; Docker uses `env_file` |
| Input injection | User messages wrapped in context framing; not injected raw into system prompt |
| Rate limiting | Dual Token Bucket prevents abuse and cost runaway |
| Financial safety | System prompt forbids fabricating investment advice; price-redaction post-processing |
| Signal queries | Always forward to Owner for review; never auto-reply trade instructions |
| Least privilege | Bot only needs Read/Send Messages + Read History + Slash Commands |
| Channel isolation | `TARGET_CHANNEL_IDS` (Q&A) fully independent from `PROMO_CHANNEL_IDS` (promotion) |
| Atomic writes | All JSON persistence uses `.tmp` → `os.replace` atomic ops |
| Docker security | Never bake secrets into the image |

---

## 10. Dependency List

```
discord.py>=2.3.0         # Discord API
openai>=1.30.0            # GPT / Embedding / Whisper
chromadb>=0.5.0            # Vector database
python-dotenv>=1.0.0       # .env config
tiktoken>=0.7.0            # Token counting
aiohttp>=3.9.0             # HTTP services (health/webhook/admin)
tqdm>=4.66.0               # Progress bar (ingestion)
youtube-transcript-api>=0.6.0  # YouTube caption fetch
yt-dlp>=2024.1.0           # YouTube audio download
pymupdf>=1.24.0            # PDF text extraction
```

**Runtime:** Python 3.11+ (uses `type | None` union type syntax)
