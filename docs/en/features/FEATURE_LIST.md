# BigTreeASignalAiBot — Full Feature List

## 🔴 Core Features (Required)

### 1. RAG Q&A

- **Files:** `bot/rag.py`, `bot/listener.py`, `bot/confidence.py`
- **Description:** Users ask questions in Discord channels; the bot retrieves relevant content from the ChromaDB knowledge base and uses GPT to generate answers that imitate the channel owner's style
- **Config:** `OPENAI_API_KEY`, `LLM_MODEL`, `RAG_TOP_K`, `RAG_MAX_DISTANCE`, `CONFIDENCE_THRESHOLD`
- **Usage:** Automatic — users just post in a target channel

### 2. Confidence Routing

- **Files:** `bot/confidence.py`
- **Description:** Based on the confidence score, either auto-reply (≥ threshold) or forward to the Owner for review (< threshold)
- **Config:** `CONFIDENCE_THRESHOLD=7` (default), `RESPOND_MODE=auto|review|questions|mention_only`

### 3. Owner Review System

- **Files:** `bot/review.py`, `bot/review_queue.py`
- **Description:** Low-confidence answers are sent to the Owner via DM with Approve / Edit / Reject buttons
- **Usage:** Owner clicks buttons in DM; Approved content is automatically learned into the knowledge base

### 4. Knowledge Base Ingestion

- **Files:** `ingestion/ingest.py`, `ingestion/preprocess.py`
- **Description:** Preprocess, chunk, and vectorize Discord-exported JSON data into ChromaDB
- **Usage:** `python -m ingestion.ingest`

### 5. Channel Listening & Message Handling

- **Files:** `bot/listener.py`
- **Description:** Listen to target channel messages, filter spam/politeness phrases, detect questions, and maintain conversation memory
- **Config:** `TARGET_CHANNEL_IDS`, `EXCLUDED_CHANNEL_IDS`, `CONVERSATION_MEMORY_SIZE`, `CONVERSATION_MEMORY_TTL`

---

## 🟡 Important Features (Strongly Recommended)

### 6. Rate Limiting

- **Files:** `bot/listener.py`
- **Description:** Per-user cooldown + global per-minute cap to prevent abuse
- **Config:** `USER_COOLDOWN_SECONDS=30`, `GLOBAL_MAX_PER_MINUTE=10`

### 7. Offline Backfill

- **Files:** `bot/listener.py`
- **Description:** After restart, automatically scan unanswered questions from the offline period
- **Config:** `OFFLINE_BACKFILL_ENABLED=true`, `OFFLINE_BACKFILL_LOOKBACK_HOURS=24`

### 8. Auto-Learn Owner Messages

- **Files:** `bot/listener.py`
- **Description:** Owner posts in channels are automatically ingested into ChromaDB so the knowledge base keeps growing
- **Usage:** Automatic — Owner posts normally

### 9. Thread Reply Support

- **Files:** `bot/listener.py`
- **Description:** Can reply inside Threads and automatically pull Thread context
- **Config:** `THREAD_AUTO_REPLY=true`, `THREAD_CONTEXT_MESSAGES=15`

### 10. Image / Chart Analysis

- **Files:** `bot/rag.py`, `bot/listener.py`
- **Description:** When users send images (e.g. candlestick charts), analyze them with GPT-4o Vision
- **Config:** `VISION_MODEL=gpt-4o`

### 11. Voice Message Transcription & Reply

- **Files:** `bot/listener.py`
- **Description:**
  - **Owner voice:** Discord voice clips are transcribed with Whisper and auto-learned into the knowledge base (no public reply)
  - **Member voice:** Only Discord **voice clips** are processed (not arbitrary mp3/songs). After Whisper transcription, RAG replies; the channel shows typing while transcribing
  - **Limits:** Over ~2MB or 90 seconds prompts the user to use text; after transcription, chit-chat like “thanks/ok” or non-questions are silently skipped without a full reply
- **Usage:** Send a Discord voice message in a target channel; voice + text caption also works
- **Note:** Bot must be able to read attachments; transcription depends on OpenAI Whisper

### 12. Stats Tracking

- **Files:** `bot/stats.py`
- **Description:** Record total queries, auto-replies, forwards, confidence, latency, etc., with time-range filters
- **Usage:** `/stats` command or Admin panel

### 13. Embedding Cache

- **Files:** `bot/cache.py`
- **Description:** LRU + TTL cache for embedding results to reduce duplicate API calls
- **Usage:** Enabled automatically

---

## 🟢 Optional Features (Enable as Needed)

### 14. Admin Web Panel

- **Files:** `bot/admin.py`
- **Description:** Browser-based admin panel for stats / config / knowledge base / FAQ
- **Config:** `ADMIN_ENABLED=true`, `ADMIN_PORT=8082`, `ADMIN_SECRET`
- **Usage:** Open `http://host:8082/admin/` in a browser

### 15. FastAPI Management API

- **Files:** `bot/api/` directory
- **Description:** RESTful API + WebSocket for stats / config / review / knowledge base / FAQ / promo management
- **Config:** `API_ENABLED=true`, `API_PORT=8090`, `API_USERNAME`, `API_PASSWORD`
- **Usage:** Admin mobile app (`app/`) manages the bot through this API

### 16. Public Client API

- **Files:** `bot/api/routes_public.py`
- **Description:** Public API for end users (chat, image analysis, FAQ, search, summaries, etc.)
- **Config:** `CLIENT_API_ENABLED=true`, `CLIENT_API_KEY`, `CLIENT_RATE_LIMIT_PER_MINUTE=20`
- **Usage:** Web client (`web-client/`) and mobile client (`app-client/`) interact via this API

### 17. Web Client

- **Files:** `web-client/` directory
- **Description:** React Web App — chat, search, summaries, FAQ, bookmarks, history
- **Usage:** `npm run dev` (dev) or `npm run build` (production)

### 18. Mobile Client

- **Files:** `app-client/` directory
- **Description:** Expo React Native App — same features as the Web client
- **Usage:** Publish to App Store / Google Play via EAS Build

### 19. Admin Mobile App

- **Files:** `app/` directory
- **Description:** Expo App for Owner remote management (review, stats, config, knowledge base)
- **Usage:** Connects through the FastAPI management API

### 20. Daily Digest

- **Files:** `bot/digest.py`
- **Description:** Daily scheduled 24-hour activity digest posted to a designated channel + DM to Owner
- **Config:** `DIGEST_ENABLED=true`, `DIGEST_HOUR=22` (UTC), `DIGEST_CHANNEL_ID`

### 21. FAQ Auto-Generation

- **Files:** `bot/faq.py`
- **Description:** Cluster high-confidence queries with GPT to auto-generate FAQ entries
- **Usage:** `/generate_faq` command or Generate FAQ button in Admin panel

### 22. Promo Scheduling System

- **Files:** `bot/scheduler.py`, `bot/commands.py`, `bot/promo_config.py`
- **Description:** Schedule promo posts / signal recaps / educational content with repeat options (hourly/daily/weekly/monthly)
- **Config:** `PROMO_ENABLED=true`, `PROMO_CHANNEL_IDS`, `SIGNAL_PRODUCT_NAME`, `SIGNAL_PRODUCT_URL`
- **Usage:** `/schedule_promo` (optional `dm_role` to also DM the opt-in notify role), `/schedule_trial`, `/schedule_lesson`

### 23. User Testimonial Collection

- **Files:** `bot/testimonials.py`
- **Description:** Auto-detect positive user messages, forward to Owner for Approve/Reject, and display approved testimonials
- **Config:** `TESTIMONIAL_DETECTION_ENABLED=true`, `TESTIMONIAL_CHANNEL_ID`
- **Usage:** `/testimonials` to view

### 24. Webhook Ingestion

- **Files:** `bot/webhook.py`
- **Description:** External systems ingest text into the knowledge base via HTTP POST
- **Config:** `WEBHOOK_ENABLED=true`, `WEBHOOK_PORT=8081`, `WEBHOOK_SECRET`

### 25. YouTube Ingestion

- **Files:** `ingestion/ingest_youtube.py`
- **Description:** Ingest YouTube video captions into ChromaDB (captions API first; if none, Whisper fallback: yt-dlp download audio → ffmpeg transcode → OpenAI Whisper)
- **Usage:** `python -m ingestion.ingest_youtube --urls "URL"`
- **Dependencies:** `pip install 'yt-dlp[default]' imageio-ffmpeg`; if system ffmpeg is missing, place `ffmpeg`/`ffprobe` (and `deno` required by newer yt-dlp) into the venv `Scripts/` or `bin/` directory. Code resolves binaries by full path and does not rely on system PATH

### 26. PDF Ingestion

- **Files:** `ingestion/ingest_pdf.py`
- **Description:** Ingest PDF documents into the knowledge base
- **Usage:** `python -m ingestion.ingest_pdf --files "file.pdf"`

### 27. Style Analysis

- **Files:** `ingestion/analyze_style.py`
- **Description:** Analyze Owner writing style and generate a style guide for RAG
- **Usage:** `python -m ingestion.analyze_style`

### 28. Scheduled Ingestion

- **Files:** `bot/ingestion_scheduler.py`
- **Description:** Background scheduled runs of ingestion and style analysis
- **Config:** `INGEST_INTERVAL_HOURS`, `STYLE_INTERVAL_HOURS`

### 29. Multilingual Support

- **Files:** `bot/config.py`
- **Description:** UI strings in Chinese (zh) and English (en)
- **Config:** `BOT_LANGUAGE=zh`

### 30. Negative Feedback Learning

- **Files:** `bot/review.py`, `bot/rag.py`
- **Description:** Owner-Rejected answers are saved as negative samples and injected into later prompts to avoid repeating mistakes
- **Usage:** Automatic; stored in `data/negative_samples.json`

---

## Slash Commands Summary

### Public Commands (All Users)

| Command | Description | Usage |
| --- | --- | --- |
| `/ask` | Ask the AI assistant (RAG knowledge base) | `/ask question:your question` |
| `/signal` | View BigTreeSignal product intro (not limited to promo channels) | `/signal` |
| `/invite` | Generate a personal invite link | `/invite` |
| `/testimonials` | Show recent user testimonials | `/testimonials` |
| `/faq` | View FAQ | `/faq` |
| `/promo_notify` | Opt in or out of promo DM notifications | `/promo_notify action:opt-in` |

### Owner-Only Commands

**Promo management:**

| Command | Description | Usage |
| --- | --- | --- |
| `/post_promo` | Post a promo immediately (optional sync DM) | `/post_promo title:title description:content dm_role:@promo-notify` |
| `/schedule_promo` | Schedule a promo (supports repeat; optional sync DM) | `/schedule_promo title:title description:desc time:time repeat:mode dm_role:@promo-notify` |
| `/dm_role` | Send promo DMs to the opt-in notify role | `/dm_role role:@promo-notify title:title description:content` |
| `/promo_notify_panel` | Post a promo DM subscription panel in a channel | `/promo_notify_panel` |
| `/list_promos` | List all scheduled promos | `/list_promos` |
| `/cancel_promo` | Cancel a scheduled promo | `/cancel_promo promo_id:ID` |
| `/schedule_trial` | Schedule a free signal recap post (supports repeat) | `/schedule_trial title:title content:content time:time repeat:mode` |

**Education management:**

| Command | Description | Usage |
| --- | --- | --- |
| `/schedule_lesson` | Schedule an educational push (supports repeat) | `/schedule_lesson title:title content:content time:time repeat:mode` |
| `/list_lessons` | List all scheduled lessons | `/list_lessons` |
| `/cancel_lesson` | Cancel a scheduled lesson | `/cancel_lesson lesson_id:ID` |
| `/resend_summary` | Resend a YouTube video GPT summary (auto-ingest if transcript missing) | `/resend_summary` or `/resend_summary video_url:link` |

**Dev / Ops:**

| Command | Description | Usage |
| --- | --- | --- |
| `/status` | Bot status (uptime, queue, knowledge base count) | `/status` |
| `/stats` | Query stats (totals, confidence, popular questions) | `/stats` |
| `/search_kb` | Search knowledge base documents | `/search_kb query:keywords top_k:count` |
| `/generate_faq` | Auto-generate FAQ from frequent questions | `/generate_faq` |
| `/weekly_summary` | Immediately generate and post this week's summary | `/weekly_summary` |
| `/daily_summary` | Immediately generate and post today's summary | `/daily_summary` |
| `/views` | [Owner] Scan owner posts across the server, briefly summarize, and post to this channel | `/views hours:24` |
| `/funnel` | View acquisition conversion funnel | `/funnel days:7` |

---

## Repeat Mode Options

Schedule commands (`/schedule_promo`, `/schedule_trial`, `/schedule_lesson`) all support these repeat modes:

| Option | Description |
| --- | --- |
| No repeat | Send once and stop (default) |
| Hourly | Automatically resend every hour |
| Daily | Automatically resend every day |
| Weekly | Automatically resend every week |
| Monthly | Automatically resend every 30 days |

---

## 🆕 Newer Features

### 31. Multilingual Auto-Detect & Reply

- **Files:** `bot/lang_detect.py`, `bot/listener.py`
- **Description:** Auto-detect user message language (zh/en/ja/ko) and instruct the LLM to reply in the same language
- **Config:** `AUTO_LANG_DETECT=true` (on by default)
- **Usage:** Users ask in any supported language; the bot answers in the same language

### 32. Knowledge Base Quality Report & /kb_report

- **Files:** `bot/commands.py`, `bot/feedback.py`, `bot/leaderboard.py`
- **Description:** Owner can view KB quality report: total docs, 30-day queries, low-confidence ratio, satisfaction, frequent questions
- **Command:** `/kb_report`

### 33. User Satisfaction Feedback (👍/👎 Reactions)

- **Files:** `bot/feedback.py`, `bot/listener.py`
- **Description:** When users add thumbs-up/down reactions to bot replies, feedback is recorded; Owner can view stats via `/satisfaction`
- **Config:** `FEEDBACK_ENABLED=true` (on by default)
- **Command:** `/satisfaction days:30`

### 34. Conversation Summary & /pin_summary

- **Files:** `bot/commands.py`
- **Description:** Owner uses `/pin_summary` to summarize recent channel discussion, generate a summary, and pin it
- **Command:** `/pin_summary count:20`

### 35. Scheduled Reminders /schedule_reminder

- **Files:** `bot/reminders.py`, `bot/scheduler.py`, `bot/commands.py`
- **Description:** Owner can schedule custom reminder messages (e.g. market open, data releases) with repeat support
- **Command:** `/schedule_reminder`, `/list_reminders`, `/cancel_reminder`

### 36. VIP Role Recognition

- **Files:** `bot/listener.py`, `bot/config.py`
- **Description:** Configure VIP role IDs; users with those roles are exempt from rate limits
- **Config:** `VIP_ROLE_IDS=roleId1,roleId2`

### 37. Keyword Monitoring & Alerts

- **Files:** `bot/keyword_alert.py`, `bot/listener.py`, `bot/commands.py`
- **Description:** Owner configures watch keywords; when a user message contains one, the bot immediately DMs the Owner
- **Config:** `KEYWORD_ALERT_ENABLED=true` (on by default)
- **Command:** `/add_alert`, `/remove_alert`, `/list_alerts`

### 38. Knowledge Base Versioning & Rollback

- **Files:** `bot/kb_versioning.py`, `bot/commands.py`
- **Description:** KB snapshot management; snapshots can be created before ingest; Owner can browse historical snapshots
- **Command:** `/kb_snapshots`

### 39. Enhanced Welcome Flow

- **Files:** `bot/welcome_flow.py`, `bot/listener.py`
- **Description:** Multi-step welcome DM for new members: immediate welcome (with `/faq` `/ask` `/signal`). If `PROMO_NOTIFY_ROLE_IDS` is configured, the same welcome DM includes “Opt in / Unsubscribe” buttons; members only join the promo DM list after clicking
- **Config:** `WELCOME_FLOW_ENABLED=true` (recommended), `WELCOME_STEP2_DELAY` replaced by drip delays: `WELCOME_VALUE_DELAY_SECONDS=14400` (value content after 4 hours), `WELCOME_CTA_DELAY_SECONDS=86400` (product CTA next day), `WELCOME_REMINDER_DELAY_SECONDS=259200` (day-3 reminder)

### 40. Leaderboard Command

- **Files:** `bot/leaderboard.py`, `bot/commands.py`
- **Description:** View most active channels, confidence distribution, and other ranked stats
- **Command:** `/leaderboard days:30`

### 41. A/B Test Reply Styles

- **Files:** `bot/ab_test.py`, `bot/commands.py`
- **Description:** When enabled, each reply randomly picks a style variant and tracks satisfaction per variant
- **Config:** `AB_TEST_ENABLED=false` (off by default), `AB_TEST_VARIANTS=casual:style_a.txt,formal:style_b.txt`
- **Command:** `/ab_results`

### 42. Export Conversations

- **Files:** `bot/export.py`, `bot/commands.py`
- **Description:** Owner can export conversation logs as JSON or CSV
- **Command:** `/export_conversations format:JSON days:30`

---

## Newer Slash Commands Quick Reference

| Command | Description | Usage |
| --- | --- | --- |
| `/schedule_reminder` | Schedule a reminder message | `/schedule_reminder title:title message:content time:2025-01-01 09:00` |
| `/list_reminders` | List all reminders | `/list_reminders` |
| `/cancel_reminder` | Cancel a reminder | `/cancel_reminder reminder_id:ID` |
| `/add_alert` | Add keyword alert | `/add_alert keyword:keyword` |
| `/remove_alert` | Remove keyword alert | `/remove_alert keyword:keyword` |
| `/list_alerts` | List monitored keywords | `/list_alerts` |
| `/kb_report` | Knowledge base quality report | `/kb_report` |
| `/kb_snapshots` | View knowledge base snapshots | `/kb_snapshots` |
| `/leaderboard` | Activity leaderboard | `/leaderboard days:30` |
| `/ab_results` | A/B test results | `/ab_results` |
| `/export_conversations` | Export conversations | `/export_conversations format:JSON days:30` |
| `/pin_summary` | Channel discussion summary | `/pin_summary count:20` |
| `/satisfaction` | Satisfaction stats | `/satisfaction days:30` |
| `/weekly_summary` | Immediately generate and post this week's summary | `/weekly_summary` |
| `/daily_summary` | Immediately generate and post today's summary | `/daily_summary` |
| `/views` | [Owner] Scan owner posts across the server, briefly summarize, and post here | `/views hours:24` |
| `/funnel` | Acquisition conversion funnel | `/funnel days:7` |
| `/invite` | Generate a personal invite link | `/invite` |
| `/promo_notify` | Opt in or out of promo DM notifications | `/promo_notify action:opt-in` |
| `/promo_notify_panel` | [Owner] Post promo DM subscription panel | `/promo_notify_panel` |
| `/dm_role` | [Owner] Send promo DMs to opt-in notify role | `/dm_role role:@promo-notify title:title description:content` |
| `/resend_summary` | [Owner] Resend YouTube video summary (auto lookup/ingest) | `/resend_summary` or `video_url:https://youtu.be/xxx` |

---

## Environment Variables Quick Reference

All settings are configured via the `.env` file; see `.env.example` for a full sample.

---

## 🚀 Advanced Enhancements

### 43. Clarification Follow-up After Auto-Reply

- **Files:** `bot/clarification.py`, `bot/listener.py`, `bot/config.py`
- **Description:** When confidence is lower but still eligible for auto-reply, ask 1 clarifying question first (e.g. timeframe / risk preference) instead of outputting a vague conclusion
- **Config:** `FEATURE_CLARIFICATION_FOLLOWUP`, `CLARIFICATION_CONFIDENCE_MAX`, `FEATURE_CLARIFICATION_CANARY_CHANNEL_IDS`

### 44. Session Memory Summary

- **Files:** `bot/session_summary.py`, `bot/listener.py`, `bot/config.py`
- **Description:** In long conversations, automatically compress older messages into a short summary while keeping the most recent turns verbatim, improving context stability and reducing token use
- **Config:** `FEATURE_SESSION_SUMMARY`, `SESSION_SUMMARY_TRIGGER_MESSAGES`, `SESSION_SUMMARY_KEEP_RECENT`, `FEATURE_SESSION_SUMMARY_CANARY_CHANNEL_IDS`

### 45. Feature Flags + Canary Channels

- **Files:** `bot/feature_flags.py`, `bot/config.py`
- **Description:** Per-channel canary rollout. If the canary list is empty, the feature is enabled everywhere; otherwise only in canary channels
- **Example:** `FEATURE_LANG_DETECT=true`, `FEATURE_LANG_DETECT_CANARY_CHANNEL_IDS=123,456`

### 46. High-Risk Answer Safety Guardrails

- **Files:** `bot/guardrails.py`, `bot/listener.py`, `bot/config.py`
- **Description:** Detect high-risk phrasing (e.g. all-in, guaranteed returns, max position / full portfolio) and either force owner review or append a risk disclaimer template
- **Config:** `FEATURE_SAFETY_GUARDRAILS`, `GUARDRAIL_MODE=force_review|disclaimer`, `GUARDRAIL_DISCLAIMER`, `FEATURE_SAFETY_GUARDRAILS_CANARY_CHANNEL_IDS`

### 47. Active Learning Loop (Feedback-to-Ingestion Pipeline)

- **Files:** `bot/feedback_learning.py`, `bot/listener.py`, `bot/review.py`, `bot/scheduler.py`
- **Description:** Automatically collect 👎 feedback and owner-edited replies into a “KB gaps queue,” and daily summarize Top 10 missing questions
- **Config:** `FEATURE_FEEDBACK_LEARNING`, `FEATURE_FEEDBACK_LEARNING_CANARY_CHANNEL_IDS`

### 48. SLA / Reliability Monitoring

- **Files:** `bot/reliability.py`, `bot/rag.py`, `bot/scheduler.py`, `bot/config.py`
- **Description:** Monitor p95 latency, OpenAI error rate, review queue backlog, scheduler tick lag; alert the owner when thresholds are exceeded
- **Config:** `FEATURE_SLA_MONITORING`, `SLA_P95_LATENCY_MS_THRESHOLD`, `SLA_OPENAI_ERROR_RATE_THRESHOLD`, `SLA_REVIEW_QUEUE_BACKLOG_THRESHOLD`, `SLA_SCHEDULER_MISS_SECONDS`, `SLA_ALERT_COOLDOWN_SECONDS`

### 49. Jin10 Market Flash News Feed

- **Files:** `bot/news_feed.py`, `bot/config.py`
- **Description:** Poll Jin10 Flash API every 30 seconds and push important market flashes (e.g. central bank decisions, NFP, breaking events) to designated Discord channels. Important flashes use Embed rich format; normal flashes are plain text. Supports dedupe, ad filtering, multi-channel push. On bot reconnect, backfills important flashes missed while offline (default last 24 hours, max 50). `last_id` advances only after a successful post to avoid gaps
- **Config:** `NEWS_FEED_ENABLED=true`, `NEWS_CHANNEL_IDS=channelId1,channelId2`, `NEWS_POLL_INTERVAL_SECONDS=30`, `NEWS_IMPORTANT_ONLY=true`, `NEWS_BACKFILL_HOURS=24` (if offline longer than 24 hours or more than 50 important flashes, older ones are not backfilled)

### 50. Weekly Summary

- **Files:** `bot/weekly_summary.py`, `bot/config.py`
- **Description:** On a configurable weekday at a configured ET time, collect all owner messages and owner replies from designated channels for the week, generate a key summary with GPT, post as Embed to designated channels and @everyone. Reply messages automatically pull the original question as context. Supports multi-channel scan and multi-channel publish. **Reliability:** channel read / network failures are no longer misclassified as “no messages this week”; retries every 30 minutes after failure; still runs within 18 hours if the scheduled time was missed; sleep uses chunked timing to reduce overslept schedules after PC sleep
- **Config:** `WEEKLY_SUMMARY_ENABLED=true`, `WEEKLY_SUMMARY_CHANNELS=channelId1,channelId2` (scan sources), `WEEKLY_SUMMARY_DAY=5` (0=Mon, 5=Sat), `WEEKLY_SUMMARY_HOUR=20` (ET), `WEEKLY_SUMMARY_MINUTE=5`, `WEEKLY_SUMMARY_POST_CHANNELS=channelId` (publish targets; empty falls back to SUMMARY_CHANNELS)
- **Command:** `/weekly_summary` (Owner manual trigger; can immediately resend last week's missed summary)

### 51. Promo Auto-Scheduling (Promo Monitor)

- **Files:** `bot/promo_monitor.py`, `bot/scheduler.py`, `bot/config.py`
- **Description:** When Owner posts promo info in a designated source channel, the bot automatically cancels old promo schedules, creates a new daily-repeat `schedule_promo` with `@everyone`, pushes to target channels at a configured time (default 4 PM ET), valid for 3 months (configurable). Auto-cancels on expiry. Image attachments are automatically embedded
- **Config:** `PROMO_MONITOR_ENABLED=true`, `PROMO_SOURCE_CHANNEL_ID=channelId`, `PROMO_PUSH_HOUR=16`, `PROMO_DURATION_DAYS=90`, `PROMO_PUSH_CHANNELS=channelId1,channelId2`

### 52. YouTube New Video Auto-Push (YouTube Monitor)

- **Files:** `bot/youtube_monitor.py`, `bot/config.py`
- **Description:** Daily at a configured time, poll the YouTube channel RSS feed; on new video, cancel old YouTube lesson schedules and create a new daily-repeat `schedule_lesson` pushed to Discord channels at a configured time (default 4 PM ET). Push includes title and watch link. If auto-ingest is on, captions/Whisper transcript go into the KB and a GPT summary is pushed to `YOUTUBE_SUMMARY_CHANNELS`. If transcription fails, a “new video notice” Embed is still sent; already-recorded videos need `/resend_summary` to resend the summary (see item 56)
- **Config:** `YOUTUBE_MONITOR_ENABLED=true`, `YOUTUBE_CHANNEL_ID=UCxxxxxxxxxx`, `YOUTUBE_CHECK_HOUR=11`, `YOUTUBE_CHECK_MINUTE=05`, `YOUTUBE_LESSON_PUSH_HOUR=16`, `YOUTUBE_LESSON_PUSH_CHANNELS=channelId1,channelId2`, `YOUTUBE_AUTO_INGEST=true`, `YOUTUBE_SUMMARY_CHANNELS=channelId`

### 53. Daily Summary

- **Files:** `bot/daily_summary.py`, `bot/config.py`
- **Description:** On each workday (Mon–Fri, configurable) at a configured time, collect that day's owner messages and replies, generate today's key summary with GPT, post as Embed to designated channels and @everyone. Fully independent from Weekly Summary. Posts once per day: if the timer fires early (e.g. 15:59) and already sent, it will not send again in the same minute
- **Config:** `DAILY_SUMMARY_ENABLED=true`, `DAILY_SUMMARY_CHANNELS=channelId1,channelId2` (scan sources), `DAILY_SUMMARY_DAYS=0,1,2,3,4` (0=Mon..6=Sun, default Mon–Fri), `DAILY_SUMMARY_HOUR=16` (ET), `DAILY_SUMMARY_MINUTE=0`, `DAILY_SUMMARY_POST_CHANNELS=channelId` (publish targets; empty falls back to DAILY_SUMMARY_CHANNELS)
- **Command:** `/daily_summary` (Owner manual trigger)

### 54. Auto Moderation

- **Files:** `bot/auto_mod.py`, `bot/ban_words.py`, `bot/config.py`
- **Description:** Automatically detect and delete spam, scam, and ads. Supports 7 detection layers:
  1. **Keyword matching** — zh/en spam/scam/ad phrases (free signals, guaranteed profit, etc.)
  2. **Ban-word list (exact match)** — Owner can dynamically add ban words via `/add_ban_word`; messages containing them are deleted
  3. **Ban-word list (semantic match)** — OpenAI embeddings for semantic similarity; different wording of the same meaning is still blocked (threshold configurable, default 0.82)
  4. **External platform links** — Telegram, WhatsApp, Line, short links, etc.
  5. **Discord invite links** — discord.gg links from non-exempt users
  6. **Mass @ mentions / link spam** — blocked above threshold
  7. **Duplicate spam** — same user repeating the same content in a short window
- **Ban-word management commands:**
  - `/add_ban_word <word>` — add a ban word (auto-computes embedding for semantic match)
  - `/remove_ban_word <word>` — remove a ban word
  - `/list_ban_words` — list all ban words
- **Exemptions:** Owner (`OWNER_USER_ID`), Bot, and designated roles (`AUTO_MOD_EXEMPT_ROLE_IDS`) are exempt
- **Logging:** Deletes are logged as Embeds to a designated log channel (author, channel, reason, content preview), and Owner is DMed (deleted content + sender Discord ID)
- **Config:** `AUTO_MOD_ENABLED=true`, `AUTO_MOD_LOG_CHANNEL_ID=channelId`, `AUTO_MOD_EXEMPT_ROLE_IDS=roleId1,roleId2`, `AUTO_MOD_MAX_MENTIONS=8`, `AUTO_MOD_MAX_LINKS=5`, `AUTO_MOD_DUP_WINDOW=60` (seconds), `AUTO_MOD_DUP_THRESHOLD=3`, `AUTO_MOD_BAN_WORDS_FILE=data/ban_words.json`, `AUTO_MOD_BAN_WORDS_SIMILARITY=0.82`
- **Permission required:** Bot needs `Manage Messages`
- **Persistence:** Ban-word list stored in `data/ban_words.json` with words and embeddings; loaded automatically on restart

### 55. Channel Topic Guard

- **Files:** `bot/topic_guard.py`, `bot/auto_mod.py`, `bot/config.py`
- **Description:** Enforce topic limits on designated channels — only allow investment-related discussion (trading, signals, stocks, FX, crypto, technical analysis, etc.). Chit-chat, nonsense, and offensive posts are auto-deleted
- **Classification:** GPT-4o-mini classifies each message as `on_topic` (allow), `off_topic` (delete), or `offensive` (delete); results cached 5 minutes to avoid duplicate API calls
- **Pre-filter:** Pure emoji or 1–2 character messages are treated as off_topic without calling GPT
- **Fault tolerance:** On GPT failure, default to allow (on_topic) to avoid false deletes
- **Exemptions:** Owner, Bot, and designated roles are exempt (inherits Auto Moderation exemptions)
- **Config:** `TOPIC_RESTRICTED_CHANNEL_IDS=channelId1,channelId2` (empty = disabled)
- **Relation to Auto Mod:** Topic Guard is the final Auto Moderation layer — after site-wide spam/ban-word filters, restricted channels get a topic check

### 56. Resend YouTube Summary

- **Files:** `bot/youtube_monitor.py`, `scripts/resend_youtube_summary.py`, `ingestion/ingest_youtube.py`
- **Command:** `/resend_summary`
- **Description:** Owner uses a slash command to resend a YouTube video GPT summary to `YOUTUBE_SUMMARY_CHANNELS`. Auto-checks ChromaDB: if transcript exists, summarize directly; if not, Whisper ingest then summarize; if still failing, generate a teaser summary from the title (gold Embed + footer note). Progress updates on the same ephemeral message; send failures are not reported as success. Only one resend job at a time. Works even when Monitor is off. `scripts/resend_youtube_summary.py` is a CLI backup (ingested videos only)
- **Config:** `YOUTUBE_SUMMARY_CHANNELS=channelId`, `OPENAI_API_KEY`, `LLM_MODEL`, `OWNER_USER_ID`
- **Whisper dependencies (required when no captions):** `pip install 'yt-dlp[default]' imageio-ffmpeg`; on Windows, place `ffmpeg.exe`, `ffprobe.exe`, `deno.exe` in `.venv/Scripts/` (newer yt-dlp needs a JS runtime to download YouTube)
- **Usage (Slash command):**
  ```
  /resend_summary                                    — resend the most recently detected video
  /resend_summary video_url:https://youtu.be/xxxxx   — resend a specific video
  /resend_summary video_url:... title:custom title   — override title
  ```
- **Usage (script backup):**
  ```
  python scripts/resend_youtube_summary.py
  python scripts/resend_youtube_summary.py --video-id nTWo8Wv7Jao
  python scripts/resend_youtube_summary.py --video-id nTWo8Wv7Jao --dry-run
  ```
- **Flow:** ChromaDB has transcript → summarize directly; not ingested → auto Whisper ingest → summarize; transcription fails → teaser summary from title → post to summary channels (with acquisition CTA buttons; see item 59)

### 57. Purchase Intent Auto-Conversion

- **Files:** `bot/acquisition.py`, `bot/listener.py`
- **Description:** When users ask about subscription, price, trial, VIP, or how to buy, the bot skips normal RAG and immediately replies with a product Embed + CTA buttons (Learn product / Request trial / View FAQ), and DMs the Owner. Optionally assigns an “Inquiring” role for follow-up
- **Config:** `INTENT_CONVERT_ENABLED=true`, `INTENT_NOTIFY_OWNER=true`, `INTENT_LEAD_ROLE_ID=roleId` (0 = do not assign role), `SIGNAL_PRODUCT_URL`, `FREE_TRIAL_ENABLED`, `FREE_TRIAL_URL`
- **Usage:** Automatic. Placeholder links (e.g. `your-product-url.com`) will not generate buttons — replace with real URLs

### 58. New-Member 24–72 Hour Conversion Drip

- **Files:** `bot/welcome_flow.py`, `bot/acquisition.py`, `bot/acquisition_cog.py`
- **Description:** Immediate welcome DM after join (with `/faq` `/ask` `/signal`). If `PROMO_NOTIFY_ROLE_IDS` is set, welcome DM includes Opt in / Unsubscribe buttons. Then delayed sends: latest daily/video summary (prove value) → product CTA + testimonials → light day-3 reminder. Tasks persist in `data/welcome_drip.json` across restarts. VIP role holders stop further drip
- **Config:** `WELCOME_FLOW_ENABLED=true`, `WELCOME_VALUE_DELAY_SECONDS=14400` (4 hours), `WELCOME_CTA_DELAY_SECONDS=86400` (next day), `WELCOME_REMINDER_DELAY_SECONDS=259200` (day 3)
- **Usage:** With `WELCOME_FLOW_ENABLED` on, runs for every new member. Delays are in seconds from join time

### 59. YouTube Summary Conversion Buttons

- **Files:** `bot/youtube_monitor.py`, `bot/acquisition.py`, `scripts/resend_youtube_summary.py`
- **Description:** Video summary Embeds include bottom buttons “Learn BigTreeSignal / Request trial / View FAQ,” so educational content also acquires leads. Auto-push and `/resend_summary` (plus the resend script) all include these buttons
- **Config:** `SIGNAL_PRODUCT_URL`, `FREE_TRIAL_ENABLED`, `FREE_TRIAL_URL`, `YOUTUBE_SUMMARY_CHANNELS`
- **Usage:** Sent with summaries after new-video auto-ingest; resend see item 56

### 60. Invite Virality / Personal Invite Links

- **Files:** `bot/acquisition.py`, `bot/acquisition_cog.py`, `bot/commands.py`
- **Description:** Members use `/invite` to create a personal Discord invite. On join, the bot compares invite use counts and records the inviter. Reaching a threshold can auto-grant a reward role. Requires create/view invite permissions and Server Members Intent
- **Config:** `INVITE_TRACKING_ENABLED=true`, `INVITE_REWARD_THRESHOLD=3`, `INVITE_REWARD_ROLE_ID=roleId` (0 = no reward role)
- **Command:** `/invite`
- **Usage:** Members run `/invite` in any server channel and get an ephemeral personal link

### 61. Conversion Funnel Dashboard

- **Files:** `bot/acquisition.py`, `bot/commands.py`
- **Description:** Track joins, welcome DM success/denied, `/signal` uses, purchase-intent hits, CTA sends, invite joins. Data in `data/funnel.json`
- **Command:** `/funnel days:7` (Owner)
- **Usage:** Owner privately views last N days (1–90) funnel plus all-time totals. `/signal` is public and not limited to `PROMO_CHANNEL_IDS`

### 62. Opt-In Notify Role Promo DMs

- **Files:** `bot/role_dm.py`, `bot/commands.py`, `bot/scheduler.py`, `bot/welcome_flow.py`
- **Description:** Only send promo DMs to members who **voluntarily opted into** a notify role. Do not mass-DM manually tagged ops/interest roles (Discord treats unsolicited bulk DMs as spam). Roles outside the whitelist are rejected by the command.
- **Config:** `PROMO_NOTIFY_ROLE_IDS` (opt-in “promo notify” role IDs, comma-separated), `PROMO_DM_DELAY_SECONDS=1.2`, `PROMO_DM_MAX_RECIPIENTS=200`
- **Usage:**
  1. Create a “Promo Notify” role in Discord (no admin permissions), put its ID in `PROMO_NOTIFY_ROLE_IDS`; Bot role must be above it and have Manage Roles
  2. Owner runs `/promo_notify_panel` in an announcement channel (pin recommended); members click “Opt in” to join the list
  3. On join, welcome DM also includes the same Opt in / Unsubscribe buttons (requires `WELCOME_FLOW_ENABLED=true`)
  4. Send promos: `/dm_role` for DMs only (confirm recipient count first); or `/post_promo` / `/schedule_promo` with optional `dm_role` to sync DMs
  5. Unsubscribe only removes the notify role; existing ops tags are untouched. Sends exceeding `PROMO_DM_MAX_RECIPIENTS` are rejected
- **Commands:** `/promo_notify_panel`, `/promo_notify`, `/dm_role`; `dm_role` param on `/post_promo` and `/schedule_promo`
- **Activation & subscription playbook:** [`GROWTH_PLAYBOOK.md`](../growth/GROWTH_PLAYBOOK.md)

### 63. Owner Views Summary (/views)

- **Files:** `bot/commands.py`, `bot/views_summary.py`, `bot/weekly_summary.py`, `bot/listener.py`
- **Description:** Owner runs `/views` in a server text channel or thread; the bot scans **the whole server** for your recent posts, uses GPT to generate a **short, clear** key-points summary (about ≤1200 characters, at most 3 subheadings), and publicly posts it in the current channel without @everyone. Collection scope:
  - All server text channels / forum posts / public threads: your posts, plus replies to members (reply targets anonymized as “member,” no nicknames)
  - Private threads / bot-visible group DMs you participated in: primarily your posts; counterparts keep only very short anonymous context — public summary does not name anyone or paste originals
  - Discord **does not allow** bots to read 1:1 DMs between you and members; to include 1:1 conversations, open a private server thread visible to the bot
  - Each channel pages newest→oldest until the time window ends, counting by **owner message count** so busy channels do not crowd out your posts
  - Excluded channels (`EXCLUDED_CHANNEL_IDS`) and promo source channel (`PROMO_SOURCE_CHANNEL_ID`) are not scanned
- **Usage:** `/views` (default last 24 hours); `/views hours:48` (1–168 hours). Owner only; server text channels/threads only
- **Command:** `/views hours:24`
- **Note:** Unlike `/daily_summary` and `/pin_summary`: summarizes only the channel owner's views and posts immediately in the command channel
