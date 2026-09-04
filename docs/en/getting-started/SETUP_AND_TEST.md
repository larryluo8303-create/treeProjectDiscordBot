# Local Setup and Test Guide

---

## Current Environment Status

| Component | Status |
|---|---|
| Python 3.11 + virtualenv + dependencies | ✅ Ready |
| `.env` configuration file | ❌ Needs to be created |
| Discord export data | ❌ `data/exports/` is empty |
| ChromaDB vector database | ❌ 0 documents |
| Style analysis file | ❌ Not generated |

---

## Prerequisites: Install System Tools

These tools are **system-level** and are not included in the Python dependencies; install them separately.

### Python 3.11+

```powershell
winget install --id Python.Python.3.11 -e
```

### FFmpeg (required for YouTube audio transcription)

```powershell
winget install --id Gyan.FFmpeg -e
```

### Deno (required by yt-dlp to parse YouTube pages)

```powershell
winget install --id DenoLand.Deno -e
```

> **Important:** After installing the tools above, **reopen PowerShell** so PATH updates take effect.

### Verify installation

```powershell
python --version    # Should show 3.11.x or higher
ffmpeg -version     # Should show a version number
deno --version      # Should show a version number
```

### Create a virtual environment and install Python dependencies

```powershell
cd C:\treeProjectDiscordBot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

---

## Step 1: Create the `.env` configuration file

```powershell
Copy-Item .env.example .env
notepad .env
```

In Notepad, fill in these **4 required fields**; leave the rest at their defaults:

```
DISCORD_BOT_TOKEN=your Bot Token
OPENAI_API_KEY=your OpenAI API Key
OWNER_USER_ID=your Discord user ID
TARGET_CHANNEL_IDS=channel IDs to listen on
```

**How to get these values:**

| Value | How to obtain |
|---|---|
| `DISCORD_BOT_TOKEN` | https://discord.com/developers/applications → your app → Bot (left) → "Reset Token" → copy |
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys → create a new key → copy |
| `OWNER_USER_ID` | Discord Settings → Advanced → enable "Developer Mode" → right-click your avatar → "Copy User ID" |
| `TARGET_CHANNEL_IDS` | Right-click the channel name → "Copy Channel ID" (comma-separate multiple channels) |

Save and close Notepad when done.

---

## Step 2: Make sure the Bot is invited to your Discord server

Bot invite URL format (replace `YOUR_CLIENT_ID`):

```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=274877975552&scope=bot
```

`YOUR_CLIENT_ID` is in Discord Developer Portal → your app → OAuth2 → "CLIENT ID" at the top of the page.

**Required permissions (already included in the link above):**
- Send Messages
- Read Message History
- Read Messages / View Channels

---

## Step 3: Prepare Discord historical message data

### Option A — Export real data (production use)

Use the [DiscordChatExporter](https://github.com/Tyrrrz/DiscordChatExporter/releases) tool:

1. Download and extract DiscordChatExporter (choose the `.zip` build)
2. Run the export command (replace the user Token and channel ID):

```powershell
DiscordChatExporter.Cli.exe export -t "your Discord user Token" -c CHANNEL_ID -f Json -o data\exports\channel_export.json
```

> **Note:** This uses your **user Token** (not the Bot Token). You can obtain it from the browser DevTools Network tab.

3. After export completes, confirm the JSON file is under `data\exports\`

---

### Option B — Use mock data for a quick test (recommended first)

After activating the virtual environment, run the following (**replace `your-user-id` with the `OWNER_USER_ID` from `.env`**):

```powershell
.venv\Scripts\activate
```

```powershell
python -c "
import json
owner_id = 'your-user-id'
data = {
    'channel': {'id': '123456'},
    'messages': [
        {'id': '1', 'content': 'What do you think about AAPL?', 'timestamp': '2024-01-01T00:00:00+00:00', 'author': {'id': '999', 'name': 'Member', 'nickname': 'Member'}},
        {'id': '2', 'content': 'AAPL is near key support around 180; worth watching', 'timestamp': '2024-01-01T00:01:00+00:00', 'author': {'id': owner_id, 'name': 'Owner', 'nickname': 'Owner'}, 'reference': {'messageId': '1'}},
        {'id': '3', 'content': 'Technically, moving averages are in a bullish stack and MACD just crossed up — short-term bullish', 'timestamp': '2024-01-01T00:01:30+00:00', 'author': {'id': owner_id, 'name': 'Owner', 'nickname': 'Owner'}},
        {'id': '4', 'content': 'Can I buy TSLA?', 'timestamp': '2024-01-02T00:00:00+00:00', 'author': {'id': '888', 'name': 'User2', 'nickname': 'User2'}},
        {'id': '5', 'content': 'TSLA is too volatile — unless you can handle a 20% drawdown, stay away', 'timestamp': '2024-01-02T00:01:00+00:00', 'author': {'id': owner_id, 'name': 'Owner', 'nickname': 'Owner'}, 'reference': {'messageId': '4'}},
        {'id': '6', 'content': 'The broader market is weak today; better to wait and not chase highs', 'timestamp': '2024-01-03T00:00:00+00:00', 'author': {'id': owner_id, 'name': 'Owner', 'nickname': 'Owner'}},
        {'id': '7', 'content': 'SPY broke below the 5-day MA — watch risk control', 'timestamp': '2024-01-03T00:05:00+00:00', 'author': {'id': owner_id, 'name': 'Owner', 'nickname': 'Owner'}},
    ]
}
with open('data/exports/test_export.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print('Test data created: data/exports/test_export.json')
"
```

---

## Step 4: Run data ingestion

```powershell
.venv\Scripts\activate
python -m ingestion.ingest
```

Expected output:
```
Starting ingestion pipeline
  Export dir : ./data/exports
  Owner ID  : your-user-id
Embedding & storing: 100%|████████| 1/1
Ingestion complete: X documents stored in ChromaDB
Done — total documents in collection: X
```

---

## Step 5 (optional): Generate style analysis

Analyze your writing style so model replies sound more like you:

```powershell
python -m ingestion.analyze_style
```

Results are saved to `data/style_profile.txt` and loaded automatically the next time the Bot starts.

---

## Step 6: Start the Bot

```powershell
python -m bot.main
```

**A successful start** looks like:

```
INFO  OpenAI client initialized
INFO  ChromaDB collection 'discord_posts' loaded — X documents
INFO  Logged in as YourBotName#1234
INFO  Serving 1 guild(s)
INFO  Bot is ready — starting message queue worker
```

Press `Ctrl+C` to stop the Bot.

---

## Step 7: Test Bot replies

1. Open a Discord channel listed in `TARGET_CHANNEL_IDS`
2. **Use another account** (not the channel owner account) to ask a question, for example:
   - `Can I buy AAPL now?`
   - `How do you see the market?`
3. Observe Bot behavior:
   - **Confidence ≥ 7** → Bot replies automatically
   - **Confidence < 7** → Bot DMs you for review, with these buttons:
     - ✅ **Approve** — send the draft reply as-is
     - ✏️ **Edit** — type a revised reply in DM, then send
     - ❌ **Reject** — do not reply; discard
4. The terminal running the Bot shows live logs; logs are also written to `logs/bot.log`

---

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `DISCORD_BOT_TOKEN is not set` | `.env` missing or Token blank | Redo Step 1 |
| `ChromaDB collection not found` | Data not ingested | Redo Step 4 |
| Bot is online but does not reply | Wrong channel ID, or the poster is the channel owner | Confirm `TARGET_CHANNEL_IDS`; test with another account |
| `Forbidden 403` | Bot lacks channel permissions | Re-invite the Bot with the Step 2 invite link |
| Replies are inaccurate | Too little test data | Import more real history (Option A) |
| Review DMs not received | Wrong `OWNER_USER_ID` | Confirm it is your own Discord user ID |
| `No JSON files found` | Export files in the wrong folder | Confirm JSON files are under `data\exports\` |

---

## Everyday command cheat sheet

```powershell
# Activate the virtual environment (run this first whenever you open a terminal)
.venv\Scripts\activate

# Start the Bot
python -m bot.main

# Re-ingest after adding new data (incremental; no duplicates)
python -m ingestion.ingest

# Regenerate style analysis
python -m ingestion.analyze_style

# Run tests to confirm the code is healthy
python -m pytest tests/ -v
```
