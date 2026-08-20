# BigTree — Client Applications Design Document

> **Version:** 1.0.0
> **Last updated:** 2026-08-13

This document describes the architecture, technology choices, and implementation details for the two public-facing client applications: the **Expo React Native mobile app** (`app-client/`) and the **React web SPA** (`web-client/`). Both share the same public API surface and offer identical feature sets.

---

## 1. Overview

The BigTree Client Applications provide end-users with a chat interface to the BigTree RAG Bot, along with supplementary features like daily digests, knowledge base search, event listings, FAQ, bookmarks, and chat history. Unlike the admin management app (`app/`), these clients require **no login** — they use the unauthenticated public API endpoints with optional API key.

### 1.1 Two Clients, One API

| | Mobile App (`app-client/`) | Web Client (`web-client/`) |
|---|---|---|
| **Framework** | Expo SDK 52 + React Native | Vite 6 + React 18 |
| **Language** | TypeScript | TypeScript |
| **Styling** | React Native StyleSheet | TailwindCSS 3 |
| **Navigation** | expo-router (file-based) | React Router 6 (sidebar) |
| **Data Fetching** | TanStack React Query 5 | TanStack React Query 5 |
| **HTTP Client** | Axios | Axios |
| **Icons** | Ionicons (@expo/vector-icons) | Lucide React |
| **Persistence** | AsyncStorage | localStorage |
| **Image Upload** | expo-image-picker | HTML File Input API |
| **Push Notifications** | expo-notifications | N/A (browser only) |
| **Platforms** | iOS, Android, Web (via Expo) | Any modern browser |

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (:8090)                    │
│                                                              │
│   Public API (no auth required, optional x-api-key header)   │
│   ┌─ POST /api/public/chat                                   │
│   ├─ POST /api/public/analyze-image                          │
│   ├─ GET  /api/public/faq                                    │
│   ├─ GET  /api/public/kb/search?q=...&top_k=N               │
│   ├─ GET  /api/public/promos                                 │
│   ├─ GET  /api/public/lessons                                │
│   ├─ GET  /api/public/lessons/archive                        │
│   └─ GET  /api/public/digest                                 │
│                                                              │
│   Security: per-IP rate limiting (CLIENT_RATE_LIMIT/min)     │
│   CORS: allow_origins=["*"]                                  │
└──────────────────────────────────────────────────────────────┘
            ▲                           ▲
            │  Axios + React Query      │  Axios + React Query
            │                           │
┌───────────┴──────────┐   ┌────────────┴─────────────┐
│  Mobile App          │   │  Web Client               │
│  (app-client/)       │   │  (web-client/)            │
│                      │   │                           │
│  Expo + React Native │   │  Vite + React + Tailwind  │
│  AsyncStorage        │   │  localStorage             │
│  expo-image-picker   │   │  <input type="file">      │
│  expo-notifications  │   │  Sidebar + Routes         │
│  Tab navigation      │   │                           │
└──────────────────────┘   └───────────────────────────┘
```

### 2.1 Data Flow

1. **User input** → React component state
2. **API call** → TanStack React Query mutation/query → Axios → `POST/GET /api/public/*`
3. **Response** → Query cache update → UI re-render
4. **Persistence** → Chat sessions and bookmarks saved to AsyncStorage (mobile) or localStorage (web) after every message

### 2.2 Shared Patterns

Both clients share identical architectural patterns despite different UI frameworks:

- **API client singleton** — Axios instance with configurable `baseURL` and optional `x-api-key` header, persisted to storage
- **React Query hooks** — One hook per API endpoint with appropriate `staleTime` and `refetchInterval`
- **Storage layer** — CRUD for chat sessions (max 50) and bookmarks (max 100)
- **Helper utilities** — Confidence color mapping, date/time formatting

---

## 3. Project Structure

### 3.1 Mobile App (`app-client/`)

```
app-client/
├── package.json              # Expo SDK 52, React Native deps
├── tsconfig.json
├── src/
│   ├── api/
│   │   ├── client.ts         # Axios instance + base URL + API key management
│   │   ├── chat.ts           # useSendMessage hook (POST /api/public/chat)
│   │   ├── vision.ts         # useAnalyzeImage hook (POST /api/public/analyze-image)
│   │   ├── faq.ts            # useFAQ hook
│   │   ├── kb.ts             # useKBSearch hook
│   │   ├── promos.ts         # usePromos + useLessons hooks
│   │   └── digest.ts         # useDigest hook
│   ├── utils/
│   │   └── storage.ts        # AsyncStorage: chat sessions + bookmarks
│   ├── theme/
│   │   └── colors.ts         # Color palette + confidenceColor helper
│   └── app/
│       ├── _layout.tsx       # Root layout with QueryClientProvider
│       └── (tabs)/
│           ├── _layout.tsx   # Tab navigator (Chat, Digest, Search, Events, More)
│           ├── index.tsx     # Chat screen (main)
│           ├── digest.tsx    # Daily digest screen
│           ├── search.tsx    # KB search screen
│           ├── promos.tsx    # Events / promotions screen
│           ├── more.tsx      # Menu hub (FAQ, bookmarks, history, lessons, settings)
│           ├── faq.tsx       # FAQ screen (hidden tab)
│           ├── bookmarks.tsx # Bookmarks screen (hidden tab)
│           ├── history.tsx   # Chat history screen (hidden tab)
│           └── lessons-archive.tsx  # Lesson archive screen (hidden tab)
```

### 3.2 Web Client (`web-client/`)

```
web-client/
├── package.json              # Vite 6, React 18, TailwindCSS 3
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.js        # Custom dark theme color palette
├── postcss.config.js
├── index.html                # Entry HTML
├── public/
│   └── favicon.svg
├── src/
│   ├── main.tsx              # React entry (QueryClient + BrowserRouter)
│   ├── index.css             # Tailwind imports + global styles
│   ├── App.tsx               # Sidebar navigation + React Router routes
│   ├── api/
│   │   ├── client.ts         # Axios instance + localStorage config
│   │   └── hooks.ts          # All React Query hooks (consolidated)
│   ├── utils/
│   │   ├── storage.ts        # localStorage: chat sessions + bookmarks
│   │   └── helpers.ts        # Confidence colors, date formatting
│   └── pages/
│       ├── ChatPage.tsx      # Chat with image upload, bookmarks, sessions
│       ├── DigestPage.tsx    # 24h activity summary
│       ├── SearchPage.tsx    # KB semantic search
│       ├── EventsPage.tsx    # Promos + upcoming lessons
│       ├── FAQPage.tsx       # Expandable FAQ accordion
│       ├── BookmarksPage.tsx # Saved Q&A pairs
│       ├── HistoryPage.tsx   # Past chat sessions
│       ├── LessonsArchivePage.tsx  # Completed lessons
│       └── SettingsPage.tsx  # Server URL + API key config
```

---

## 4. Feature Matrix

| Feature | Mobile App | Web Client | API Endpoint |
|---|---|---|---|
| **Chat** | Tab 1 (index.tsx) | /chat | POST /api/public/chat |
| **Image/Chart Analysis** | expo-image-picker | File input | POST /api/public/analyze-image |
| **Bookmark Bot Answers** | AsyncStorage | localStorage | Client-side only |
| **Session Persistence** | AsyncStorage (50 max) | localStorage (50 max) | Client-side only |
| **Daily Digest** | Tab 2 (digest.tsx) | /digest | GET /api/public/digest |
| **KB Search** | Tab 3 (search.tsx) | /search | GET /api/public/kb/search |
| **Promotions** | Tab 4 (promos.tsx) | /events | GET /api/public/promos |
| **Upcoming Lessons** | Tab 4 (promos.tsx) | /events | GET /api/public/lessons |
| **FAQ** | More → FAQ | /faq | GET /api/public/faq |
| **Bookmarks** | More → Bookmarks | /bookmarks | Client-side only |
| **Chat History** | More → History | /history | Client-side only |
| **Lesson Archive** | More → Lessons | /lessons | GET /api/public/lessons/archive |
| **Server Settings** | More → Settings | /settings | Client-side only |
| **Push Notifications** | expo-notifications | N/A | — |

---

## 5. API Layer Design

### 5.1 API Client

Both clients configure an Axios instance that:

1. Reads `baseURL` from persistent storage (default: `http://localhost:8090`)
2. Reads optional `apiKey` from persistent storage
3. Sets `x-api-key` header if key is present
4. Uses 30-second default timeout (60s for image analysis)

```typescript
// Web client example (web-client/src/api/client.ts)
export const api = axios.create({
  baseURL: localStorage.getItem('bigtree_server_url') || 'http://localhost:8090',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});
```

### 5.2 React Query Hooks

Each API endpoint is wrapped in a React Query hook with appropriate caching:

| Hook | Type | Stale Time | Refetch Interval |
|---|---|---|---|
| `useSendMessage` | Mutation | — | — |
| `useAnalyzeImage` | Mutation | — | — |
| `useFAQ` | Query | 5 min | — |
| `useKBSearch(q)` | Query | 1 min | — |
| `usePromos` | Query | 5 min | — |
| `useLessons` | Query | 5 min | — |
| `useDigest` | Query | 5 min | 5 min |
| `useLessonArchive` | Query | 10 min | — |

### 5.3 Backend Constraints

- **Rate limiting:** `CLIENT_RATE_LIMIT_PER_MINUTE` per IP (default 20)
- **Chat message limit:** 2000 characters max
- **Image upload limit:** 10 MB, JPEG/PNG/GIF/WebP only
- **Auth:** Optional `x-api-key` header (validated against `CLIENT_API_KEY` config)
- **CORS:** `allow_origins=["*"]` — any web client origin is permitted

---

## 6. Persistence Design

### 6.1 Chat Sessions

```typescript
interface ChatSession {
  id: string;        // Generated via Date.now().toString(36)
  title: string;     // First user message, truncated to 40 chars
  messages: ChatMessage[];
  createdAt: number; // Unix timestamp (ms)
  updatedAt: number;
}
```

- **Storage key:** `bigtree_chat_history`
- **Max sessions:** 50 (oldest trimmed on save)
- **Auto-save:** After every message exchange

### 6.2 Bookmarks

```typescript
interface Bookmark {
  id: string;
  question: string;     // Previous user message
  answer: string;       // Bot answer text
  confidence: number;   // Bot confidence score (1–10)
  savedAt: number;
}
```

- **Storage key:** `bigtree_bookmarks`
- **Max bookmarks:** 100

### 6.3 Server Configuration

- **Storage keys:** `bigtree_server_url`, `bigtree_api_key`
- Persisted across sessions; editable via Settings page

---

## 7. UI Design

### 7.1 Color Palette

Both clients use a consistent dark theme:

| Token | Value | Usage |
|---|---|---|
| `background` | `#0f172a` | Page background |
| `surface` | `#1e293b` | Cards, sidebar |
| `surface-light` | `#334155` | Hover states |
| `border` | `#334155` | Borders |
| `primary` | `#3b82f6` | Accent, active nav, buttons |
| `success` | `#22c55e` | High confidence, positive |
| `warning` | `#eab308` | Medium confidence |
| `danger` | `#ef4444` | Low confidence, errors |
| `info` | `#06b6d4` | Informational badges |
| `text-main` | `#f1f5f9` | Primary text |
| `text-secondary` | `#94a3b8` | Secondary text |
| `text-muted` | `#64748b` | Muted text |

### 7.2 Navigation

**Mobile:** 5-tab bottom navigation (Chat, Digest, Search, Events, More) with hidden sub-screens (FAQ, Bookmarks, History, Lessons Archive) accessible from the More menu.

**Web:** Left sidebar with 9 direct navigation links (Chat, Digest, Search, Events, FAQ, Bookmarks, History, Lessons, Settings). Sidebar collapses to icon-only on screens narrower than `lg` breakpoint (1024px).

### 7.3 Chat UI

- **User messages:** Right-aligned, blue bubble with rounded corners
- **Bot messages:** Left-aligned, dark surface bubble with:
  - BigTree icon + name header
  - Confidence badge (color-coded)
  - Bookmark button
  - Source references (collapsible, max 3 shown)
  - Timestamp
- **Image upload:** Inline preview in user bubble
- **Loading state:** Spinning indicator with contextual text ("BigTree is thinking..." / "Analyzing chart...")
- **Empty state:** Logo, tagline, suggestion chips, upload button

### 7.4 Confidence Visualization

| Score | Color | CSS Class |
|---|---|---|
| 7–10 | Green | `text-success` / `bg-success/20` |
| 4–6 | Yellow | `text-warning` / `bg-warning/20` |
| 1–3 | Red | `text-danger` / `bg-danger/20` |

---

## 8. Build & Deployment

### 8.1 Mobile App

```bash
cd app-client
npm install
npx expo start          # Development (Expo Go)
npx eas build --platform android   # Production APK/AAB
npx eas build --platform ios       # Production IPA
```

### 8.2 Web Client

```bash
cd web-client
npm install
npm run dev             # Development (http://localhost:5173)
npm run build           # Production (outputs to dist/)
npm run preview         # Preview production build
```

**Production build output:** ~95 KB gzipped (JS + CSS). Can be served by any static host (Nginx, Vercel, Netlify, Cloudflare Pages, etc.).

### 8.3 Environment Configuration

No build-time environment variables are required. Both clients are configured at runtime via the Settings page:

| Setting | Default | Stored In |
|---|---|---|
| Server URL | `http://localhost:8090` | AsyncStorage / localStorage |
| API Key | (empty) | AsyncStorage / localStorage |

---

## 9. Security Considerations

1. **No authentication required** — These are public-facing clients. Rate limiting and optional API key provide basic protection.
2. **API key stored client-side** — Visible in browser DevTools / app storage. Intended as a lightweight guard, not a secret.
3. **CORS wildcard** — Backend allows `*` origins. Acceptable because the public API is designed for open access.
4. **Image uploads** — Backend validates file type (JPEG/PNG/GIF/WebP) and size (10 MB) before processing.
5. **Input sanitization** — Chat messages are capped at 2000 characters by the backend.
6. **No PII storage** — Chat sessions and bookmarks are stored locally on the user's device only.

---

## 10. Differences from Admin App

| Aspect | Admin App (`app/`) | Client Apps (`app-client/`, `web-client/`) |
|---|---|---|
| **Purpose** | Bot management & moderation | End-user chat & information |
| **Authentication** | JWT login required | No login required |
| **API endpoints** | `/api/*` (authenticated) | `/api/public/*` (unauthenticated) |
| **Features** | Stats, review queue, KB, config, FAQ management | Chat, digest, search, events, FAQ (read-only) |
| **Real-time** | WebSocket push updates | Polling via React Query |
| **Target users** | Bot owner / admin | Community members |
