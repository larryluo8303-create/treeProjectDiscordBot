> **Archived**: Historical design/phase guide for reference only. See living docs under architecture/features/getting-started for current guidance.

# BigTreeSignal Promotion System — Design Document

---

## Table of Contents

- [1. Background & Goals](#1-background--goals)
- [2. System Architecture](#2-system-architecture)
- [3. Module Design](#3-module-design)
  - [3.1 Configuration Layer](#31-configuration-layer)
  - [3.2 Promotion Helpers promo_config.py](#32-promotion-helpers-promo_configpy)
  - [3.3 Slash Commands commands.py](#33-slash-commands-commandspy)
  - [3.4 Scheduled Posts scheduler.py](#34-scheduled-posts-schedulerpy)
  - [3.5 User Testimonials testimonials.py](#35-user-testimonials-testimonialspy)
  - [3.6 Listener Extensions listener.py](#36-listener-extensions-listenerpy)
- [4. Data Models](#4-data-models)
- [5. Channel Isolation Design](#5-channel-isolation-design)
- [6. Feature Checklist](#6-feature-checklist)
- [7. File Change List](#7-file-change-list)
- [8. Security & Compliance](#8-security--compliance)

---

## 1. Background & Goals

### Background

The existing Discord bot already has core capabilities such as RAG auto-replies, owner review, and signal-query routing. The channel owner operates the **BigTreeSignal** signal product (covering US stocks, ETFs, and crypto) and needs to use the bot’s high-quality answers to build user trust, then naturally guide users toward the paid signal product at the right moments.

### Goals

1. **Natural guidance**: When users ask signal-related questions, automatically show product information
2. **Scheduled promotion**: Support promo scheduling, free-signal recaps, and educational content pushes
3. **Community growth**: New-member welcome + collection and display of user testimonials
4. **Channel isolation**: All promotional behavior is limited to channels in `PROMO_CHANNEL_IDS`, without affecting other channels
5. **Flexible configuration**: All URLs, copy, and frequencies are configurable via `.env`, with a one-switch master toggle

---

## 2. System Architecture

```
User message
    │
    ▼
┌──────────────────────────────────────────────┐
│  listener.py (MessageListener Cog)           │
│  ┌─────────────────────────────────────────┐ │
│  │ Signal query detection (is_signal_query) │ │
│  │   → Promo channel? → Send CTA Embed     │ │
│  ├─────────────────────────────────────────┤ │
│  │ Auto-reply (auto_reply)                  │ │
│  │   → Promo channel? → Append CTA every N  │ │
│  ├─────────────────────────────────────────┤ │
│  │ Testimonial detection (_TESTIMONIAL_PATTERNS) │
│  │   → Promo channel? → collect_testimonial()│ │
│  ├─────────────────────────────────────────┤ │
│  │ on_member_join                           │ │
│  │   → Guild has promo channel? → Welcome DM│ │
│  └─────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│  commands.py (PromotionCommands Cog)         │
│  /signal        — Product showcase            │
│  /post_promo    — Post promo immediately      │
│  /schedule_promo — Schedule promo             │
│  /schedule_trial — Schedule signal recap      │
│  /schedule_lesson — Schedule lesson           │
│  /list_promos / /cancel_promo                │
│  /list_lessons / /cancel_lesson              │
│  /testimonials  — Show user testimonials      │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│  scheduler.py (SchedulerCog)                 │
│  Check every 60 seconds:                      │
│  ├─ data/promos.json  → auto-post when due    │
│  └─ data/lessons.json → auto-post when due    │
│     └─ Supports daily / weekly repeat         │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│  testimonials.py                             │
│  collect → DM Owner review → forward #user-wins │
│  data/testimonials.json                      │
└──────────────────────────────────────────────┘
```

---

## 3. Module Design

### 3.1 Configuration Layer

The following environment variables are added in `bot/config.py`:

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `PROMO_ENABLED` | bool | `true` | Master switch; when off, all promo features are disabled |
| `PROMO_CHANNEL_IDS` | list[int] | `[]` | Promo channel ID list (comma-separated) |
| `SIGNAL_PRODUCT_NAME` | str | `BigTreeSignal` | Product name |
| `SIGNAL_PRODUCT_URL` | str | `""` | Product URL |
| `SIGNAL_CTA_TEXT` | str | `Want live trading signals? Learn about BigTreeSignal` | Signal-query CTA copy |
| `AUTO_REPLY_CTA_TEXT` | str | `Want live trading signals? Learn about BigTreeSignal →` | Auto-reply CTA copy |
| `CTA_FREQUENCY` | int | `5` | Append CTA once every N auto-replies |
| `FREE_TRIAL_ENABLED` | bool | `false` | Whether to show free-trial entry |
| `FREE_TRIAL_URL` | str | `""` | Free-trial URL |
| `WELCOME_MESSAGE` | str | `Welcome!...` | New-member welcome copy |
| `TESTIMONIAL_CHANNEL_ID` | int | `0` | `#user-wins` channel ID |
| `TESTIMONIAL_DETECTION_ENABLED` | bool | `true` | Whether to auto-detect testimonials |

**Design principle:** `PROMO_CHANNEL_IDS` is independent of `TARGET_CHANNEL_IDS`. The bot can answer in channel A without promoting, and both answer and promote in channel B, depending on the intersection of the two lists.

### 3.2 Promotion Helpers `promo_config.py`

A pure-function module with no held state. Helpers:

| Function | Purpose |
|----------|---------|
| `is_promo_channel(channel_id)` | Whether the channel is in the promo list |
| `get_signal_cta_embed()` | Build the CTA Embed for signal queries |
| `get_auto_reply_cta()` | Build the trailing CTA text for auto-replies |
| `should_append_cta(counter)` | Whether to append based on `CTA_FREQUENCY` |
| `get_welcome_embed(member)` | Build the new-member welcome Embed |
| `get_signal_product_embed()` | Build the detailed product Embed for `/signal` |

### 3.3 Slash Commands `commands.py`

Registered as the `PromotionCommands` Cog with 10 slash commands.

**Permissions:** Scheduling commands (schedule/cancel/list/post) are Owner-only (`OWNER_USER_ID`). `/signal` and `/testimonials` are available to all users but limited to promo channels.

**Time input:** Unified `YYYY-MM-DD HH:MM` format, parsed as UTC-4 (ET).

### 3.4 Scheduled Posts `scheduler.py`

- Background polling via `discord.ext.tasks.loop(seconds=60)`
- Persistence in `data/promos.json` and `data/lessons.json`
- Atomic writes via `.tmp` + `os.replace` to avoid corruption on interrupted writes
- Promos support `promo` and `trial_signal` types with different Embed styles
- Lessons support `none` (one-shot), `daily`, and `weekly` repeat modes

### 3.5 User Testimonials `testimonials.py`

**Detect → Review → Forward** three-step flow:

1. Regex match on profit/praise keywords via `_TESTIMONIAL_PATTERNS` in `listener.py`
2. On match, call `collect_testimonial()`: persist to JSON + DM Owner
3. Owner clicks Approve → Embed forwarded to `TESTIMONIAL_CHANNEL_ID`
4. Owner clicks Reject → marked rejected, not forwarded

**Dedup:** Deduplicate by `message.id`; the same message is collected only once.

### 3.6 Listener Extensions `listener.py`

Added on top of the existing `MessageListener` Cog:

| Feature | Trigger | Behavior |
|---------|---------|----------|
| Signal CTA | signal query + promo channel + forward_to_owner | Post CTA Embed in channel |
| Auto-reply CTA | auto_reply + promo channel + counter hit | Append CTA text to reply |
| Testimonial detection | non-bot/owner + promo channel + regex match | Call `collect_testimonial` |
| New-member welcome | on_member_join + guild has promo channel + non-bot | Send welcome DM |

---

## 4. Data Models

### `data/promos.json`

```json
[
  {
    "id": "promo_a1b2c3d4",
    "type": "promo",
    "title": "New Year 30% Off",
    "description": "BigTreeSignal New Year special — 30% off subscriptions",
    "url": "https://...",
    "scheduled_at": "2024-01-15T10:00:00-04:00",
    "channel_ids": [123456789, 987654321],
    "posted": false,
    "cancelled": false,
    "created_by": 111222333,
    "posted_at": null
  }
]
```

### `data/lessons.json`

```json
[
  {
    "id": "lesson_e5f6g7h8",
    "title": "Three Buy Points Intro",
    "content": "Today we cover the basics of Chan Theory's three buy points...",
    "scheduled_at": "2024-01-16T09:00:00-04:00",
    "repeat": "weekly",
    "channel_ids": [123456789],
    "last_posted": null,
    "cancelled": false,
    "created_by": 111222333
  }
]
```

### `data/testimonials.json`

```json
[
  {
    "id": "test_i9j0k1l2",
    "message_id": "1234567890",
    "channel_id": "123456789",
    "author_id": "111222333",
    "author_name": "TraderWang",
    "content": "Made solid gains following the signals — thanks BigTree!",
    "timestamp": "2024-01-15T14:30:00+00:00",
    "status": "approved",
    "jump_url": "https://discord.com/channels/...",
    "reviewed_at": "2024-01-15T15:00:00+00:00"
  }
]
```

---

## 5. Channel Isolation Design

```
                      TARGET_CHANNEL_IDS          PROMO_CHANNEL_IDS
                    (channels where bot answers) (channels with promo behavior)
                    ┌───────────────────┐      ┌──────────────────┐
#general-chat       │        ✅          │      │        ❌         │
#stock-analysis     │        ✅          │      │        ✅         │
#signal-promo       │        ❌          │      │        ✅         │
#random             │        ❌          │      │        ❌         │
                    └───────────────────┘      └──────────────────┘

#general-chat:    Bot answers questions, no promotion
#stock-analysis:  Bot answers + promo CTA + testimonial detection
#signal-promo:    No Q&A answers; accepts /signal and other promo commands only
#random:          Bot does not participate at all
```

---

## 6. Feature Checklist

| # | Feature | Phase | Trigger | Promo channels only |
|---|---------|-------|---------|---------------------|
| 1 | Signal-query CTA | Phase 1 | Auto (signal query detected) | ✅ |
| 2 | Auto-reply trailing CTA | Phase 1 | Auto (every N replies) | ✅ |
| 3 | `/signal` product showcase | Phase 2 | User runs command | ✅ |
| 4 | New-member welcome DM | Phase 2 | Auto (on_member_join) | ✅ (guild-level) |
| 5 | `/post_promo` post immediately | Phase 3 | Owner runs command | ✅ |
| 6 | `/schedule_promo` schedule promo | Phase 3 | Owner runs command | ✅ |
| 7 | `/schedule_trial` signal recap | Phase 3 | Owner runs command | ✅ |
| 8 | `/schedule_lesson` lesson push | Phase 3 | Owner runs command | ✅ |
| 9 | Testimonial collect & review | Phase 3 | Auto detect + Owner review | ✅ |
| 10 | `/testimonials` show praise | Phase 3 | User runs command | ✅ |

---

## 7. File Change List

### New Files

| File | Lines | Description |
|------|-------|-------------|
| `bot/promo_config.py` | ~150 | Promotion helper functions |
| `bot/commands.py` | ~340 | 10 slash commands |
| `bot/scheduler.py` | ~260 | Scheduler Cog + CRUD |
| `bot/testimonials.py` | ~240 | Testimonial collection + review UI |

### Modified Files

| File | Changes |
|------|---------|
| `bot/config.py` | +13 env vars |
| `bot/listener.py` | +CTA logic / testimonial detection / on_member_join (~60 lines) |
| `bot/main.py` | +register 2 Cogs / sync slash commands |
| `.env.example` | +14 lines of promo config examples |

---

## 8. Security & Compliance

| Mechanism | Description |
|-----------|-------------|
| Channel isolation | All promo behavior strictly limited to `PROMO_CHANNEL_IDS` |
| Owner permissions | Schedule/post/cancel commands are Owner-only |
| Master switch | `PROMO_ENABLED=false` disables all promotion at once |
| Testimonial review | Testimonials must be Owner-approved before forwarding |
| Dedup | Testimonials deduped by `message_id`; schedules use `posted` flag to prevent re-send |
| Atomic writes | JSON files use `.tmp` + `os.replace` to prevent corruption |
| CTA frequency control | Auto-reply CTAs gated by `CTA_FREQUENCY` to avoid over-promotion |
