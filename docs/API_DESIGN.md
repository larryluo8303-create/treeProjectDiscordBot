# BigTree Bot — API & Mobile App Design Document

> **Version:** 1.0.0
> **Last updated:** 2026-08-13

---

## 1. Overview

The BigTree Bot Management Platform extends the existing Discord RAG Bot with:

1. **FastAPI Backend API** (`bot/api/`) — a REST + WebSocket API running in-process alongside the Discord bot, providing programmatic access to bot stats, configuration, knowledge base, review queue, promotions, lessons, and FAQ.
2. **Expo React Native + Web Frontend** (`app/`) — a cross-platform mobile (iOS/Android) and web management console that consumes the API.
3. **Public Client Apps** (`app-client/` + `web-client/`) — end-user-facing mobile and web clients for chat, digest, search, events, FAQ, bookmarks, history, and lesson archive. See [`CLIENT_DESIGN.md`](./CLIENT_DESIGN.md) and [`CLIENT_USER_GUIDE.md`](./CLIENT_USER_GUIDE.md).

Both layers share the same data as the Discord bot (ChromaDB, JSON files, in-memory state) because the API server runs inside the same Python process.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      main.py                            │
│                                                         │
│   ┌──────────────┐    ┌──────────────────────────────┐  │
│   │ Discord Bot   │    │ FastAPI Server (uvicorn)     │  │
│   │ (discord.py)  │    │   ┌─ /api/auth   (JWT)      │  │
│   │               │    │   ├─ /api/stats              │  │
│   │  listener.py ─┼────┼─► ├─ /api/config             │  │
│   │  review.py    │    │   ├─ /api/digest             │  │
│   │  commands.py  │    │   ├─ /api/kb                 │  │
│   │  ...          │    │   ├─ /api/review             │  │
│   │               │    │   ├─ /api/faq                │  │
│   │               │    │   ├─ /api/promos             │  │
│   │               │    │   ├─ /api/lessons            │  │
│   │               │    │   ├─ /api/ws     (WebSocket) │  │
│   │               │    │   └─ /api/health             │  │
│   └──────────────┘    └──────────────────────────────┘  │
│           │                        │                     │
│      Shared state:  ChromaDB, bot_stats, review_queue,  │
│      config module, JSON files (promos, lessons, faq)   │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
        ┌────────────────────────────┐
        │  Expo App (React Native)   │
        │  ┌──────────────────────┐  │
        │  │ Axios + JWT Token    │  │
        │  │ TanStack React Query │  │
        │  │ WebSocket Manager    │  │
        │  └──────────────────────┘  │
        │  Screens:                  │
        │   Login → (tabs)           │
        │    ├─ Dashboard            │
        │    ├─ Review               │
        │    ├─ KB Search            │
        │    ├─ Config               │
        │    └─ More (FAQ, Logout)   │
        └────────────────────────────┘
```

---

## 3. Backend Design

### 3.1 Dependency Injection

The API server runs as an asyncio task inside `main.py`. Before starting, `main.py` calls `server.set_dependencies(collection, openai_client, bot)` to inject the shared ChromaDB collection, OpenAI client, and Discord bot instance. Route handlers access these via `server.get_collection()`, `server.get_openai_client()`, `server.get_bot()`.

### 3.2 Authentication

| Item | Detail |
|---|---|
| **Scheme** | OAuth2 Password Bearer (JWT) |
| **Login** | `POST /api/auth/login` with `username` + `password` form data |
| **Token** | JWT signed with `API_SECRET_KEY`, contains `sub` (username) and `exp` |
| **Expiry** | Configurable via `API_TOKEN_EXPIRE_MINUTES` (default 1440 = 24h) |
| **Enforcement** | All routes except `/api/health` and `/api/auth/login` require `Authorization: Bearer <token>` |

Password is verified against the bcrypt hash of `API_PASSWORD` from `.env`.

### 3.3 WebSocket

- **Endpoint:** `GET /api/ws?token=<jwt>`
- **Auth:** JWT is validated from the `token` query parameter.
- **Events pushed by the server:**
  - `review_request` — new message forwarded for review
  - `review_resolved` — item approved/edited/rejected
  - `config_changed` — runtime config updated via API
  - `new_query` — new query processed by the bot
- **Client behavior:** The frontend `WSManager` auto-reconnects on disconnect (5s backoff) and invalidates relevant TanStack Query caches on each event type.

### 3.4 API Endpoints Reference

All endpoints return JSON. Auth-protected endpoints return `401` if no/invalid token.

#### Health (no auth)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Server status, uptime, timestamp |

#### Authentication

| Method | Path | Body | Description |
|---|---|---|---|
| `POST` | `/api/auth/login` | `username`, `password` (form) | Returns `{ access_token, token_type, expires_in }` |

#### Statistics

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/stats` | Bot stats snapshot: total queries, auto replies, avg confidence, avg latency, uptime, recent queries list |

#### Configuration

| Method | Path | Body | Description |
|---|---|---|---|
| `GET` | `/api/config` | — | Full config snapshot (models, thresholds, channels, etc.) |
| `PATCH` | `/api/config` | JSON with optional fields | Update runtime config. Fields: `confidence_threshold`, `respond_mode`, `user_cooldown_seconds`, `global_max_per_minute`, `thread_auto_reply`, `thread_context_messages`, `conversation_memory_size`, `conversation_memory_ttl`. Broadcasts `config_changed` WS event. |

#### Digest

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/digest` | 24-hour activity digest: query count, auto-reply count, avg confidence, top channels, recent queries |

#### Knowledge Base

| Method | Path | Query Params | Description |
|---|---|---|---|
| `GET` | `/api/kb` | — | Document count + sample documents |
| `GET` | `/api/kb/search` | `q` (required), `top_k` (default 5) | Semantic search using `retrieve_context`. Returns `{ query, count, results: [{ text, distance, metadata }] }` |

#### Review Queue

| Method | Path | Body | Description |
|---|---|---|---|
| `GET` | `/api/review/pending` | — | List pending review items |
| `GET` | `/api/review/all` | `?limit=50` | List all items (any status) |
| `GET` | `/api/review/{item_id}` | — | Get single review item |
| `POST` | `/api/review/{item_id}/approve` | — | Approve: posts answer to Discord, auto-learns Q&A to ChromaDB |
| `POST` | `/api/review/{item_id}/edit` | `{ "answer": "..." }` | Edit: posts edited answer, learns edited Q&A, stores original as negative sample |
| `POST` | `/api/review/{item_id}/reject` | — | Reject: stores Q&A as negative sample |

Each action broadcasts a `review_resolved` WebSocket event.

**Review Item schema:**
```json
{
  "id": "uuid",
  "channel_id": 123456,
  "channel_name": "general",
  "message_id": 789012,
  "author_name": "User",
  "author_id": 345678,
  "question": "What is X?",
  "draft_answer": "X is...",
  "confidence": 6,
  "context_snippets": [{ "text": "...", "score": 0.85, "metadata": {} }],
  "status": "pending",
  "final_answer": null,
  "created_at": 1691234567.89,
  "resolved_at": null
}
```

#### FAQ

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/faq` | Cached FAQ items `{ items: [{ question, answer }] }` |
| `POST` | `/api/faq/generate` | Regenerate FAQ from recent high-confidence queries via GPT |

#### Promotions

| Method | Path | Body | Description |
|---|---|---|---|
| `GET` | `/api/promos` | — | List scheduled promos |
| `POST` | `/api/promos` | `{ title, description, scheduled_at, channel_ids?, url? }` | Create promo |
| `DELETE` | `/api/promos/{id}` | — | Cancel promo |

#### Lessons

| Method | Path | Body | Description |
|---|---|---|---|
| `GET` | `/api/lessons` | — | List scheduled lessons |
| `POST` | `/api/lessons` | `{ title, content, scheduled_at, channel_ids?, repeat? }` | Create lesson (`repeat`: `none`, `daily`, `weekly`) |
| `DELETE` | `/api/lessons/{id}` | — | Cancel lesson |

### 3.5 Interactive API Docs

When the API server is running, interactive Swagger docs are available at `http://<host>:<port>/api/docs` and ReDoc at `/api/redoc`.

---

## 4. Frontend Design

### 4.1 Tech Stack

| Layer | Technology |
|---|---|
| Framework | Expo SDK 52 (React Native) |
| Routing | Expo Router (file-based) |
| Language | TypeScript (strict) |
| Data Fetching | TanStack React Query v5 |
| HTTP Client | Axios |
| Real-time | Native WebSocket + custom `WSManager` |
| Icons | `@expo/vector-icons` (Ionicons) |
| Styling | React Native StyleSheet (dark theme) |
| Platforms | iOS, Android, Web (via Expo) |

### 4.2 Project Structure

```
app/
├── package.json
├── app.json              # Expo config
├── tsconfig.json
├── babel.config.js
├── assets/               # Icons, splash (placeholder)
└── src/
    ├── theme/
    │   └── colors.ts     # Dark theme palette + helpers
    ├── api/
    │   ├── client.ts     # Axios instance, JWT token mgmt
    │   ├── auth.ts       # login() / logout()
    │   ├── stats.ts      # useStats() query hook
    │   ├── config.ts     # useConfig() / usePatchConfig() hooks
    │   ├── review.ts     # usePendingReviews(), useApproveReview(), etc.
    │   ├── kb.ts         # useKBInfo() / useKBSearch(query)
    │   ├── faq.ts        # useFAQ() / useGenerateFAQ()
    │   └── ws.ts         # WSManager singleton (connect, reconnect, dispatch)
    └── app/
        ├── _layout.tsx           # Root: QueryClientProvider + auth guard
        ├── login.tsx             # Login screen
        └── (tabs)/
            ├── _layout.tsx       # Bottom tab navigator
            ├── index.tsx         # Dashboard
            ├── review.tsx        # Review queue
            ├── kb.tsx            # KB search
            ├── config.tsx        # Config editor
            └── more.tsx          # FAQ + logout
```

### 4.3 Theme

Dark theme with a blue primary accent. Color palette defined in `colors.ts`:

| Token | Hex | Usage |
|---|---|---|
| `background` | `#0F1419` | Screen background |
| `surface` | `#1A2332` | Cards, inputs |
| `primary` | `#3B82F6` | Buttons, active tab |
| `success` | `#10B981` | Approve, auto-reply badge |
| `warning` | `#F59E0B` | Pending, forwarded badge |
| `danger` | `#EF4444` | Reject, error |
| `info` | `#06B6D4` | Info badge |

The `confidenceColor(score)` helper returns green/yellow/red based on the 1–10 score.

### 4.4 Authentication Flow

1. User enters **Server URL**, **username**, and **password** on the Login screen.
2. `login()` sends `POST /api/auth/login` with form data.
3. On success, the JWT token is stored in-memory via `setToken()` and injected into all Axios requests via `Authorization: Bearer <token>`.
4. `WSManager.connect()` opens a WebSocket with the token.
5. On 401 response, the Axios interceptor clears the token and the auth guard in `_layout.tsx` redirects to `/login`.

### 4.5 Real-Time Updates

`WSManager` (singleton in `ws.ts`):
- Connects to `ws://<host>:<port>/api/ws?token=<jwt>`
- Auto-reconnects with 5-second backoff
- On incoming events, invalidates relevant TanStack Query caches:
  - `review_request` / `review_resolved` → invalidate `['reviews']`
  - `config_changed` → invalidate `['config']`
  - `new_query` → invalidate `['stats']`
- Custom event handlers can be registered via `wsManager.onEvent(handler)`.

### 4.6 Screen Details

| Screen | Tab | Key Features |
|---|---|---|
| **Dashboard** | Home | 6 status cards (uptime, queries, auto-replies, pending reviews, avg confidence, avg latency). Recent query feed with action badges and confidence colors. Pull-to-refresh. |
| **Review** | Review | Pending review items with question, draft answer, context snippets, confidence badge, channel info. Approve/Edit/Reject buttons. Edit opens a modal with text editor. Confirmation alerts. |
| **KB** | KB | Document count. Text search input with debounced semantic search. Results with distance scores and type badges. Sample documents when idle. |
| **Config** | Config | Read-only model info. Editable fields for threshold, respond mode, cooldowns, thread settings, memory settings. Save button with runtime-only warning. |
| **More** | More | FAQ list with generate button. Logout with confirmation. App version. |

---

## 5. Data Flow Diagrams

### 5.1 Review Flow (App)

```
User question in Discord
    │
    ▼
listener.py → confidence < threshold
    │
    ├─ Forward to owner DM (existing)
    │
    └─ review_queue.add()          ←── New: enqueue for app
       │
       ├─ ws_manager.broadcast("review_request")
       │         │
       │         ▼
       │   App receives WS event
       │   → invalidates ['reviews'] cache
       │   → Review screen re-fetches
       │
       └─ User opens Review tab
          │
          ├─ Approve → POST /api/review/{id}/approve
          │     ├─ Reply to Discord message
          │     ├─ Learn Q&A to ChromaDB
          │     └─ Broadcast "review_resolved"
          │
          ├─ Edit → POST /api/review/{id}/edit
          │     ├─ Reply with edited answer
          │     ├─ Learn edited Q&A
          │     ├─ Store original as negative sample
          │     └─ Broadcast "review_resolved"
          │
          └─ Reject → POST /api/review/{id}/reject
                ├─ Store as negative sample
                └─ Broadcast "review_resolved"
```

### 5.2 Config Update Flow

```
App Config screen → PATCH /api/config
    │
    ├─ Update Python module globals in-memory
    ├─ Broadcast "config_changed" via WS
    │       │
    │       ▼
    │   All connected clients invalidate config cache
    │
    └─ Response: { updated: { field: { old, new } } }

Note: Changes are runtime-only and reset on bot restart.
```

---

## 6. Security Considerations

| Concern | Mitigation |
|---|---|
| Credential exposure | Password is bcrypt-hashed at startup; JWT secret via `API_SECRET_KEY` env var |
| Token theft | Tokens expire (default 24h); 401 interceptor clears stale tokens |
| CORS | Currently `allow_origins=["*"]` for dev; restrict in production |
| WebSocket auth | JWT validated on connection; close `4001` on failure |
| Config changes | Runtime-only; `.env` never modified; changes lost on restart |
| Rate limiting | Inherits bot's rate limiter; API itself has no additional rate limiting (add in production) |

---

## 7. Configuration Reference

Add these to your `.env` file:

```env
# ── API Server ──
API_ENABLED=true              # Set to false to disable the API server
API_PORT=8090                 # Port for the FastAPI server
API_SECRET_KEY=change-me      # JWT signing secret (use a strong random string)
API_USERNAME=admin            # Login username
API_PASSWORD=admin            # Login password (stored as bcrypt hash in memory)
API_TOKEN_EXPIRE_MINUTES=1440 # JWT token lifetime (default: 24 hours)
```

---

## 8. Dependencies

### Backend (Python)
- `fastapi>=0.111.0`
- `uvicorn[standard]>=0.30.0`
- `python-jose[cryptography]>=3.3.0`
- `passlib[bcrypt]>=1.7.4`
- `bcrypt==4.0.1`
- `python-multipart>=0.0.6`

### Frontend (Node.js)
- `expo ~52.0.46`
- `expo-router ~4.0.0`
- `react-native 0.76.9`
- `@tanstack/react-query ^5.62.0`
- `axios ^1.7.9`
- `@react-navigation/bottom-tabs ^7.0.0`
- `@expo/vector-icons ^14.0.0`

---

## 9. File Inventory

### Backend (`bot/api/`)

| File | Purpose |
|---|---|
| `__init__.py` | Module init |
| `auth.py` | JWT authentication (login, token create/verify, `get_current_user` dependency) |
| `ws.py` | WebSocket connection manager + endpoint |
| `server.py` | FastAPI app factory, dependency injection, uvicorn runner |
| `routes_stats.py` | `GET /api/stats` |
| `routes_config.py` | `GET/PATCH /api/config` |
| `routes_digest.py` | `GET /api/digest` |
| `routes_kb.py` | `GET /api/kb`, `GET /api/kb/search` |
| `routes_review.py` | Review CRUD + Discord reply + auto-learn |
| `routes_faq.py` | `GET /api/faq`, `POST /api/faq/generate` |
| `routes_promo.py` | Promo + Lesson CRUD |

### Supporting (`bot/`)

| File | Purpose |
|---|---|
| `review_queue.py` | `ReviewItem` dataclass + `ReviewQueue` with JSON persistence (`data/review_queue.json`) |

### Frontend (`app/src/`)

| File | Purpose |
|---|---|
| `theme/colors.ts` | Dark theme palette and `confidenceColor()` helper |
| `api/client.ts` | Axios instance, base URL + JWT token management, 401 interceptor |
| `api/auth.ts` | `login()` / `logout()` functions |
| `api/stats.ts` | `useStats()` React Query hook |
| `api/config.ts` | `useConfig()` / `usePatchConfig()` hooks |
| `api/review.ts` | `usePendingReviews()`, `useApproveReview()`, `useEditReview()`, `useRejectReview()` |
| `api/kb.ts` | `useKBInfo()` / `useKBSearch(query)` hooks |
| `api/faq.ts` | `useFAQ()` / `useGenerateFAQ()` hooks |
| `api/ws.ts` | `WSManager` singleton — connect, reconnect, dispatch, cache invalidation |
| `app/_layout.tsx` | Root layout with `QueryClientProvider` + auth guard |
| `app/login.tsx` | Login screen |
| `app/(tabs)/_layout.tsx` | Bottom tab navigator (5 tabs) |
| `app/(tabs)/index.tsx` | Dashboard screen |
| `app/(tabs)/review.tsx` | Review queue screen |
| `app/(tabs)/kb.tsx` | Knowledge base search screen |
| `app/(tabs)/config.tsx` | Config editor screen |
| `app/(tabs)/more.tsx` | FAQ + logout screen |

---

## 10. Public Client API

A separate set of **public endpoints** (no admin JWT required) powers the client-facing app. These live under `/api/public/` and are optionally gated by a simple API key.

### 10.1 Configuration

```env
CLIENT_API_ENABLED=true              # Enable/disable public API
CLIENT_API_KEY=                       # Empty = open access; set a key to require x-api-key header
CLIENT_RATE_LIMIT_PER_MINUTE=20       # Per-IP rate limit
```

### 10.2 Authentication

- If `CLIENT_API_KEY` is empty, all public endpoints are open.
- If set, clients must send `x-api-key: <key>` header. Returns `403` on mismatch.
- Per-IP rate limiting: returns `429` when exceeded.

### 10.3 Public Endpoints

| Method | Path | Body/Params | Description |
|---|---|---|---|
| `POST` | `/api/public/chat` | `{ "message": "...", "conversation_history?": [...] }` | RAG-powered chat. Returns `{ answer, confidence, sources }`. Max 2000 chars. |
| `GET` | `/api/public/faq` | — | Cached FAQ items |
| `GET` | `/api/public/kb/search` | `?q=...&top_k=5` | Semantic KB search |
| `GET` | `/api/public/promos` | — | Upcoming promotions |
| `GET` | `/api/public/lessons` | — | Upcoming lessons |

### 10.4 Client App (`app-client/`)

A separate Expo project for end users (no Discord account needed).

| Screen | Tab | Features |
|---|---|---|
| **Chat** | Chat | Full RAG-powered conversation with message bubbles, confidence badges, source citations, suggestion chips, typing indicator |
| **FAQ** | FAQ | Expandable FAQ accordion from cached items |
| **Search** | Search | Semantic KB search with type badges and match scores |
| **Events** | Events | Upcoming promos (with links) and lessons (with repeat badges) |

### 10.5 Client App Files

| File | Purpose |
|---|---|
| `app-client/src/api/client.ts` | Axios instance with base URL + API key management |
| `app-client/src/api/chat.ts` | `useSendMessage()` mutation hook |
| `app-client/src/api/faq.ts` | `useFAQ()` query hook |
| `app-client/src/api/kb.ts` | `useKBSearch(query)` query hook |
| `app-client/src/api/promos.ts` | `usePromos()` / `useLessons()` query hooks |
| `app-client/src/app/_layout.tsx` | Root layout with QueryClientProvider |
| `app-client/src/app/(tabs)/_layout.tsx` | Bottom tab navigator (4 tabs) |
| `app-client/src/app/(tabs)/index.tsx` | Chat screen |
| `app-client/src/app/(tabs)/faq.tsx` | FAQ screen |
| `app-client/src/app/(tabs)/search.tsx` | KB search screen |
| `app-client/src/app/(tabs)/promos.tsx` | Promos & lessons screen |
