# Discord Auto-Reply RAG Bot — Full Implementation Plan

---

## Table of Contents

- [Overview](#overview)
- [Getting Started (Step-by-Step)](#getting-started-step-by-step)
  - [Prerequisites](#prerequisites)
  - [Step A: Create a Discord Bot Application](#step-a-create-a-discord-bot-application)
  - [Step B: Get an OpenAI API Key](#step-b-get-an-openai-api-key)
  - [Step C: Install Python & Set Up the Project](#step-c-install-python--set-up-the-project)
  - [Step D: Configure Your Environment](#step-d-configure-your-environment)
  - [Step E: Export Your Discord History](#step-e-export-your-discord-history)
  - [Step F: Ingest Your Data](#step-f-ingest-your-data)
  - [Step G: (Optional) Analyze Your Writing Style](#step-g-optional-analyze-your-writing-style)
  - [Step G2: (Optional) Ingest YouTube Videos](#step-g2-optional-ingest-youtube-videos)
  - [Step H: Start the Bot](#step-h-start-the-bot)
  - [Step I: Test the Bot](#step-i-test-the-bot)
  - [Step J: Deploy for 24/7 Uptime](#step-j-deploy-for-247-uptime)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Phase 1: Setup & Data Collection](#phase-1-setup--data-collection)
  - [Step 1: Create Discord Bot Application](#step-1-create-discord-bot-application)
  - [Step 2: Export Historical Messages](#step-2-export-historical-messages)
  - [Step 3: Project Scaffolding](#step-3-project-scaffolding)
- [Phase 2: Data Ingestion Pipeline](#phase-2-data-ingestion-pipeline)
  - [Step 4: Preprocess Messages](#step-4-preprocess-messages)
  - [Step 5: Generate Embeddings & Store in ChromaDB](#step-5-generate-embeddings--store-in-chromadb)
  - [Step 5b: Analyze Style (Optional)](#step-5b-optional-analyze-style)
- [Phase 3: RAG Pipeline](#phase-3-rag-pipeline)
  - [Step 6: Build Retrieval Module](#step-6-build-retrieval-module)
  - [Step 7: Build Generation Module](#step-7-build-generation-module)
  - [Step 8: Confidence Routing](#step-8-confidence-routing)
- [Phase 4: Discord Bot Integration](#phase-4-discord-bot-integration)
  - [Step 9: Bot Listener](#step-9-bot-listener)
  - [Step 10: Wire RAG Pipeline to Bot](#step-10-wire-rag-pipeline-to-bot)
  - [Step 11: Owner Review Interface](#step-11-owner-review-interface)
- [Phase 5: Polish & Deploy](#phase-5-polish--deploy)
  - [Step 12: Logging & Monitoring](#step-12-logging--monitoring)
  - [Step 13: Feedback Loop (Future)](#step-13-feedback-loop-future-enhancement)
  - [Step 14: Deployment](#step-14-deployment)
- [Implementation Order & Dependencies](#implementation-order--dependencies)
- [Verification Checklist](#verification-checklist)
- [Troubleshooting](#troubleshooting)
- [Security Considerations](#security-considerations)
- [Configuration Reference](#configuration-reference)
- [Decisions & Scope](#decisions--scope)

---

## Overview

Build a Python Discord bot that:
1. Ingests 200K+ historical Discord posts (yours only)
2. Stores them as vector embeddings in a local ChromaDB database
3. Uses OpenAI GPT-4o-mini to generate answers in YOUR style via RAG
4. Auto-replies in your Discord channel
5. Forwards low-confidence answers to you for approval via DM

---

## Getting Started (Step-by-Step)

> **This section walks you through every step from zero to a running bot.**
> If you already know what you're doing, jump to the [Quick Start Summary](#quick-start-summary).

### Prerequisites

Before you begin, make sure you have:

| Requirement | Where to get it |
|-------------|----------------|
| **A Discord account** | https://discord.com |
| **Admin access to your Discord server** | Needed to invite the bot |
| **Python 3.11 or newer** | https://www.python.org/downloads/ — check with `python --version` |
| **An OpenAI account** | https://platform.openai.com/signup |
| **A credit card on file with OpenAI** | Required for API access (pay-as-you-go) |
| **Git** (optional) | https://git-scm.com/downloads |

[↑ Back to Table of Contents](#table-of-contents)

---

### Step A: Create a Discord Bot Application

> **Time needed:** ~10 minutes
> **What you'll get:** A bot token and your user ID

1. **Open the Discord Developer Portal**
   - Go to https://discord.com/developers/applications
   - Log in with your Discord account

2. **Create a new application**
   - Click the **"New Application"** button (top right)
   - Name it something like **"TreeBot Auto-Reply"**
   - Click **"Create"**

3. **Set up the bot**
   - In the left sidebar, click **"Bot"**
   - Click **"Reset Token"** → click **"Yes, do it!"**
   - **COPY THE TOKEN IMMEDIATELY** — you won't see it again
   - Save it somewhere safe (you'll paste it into `.env` later)

4. **Enable required intents**
   - Scroll down to **"Privileged Gateway Intents"**
   - Toggle ON: ✅ **MESSAGE CONTENT INTENT** (required — the bot can't read messages without this)
   - Toggle ON: ✅ **SERVER MEMBERS INTENT** (optional but recommended)
   - Click **"Save Changes"**

5. **Generate the invite URL**
   - In the left sidebar, click **"OAuth2"** → **"URL Generator"**
   - Under **Scopes**, check: `bot` and `applications.commands`
   - Under **Bot Permissions**, check:
     - ✅ Read Messages/View Channels
     - ✅ Send Messages
     - ✅ Read Message History
     - ✅ Use Slash Commands
   - Copy the **Generated URL** at the bottom

6. **Invite the bot to your server**
   - Paste the URL into your browser
   - Select your server from the dropdown
   - Click **"Authorize"**
   - Complete the CAPTCHA
   - You should see the bot appear (offline) in your server's member list

7. **Get your own user ID**
   - In Discord, go to **Settings → Advanced → enable Developer Mode**
   - Right-click your own name in any chat → **"Copy User ID"**
   - Save this ID — you'll need it for `.env`

8. **Get your channel ID(s)**
   - Right-click the channel(s) you want the bot to monitor → **"Copy Channel ID"**
   - Save these IDs — you'll need them for `.env`

> **You now have:** Bot Token, Your User ID, Channel ID(s)

[↑ Back to Table of Contents](#table-of-contents)

---

### Step B: Get an OpenAI API Key

> **Time needed:** ~5 minutes
> **What you'll get:** An OpenAI API key

1. Go to https://platform.openai.com/api-keys
2. Click **"Create new secret key"**
3. Name it (e.g., "Discord Bot") and click **"Create"**
4. **COPY THE KEY IMMEDIATELY** — you won't see it again
5. Save it somewhere safe (you'll paste it into `.env` later)

**Billing setup** (if not already done):
- Go to https://platform.openai.com/settings/organization/billing/overview
- Add a payment method
- Set a monthly usage limit (e.g., $50) at https://platform.openai.com/settings/organization/limits to prevent surprises

> **Estimated cost:** ~$1-3 one-time for ingesting 200K posts, then ~$30-50/month for answering questions.

[↑ Back to Table of Contents](#table-of-contents)

---

### Step C: Install Python & Set Up the Project

> **Time needed:** ~5 minutes
> **What you'll get:** A working Python environment with all dependencies installed

1. **Verify Python is installed:**
   ```bash
   python --version
   # Should show Python 3.11.x or newer
   ```
   If not installed, download from https://www.python.org/downloads/
   > **Windows users:** During installation, check ✅ "Add Python to PATH"

2. **Open a terminal** and navigate to the project folder:
   ```bash
   cd c:\treeProjectDiscordBot
   ```

3. **Create a virtual environment:**
   ```bash
   python -m venv .venv
   ```

4. **Activate the virtual environment:**
   ```bash
   # Windows (PowerShell):
   .venv\Scripts\Activate.ps1

   # Windows (CMD):
   .venv\Scripts\activate.bat

   # macOS/Linux:
   source .venv/bin/activate
   ```
   You should see `(.venv)` appear before your prompt.

5. **Install all dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   This installs: `discord.py`, `openai`, `chromadb`, `tiktoken`, `python-dotenv`, `tqdm`, `aiohttp`

[↑ Back to Table of Contents](#table-of-contents)

---

### Step D: Configure Your Environment

> **Time needed:** ~2 minutes
> **What you'll get:** A configured `.env` file with all your credentials

1. **Copy the example config:**
   ```bash
   # Windows:
   copy .env.example .env

   # macOS/Linux:
   cp .env.example .env
   ```

2. **Edit `.env`** with your actual values:
   ```env
   DISCORD_BOT_TOKEN=MTIzNDU2Nzg5MDEyMzQ1Njc4OQ.XXXXXX.XXXXXXXXXXXXXXXXXXXXXXXXXX
   OPENAI_API_KEY=sk-proj-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
   OWNER_USER_ID=123456789012345678
   TARGET_CHANNEL_IDS=111111111111111111,222222222222222222
   CONFIDENCE_THRESHOLD=7
   CHROMADB_PATH=./chromadb_store
   LOG_LEVEL=INFO
   ```

   | Field | Where to find it |
   |-------|-----------------|
   | `DISCORD_BOT_TOKEN` | From [Step A.3](#step-a-create-a-discord-bot-application) |
   | `OPENAI_API_KEY` | From [Step B.4](#step-b-get-an-openai-api-key) |
   | `OWNER_USER_ID` | From [Step A.7](#step-a-create-a-discord-bot-application) |
   | `TARGET_CHANNEL_IDS` | From [Step A.8](#step-a-create-a-discord-bot-application) (comma-separated, no spaces) |

   > **IMPORTANT:** Never share your `.env` file or commit it to git. It's already in `.gitignore`.

[↑ Back to Table of Contents](#table-of-contents)

---

### Step E: Export Your Discord History

> **Time needed:** ~15-60 minutes (depends on channel size)
> **What you'll get:** JSON file(s) with all your historical messages in `data/exports/`

1. **Download DiscordChatExporter**
   - Go to https://github.com/Tyrrrz/DiscordChatExporter/releases
   - Download the latest **CLI** version:
     - Windows: `DiscordChatExporter.Cli.win-x64.zip`
     - macOS: `DiscordChatExporter.Cli.osx-x64.zip`
     - Linux: `DiscordChatExporter.Cli.linux-x64.zip`
   - Extract the zip file to a convenient location

2. **Export your channel(s):**
   ```bash
   # Single channel export:
   DiscordChatExporter.Cli export ^
     -t "YOUR_BOT_TOKEN" ^
     -c CHANNEL_ID ^
     -f Json ^
     -o "c:\treeProjectDiscordBot\data\exports\channel_export.json"
   ```

   > **Note:** Use your **bot token** (the bot must be in the server and have Read Message History permission). Alternatively, use your personal user token for a self-export.

   For very large channels (200K+ messages), export in date ranges to avoid timeouts:
   ```bash
   DiscordChatExporter.Cli export ^
     -t "YOUR_BOT_TOKEN" ^
     -c CHANNEL_ID ^
     -f Json ^
     --after "2020-01-01" --before "2022-01-01" ^
     -o "c:\treeProjectDiscordBot\data\exports\channel_2020_2021.json"

   DiscordChatExporter.Cli export ^
     -t "YOUR_BOT_TOKEN" ^
     -c CHANNEL_ID ^
     -f Json ^
     --after "2022-01-01" --before "2024-01-01" ^
     -o "c:\treeProjectDiscordBot\data\exports\channel_2022_2023.json"

   DiscordChatExporter.Cli export ^
     -t "YOUR_BOT_TOKEN" ^
     -c CHANNEL_ID ^
     -f Json ^
     --after "2024-01-01" ^
     -o "c:\treeProjectDiscordBot\data\exports\channel_2024_present.json"
   ```

3. **Verify the export:**
   - Check that `.json` files appeared in `data/exports/`
   - Open one file — you should see a `"messages"` array with your posts
   - The ingestion script will automatically load all `.json` files from this folder

> **Multiple channels?** Repeat the export for each channel. The ingestion script handles multiple files automatically.

[↑ Back to Table of Contents](#table-of-contents)

---

### Step F: Ingest Your Data

> **Time needed:** ~15-30 minutes for 200K messages
> **What you'll get:** A ChromaDB vector database populated with your posts, ready for RAG

1. **Make sure your virtual environment is activated** (you should see `(.venv)` in your prompt)

2. **Run a quick test first** with a small sample:
   ```bash
   python -m ingestion.ingest --sample 100
   ```
   You should see a progress bar and a message like: `Done — total documents in collection: 100`

3. **If the test works, run the full ingestion:**
   ```bash
   python -m ingestion.ingest
   ```
   This will:
   - Parse all JSON files in `data/exports/`
   - Filter to only YOUR messages (by `OWNER_USER_ID`)
   - Build Q&A pairs from your replies
   - Group consecutive messages into answer blocks
   - Clean and chunk the text
   - Generate embeddings via OpenAI API
   - Store everything in ChromaDB at `./chromadb_store/`

   > **Progress:** You'll see a `tqdm` progress bar. For 200K messages, expect ~15-30 minutes.

4. **Verify ingestion worked:**
   ```bash
   python -c "import chromadb; c = chromadb.PersistentClient('./chromadb_store'); col = c.get_collection('discord_posts'); print(f'Documents stored: {col.count()}')"
   ```

> **Re-running ingestion:** The script supports incremental ingestion — if you export more messages later, just run it again. It skips documents already in the database.

[↑ Back to Table of Contents](#table-of-contents)

---

### Step G: (Optional) Analyze Your Writing Style

> **Time needed:** ~1 minute
> **What you'll get:** A style profile that makes the bot's answers match your writing style more closely

```bash
python -m ingestion.analyze_style
```

This analyzes your messages and saves a profile to `data/style_profile.txt` containing:
- Your average response length
- Your most common phrases
- Your emoji usage patterns
- Sample messages that represent your typical style

The bot automatically loads this file when generating answers. You can also manually edit `data/style_profile.txt` to fine-tune the style.

> **Recommended:** Run this step. It significantly improves the quality of generated answers.

[↑ Back to Table of Contents](#table-of-contents)

---

### Step G2: (Optional) Ingest YouTube Videos

> **Time needed:** ~5 minutes setup + transcription time per video
> **What you'll get:** Your YouTube video content added to the knowledge base, so the bot can answer questions based on what you've said in your videos

The script `ingestion/ingest_youtube.py` handles two scenarios automatically:
- **Video has subtitles/captions** → fetches them directly (free, instant)
- **Video has no subtitles (audio only)** → downloads audio with `yt-dlp` and transcribes with OpenAI Whisper API (~$0.006/minute)

#### Prerequisites

1. **Install ffmpeg** (required for audio download and splitting):
   ```powershell
   # Check if already installed:
   ffmpeg -version

   # If not, install with winget:
   winget install Gyan.FFmpeg
   ```
   After installing, restart your terminal.

2. **Confirm dependencies are installed** (already in `requirements.txt`):
   ```powershell
   pip install -r requirements.txt
   ```

#### Usage

**Single video (auto-detects subtitles, falls back to Whisper if none):**
```powershell
python -m ingestion.ingest_youtube --urls "https://www.youtube.com/watch?v=VIDEO_ID"
```

**Multiple videos at once:**
```powershell
python -m ingestion.ingest_youtube --urls "https://youtu.be/AAA" "https://youtu.be/BBB" "https://youtu.be/CCC"
```

**Batch import from a text file** (one URL per line, recommended when you have many videos):

Create `my_videos.txt`:
```
https://www.youtube.com/watch?v=AAA
https://www.youtube.com/watch?v=BBB
# Lines starting with # are ignored
https://youtu.be/CCC
```

Then run:
```powershell
python -m ingestion.ingest_youtube --url-file my_videos.txt
```

**Specify Whisper transcription language** (default is Chinese `zh`):
```powershell
python -m ingestion.ingest_youtube --urls "https://youtu.be/AAA" --whisper-lang zh
```

**Skip videos with no subtitles** (disable Whisper fallback):
```powershell
python -m ingestion.ingest_youtube --urls "https://youtu.be/AAA" --no-whisper
```

#### How the pipeline works internally

```
For each video URL:
    ↓
    1. Try youtube_transcript_api to fetch existing subtitles
       ✅ Found → use directly (free)
       ❌ Not found → go to step 2
    ↓
    2. Download audio via yt-dlp (32K mono MP3, ~14 MB/hr)
       If file < 24 MB → send directly to Whisper API
       If file > 24 MB → split into 10-minute chunks → transcribe each → merge
    ↓
    3. Chunk transcript text → embed via OpenAI → store in ChromaDB
       (incremental — already-ingested videos are skipped)
```

#### Cost estimate (Whisper API)

| Video length | Cost |
|---|---|
| 10 minutes | ~$0.006 |
| 1 hour | ~$0.036 |
| 10 hours total | ~$0.36 |

> **Incremental:** Re-running the command for the same video IDs is safe — they will be skipped automatically.

[↑ Back to Table of Contents](#table-of-contents)

---

### Step H: Start the Bot

> **Time needed:** ~1 minute
> **What you'll get:** A running bot that auto-replies in your Discord channel

1. **Make sure your virtual environment is activated**

2. **Start the bot:**
   ```bash
   python -m bot.main
   ```

3. **Check the output — you should see:**
   ```
   2026-05-05 10:30:00 [INFO] bot.main: OpenAI client initialized
   2026-05-05 10:30:00 [INFO] bot.main: ChromaDB collection 'discord_posts' loaded — 150000 documents
   2026-05-05 10:30:00 [INFO] bot.main: Starting Discord bot...
   2026-05-05 10:30:02 [INFO] bot.main: Logged in as TreeBot Auto-Reply#1234 (ID: 999999999999999999)
   2026-05-05 10:30:02 [INFO] bot.main: Serving 1 guild(s)
   2026-05-05 10:30:02 [INFO] bot.listener: Bot is ready — starting message queue worker
   ```

4. **The bot is now live!** Go to your Discord channel and try sending a question.

> **To stop the bot:** Press `Ctrl+C` in the terminal.

[↑ Back to Table of Contents](#table-of-contents)

---

### Step I: Test the Bot

> **Time needed:** ~10 minutes
> **What you'll get:** Confidence that the bot works correctly before going live

1. **Create a private test channel** in your Discord server
   - Add the bot's role to the channel so it can see it
   - Add the test channel ID to `TARGET_CHANNEL_IDS` in `.env`
   - Restart the bot

2. **Test auto-reply** — Ask a stock question you know is in your history:
   ```
   What do you think about AAPL?
   ```
   The bot should reply within a few seconds with an answer in your style.

3. **Test confidence routing** — Ask something completely off-topic:
   ```
   What's the best recipe for chocolate cake?
   ```
   The bot should NOT reply in the channel. Instead, you should receive a DM with:
   - The question
   - A draft answer
   - Approve / Edit / Reject buttons

4. **Test the review buttons:**
   - Click ✅ **Approve** → the draft gets posted as a reply
   - (Next time) Click ✏️ **Edit** → type a corrected answer → it gets posted
   - (Next time) Click ❌ **Reject** → nothing is posted

5. **Test rate limiting** — Send 5 messages in rapid succession. Only the first should get a reply (30-second cooldown per user).

6. **Run the unit tests:**
   ```bash
   python -m pytest tests/ -v
   ```

> **Once satisfied, remove the test channel from `TARGET_CHANNEL_IDS` and add your real channel(s) back. Restart the bot.**

[↑ Back to Table of Contents](#table-of-contents)

---

### Step J: Deploy for 24/7 Uptime

> **Time needed:** ~30 minutes
> **What you'll get:** A bot that runs continuously without needing your computer on

See [Step 14: Deployment](#step-14-deployment) for detailed instructions on three options:

| Option | Best for | Cost |
|--------|----------|------|
| **[Local Machine](#step-14-deployment)** | Testing only | Free (but your PC must stay on) |
| **[Docker on VPS](#step-14-deployment)** | Production (recommended) | $4-10/month |
| **[systemd on VPS](#step-14-deployment)** | Linux servers without Docker | $4-10/month |

**Quick Docker deployment:**
```bash
# On your VPS:
git clone <your-repo-url>
cd treeProjectDiscordBot
# Create .env with your credentials
# Copy your chromadb_store/ folder from local
docker-compose up -d
```

[↑ Back to Table of Contents](#table-of-contents)

---

## Architecture

```
Discord Channel (incoming message)
       ↓
discord.py bot listener (on_message)
       ↓
Filter (ignore bots, own messages)
       ↓
RAG Pipeline:
  1. Embed the question → OpenAI text-embedding-3-small
  2. Query ChromaDB for top-K (5-10) relevant historical posts
  3. Build prompt: system (style guide) + retrieved context + question
  4. Call GPT-4o-mini → get answer + confidence score
       ↓
Confidence Check:
  ≥ 7/10 → Auto-reply in channel
  < 7/10 → DM owner with question + draft + Approve/Reject buttons
```

---

## Tech Stack

| Component       | Choice                      | Cost                         |
|-----------------|-----------------------------|------------------------------|
| Language        | Python 3.11+                | Free                         |
| Discord Library | discord.py v2.x             | Free                         |
| LLM             | OpenAI GPT-4o-mini          | ~$0.15/1M input tokens       |
| Embeddings      | text-embedding-3-small      | ~$0.02/1M tokens             |
| Vector DB       | ChromaDB (local, persistent)| Free                         |
| Data Export     | DiscordChatExporter CLI     | Free                         |

**Estimated monthly cost**: ~$30-50/month at moderate usage (up to 1000 questions/day).
**One-time ingestion**: ~$1-3 for 200K posts.

[↑ Back to Table of Contents](#table-of-contents)

---

## Project Structure

```
treeProjectDiscordBot/
├── bot/
│   ├── __init__.py
│   ├── main.py              # Bot entry point & startup
│   ├── config.py            # Settings, env vars, constants
│   ├── listener.py          # on_message handler & message filtering
│   ├── rag.py               # RAG pipeline: embed → retrieve → generate
│   ├── confidence.py        # Confidence scoring & routing logic
│   └── review.py            # Owner DM review interface (approve/reject)
├── ingestion/
│   ├── __init__.py
│   ├── ingest.py            # Main ingestion script: JSON → ChromaDB
│   ├── preprocess.py        # Message cleaning, grouping, chunking
│   └── analyze_style.py     # Analyze posts for style patterns
├── data/
│   └── exports/             # Place exported JSON files here
├── chromadb_store/           # Persisted ChromaDB data (auto-created)
├── logs/                     # Runtime logs
├── tests/
│   ├── __init__.py
│   ├── test_ingestion.py
│   ├── test_rag.py
│   └── test_confidence.py
├── .env                      # API keys & bot token (NEVER commit)
├── .env.example              # Template for .env
├── .gitignore
├── requirements.txt
├── Dockerfile                # For containerized deployment
├── docker-compose.yml        # For containerized deployment
└── PLAN.md                   # ← This file
```

[↑ Back to Table of Contents](#table-of-contents)

---

## Phase 1: Setup & Data Collection

### Step 1: Create Discord Bot Application

**Instructions:**

1. Go to https://discord.com/developers/applications
2. Click "New Application" → name it (e.g., "TreeBot Auto-Reply")
3. Go to **Bot** section in the left sidebar
4. Click "Reset Token" → copy and save the token securely
5. Under **Privileged Gateway Intents**, enable:
   - ✅ MESSAGE CONTENT INTENT (required to read message text)
   - ✅ SERVER MEMBERS INTENT (optional, for mention resolution)
6. Go to **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Read Messages/View Channels`, `Send Messages`, `Read Message History`, `Use Slash Commands`
7. Copy the generated URL → open in browser → invite bot to your server
8. Note your own Discord User ID (Enable Developer Mode in Discord Settings → right-click your name → Copy ID)

**Output:** Bot token + your User ID

### Step 2: Export Historical Messages

**Instructions:**

1. Download DiscordChatExporter CLI from https://github.com/Tyrrrz/DiscordChatExporter/releases
2. You need your **user token** (for self-export) OR use bot token with Read Message History permission
3. Find your channel ID (right-click channel → Copy ID with Developer Mode on)
4. Run export command:

```bash
# Using bot token:
DiscordChatExporter.Cli export \
  -t "YOUR_BOT_TOKEN" \
  -c CHANNEL_ID \
  -f Json \
  -o data/exports/channel_export.json

# If the channel is very large, export in date ranges:
DiscordChatExporter.Cli export \
  -t "YOUR_BOT_TOKEN" \
  -c CHANNEL_ID \
  -f Json \
  --after "2020-01-01" \
  --before "2023-01-01" \
  -o data/exports/channel_2020_2022.json
```

5. Repeat for each channel if you have multiple
6. Place all JSON files in `data/exports/`

**Output:** JSON file(s) in `data/exports/` with all messages

**JSON structure** (DiscordChatExporter format):
```json
{
  "messages": [
    {
      "id": "123456789",
      "timestamp": "2023-01-15T10:30:00+00:00",
      "content": "The message text...",
      "author": {
        "id": "YOUR_USER_ID",
        "name": "YourName",
        "nickname": "YourNick"
      },
      "reference": {
        "messageId": "original_message_id"
      }
    }
  ]
}
```

### Step 3: Project Scaffolding

**Already created.** The project structure is in place with all files.

1. Set up virtual environment:

```bash
python -m venv .venv
.venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and fill in real values:

```env
DISCORD_BOT_TOKEN=your_bot_token_here
OPENAI_API_KEY=your_openai_api_key_here
OWNER_USER_ID=your_discord_user_id_here
TARGET_CHANNEL_IDS=channel_id_1,channel_id_2
CONFIDENCE_THRESHOLD=7
CHROMADB_PATH=./chromadb_store
LOG_LEVEL=INFO
```

> **Need detailed help?** See the step-by-step guides: [Step A (Discord Bot)](#step-a-create-a-discord-bot-application) | [Step B (OpenAI Key)](#step-b-get-an-openai-api-key) | [Step C (Python Setup)](#step-c-install-python--set-up-the-project) | [Step D (Configure .env)](#step-d-configure-your-environment) | [Step E (Export History)](#step-e-export-your-discord-history)

[↑ Back to Table of Contents](#table-of-contents)

---

## Phase 2: Data Ingestion Pipeline

### Step 4: Preprocess Messages

**File:** `ingestion/preprocess.py` *(implemented)*

This module takes raw JSON exports from DiscordChatExporter and prepares them for embedding.

**What it does:**

1. **Load JSON exports** — reads all `.json` files from `data/exports/`, extracts messages and user info
2. **Build Q&A pairs** — for each owner reply to another user's question, creates a paired document:
   ```
   Q: What stock should I buy?
   A: I like AAPL right now, support at 180
   ```
   These are the most valuable training data — real Q&A in your style.
3. **Group consecutive messages** — merges multiple owner messages posted within 2 minutes into a single "answer block"
4. **Clean messages** — resolves `<@USER_ID>` mentions to readable names, strips custom emoji to `:name:` format, removes channel/role mention artifacts
5. **Filter trivial messages** — removes messages under 10 characters and messages that are just URLs
6. **Chunk long messages** — splits text exceeding 500 tokens at paragraph/sentence boundaries with 50-token overlap between chunks

**Key functions:**
- `load_exports(export_dir)` → `(messages, users)` — loads all JSON files
- `build_qa_pairs(messages, owner_id)` → `[{text, metadata}]` — extracts Q&A pairs
- `group_consecutive(messages, owner_id, window_seconds=120)` → `[{text, metadata}]` — merges consecutive posts
- `clean_message(content, users)` → `str` — cleans formatting
- `chunk_text(text, max_tokens=500, overlap=50)` → `[str]` — splits long text
- `preprocess_all(export_dir, owner_id)` → `[{id, text, metadata}]` — full pipeline

**Output format** (each item ready for embedding):
```python
{
    "id": "123456",          # message ID (or message_id_chunkN)
    "text": "The text to embed",
    "metadata": {
        "source_message_id": "123456",
        "timestamp": "2023-01-15T10:30:00",
        "type": "qa_pair" | "standalone" | "grouped",
        "question": "What was asked",  # only for qa_pair type
        "channel_id": "channel_id",
        "chunk_index": 0,
        "total_chunks": 1
    }
}
```

### Step 5: Generate Embeddings & Store in ChromaDB

**File:** `ingestion/ingest.py` *(implemented)*

This script takes the preprocessed documents, generates embeddings via OpenAI, and stores everything in a persistent ChromaDB collection.

**What it does:**

1. **Initialize ChromaDB** with persistent storage using cosine similarity:
   ```python
   client = chromadb.PersistentClient(path="./chromadb_store")
   collection = client.get_or_create_collection(
       name="discord_posts",
       metadata={"hnsw:space": "cosine"}
   )
   ```

2. **Deduplication check** — queries existing IDs in the collection and skips documents already ingested (supports incremental ingestion)

3. **Batch embed and store** — processes documents in batches of 100:
   - Calls `openai.embeddings.create(model="text-embedding-3-small", input=batch_texts)`
   - Stores embeddings + documents + metadata in ChromaDB
   - Shows progress bar via `tqdm`
   - Adds 0.25s delay between batches for rate limiting
   - Retries once on `RateLimitError` with 30s backoff

4. **Error handling** — logs and skips failed batches without crashing

**Run commands:**
```bash
# Full ingestion
python -m ingestion.ingest

# Test with a small sample
python -m ingestion.ingest --sample 100

# Custom paths
python -m ingestion.ingest --export-dir ./data/exports --owner-id YOUR_ID --db-path ./chromadb_store
```

**Expected timing**: 200K messages → ~150-250K chunks → ~15-30 minutes for embedding + storage.

### Step 5b (Optional): Analyze Style

**File:** `ingestion/analyze_style.py` *(implemented)*

Analyzes the owner's historical messages to automatically extract style characteristics. The output is used in the system prompt for more accurate style matching.

**What it analyzes:**
- Average response length (words/sentences)
- Common phrases (top bigrams and trigrams)
- Emoji usage patterns (which emojis, how often)
- Message length distribution (short/medium/long)
- Common opening words
- Sample messages near median length for tone reference

**Run command:**
```bash
python -m ingestion.analyze_style
```

**Output:** Saves a style profile to `data/style_profile.txt`. The bot's RAG pipeline (`bot/rag.py`) automatically loads this file if it exists and includes it in the system prompt.

> **Need detailed help?** See the step-by-step guides: [Step F (Ingest Data)](#step-f-ingest-your-data) | [Step G (Analyze Style)](#step-g-optional-analyze-your-writing-style)

[↑ Back to Table of Contents](#table-of-contents)

---

## Phase 3: RAG Pipeline

### Step 6: Build Retrieval Module

**File:** `bot/rag.py` — `retrieve_context()` function *(implemented)*

**How it works:**

1. **Embeds the incoming question** using the same `text-embedding-3-small` model (async via `openai.AsyncOpenAI`)
2. **Queries ChromaDB** for top-K (default 8) most similar documents:
   ```python
   results = collection.query(
       query_embeddings=[question_embedding],
       n_results=8,
       include=["documents", "metadatas", "distances"]
   )
   ```
3. **Post-processes results:**
   - Filters out results with cosine distance > 0.8 (configurable via `RAG_MAX_DISTANCE`)
   - Deduplicates near-identical text (by first 100 chars)
   - Returns list of `{text, score, distance, metadata}` sorted by relevance

**Configuration** (via `.env` or `bot/config.py`):
- `RAG_TOP_K=8` — number of results to retrieve
- `RAG_MAX_DISTANCE=0.8` — maximum cosine distance threshold

### Step 7: Build Generation Module

**File:** `bot/rag.py` — `generate_answer()` function *(implemented)*

**How it works:**

1. **Loads style guidelines** — checks `data/style_profile.txt` first, falls back to default guidelines
2. **Builds the system prompt** using the template in `bot/config.py`:
   ```
   You are an AI assistant that responds EXACTLY in the style of the channel owner.
   You are answering questions in a Discord stock/investing channel.

   STYLE GUIDELINES:
   {loaded from style_profile.txt or defaults}

   RULES:
   1. ONLY answer based on the provided context from historical posts
   2. If the context doesn't contain enough information, say so
   3. Do NOT make up financial advice — only relay what was previously said
   4. Match the tone, length, and vocabulary exactly
   5. Do NOT add disclaimers unless the original style includes them

   At the end, output EXACTLY:
   CONFIDENCE: X  (1-10 scale)
   ```

3. **Builds the user prompt** with retrieved context chunks formatted as numbered examples, distinguishing Q&A pairs from standalone posts

4. **Calls GPT-4o-mini** with `temperature=0.7`, `max_tokens=500`

5. **Parses the response** — extracts the answer text and `CONFIDENCE: X` score (regex). If parsing fails, defaults to confidence=3 (safe low value)

6. **Retries once** on `APITimeoutError`

**Full pipeline function:** `run_rag_pipeline(question, collection, openai_client)` → `(answer, confidence, context_chunks)`

### Step 8: Confidence Routing

**File:** `bot/confidence.py` *(implemented)*

**Routing logic:**

| Condition | Action | Reason |
|-----------|--------|--------|
| `confidence >= 7` AND `best_distance <= 0.6` AND `context_count > 0` | `auto_reply` | High confidence with relevant context |
| `confidence < 7` | `forward_to_owner` | Below threshold |
| `context_count == 0` | `forward_to_owner` | No relevant context found |
| `best_distance > 0.6` | `forward_to_owner` | Context too dissimilar (even if LLM says confident) |

**Function:** `route_answer(answer, confidence, threshold=7, context_count=0, best_distance=1.0)` → `{action, answer, confidence, reason}`

The threshold is configurable via `CONFIDENCE_THRESHOLD` in `.env`.

[↑ Back to Table of Contents](#table-of-contents)

---

## Phase 4: Discord Bot Integration

### Step 9: Bot Listener

**File:** `bot/listener.py` *(implemented)*

The `MessageListener` Cog handles all incoming messages with filtering, rate limiting, and async queue processing.

**Message filters** (skip if any match):
- `message.author.bot` — ignore all bots (including self)
- `message.author.id == OWNER_USER_ID` — don't reply to the owner
- `message.channel.id not in TARGET_CHANNEL_IDS` — ignore non-target channels
- Empty messages or messages with no text content

**Rate limiting:**
- **Per-user cooldown:** max 1 reply per user per 30 seconds (configurable via `USER_COOLDOWN_SECONDS`)
- **Global cooldown:** max 10 replies per minute (configurable via `GLOBAL_MAX_PER_MINUTE`)

**Processing queue:**
- Uses `asyncio.Queue` to avoid blocking the event loop
- Single background worker task processes messages sequentially
- Prevents overwhelming the bot with concurrent OpenAI API calls

**Message handling flow:**
1. Show typing indicator while processing
2. Call `run_rag_pipeline(question)` — retrieve context + generate answer
3. Call `route_answer()` — decide auto-reply vs. forward
4. If auto-reply: `message.reply(answer)` (truncated to 2000 chars for Discord limit)
5. If forward: `send_for_review()` — DM owner with approve/edit/reject buttons
6. Log structured JSON for every interaction (question, confidence, action, response time)

### Step 10: Wire RAG Pipeline to Bot

**File:** `bot/main.py` *(implemented)*

The entry point that wires everything together:

1. **Validates config** — checks that `DISCORD_BOT_TOKEN` and `OPENAI_API_KEY` are set
2. **Initializes OpenAI** async client
3. **Initializes ChromaDB** — loads existing collection or creates empty one (with a warning to run ingestion)
4. **Creates Discord bot** with required intents (`message_content`, `members`)
5. **Registers the MessageListener Cog**
6. **Starts the bot**

**Run command:**
```bash
python -m bot.main
```

### Step 11: Owner Review Interface

**File:** `bot/review.py` *(implemented)*

When the confidence is below threshold, the bot DMs the owner with a rich embed and interactive buttons.

**The DM contains:**
- Channel where the question was asked
- Who asked the question
- Confidence score (X/10)
- The full question text
- The draft answer
- Top 3 context snippets used (abbreviated)
- Jump link to the original message

**Three buttons:**
| Button | Action |
|--------|--------|
| ✅ **Approve** | Posts the draft answer as a reply in the original channel |
| ✏️ **Edit** | Prompts the owner to type an edited answer (5-minute timeout), then posts that instead |
| ❌ **Reject** | Discards the draft — no reply is sent |

**Timeout:** If the owner doesn't respond within 1 hour, the review expires silently (no reply sent).

**Double-click protection:** The `handled` flag prevents the same review from being acted on twice.

> **Need detailed help?** See the step-by-step guides: [Step H (Start Bot)](#step-h-start-the-bot) | [Step I (Test Bot)](#step-i-test-the-bot)

[↑ Back to Table of Contents](#table-of-contents)

---

## Phase 5: Polish & Deploy

### Step 12: Logging & Monitoring

**Integrated into all modules.**

- **Python logging** to both console and `logs/bot.log` (configured in `bot/config.py`)
- **Structured JSON logs** for every processed query:
  ```json
  {
    "event": "query_processed",
    "question": "What about AAPL?",
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
- Routing decisions logged with reasons
- Error conditions logged with full tracebacks

### Step 13: Feedback Loop (Future Enhancement)

After the bot is running stably:

1. **Auto-ingest approved answers** — when owner approves a forwarded answer, embed it and add to ChromaDB
2. **Track rejection patterns** — if certain question types always get rejected, consider adding explicit handling
3. **Periodic re-ingestion** — as the owner continues posting manually, periodically export and ingest new messages
4. **Threshold tuning** — after 100+ interactions, analyze approval rate:
   - If >90% approved → lower threshold to 6
   - If <70% approved → raise to 8

### Step 14: Deployment

**Option A: Local Machine (start here)**
```bash
cd treeProjectDiscordBot
.venv\Scripts\activate
python -m bot.main
```
- Keep terminal open or use a process manager
- Not ideal: computer must stay on 24/7

**Option B: Docker on VPS (recommended for production)**

`Dockerfile` and `docker-compose.yml` are already included in the project.

1. Get a VPS: DigitalOcean ($6/mo), Hetzner ($4/mo), or Railway (usage-based)
2. Clone repo to server
3. Create `.env` file with your credentials
4. Run:
```bash
docker-compose up -d
```

The Docker setup mounts `chromadb_store/`, `logs/`, and `data/` as volumes so data persists across container restarts.

**Option C: systemd (Linux VPS without Docker)**
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
```

> **Need detailed help?** See [Step J (Deploy for 24/7)](#step-j-deploy-for-247-uptime)

[↑ Back to Table of Contents](#table-of-contents)

---

## Implementation Order & Dependencies

```
Step 1 (Discord Bot App) ──────────────────────────────┐
Step 2 (Export Data) ──→ Step 4 (Preprocess) ──→ Step 5 (Ingest) ──→ Step 6 (Retrieve) ──→ Step 7 (Generate) ──→ Step 8 (Confidence)
Step 3 (Scaffold) ─────→ Step 9 (Listener) ──────────────────────────────────────────────────────────────┘
                                                                                                          ↓
                                                                                              Step 10 (Wire Together)
                                                                                                          ↓
                                                                                              Step 11 (Review UI)
                                                                                                          ↓
                                                                                              Step 12 (Logging)
                                                                                                          ↓
                                                                                              Step 14 (Deploy)
```

- Steps 1, 2, 3 can all be done in parallel (independent setup tasks)
- Steps 4-8 are sequential (data pipeline)
- Step 9 can be done in parallel with Steps 4-8 (bot listener is independent of RAG pipeline)
- Steps 10+ require both the RAG pipeline and the bot listener

[↑ Back to Table of Contents](#table-of-contents)

---

## Quick Start Summary

> Already know what you're doing? Here's the short version. For detailed walkthroughs, see the links.

| # | Action | Command / Link | Time |
|---|--------|---------------|------|
| 1 | Create Discord bot & get token | [Step A](#step-a-create-a-discord-bot-application) | ~10 min |
| 2 | Get OpenAI API key | [Step B](#step-b-get-an-openai-api-key) | ~5 min |
| 3 | Set up Python & install deps | [Step C](#step-c-install-python--set-up-the-project) — `pip install -r requirements.txt` | ~5 min |
| 4 | Configure `.env` | [Step D](#step-d-configure-your-environment) — `copy .env.example .env` | ~2 min |
| 5 | Export Discord history | [Step E](#step-e-export-your-discord-history) — DiscordChatExporter CLI | ~15-60 min |
| 6 | Ingest data into vector DB | [Step F](#step-f-ingest-your-data) — `python -m ingestion.ingest` | ~15-30 min |
| 7 | Analyze your style (optional) | [Step G](#step-g-optional-analyze-your-writing-style) — `python -m ingestion.analyze_style` | ~1 min |
| 8 | Start the bot | [Step H](#step-h-start-the-bot) — `python -m bot.main` | ~1 min |
| 9 | Test the bot | [Step I](#step-i-test-the-bot) | ~10 min |
| 10 | Deploy for 24/7 | [Step J](#step-j-deploy-for-247-uptime) | ~30 min |

```bash
# Quick copy-paste version:
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env                    # then edit .env with your real values
# ... export Discord history to data/exports/ ...
python -m ingestion.ingest
python -m ingestion.analyze_style         # optional
python -m bot.main
```

[↑ Back to Table of Contents](#table-of-contents)

---

## Verification Checklist

1. **Ingestion test** — ingest 100 sample messages → query ChromaDB → verify results are relevant
   ```bash
   python -m ingestion.ingest --sample 100
   python -c "import chromadb; c = chromadb.PersistentClient('./chromadb_store'); col = c.get_collection('discord_posts'); print(col.count()); print(col.query(query_texts=['what stock should I buy'], n_results=3))"
   ```

2. **RAG quality test** — prepare 10 questions from real channel history → run through RAG pipeline → compare to actual answers
   ```bash
   python -m pytest tests/test_rag.py -v
   ```

3. **Confidence routing test** — run unit tests
   ```bash
   python -m pytest tests/test_confidence.py -v
   ```

4. **Ingestion unit tests**
   ```bash
   python -m pytest tests/test_ingestion.py -v
   ```

5. **Style consistency test** — have someone familiar with your channel read 5 generated answers blind — can they tell it's not you?

6. **End-to-end test** — create a private test channel → add bot → send messages → verify replies appear

7. **Rate limit test** — send 10 messages rapidly from same user → verify only 1 gets a reply (cooldown works)

8. **Owner review test** — trigger a low-confidence response → verify DM arrives with buttons → test approve, edit, and reject flows

9. **Uptime test** — run bot for 24 hours → verify no crashes, memory leaks, or connection drops

[↑ Back to Table of Contents](#table-of-contents)

---

## Troubleshooting

### Bot connects but doesn't reply to messages

| Possible cause | Fix |
|---------------|-----|
| MESSAGE CONTENT INTENT not enabled | Go to Discord Developer Portal → Bot → enable ✅ MESSAGE CONTENT INTENT. See [Step A.4](#step-a-create-a-discord-bot-application) |
| Channel ID not in `TARGET_CHANNEL_IDS` | Check `.env` — the channel ID must be listed. See [Step D](#step-d-configure-your-environment) |
| Bot doesn't have Read Messages permission | Re-invite with correct permissions. See [Step A.5](#step-a-create-a-discord-bot-application) |
| You're the owner sending messages | The bot ignores messages from `OWNER_USER_ID` by design. Test from another account or temporarily change the ID |
| Rate limit active | Wait 30 seconds (per-user cooldown). Check logs in `logs/bot.log` |

### `DISCORD_BOT_TOKEN is not set` error

Your `.env` file is missing or the token is blank. See [Step D](#step-d-configure-your-environment).

### `OPENAI_API_KEY is not set` error

Your `.env` file is missing the OpenAI key. See [Step B](#step-b-get-an-openai-api-key).

### `ChromaDB collection 'discord_posts' not found` warning

You haven't run the ingestion step yet. See [Step F](#step-f-ingest-your-data):
```bash
python -m ingestion.ingest
```

### `No JSON files found` during ingestion

Your export files aren't in the right folder. Place `.json` files in `data/exports/`. See [Step E](#step-e-export-your-discord-history).

### `RateLimitError` from OpenAI during ingestion

The script retries automatically with a 30-second backoff. If it persists:
- Reduce batch size: add `EMBED_BATCH_SIZE=50` to `.env`
- Check your OpenAI usage limits at https://platform.openai.com/settings/organization/limits

### Bot replies to everything / replies to nothing

- **Replies to everything:** Check `TARGET_CHANNEL_IDS` — if empty, the bot monitors all channels. Set specific channel IDs.
- **Replies to nothing:** Check `CONFIDENCE_THRESHOLD` — if set too high (e.g., 10), the bot forwards everything to you. Try lowering to `5` for testing.

### DM review buttons don't work

- The bot must stay running for buttons to work (they're handled in-process)
- Buttons expire after 1 hour
- Make sure your DMs are open (Discord Settings → Privacy → Allow direct messages)

### `pip install` fails

- Make sure you're using Python 3.11+ (`python --version`)
- Make sure the virtual environment is activated (`(.venv)` in your prompt)
- On Windows, if `pip` isn't found, try `python -m pip install -r requirements.txt`

[↑ Back to Table of Contents](#table-of-contents)

---

## Security Considerations

- **NEVER commit `.env`** — bot token + API keys must stay out of version control (`.gitignore` is configured)
- **Input sanitization** — user messages are wrapped in context framing, never injected raw into system prompts
- **Rate limiting** — per-user and global cooldowns prevent abuse and runaway API costs
- **Financial safety** — the bot never generates novel financial advice — only relays what was previously said (enforced by system prompt)
- **Minimal permissions** — bot only needs Read Messages, Send Messages, Read Message History (no admin, no manage channels)
- **Secrets in Docker** — use `env_file` in docker-compose, never bake secrets into the image

[↑ Back to Table of Contents](#table-of-contents)

---

## Configuration Reference

All settings are configured via `.env` (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCORD_BOT_TOKEN` | — | Your Discord bot token |
| `OPENAI_API_KEY` | — | Your OpenAI API key |
| `OWNER_USER_ID` | — | Your Discord user ID |
| `TARGET_CHANNEL_IDS` | — | Comma-separated channel IDs to monitor |
| `CONFIDENCE_THRESHOLD` | `7` | Minimum confidence for auto-reply (1-10) |
| `CHROMADB_PATH` | `./chromadb_store` | Path to ChromaDB persistent storage |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `LLM_MODEL` | `gpt-4o-mini` | OpenAI model for generation |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI model for embeddings |
| `LLM_MAX_TOKENS` | `500` | Max tokens in generated response |
| `LLM_TEMPERATURE` | `0.7` | Temperature for generation |
| `RAG_TOP_K` | `8` | Number of context chunks to retrieve |
| `RAG_MAX_DISTANCE` | `0.8` | Max cosine distance for context filtering |
| `USER_COOLDOWN_SECONDS` | `30` | Per-user reply cooldown |
| `GLOBAL_MAX_PER_MINUTE` | `10` | Max replies per minute globally |
| `CHUNK_MAX_TOKENS` | `500` | Max tokens per chunk during ingestion |
| `CHUNK_OVERLAP_TOKENS` | `50` | Token overlap between chunks |
| `EMBED_BATCH_SIZE` | `100` | Batch size for embedding API calls |

[↑ Back to Table of Contents](#table-of-contents)

---

## Decisions & Scope

### Included
- Full data pipeline: export → preprocess → embed → store
- RAG retrieval and LLM generation
- Auto-reply with confidence routing
- Owner review via DM with approve/edit/reject
- Basic logging and monitoring
- Docker deployment option
- Unit tests for core modules

### Excluded (future enhancements)
- Web dashboard for analytics
- Slash commands for bot management
- Multi-server support
- Automatic periodic re-ingestion
- Fine-tuning a model on your data (RAG is sufficient to start)
- Sentiment analysis or topic classification

[↑ Back to Table of Contents](#table-of-contents)
