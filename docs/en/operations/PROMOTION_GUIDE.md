# BigTreeSignal Promotion Features — User Guide

---

## Table of Contents

- [1. Quick Start](#1-quick-start)
- [2. Environment Variable Reference](#2-environment-variable-reference)
- [3. Feature Usage](#3-feature-usage)
  - [3.1 Automatic Signal-Query Guidance](#31-automatic-signal-query-guidance)
  - [3.2 Auto-Reply Trailing CTA](#32-auto-reply-trailing-cta)
  - [3.3 /signal Command](#33-signal-command)
  - [3.4 New Member Welcome DM](#34-new-member-welcome-dm)
  - [3.5 Post Promo Immediately /post_promo](#35-post-promo-immediately-post_promo)
  - [3.6 Schedule Promo /schedule_promo](#36-schedule-promo-schedule_promo)
  - [3.7 Schedule Signal Recap /schedule_trial](#37-schedule-signal-recap-schedule_trial)
  - [3.8 Schedule Lesson Push /schedule_lesson](#38-schedule-lesson-push-schedule-lesson)
  - [3.9 Manage Schedules](#39-manage-schedules)
  - [3.10 Testimonial Collection](#310-testimonial-collection)
  - [3.11 Show Testimonials /testimonials](#311-show-testimonials-testimonials)
  - [3.12 Opt-In Notify Role Promo DMs](#312-opt-in-notify-role-promo-dms)
- [4. Slash Command Cheat Sheet](#4-slash-command-cheat-sheet)
- [5. Common Scenario Examples](#5-common-scenario-examples)
- [6. Data File Locations](#6-data-file-locations)
- [7. Troubleshooting](#7-troubleshooting)

---

## 1. Quick Start

### Prerequisites

Before using promotion features, confirm the following are ready:

| Component | Requirement | Notes |
|-----------|-------------|-------|
| Python | 3.11+ | Verify with `python --version` |
| Virtual environment | Created and activated | `.venv\Scripts\Activate.ps1` (PowerShell) |
| Python dependencies | Installed | `pip install -r requirements.txt` |
| `.env` file | Core config complete | Must include `DISCORD_BOT_TOKEN`, `OPENAI_API_KEY`, `OWNER_USER_ID`, `TARGET_CHANNEL_IDS` |
| Discord Bot | Invited to the server | Needs `bot` + `applications.commands` scopes |
| Knowledge base data | Ingested into ChromaDB | `python -m ingestion.ingest` has been run |

> **Note:** If the bot is not deployed yet, complete the full install flow in [`SETUP_AND_TEST.md`](../getting-started/SETUP_AND_TEST.md) (or the archived [`PHASE1_2_GUIDE.md`](../archive/PHASE1_2_GUIDE.md)) first, then return to enable promotion features.

### Environment Setup (if not done yet)

```powershell
# 1. Install Python 3.11+
winget install --id Python.Python.3.11 -e

# 2. Create virtual environment
cd C:\treeProjectDiscordBot
python -m venv .venv

# 3. Activate virtual environment
.venv\Scripts\Activate.ps1

# 4. Install dependencies
pip install -r requirements.txt

# 5. Create .env (if missing)
Copy-Item .env.example .env
# Edit .env and fill in core settings
```

### 1. Configure `.env`

Append promotion settings to the end of your existing `.env`:

```env
# ── BigTreeSignal Promo ──
PROMO_ENABLED=true
PROMO_CHANNEL_IDS=your_promo_channel_id_1,promo_channel_id_2
SIGNAL_PRODUCT_NAME=BigTreeSignal
SIGNAL_PRODUCT_URL=https://your-product-link.com
TESTIMONIAL_CHANNEL_ID=your_user-wins_channel_id
```

### 2. Get Channel IDs

In Discord:
1. Open **User Settings → Advanced → Developer Mode** (enable it)
2. Right-click the target channel → **Copy Channel ID**

### 3. Start the Bot

```powershell
# Activate virtual environment
.venv\Scripts\Activate.ps1

# Start the bot
python -m bot.main

# If using Docker
docker-compose restart
```

### 4. Verify Startup

After a normal start you should see logs like:

```
[INFO] bot.main: OpenAI client initialized
[INFO] bot.main: ChromaDB collection loaded — XXXXX documents
[INFO] bot.main: Starting Discord bot...
[INFO] bot.listener: Bot is ready — starting message queue worker
```

After start, the bot syncs Slash Commands automatically (first sync may take a few minutes before they appear in Discord).

Confirm promotions are ready: in a promo channel, type `/signal`. If the bot replies with a product Embed, promotion features are working.

---

## 2. Environment Variable Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PROMO_ENABLED` | No | `true` | Master promo switch. Set `false` to disable all promotion features |
| `PROMO_CHANNEL_IDS` | **Yes** | `""` | Promo channel IDs, comma-separated. **If unset, promotions do not run** |
| `SIGNAL_PRODUCT_NAME` | No | `BigTreeSignal` | Product name shown in Embed titles |
| `SIGNAL_PRODUCT_URL` | Recommended | `""` | Product URL. If unset, CTAs have no link |
| `SIGNAL_CTA_TEXT` | No | `Want live trading signals? Learn about BigTreeSignal` | Guidance copy when a signal query is detected |
| `AUTO_REPLY_CTA_TEXT` | No | `Want live trading signals? Learn about BigTreeSignal →` | Trailing CTA copy on auto-replies |
| `CTA_FREQUENCY` | No | `5` | Attach 1 CTA every N auto-replies. Set `0` to disable |
| `FREE_TRIAL_ENABLED` | No | `false` | Whether to show a free-trial entry on product displays |
| `FREE_TRIAL_URL` | No | `""` | Free-trial URL |
| `WELCOME_MESSAGE` | No | `Welcome!...` | Body text of the new-member welcome DM |
| `TESTIMONIAL_CHANNEL_ID` | Recommended | `0` | #user-wins channel ID. If unset, approved testimonials are not forwarded |
| `TESTIMONIAL_DETECTION_ENABLED` | No | `true` | Whether to auto-detect testimonial messages |
| `PROMO_NOTIFY_ROLE_IDS` | Required for DMs | `""` | Opt-in “event notify” role IDs, comma-separated. **Not** ops/interest tags. If unset, promo DMs cannot be sent |
| `PROMO_DM_DELAY_SECONDS` | No | `1.2` | Delay between promo DMs (seconds) |
| `PROMO_DM_MAX_RECIPIENTS` | No | `200` | Max recipients per DM batch; over limit refuses send |

### Configuration Examples

**Minimal config** (basic CTAs only):

```env
PROMO_CHANNEL_IDS=123456789012345678
SIGNAL_PRODUCT_URL=https://bigtreesignal.com
```

**Full config**:

```env
PROMO_ENABLED=true
PROMO_CHANNEL_IDS=123456789012345678,987654321098765432
SIGNAL_PRODUCT_NAME=BigTreeSignal
SIGNAL_PRODUCT_URL=https://bigtreesignal.com
SIGNAL_CTA_TEXT=Want live trading signals? Learn about BigTreeSignal
AUTO_REPLY_CTA_TEXT=Want live trading signals? Learn about BigTreeSignal →
CTA_FREQUENCY=5
FREE_TRIAL_ENABLED=true
FREE_TRIAL_URL=https://bigtreesignal.com/trial
WELCOME_MESSAGE=Welcome to the BigTree community! Professional stock analysis and trading signal services.
TESTIMONIAL_CHANNEL_ID=111222333444555666
TESTIMONIAL_DETECTION_ENABLED=true
PROMO_NOTIFY_ROLE_IDS=777888999000111222
PROMO_DM_DELAY_SECONDS=1.2
PROMO_DM_MAX_RECIPIENTS=200
```

---

## 3. Feature Usage

### 3.1 Automatic Signal-Query Guidance

**No action needed — triggers automatically.**

When a user asks signal-related questions in a promo channel (e.g. "Any signals?", "Can I buy?", "Where's the entry?"), the bot will:
1. Forward the question to the Owner for review as usual
2. **Also** post a product-guidance Embed in the channel

Embed example:
```
🌳 BigTreeSignal
Want live trading signals? Learn about BigTreeSignal

📊 Markets covered: US stocks · ETF · Crypto
🔗 Learn more: Click to view
```

### 3.2 Auto-Reply Trailing CTA

**No action needed — triggers automatically.**

In promo channels, every N auto-replies (controlled by `CTA_FREQUENCY`), the bot appends a CTA line at the end:

```
(Bot's normal answer content)

💡 Want live trading signals? Learn about BigTreeSignal →
```

- Default: 1 CTA every 5 replies
- Set `CTA_FREQUENCY=0` to disable completely
- Only applies in promo channels

### 3.3 /signal Command

**Any user** can type `/signal` in a promo channel to view product info.

```
/signal
```

The bot replies with a polished Embed showing:
- Product name and summary
- Markets covered
- Delivery method
- Subscribe link
- Free trial (if enabled)

Outside promo channels you get: "Promotion is not enabled in this channel."

### 3.4 New Member Welcome DM

**No action needed — triggers automatically.**

When a new member joins a server that contains a promo channel, the bot sends a welcome DM Embed with:
- Welcome text (`WELCOME_MESSAGE`)
- Hints for `/faq` `/ask` `/signal`
- Product link + free-trial button (if real URLs are configured)
- If `PROMO_NOTIFY_ROLE_IDS` is set: copy inviting them to opt into promo DMs, with **Get notifications** / **Unsubscribe** buttons

> Note: If the user has DMs closed, the bot skips silently with no error. Clicking **Get notifications** adds them to the promo DM list; they are not added automatically.

### 3.5 Post Promo Immediately /post_promo

**Owner only.** Immediately posts a promo to promo channels.

```
/post_promo title:"New Year 30% Off" description:"BigTreeSignal New Year special — subscribe by Jan 31 and save 30%"
```

Optional parameters:
- `url` — promo link (falls back to `SIGNAL_PRODUCT_URL` if omitted)
- `channel` — specific channel (defaults to all promo channels)
- `dm_role` — also DM the **whitelisted notify role** (ops tags are rejected). Channel post goes first; DMs send after recipient count is confirmed

### 3.6 Schedule Promo /schedule_promo

**Owner only.** Schedule a promo post to send automatically at a given time.

```
/schedule_promo title:"Weekend Special" description:"3-day limited offer — 20% off subscriptions" time:"2024-01-20 10:00"
```

Optional parameters:
- `url` — promo link
- `channel` — specific channel
- `dm_role` — when due, also DM the whitelisted notify role

**Time format:** `YYYY-MM-DD HH:MM` (parsed as UTC-4 / ET)

Bot confirmation:
```
✅ Promo scheduled!
ID: promo_a1b2c3d4
Title: Weekend Special
Send time: 2024-01-20 10:00 (ET)
Channels: 2
```

### 3.7 Schedule Signal Recap /schedule_trial

**Owner only.** Schedule a free signal-recap post (delayed results of historical signals).

```
/schedule_trial title:"Today's Free Signal Recap" content:"Yesterday's AAPL long signal: open xxx → close xxx, profit +2.3%" time:"2024-01-16 20:00"
```

Signal-recap posts use a green Embed with a "Free Signal Recap" tag, distinct from normal promos.

### 3.8 Schedule Lesson Push /schedule_lesson

**Owner only.** Schedule educational content, with optional repeat.

```
/schedule_lesson title:"Intro to Three Buy Points" content:"Today we cover Chan Theory's three buy points..." time:"2024-01-16 09:00" repeat:weekly
```

Repeat modes:
- **No repeat** (default) — send once
- **Daily** — same time every day
- **Weekly** — same weekday and time every week

Lesson posts use a blue Embed with a "📚 Lesson" tag.

### 3.9 Manage Schedules

```
/list_promos         — list scheduled promos (latest 10)
/cancel_promo id     — cancel a schedule (promo ID)
/list_lessons        — list scheduled lessons (latest 10)
/cancel_lesson id    — cancel a schedule (lesson ID)
```

Example:
```
/list_promos
```
Bot reply:
```
Scheduled promos:
⏳ Pending promo_a1b2c3d4 — Weekend Special — 2024-01-20 10:00
✅ Sent promo_e5f6g7h8 — New Year Offer — 2024-01-15 10:00
```

```
/cancel_promo promo_id:promo_a1b2c3d4
```
Bot reply:
```
✅ Promo promo_a1b2c3d4 cancelled.
```

### 3.10 Testimonial Collection

**No action needed — triggers automatically.**

When a user in a promo channel posts a message with profit/praise keywords (e.g. "跟信号赚了不少", "信号准", "翻倍了" / "made money following signals", "accurate signals", "doubled"), the bot will:

1. Collect the message into `data/testimonials.json`
2. DM the Owner a review request with:
   - User info
   - Message content
   - Link to the original message
   - **✅ Approve** / **❌ Reject** buttons

3. Owner clicks **✅ Approve**:
   - Message is formatted as an Embed and forwarded to `TESTIMONIAL_CHANNEL_ID`
   - Embed includes username, avatar, original content, timestamp

4. Owner clicks **❌ Reject**:
   - Message is marked rejected and not forwarded

**Detection keywords (ZH/EN):**
赚了、盈利、翻倍、大赚、跟单、跟信号、信号准、赚到、出金、回本、赚钱、收益不错、profit、gains、made money、signal works、great signal、good signal

### 3.11 Show Testimonials /testimonials

**Any user** in a promo channel can use:

```
/testimonials
```

The bot shows the latest 5 approved testimonial Embeds:
```
🌟 Member Testimonials
Real feedback from community members

💬 TraderWang — 2024-01-15
Made solid gains following the signals — thanks BigTree!

💬 StockFan — 2024-01-14
Signals are really accurate — last week +5%
```

### 3.12 Opt-In Notify Role Promo DMs

You **cannot** mass-DM everyone or ops/interest tags you assigned manually. Discord treats unsolicited mass DMs as spam. DMs only go to members who opted into a notify role themselves.

**One-time setup**

1. Create a server role **Event Notify** (no admin permissions).
2. Copy the role ID into `.env` as `PROMO_NOTIFY_ROLE_IDS`.
3. Place the Bot role above **Event Notify** and grant the Bot **Manage Roles**.
4. Restart the bot.

**Post subscribe panel (Owner, once in an announcement channel)**

```
/promo_notify_panel
```

Pin that message, and optionally `@everyone` once in-channel (that is a channel announcement, not a mass DM). Members must click **Get notifications** to join the DM list; **Unsubscribe** only removes the notify role and leaves ops tags alone. Members can also use `/promo_notify`. New joiners see the same buttons in the welcome DM (requires `PROMO_NOTIFY_ROLE_IDS` and welcome flow enabled).

**Send event DMs (Owner)**

```
/dm_role role:@Event Notify title:"Weekend Special" description:"Limited-time 20% off"
```

The bot first shows how many people will be messaged; only after confirm does it send with rate limiting. You can also pass optional `dm_role` on `/post_promo` / `/schedule_promo` (must be a whitelisted role, or the command is refused).

Batches over `PROMO_DM_MAX_RECIPIENTS` (default 200) are refused — split the send or raise the limit.

---

## 4. Slash Command Cheat Sheet

| Command | Permission | Description |
|---------|------------|-------------|
| `/signal` | Everyone | View BigTreeSignal product info |
| `/testimonials` | Everyone | View recent testimonials |
| `/promo_notify` | Everyone | Opt in/out of event promo DMs |
| `/post_promo` | Owner | Post promo immediately (optional sync DMs) |
| `/schedule_promo` | Owner | Schedule promo (optional sync DMs) |
| `/dm_role` | Owner | DM promo to opt-in notify role |
| `/promo_notify_panel` | Owner | Post event-DM subscribe panel in channel |
| `/schedule_trial` | Owner | Schedule signal-recap post |
| `/schedule_lesson` | Owner | Schedule lesson push |
| `/list_promos` | Owner | List scheduled promos |
| `/cancel_promo` | Owner | Cancel scheduled promo |
| `/list_lessons` | Owner | List scheduled lessons |
| `/cancel_lesson` | Owner | Cancel scheduled lesson |

---

## 5. Common Scenario Examples

### Scenario 1: User asks for buy/sell signals

```
User: Can I buy AAPL now? Any signals?

Bot: (forwards to Owner for review)
Bot: 🌳 BigTreeSignal
     Want live trading signals? Learn about BigTreeSignal
     📊 Markets covered: US stocks · ETF · Crypto
     🔗 Learn more: Click to view
```

### Scenario 2: Bot auto-replies a normal question (5th time)

```
User: How do I read MACD divergence?

Bot: MACD divergence is mainly when price and MACD histogram move in opposite directions...
     (normal analysis content)

     💡 Want live trading signals? Learn about BigTreeSignal →
```

### Scenario 3: Owner schedules a weekend promo

```
Owner types: /schedule_promo title:"Weekend 20% Off" description:"BigTreeSignal weekend special" time:"2024-01-20 10:00"

Bot reply (Owner-only ephemeral):
✅ Promo scheduled!
ID: promo_a1b2c3d4
Send time: 2024-01-20 10:00 (ET)

→ At Saturday 10:00 AM, the bot automatically posts the promo Embed in promo channels
```

### Scenario 4: User shares profits

```
User: Made solid gains following the signals — thanks BigTree! 🔥

→ Bot does not reply (this is a courtesy message and is skipped)
→ But the bot auto-collects it as a testimonial and DMs the Owner for review
→ Owner clicks ✅ Approve
→ Bot posts an Embed in #user-wins:

🌟 Member Testimonials
TraderWang: Made solid gains following the signals — thanks BigTree! 🔥
Time: 2024-01-15
🌳 BigTreeSignal
```

---

## 6. Data File Locations

| File | Path | Description |
|------|------|-------------|
| Promo schedules | `data/promos.json` | All scheduled/sent promos |
| Lesson schedules | `data/lessons.json` | All scheduled/sent lessons |
| Testimonials | `data/testimonials.json` | All collected testimonials |

These files are created automatically; no manual management required. To clean up, delete the file or edit the JSON.

---

## 7. Troubleshooting

### Slash Commands not appearing

- First-time Slash Command sync can take **up to 1 hour**
- Check `logs/bot.log` for "Synced X slash command(s)"
- Ensure the bot has the `applications.commands` scope (Discord Developer Portal)

### CTA not showing

- Confirm the channel ID is in `PROMO_CHANNEL_IDS`
- Confirm `PROMO_ENABLED=true`
- Auto-reply CTAs need the counter to hit (default every 5 replies)

### Testimonials not detected

- Confirm `TESTIMONIAL_DETECTION_ENABLED=true`
- Confirm the message is in a promo channel
- Confirm the message contains detection keywords
- Owner's own messages are not detected

### Scheduled promo not sent

- Check whether the time has passed (parsed as UTC-4)
- Check whether `data/promos.json` marks it `cancelled`
- Check logs for "Failed to post promo"
- Confirm the bot can send messages in the target channel

### New-member welcome DM not sent

- Confirm the bot has the `members` Intent (already enabled in code)
- Confirm the server has at least one channel in `PROMO_CHANNEL_IDS`
- User may have DMs closed (bot skips silently)
