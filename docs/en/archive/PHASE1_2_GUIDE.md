> **Archived**: Historical design/phase guide for reference only. See living docs under architecture/features/getting-started for current guidance.

# Phase 1 & Phase 2: Core & Enhancement Features — User Guide

---

## Table of Contents

- [1. Quick Start](#1-quick-start)
- [2. Full Deploy From Scratch](#2-full-deploy-from-scratch)
  - [2.1 Create a Discord Bot](#21-create-a-discord-bot)
  - [2.2 Get an OpenAI API Key](#22-get-an-openai-api-key)
  - [2.3 Install Environment & Dependencies](#23-install-environment--dependencies)
  - [2.4 Configure .env](#24-configure-env)
  - [2.5 Export Discord History](#25-export-discord-history)
  - [2.6 Ingest Data](#26-ingest-data)
  - [2.7 Start the Bot](#27-start-the-bot)
- [3. Data Ingestion Details](#3-data-ingestion-details)
  - [3.1 Discord History Ingestion](#31-discord-history-ingestion)
  - [3.2 Style Analysis](#32-style-analysis)
  - [3.3 YouTube Video Ingestion](#33-youtube-video-ingestion)
  - [3.4 PDF Book Ingestion](#34-pdf-book-ingestion)
- [4. Core Feature Usage](#4-core-feature-usage)
  - [4.1 How Auto-Reply Works](#41-how-auto-reply-works)
  - [4.2 Owner Review Flow](#42-owner-review-flow)
  - [4.3 Auto Learning](#43-auto-learning)
  - [4.4 Image Analysis](#44-image-analysis)
  - [4.5 Offline Backfill](#45-offline-backfill)
  - [4.6 Conversation Memory](#46-conversation-memory)
- [5. Slash Command Reference](#5-slash-command-reference)
  - [5.1 General Commands](#51-general-commands)
  - [5.2 Promotion Commands](#52-promotion-commands)
- [6. Promotion System Usage](#6-promotion-system-usage)
  - [6.1 Enable Promotion](#61-enable-promotion)
  - [6.2 CTA Triggers](#62-cta-triggers)
  - [6.3 Schedule Promo Posts](#63-schedule-promo-posts)
  - [6.4 Schedule Lesson Posts](#64-schedule-lesson-posts)
  - [6.5 User Testimonial Collection](#65-user-testimonial-collection)
  - [6.6 New Member Welcome](#66-new-member-welcome)
- [7. Configuration Tuning](#7-configuration-tuning)
  - [7.1 Respond Modes](#71-respond-modes)
  - [7.2 Confidence Threshold Tuning](#72-confidence-threshold-tuning)
  - [7.3 Rate Limit Tuning](#73-rate-limit-tuning)
  - [7.4 Language Switching](#74-language-switching)
- [8. Monitoring & Operations](#8-monitoring--operations)
  - [8.1 Logging](#81-logging)
  - [8.2 Health Checks](#82-health-checks)
  - [8.3 Viewing Stats](#83-viewing-stats)
- [9. Deployment Options](#9-deployment-options)
  - [9.1 Local Run](#91-local-run)
  - [9.2 Docker Deployment](#92-docker-deployment)
  - [9.3 systemd Deployment](#93-systemd-deployment)
- [10. Testing](#10-testing)
- [11. FAQ](#11-faq)
- [12. Full Configuration Reference](#12-full-configuration-reference)

---

## 1. Quick Start

**Prerequisites:** Python 3.11+, Discord Bot Token, OpenAI API Key

```powershell
# 1. Create virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables
copy .env.example .env
# Edit .env with real values

# 4. Export Discord history to data/exports/ (see section 2.5)

# 5. Ingest data
python -m ingestion.ingest

# 6. (Optional) Analyze style
python -m ingestion.analyze_style

# 7. Start the bot
python -m bot.main
```

After the bot starts you should see:

```
[INFO] bot.main: OpenAI client initialized
[INFO] bot.main: ChromaDB collection loaded — XXXXX documents
[INFO] bot.main: Starting Discord bot...
[INFO] bot.listener: Bot is ready — starting message queue worker
```

---

## 2. Full Deploy From Scratch

### 2.1 Create a Discord Bot

> Estimated time: ~10 minutes

1. Open https://discord.com/developers/applications
2. Click **New Application** → name it (e.g. "TreeBot Auto-Reply")
3. Left sidebar **Bot** → **Reset Token** → **copy and save the Token**
4. Enable Privileged Gateway Intents:
   - ✅ MESSAGE CONTENT INTENT (required)
   - ✅ SERVER MEMBERS INTENT (recommended)
5. Left sidebar **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: Read Messages, Send Messages, Read Message History, Use Slash Commands
6. Copy the generated URL → open in a browser → invite the bot to your server
7. Get your **User ID**: Discord Settings → Advanced → enable Developer Mode → right-click your name → Copy ID
8. Get **Channel ID**: right-click the target channel → Copy ID

### 2.2 Get an OpenAI API Key

> Estimated time: ~5 minutes

1. Open https://platform.openai.com/api-keys
2. Create a new secret key → copy and save it
3. Set a usage limit: https://platform.openai.com/settings/organization/limits

### 2.3 Install Environment & Dependencies

```powershell
# Confirm Python version
python --version    # needs 3.11+

# Create virtual environment
python -m venv .venv

# Activate (PowerShell)
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2.4 Configure .env

```powershell
copy .env.example .env
```

Edit `.env` with real values:

```env
# Required
DISCORD_BOT_TOKEN=your-bot-token
OPENAI_API_KEY=your-openai-key
OWNER_USER_ID=your-discord-user-id
TARGET_CHANNEL_IDS=channelId1,channelId2

# Recommended defaults
CONFIDENCE_THRESHOLD=7
RAG_TOP_K=8
RESPOND_MODE=questions
BOT_LANGUAGE=zh
```

> **Security note:** `.env` is already in `.gitignore`. Never commit it to version control.

### 2.5 Export Discord History

> Estimated time: 15–60 minutes (depends on channel size)

1. Download [DiscordChatExporter CLI](https://github.com/Tyrrrz/DiscordChatExporter/releases)
2. Export channel history as JSON:

```powershell
# Single channel
DiscordChatExporter.Cli export -t "BOT_TOKEN" -c CHANNEL_ID -f Json -o "data\exports\channel.json"

# Large channels: export by date range
DiscordChatExporter.Cli export -t "BOT_TOKEN" -c CHANNEL_ID -f Json --after "2020-01-01" --before "2023-01-01" -o "data\exports\ch_2020_2022.json"
DiscordChatExporter.Cli export -t "BOT_TOKEN" -c CHANNEL_ID -f Json --after "2023-01-01" -o "data\exports\ch_2023_now.json"
```

3. Confirm `.json` files exist under `data/exports/`

### 2.6 Ingest Data

```powershell
# Test ingest (100 messages)
python -m ingestion.ingest --sample 100

# Full ingest
python -m ingestion.ingest

# Verify
python -c "import chromadb; c = chromadb.PersistentClient('./chromadb_store'); col = c.get_collection('bigtree_knowledge'); print(f'Documents: {col.count()}')"
```

**Estimated time:** 200K messages → 15–30 minutes  
**Estimated cost:** ~$1–3 (one-time)

### 2.7 Start the Bot

```powershell
python -m bot.main
```

Stop: press `Ctrl+C` (triggers graceful shutdown and saves all state)

---

## 3. Data Ingestion Details

### 3.1 Discord History Ingestion

**Ingestion pipeline:**

```
data/exports/*.json
    ↓ load_exports() — load all JSON
    ↓ filter_owner_messages() — keep only Owner messages
    ↓ build_qa_pairs() — build Q&A pairs (Owner replies to user questions)
    ↓ group_consecutive() — merge consecutive messages within 2 minutes
    ↓ clean_message() — clean mentions and emoji formatting
    ↓ chunk_text() — chunk text over 500 tokens (50-token overlap)
    ↓ embed → ChromaDB
```

**Features:**

- **Incremental ingest:** Re-runs skip already-ingested documents
- **Q&A pairing:** When Owner replies to a user message, build `Q: ... A: ...` format for better retrieval
- **Batch processing:** 100 per batch (`EMBED_BATCH_SIZE`) with rate protection

**CLI options:**

```powershell
python -m ingestion.ingest                          # full ingest
python -m ingestion.ingest --sample 100             # sample test
python -m ingestion.ingest --export-dir ./my_data   # custom path
python -m ingestion.ingest --owner-id 12345         # specify Owner ID
python -m ingestion.ingest --db-path ./my_db        # custom DB path
```

### 3.2 Style Analysis

```powershell
python -m ingestion.analyze_style
```

Analyzes Owner writing style and saves to `data/style_profile.txt`:

- Average reply length
- High-frequency phrases
- Emoji usage habits
- Message length distribution
- Typical style samples

The bot loads this file on startup so generated replies more closely match Owner style.

> **Recommended:** Always run this step. You can also manually edit `data/style_profile.txt` to fine-tune style.

### 3.3 YouTube Video Ingestion

Import your YouTube video content into the knowledge base:

```powershell
# Single video
python -m ingestion.ingest_youtube --urls "https://www.youtube.com/watch?v=VIDEO_ID"

# Multiple videos
python -m ingestion.ingest_youtube --urls "https://youtu.be/AAA" "https://youtu.be/BBB"

# Batch from file
python -m ingestion.ingest_youtube --url-file my_videos.txt

# Specify Whisper language
python -m ingestion.ingest_youtube --urls "URL" --whisper-lang zh

# Captions-only (skip Whisper)
python -m ingestion.ingest_youtube --urls "URL" --no-whisper
```

**Auto-detect path:**

- Has captions → use directly (free)
- No captions → yt-dlp download audio → Whisper API transcription (~$0.006 / 10 minutes)
- Large files (>24MB) → automatic chunked transcription

**Prerequisite:** Install ffmpeg

```powershell
winget install Gyan.FFmpeg
```

### 3.4 PDF Book Ingestion

```powershell
# Single PDF
python -m ingestion.ingest_pdf --files "path/to/book.pdf"

# Multiple PDFs
python -m ingestion.ingest_pdf --files "book1.pdf" "book2.pdf"

# Custom source label
python -m ingestion.ingest_pdf --files "book.pdf" --source "Stock Trading Bible"

# Preview (do not write to DB)
python -m ingestion.ingest_pdf --files "book.pdf" --dry-run
```

---

## 4. Core Feature Usage

### 4.1 How Auto-Reply Works

When a user posts in a target channel, the bot runs:

1. **Filter:** Skip bot messages, Owner messages, non-target channels, spam/ads, thanks/politeness
2. **Intent detection:** Decide whether to reply based on `RESPOND_MODE`
   - `questions` — only messages with question marks or question words (default)
   - `mention_only` — only @mention of the bot
   - `all` — reply to all messages
3. **Rate limit:** 30s cooldown per user; max 10 replies per minute globally
4. **RAG retrieval:** Retrieve the most relevant historical posts from the knowledge base
5. **Generate reply:** GPT-4o-mini generates an Owner-style reply from retrieved context
6. **Confidence routing:**
   - Confidence ≥ 7 + relevant context → **auto-reply** (Owner gets a notify DM)
   - Confidence < 7 / no context / trading-signal questions → **forward to Owner review**

**Cases the bot always responds to:**

- Messages with images (treated as chart analysis requests)
- @mention of the bot
- Replies to a previous bot message

### 4.2 Owner Review Flow

Low-confidence replies are sent to Owner via DM:

**DM contents include:**

- 📌 Channel name
- 👤 Asker
- 📊 Confidence score (X/10)
- ❓ Original question
- 📝 Draft reply
- 🔗 Context summary (Top 3)
- 🔗 Jump link to the original message

**Three action buttons:**

| Button | Effect |
|------|------|
| ✅ **Approve** | Post the draft to the original channel and auto-learn this Q&A |
| ✏️ **Edit** | Open an edit modal (prefilled draft), then post and auto-learn |
| ❌ **Reject** | Do not post; store in the negative-feedback library for future reference |

**Notes:**

- Buttons expire after 1 hour
- Each review can be acted on only once (double-click protection)
- The bot must stay running to handle button clicks
- Ensure your Discord DMs are open

**Auto-reply notification:** When the bot auto-replies, it also DMs you a notify (green Embed, informational only)

### 4.3 Auto Learning

The bot automatically learns from:

| Source | Trigger | Document type |
|------|----------|----------|
| Owner text messages in target channels | Real-time automatic | `owner_post` / `qa_pair` |
| Owner voice messages | Real-time automatic (Whisper transcription) | `owner_voice` |
| Approve/Edit review replies | After Owner action | `qa_pair` (source=`owner_review`) |
| Owner messages during offline backfill | On bot restart | `owner_post` / `qa_pair` |

**Auto-learn rules:**

- Skip messages that are too short (<10 characters)
- Skip emoji-only messages
- If Owner is replying to someone's question → build Q&A pair format
- Deduplicate by message ID so the same message is not ingested twice

### 4.4 Image Analysis

When users send images in a target channel (candlestick charts, indicator screenshots, etc.), the bot:

1. Extracts image URLs (attachments + Embed images, up to 4)
2. If there is text caption → retrieve RAG context for reference
3. Analyzes images with GPT-4o Vision
4. Replies with technical analysis (trend, patterns, indicator signals)
5. Automatically redacts specific price numbers

**Example interaction:**

```
User: [uploads a candlestick chart] How do you see this move?
Bot: From the chart, price is consolidating near the moving average, and MACD shows a golden cross...
```

### 4.5 Offline Backfill

After the bot goes offline or restarts, it automatically scans target channels and answers missed questions.

**Config:**

```env
OFFLINE_BACKFILL_ENABLED=true           # master switch
OFFLINE_BACKFILL_LOOKBACK_HOURS=12      # lookback hours on first start
OFFLINE_BACKFILL_MAX_PER_CHANNEL=100    # max scan per channel
OFFLINE_BACKFILL_OWNER_REPLY_WINDOW_MINUTES=15   # Owner reply window
```

**Smart skip of already-answered questions:**

- Explicitly replied by Owner or Bot (Discord reply)
- Owner posted a substantive message within 15 minutes after the question (heuristic that Owner was online)

**State persistence:** Last processed message ID per channel is stored in `data/last_seen.json`; after restart, continue from the last position.

### 4.6 Conversation Memory

The bot maintains short-term conversation memory per channel for multi-turn dialogue:

```
User: How do you see ES right now?
Bot: ES is near key levels...

User: What about NQ? (bot understands this is a follow-up)
Bot: For NQ, technically...
```

**Config:**

```env
CONVERSATION_MEMORY_SIZE=10    # keep last N messages
CONVERSATION_MEMORY_TTL=1800   # expire after (seconds) = 30 minutes
```

**Thread support:** When replying in a Thread, the bot fetches Thread history as context (last `THREAD_CONTEXT_MESSAGES`, default 15).

```env
THREAD_AUTO_REPLY=true         # whether to auto-reply in Threads
THREAD_CONTEXT_MESSAGES=15     # Thread context message count
```

---

## 5. Slash Command Reference

### 5.1 General Commands

| Command | Permission | Description |
|------|------|------|
| `/ask <question>` | Everyone | Ask the bot directly (without posting in chat) |
| `/status` | Everyone | Bot status: uptime, queue depth, knowledge base doc count |
| `/stats` | Owner | Detailed stats: total queries, auto-reply rate, avg confidence, popular questions |
| `/faq` | Everyone | View auto-generated FAQ |
| `/generate_faq` | Owner | Auto-generate FAQ from high-frequency high-confidence Q&A |

**`/ask` example:**

```
/ask question:How do you see ES on the daily?
```

The bot replies with an ephemeral message (only you can see it), useful when you do not want to ask publicly.

**`/stats` sample output:**

```
📊 Bot Stats
Total queries: 1234
Auto-replies: 890 (72.1%)
Forwarded for review: 344 (27.9%)
Avg confidence: 7.2
Avg latency: 1.8s

Recent popular questions:
1. How to trade ES today (confidence: 8)
2. BTC trend analysis (confidence: 7)
...
```

### 5.2 Promotion Commands

| Command | Permission | Description |
|------|------|------|
| `/signal` | Everyone | Show BigTreeSignal product info |
| `/schedule_promo` | Owner | Schedule a promo post |
| `/list_promos` | Owner | List scheduled promos |
| `/cancel_promo <id>` | Owner | Cancel a schedule |
| `/post_promo` | Owner | Post a promo immediately |
| `/schedule_trial` | Owner | Schedule a free-trial promo |
| `/schedule_lesson` | Owner | Schedule a lesson post (supports repeat) |
| `/list_lessons` | Owner | List lesson schedules |
| `/cancel_lesson <id>` | Owner | Cancel a lesson schedule |
| `/testimonials` | Everyone | View user testimonials |

---

## 6. Promotion System Usage

### 6.1 Enable Promotion

Configure in `.env`:

```env
PROMO_ENABLED=true
PROMO_CHANNEL_IDS=channelId1,channelId2    # independent from TARGET_CHANNEL_IDS
SIGNAL_PRODUCT_NAME=BigTreeSignal
SIGNAL_PRODUCT_URL=https://your-product-url.com
```

**Important:** `PROMO_CHANNEL_IDS` and `TARGET_CHANNEL_IDS` are independent lists. You can enable Q&A and promotion in the same channel, or keep them separate.

### 6.2 CTA Triggers

| Scenario | Trigger | Behavior |
|------|----------|------|
| Auto-reply CTA | Every `CTA_FREQUENCY` replies in promo channels | Append CTA text to the reply |
| Signal-query CTA | Trading-signal question detected in promo channels | Send a standalone CTA Embed |
| New member welcome | Member joins a guild that has promo channels | DM a welcome Embed |

**CTA frequency config:**

```env
CTA_FREQUENCY=5              # append CTA every 5 auto-replies (0=disable)
AUTO_REPLY_CTA_TEXT=Want live trading signals? Learn BigTreeSignal →
SIGNAL_CTA_TEXT=Want live trading signals? Learn BigTreeSignal
```

### 6.3 Schedule Promo Posts

```
/schedule_promo title:Limited offer description:20% off all plans time:2025-01-15 10:00 url:https://...
```

**Parameters:**

- `title` — promo title
- `description` — detailed description
- `time` — send time (YYYY-MM-DD HH:MM, UTC-4)
- `url` — promo link (optional; defaults to product URL)
- `channel` — target channel (optional; defaults to all promo channels)

At the scheduled time the bot sends an Embed to the designated channel(s).

**List / cancel:**

```
/list_promos        → list all schedules
/cancel_promo id:promo_abc12345   → cancel a schedule
```

### 6.4 Schedule Lesson Posts

```
/schedule_lesson title:Weekly technical analysis content:This week focus on MA breakouts... time:2025-01-15 20:00 repeat_days:7
```

`repeat_days` set to 7 means weekly repeat. After sending, the next occurrence is scheduled automatically.

### 6.5 User Testimonial Collection

**Auto-detect:** When a user message in a promo channel contains profit/follow-signal keywords (e.g. "made money", "doubled", "signals are accurate"), the bot DMs you for review.

```env
TESTIMONIAL_DETECTION_ENABLED=true
TESTIMONIAL_CHANNEL_ID=your-user-wins-channel-id
```

After Approve, it is automatically forwarded to `#user-wins`.

**Manual view:**

```
/testimonials    → show recent approved testimonials
```

### 6.6 New Member Welcome

When a new member joins a guild that includes promo channels, the bot auto-DMs a welcome message:

```env
WELCOME_MESSAGE=Welcome! This is BigTree's stock analysis community.
FREE_TRIAL_ENABLED=true
FREE_TRIAL_URL=https://your-trial-url.com
```

---

## 7. Configuration Tuning

### 7.1 Respond Modes

```env
RESPOND_MODE=questions      # default: only reply to question messages
```

| Mode | Description | Best for |
|------|------|----------|
| `questions` | Only messages with question marks / question words | Busy channels; less noise |
| `mention_only` | Only @mention of the bot | Most conservative; user-initiated |
| `all` | Reply to all messages (still filtered) | Small channels; full coverage |

**Always responded to in all modes:** image messages, @mentions, replies to the bot

### 7.2 Confidence Threshold Tuning

```env
CONFIDENCE_THRESHOLD=7     # default: 7/10
```

**Tuning tips:**

| Situation | Suggestion |
|----------|------|
| >90% of reviews are Approve | Lower to 6 so more replies auto-send |
| <70% of reviews are Approve | Raise to 8 to tighten auto-reply |
| Testing phase | Set to 5 and observe auto-reply quality |
| Just launched | Set to 9, review-first, then lower gradually |

### 7.3 Rate Limit Tuning

```env
USER_COOLDOWN_SECONDS=30    # interval between replies for the same user
GLOBAL_MAX_PER_MINUTE=10    # max global replies per minute
```

**Scenario tips:**

- **Large channel (1000+ online):** `USER_COOLDOWN_SECONDS=60`, `GLOBAL_MAX_PER_MINUTE=5`
- **Small channel (<50 online):** `USER_COOLDOWN_SECONDS=15`, `GLOBAL_MAX_PER_MINUTE=20`
- **Events / teaching sessions:** Temporarily raise `GLOBAL_MAX_PER_MINUTE`

### 7.4 Language Switching

```env
BOT_LANGUAGE=zh    # zh = Chinese (default), en = English
```

Affects: rate-limit notices, error messages, review notifications, and other system UI text.

---

## 8. Monitoring & Operations

### 8.1 Logging

**Output locations:**

- **Console:** live output
- **File:** `logs/bot.log` (RotatingFileHandler, 10MB × 5 backups)

**Structured log per query:**

```json
{
  "event": "query_processed",
  "question": "How do you see ES?",
  "author_id": 123456789,
  "channel_id": 987654321,
  "confidence": 8,
  "action": "auto_reply",
  "reason": "confidence meets threshold",
  "context_count": 5,
  "best_distance": 0.23,
  "response_time_ms": 1450
}
```

**Log level control:**

```env
LOG_LEVEL=INFO    # DEBUG / INFO / WARNING / ERROR
```

### 8.2 Health Checks

```env
HEALTH_PORT=8080    # set to 0 to disable
```

When enabled, open `http://localhost:8080/health`:

```json
{
  "status": "ok",
  "uptime_seconds": 3600.5,
  "guilds": 1,
  "ws_latency_ms": 45.2
}
```

- 200 = Bot ready
- 503 = Bot not ready

Useful for Docker / k8s health probes.

**Heartbeat logs:** Every 5 minutes, uptime and latency are logged automatically (no config needed).

### 8.3 Viewing Stats

**Option 1: Slash commands**

```
/stats    → view stats in Discord
/status   → view runtime status
```

**Option 2: JSON file**

Stats persist in `data/stats.json` and can be read directly:

```json
{
  "total_queries": 1234,
  "auto_replies": 890,
  "forwards": 344,
  "total_confidence": 8765,
  "total_latency_ms": 2345678,
  "channel_counts": {"123": 456, "789": 778}
}
```

---

## 9. Deployment Options

### 9.1 Local Run

```powershell
.venv\Scripts\Activate.ps1
python -m bot.main
```

Press `Ctrl+C` for graceful shutdown (saves all state).

### 9.2 Docker Deployment

The project includes `Dockerfile` and `docker-compose.yml`:

```bash
# On a VPS
git clone <your-repo>
cd treeProjectDiscordBot
# Create .env
# Copy chromadb_store/ and data/ directories

docker-compose up -d
docker-compose logs -f    # view logs
```

Volumes automatically mount `chromadb_store/`, `logs/`, and `data/`.

### 9.3 systemd Deployment

```ini
# /etc/systemd/system/discord-bot.service
[Unit]
Description=Discord Auto-Reply Bot
After=network.target

[Service]
Type=simple
User=botuser
WorkingDirectory=/home/botuser/treeProjectDiscordBot
ExecStart=/home/botuser/treeProjectDiscordBot/.venv/bin/python -m bot.main
Restart=always
RestartSec=10
EnvironmentFile=/home/botuser/treeProjectDiscordBot/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable discord-bot
sudo systemctl start discord-bot
sudo journalctl -u discord-bot -f    # view logs
```

---

## 10. Testing

```powershell
# Run all tests
python -m pytest tests/ -v

# Run module-specific tests
python -m pytest tests/test_rag.py -v
python -m pytest tests/test_confidence.py -v
python -m pytest tests/test_ingestion.py -v
python -m pytest tests/test_listener.py -v
python -m pytest tests/test_review.py -v
python -m pytest tests/test_stats.py -v
python -m pytest tests/test_cache.py -v
python -m pytest tests/test_promotion.py -v
```

**Test coverage:** 139 test cases

| Test file | Coverage |
|----------|----------|
| `test_ingestion.py` | Message cleaning, Q&A pairing, chunking |
| `test_rag.py` | RAG retrieval, generation, price redaction |
| `test_confidence.py` | Routing decisions, signal detection, confidence parsing |
| `test_listener.py` | Message filter chain, rate limits, emoji detection |
| `test_review.py` | Review flow, negative-feedback storage |
| `test_stats.py` | Stats recording, snapshots, persistence |
| `test_cache.py` | LRU cache, TTL expiry, hit rate |
| `test_promotion.py` | CTA generation, channel checks |

**End-to-end test suggestions:**

1. Create a private test channel → add Bot → add to `TARGET_CHANNEL_IDS`
2. Send an investing question → verify auto-reply
3. Send an off-topic question → verify forward to DM
4. Test review buttons (Approve / Edit / Reject)
5. Send an image → verify image analysis
6. Rapidly send 5 messages → verify rate limiting

---

## 11. FAQ

### Bot is online but does not reply

| Possible cause | Fix |
|----------|----------|
| MESSAGE CONTENT INTENT not enabled | Discord Developer Portal → Bot → enable MESSAGE CONTENT INTENT |
| Channel ID not in `TARGET_CHANNEL_IDS` | Check `.env` |
| You are Owner posting | Bot does not reply to Owner messages (unless @mention Bot) |
| Rate limited | Wait 30 seconds (or check logs for rate-limit notices) |
| `RESPOND_MODE=mention_only` | Change to `questions` or `all`, or @mention Bot |

### Review DM buttons do nothing

- Bot must stay running (buttons are handled in-process memory)
- Buttons expire after 1 hour
- Check that your DMs are open

### Reply quality is poor

1. Confirm you ran `python -m ingestion.analyze_style`
2. Check whether the knowledge base has enough data (`/status` for doc count)
3. Raise `CONFIDENCE_THRESHOLD` so more replies go through review
4. Check whether `data/negative_samples.json` has too much negative feedback

### OpenAI API errors

| Error | Fix |
|------|------|
| `RateLimitError` | Lower `EMBED_BATCH_SIZE`, or raise OpenAI limits |
| `APITimeoutError` | Bot retries once automatically; check network |
| `AuthenticationError` | Check `OPENAI_API_KEY` in `.env` |

### Ingestion error "No JSON files found"

Make sure `.json` files are under `data/exports/`.

### How to re-ingest data

Just re-run `python -m ingestion.ingest`. The script skips already-ingested documents (incremental).

To fully rebuild: delete the `chromadb_store/` directory and run again.

---

## 12. Full Configuration Reference

### Required

| Variable | Description |
|------|------|
| `DISCORD_BOT_TOKEN` | Discord Bot Token |
| `OPENAI_API_KEY` | OpenAI API Key |
| `OWNER_USER_ID` | Channel owner Discord User ID |
| `TARGET_CHANNEL_IDS` | Monitored channel IDs (comma-separated) |

### Model Settings

| Variable | Default | Description |
|------|--------|------|
| `LLM_MODEL` | `gpt-4o-mini` | Generation model |
| `VISION_MODEL` | `gpt-4o` | Vision model |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `LLM_MAX_TOKENS` | `500` | Max generation tokens |
| `LLM_TEMPERATURE` | `0.5` | Generation temperature |

### RAG & Routing

| Variable | Default | Description |
|------|--------|------|
| `RAG_TOP_K` | `8` | Number of retrieval results |
| `RAG_MAX_DISTANCE` | `0.6` | Max cosine distance |
| `CONFIDENCE_THRESHOLD` | `7` | Minimum confidence for auto-reply |
| `RESPOND_MODE` | `questions` | Respond mode |

### Conversation & Rate Limits

| Variable | Default | Description |
|------|--------|------|
| `CONVERSATION_MEMORY_SIZE` | `10` | Conversation memory size |
| `CONVERSATION_MEMORY_TTL` | `1800` | Memory TTL in seconds |
| `USER_COOLDOWN_SECONDS` | `30` | Per-user cooldown |
| `GLOBAL_MAX_PER_MINUTE` | `10` | Global per-minute limit |

### Thread Support

| Variable | Default | Description |
|------|--------|------|
| `THREAD_AUTO_REPLY` | `true` | Auto-reply in Threads |
| `THREAD_CONTEXT_MESSAGES` | `15` | Thread context message count |

### Offline Backfill

| Variable | Default | Description |
|------|--------|------|
| `OFFLINE_BACKFILL_ENABLED` | `true` | Master switch |
| `OFFLINE_BACKFILL_LOOKBACK_HOURS` | `12` | First lookback hours |
| `OFFLINE_BACKFILL_MAX_PER_CHANNEL` | `100` | Max scan per channel |
| `OFFLINE_BACKFILL_OWNER_REPLY_WINDOW_MINUTES` | `15` | Owner reply window |

### Data Paths

| Variable | Default | Description |
|------|--------|------|
| `CHROMADB_PATH` | `./chromadb_store` | Vector DB path |
| `CHROMADB_COLLECTION` | `bigtree_knowledge` | Collection name |
| `EXPORT_DIR` | `./data/exports` | Export file directory |

### Ingestion Parameters

| Variable | Default | Description |
|------|--------|------|
| `CHUNK_MAX_TOKENS` | `500` | Max tokens per chunk |
| `CHUNK_OVERLAP_TOKENS` | `50` | Chunk overlap tokens |
| `EMBED_BATCH_SIZE` | `100` | Batch size |

### Promotion

| Variable | Default | Description |
|------|--------|------|
| `PROMO_ENABLED` | `true` | Promotion master switch |
| `PROMO_CHANNEL_IDS` | (empty) | Promo channels |
| `SIGNAL_PRODUCT_NAME` | `BigTreeSignal` | Product name |
| `SIGNAL_PRODUCT_URL` | (empty) | Product URL |
| `CTA_FREQUENCY` | `5` | CTA frequency |
| `FREE_TRIAL_ENABLED` | `false` | Free trial |
| `TESTIMONIAL_CHANNEL_ID` | `0` | Testimonial channel |
| `TESTIMONIAL_DETECTION_ENABLED` | `true` | Auto-detect testimonials |

### System

| Variable | Default | Description |
|------|--------|------|
| `BOT_LANGUAGE` | `zh` | UI language |
| `LOG_LEVEL` | `INFO` | Log level |
| `HEALTH_PORT` | `0` | Health-check port |
