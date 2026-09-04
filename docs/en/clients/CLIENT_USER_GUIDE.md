# BigTree — Client App & Web User Guide

> **Version:** 1.0.0
> **Last updated:** 2026-08-13

This guide covers setup, usage, and troubleshooting for the BigTree client applications — both the **mobile app** (`app-client/`) and the **web client** (`web-client/`). These are the public-facing apps for end-users to interact with the BigTree RAG Bot.

For the admin management app, see [`USER_GUIDE.md`](./USER_GUIDE.md).
For the technical design document, see [`CLIENT_DESIGN.md`](./CLIENT_DESIGN.md).

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Backend Setup](#2-backend-setup)
3. [Mobile App Setup](#3-mobile-app-setup)
4. [Web Client Setup](#4-web-client-setup)
5. [Configuring the Server Connection](#5-configuring-the-server-connection)
6. [Chat](#6-chat)
7. [Image & Chart Analysis](#7-image--chart-analysis)
8. [Bookmarks](#8-bookmarks)
9. [Chat History](#9-chat-history)
10. [Daily Digest](#10-daily-digest)
11. [Knowledge Base Search](#11-knowledge-base-search)
12. [Events & Promotions](#12-events--promotions)
13. [FAQ](#13-faq)
14. [Lesson Archive](#14-lesson-archive)
15. [Settings](#15-settings)
16. [Deploying to Production](#16-deploying-to-production)
17. [Troubleshooting](#17-troubleshooting)

---

## 1. Prerequisites

- **Node.js 18+** and **npm**
- The BigTree Discord bot running with `API_ENABLED=true` (see [Backend Setup](#2-backend-setup))
- For the mobile app: **Expo Go** app on your phone, or Xcode / Android Studio for emulators

---

## 2. Backend Setup

The client apps connect to the bot's **public API** — a set of unauthenticated endpoints that run alongside the bot.

### 2.1 Enable the Public API

Make sure the following are in your `.env` file:

```env
API_ENABLED=true
API_PORT=8090
```

Optionally, add an API key to restrict access:

```env
CLIENT_API_KEY=your-optional-api-key
CLIENT_RATE_LIMIT_PER_MINUTE=20
```

### 2.2 Start the Bot

```bash
python -m bot.main
```

Verify the API is running:

```bash
curl http://localhost:8090/api/health
```

You should see:

```json
{
  "status": "ok",
  "uptime_seconds": 5.2,
  "timestamp": 1691234567.89
}
```

### 2.3 Public API Endpoints

These are the endpoints both client apps consume:

| Endpoint | Method | Description |
|---|---|---|
| `/api/public/chat` | POST | Send a question and receive a RAG-powered answer |
| `/api/public/analyze-image` | POST | Upload a chart/image for GPT-4o vision analysis |
| `/api/public/faq` | GET | Get cached FAQ items |
| `/api/public/kb/search` | GET | Semantic search (`?q=...&top_k=N`) |
| `/api/public/promos` | GET | Upcoming promotions |
| `/api/public/lessons` | GET | Upcoming lessons |
| `/api/public/lessons/archive` | GET | Past completed lessons |
| `/api/public/digest` | GET | Last 24 hours activity summary |

No login is required. If `CLIENT_API_KEY` is set, pass it as the `x-api-key` HTTP header.

---

## 3. Mobile App Setup

The mobile app lives in the `app-client/` directory.

### 3.1 Install Dependencies

```bash
cd app-client
npm install
```

### 3.2 Start with Expo

```bash
npx expo start
```

This opens the Expo CLI with several options:

- **Scan the QR code** with the Expo Go app on your phone (iOS/Android)
- Press **`a`** to open in Android emulator
- Press **`i`** to open in iOS simulator
- Press **`w`** to open in a web browser

### 3.3 App Navigation

The mobile app uses a **bottom tab bar** with five tabs:

| Tab | Icon | Content |
|---|---|---|
| **Chat** | 💬 | Main chat interface with image upload |
| **Digest** | 📊 | 24-hour activity summary |
| **Search** | 🔍 | Knowledge base semantic search |
| **Events** | 📣 | Upcoming promotions and lessons |
| **More** | ⋯ | Menu hub for additional features |

The **More** tab provides access to:

- **FAQ** — Frequently asked questions
- **Bookmarks** — Saved bot answers
- **History** — Past chat sessions
- **Lesson Archive** — Completed lessons
- **Server Settings** — Configure server URL and API key
- **Push Notifications** — Toggle on/off (requires device permissions)

---

## 4. Web Client Setup

The web client lives in the `web-client/` directory.

### 4.1 Install Dependencies

```bash
cd web-client
npm install
```

### 4.2 Start the Dev Server

```bash
npm run dev
```

The app opens at **http://localhost:5173**.

### 4.3 Web Navigation

The web client uses a **left sidebar** with direct links to all 9 pages:

| Sidebar Item | Route | Content |
|---|---|---|
| **Chat** | `/chat` | Main chat interface with image upload |
| **Digest** | `/digest` | 24-hour activity summary |
| **Search** | `/search` | Knowledge base semantic search |
| **Events** | `/events` | Upcoming promotions and lessons |
| **FAQ** | `/faq` | Frequently asked questions |
| **Bookmarks** | `/bookmarks` | Saved bot answers |
| **History** | `/history` | Past chat sessions |
| **Lessons** | `/lessons` | Completed lesson archive |
| **Settings** | `/settings` | Server URL and API key configuration |

The sidebar shows **icons only** on narrow screens and **icons + labels** on wider screens (≥ 1024px).

---

## 5. Configuring the Server Connection

Before using the app, you need to point it to your BigTree bot server.

### Mobile App

1. Open the **More** tab
2. Scroll down to **Server Settings**
3. Enter the **Server URL** (e.g., `http://192.168.1.100:8090`)
4. Enter the **API Key** if your server requires one
5. Tap **Save**

### Web Client

1. Click **Settings** in the sidebar
2. Enter the **Server URL** (e.g., `http://localhost:8090`)
3. Enter the **API Key** if your server requires one
4. Click **Save Settings**

> **Important:** If using the mobile app on a physical phone, use your computer's **LAN IP address** (not `localhost`). Ensure port 8090 is accessible on your network.

Settings are saved locally and persist across app restarts.

---

## 6. Chat

The Chat page is the primary interface for interacting with BigTree.

### Asking a Question

1. Type your question in the input box at the bottom
2. Press **Enter** or tap the **Send** button
3. BigTree will respond with an answer, including:
   - **Confidence score** (1–10) — color-coded green/yellow/red
   - **Source references** — knowledge base snippets used to generate the answer

### Conversation Context

The chat maintains a rolling window of your last 10 messages as conversation context. This means BigTree can understand follow-up questions like "Can you explain more?" or "What about ES?"

### Suggestion Chips

When the chat is empty, you'll see quick-start suggestion chips:

- **ES今天怎么看？** — Ask about today's ES outlook
- **什么是中枢？** — Ask about trading concepts
- **如何判断趋势？** — Ask about trend analysis
- **Upload a chart** — Start with an image upload

Click any chip to populate the input field.

### Session Auto-Save

Every conversation is automatically saved to your device. You can find past conversations in the **History** page. Up to **50 sessions** are retained (oldest are removed automatically).

---

## 7. Image & Chart Analysis

Both apps support uploading images (charts, screenshots, diagrams) for AI-powered analysis using GPT-4o vision.

### How to Upload

**Mobile App:**
1. Tap the **camera icon** next to the input box
2. Choose to take a photo or pick from your gallery
3. Optionally add a text question alongside the image
4. The image is sent to BigTree for analysis

**Web Client:**
1. Click the **camera icon** next to the input box
2. Select an image file from your computer
3. Optionally add a text question alongside the image
4. The image is sent to BigTree for analysis

### Supported Formats

- JPEG, PNG, GIF, WebP
- Maximum file size: **10 MB**

### What BigTree Can Analyze

- **Stock charts** — Identify patterns, support/resistance levels, trends
- **Technical indicators** — Read and interpret MACD, RSI, moving averages
- **Screenshots** — Extract and explain text or data from screenshots

The uploaded image appears inline in your chat as a preview.

---

## 8. Bookmarks

Save important bot answers for quick reference later.

### Saving a Bookmark

In the chat, tap/click the **bookmark icon** (🔖) on any bot message. The question-answer pair is saved locally with:

- The original question
- The bot's answer
- The confidence score
- The date saved

### Viewing Bookmarks

**Mobile:** More → Bookmarks
**Web:** Click **Bookmarks** in the sidebar

### Deleting a Bookmark

Each bookmark has a **trash icon** — tap/click it to remove the saved answer. You'll be asked to confirm before deletion.

### Storage Limits

Up to **100 bookmarks** are stored. If you exceed this, the oldest bookmarks are automatically removed when new ones are saved.

---

## 9. Chat History

View and manage past conversations.

### Viewing History

**Mobile:** More → History
**Web:** Click **History** in the sidebar

Sessions are grouped by date and show:

- **Session title** (first message, truncated)
- **Message count**
- **Last activity time**

### Deleting Sessions

Each session has a **delete button** — tap/click to remove it. You'll be asked to confirm.

### Storage Limits

Up to **50 sessions** are stored. Oldest sessions are automatically removed when the limit is reached.

---

## 10. Daily Digest

The Digest page shows a summary of BigTree's activity over the last 24 hours.

### Stats Cards

Three cards at the top show:

| Card | Description |
|---|---|
| **Queries** | Total questions received in the last 24 hours |
| **Auto Replies** | Questions answered automatically (above confidence threshold) |
| **Avg Confidence** | Average confidence score of recent answers |

### Top Questions

Below the cards, you'll see a ranked list of the most frequently asked questions from the last 24 hours.

### Empty State

If there has been no activity, you'll see a "No activity in the last 24 hours" message.

Data refreshes automatically every **5 minutes**.

---

## 11. Knowledge Base Search

Search through BigTree's knowledge base using natural language.

### How to Search

1. Go to the **Search** page
2. Type a query in the search box (e.g., "中枢" or "trend reversal")
3. Press **Enter** or click **Search**

### Understanding Results

Each result shows:

- **Type badge** — Document type (`qa_pair`, `owner_message`, `youtube`, etc.)
- **Relevance score** — Percentage showing how closely the document matches your query
- **Text content** — The matching knowledge base entry

Results use **semantic search** (not keyword matching) — so "how to identify a trend" will match documents about "趋势判断" even without exact word overlap.

---

## 12. Events & Promotions

The Events page shows upcoming activities.

### Promotions Section

Displays upcoming promotional events with:

- **Title** and **description**
- **Start date**
- **Details link** (opens in a new tab)

### Lessons Section

Displays upcoming lessons with:

- **Title** and **content description**
- **Scheduled date**
- **Repeat badge** (if the lesson recurs)

### Empty State

If there are no active promotions or upcoming lessons, the respective section shows an "No active promotions" or "No upcoming lessons" message.

---

## 13. FAQ

View frequently asked questions curated by BigTree.

**Mobile:** More → FAQ
**Web:** Click **FAQ** in the sidebar

### How It Works

FAQ items are displayed as an **expandable accordion**. Tap/click any question to reveal the answer. Tap/click again to collapse it.

FAQ items are auto-generated by GPT based on common high-confidence queries and are cached on the server (refreshed by the bot owner via the admin panel).

---

## 14. Lesson Archive

Browse past completed lessons.

**Mobile:** More → Lessons
**Web:** Click **Lessons** in the sidebar

Each archived lesson shows:

- **Title**
- **Content/description**
- **Original scheduled date**

Lessons appear in reverse chronological order (newest first).

---

## 15. Settings

Configure how the app connects to the BigTree server.

### Server URL

The full URL of your BigTree bot's API server, including the port. Examples:

- `http://localhost:8090` (local development)
- `http://192.168.1.100:8090` (LAN access from phone)
- `https://bigtree.example.com` (production with reverse proxy)

### API Key

If your server has `CLIENT_API_KEY` configured, enter the matching key here. Leave empty if no key is required.

### Saving

Click/tap **Save** to apply changes. The settings take effect immediately for all subsequent API calls. Settings are stored locally and persist across restarts.

---

## 16. Deploying to Production

### 16.1 Mobile App — Expo Build

Build standalone app binaries using Expo Application Services:

```bash
cd app-client

# Android (.apk or .aab)
npx eas build --platform android

# iOS (.ipa) — requires Apple Developer account
npx eas build --platform ios
```

This requires an [EAS account](https://expo.dev/eas). See the [Expo build docs](https://docs.expo.dev/build/introduction/) for detailed instructions.

### 16.2 Web Client — Static Build

Build the web client for production:

```bash
cd web-client
npm run build
```

This generates optimized static files in `web-client/dist/` (~95 KB gzipped). Deploy to any static hosting service:

- **Nginx** — Copy `dist/` to your web root
- **Vercel** — `npx vercel --prod` from the `web-client/` directory
- **Netlify** — Drag and drop `dist/` folder, or connect your Git repo
- **Cloudflare Pages** — Connect Git repo, set build command to `npm run build` and output to `dist`

#### Example Nginx Configuration

```nginx
server {
    listen 80;
    server_name bigtree.example.com;
    root /var/www/bigtree-web/dist;
    index index.html;

    # SPA fallback — all routes serve index.html
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache static assets
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

### 16.3 Backend CORS

The backend is pre-configured with `allow_origins=["*"]`, so any web client domain will work out of the box. If you want to restrict origins in production, edit the CORS middleware in `bot/api/server.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://bigtree.example.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 17. Troubleshooting

### Cannot connect to server

- Verify the bot is running with `API_ENABLED=true`
- Check the Server URL in Settings matches your bot's address and port
- Test connectivity: `curl http://<host>:8090/api/health`
- On mobile, use your computer's **LAN IP** (not `localhost`)
- Ensure port 8090 is not blocked by a firewall

### Chat returns errors

- Check the bot console for error messages
- Ensure the bot's OpenAI API key is valid and has credits
- Verify ChromaDB has been populated with data (run ingestion first)

### Image upload fails

- Ensure the image is JPEG, PNG, GIF, or WebP format
- File must be under **10 MB**
- The bot must be running and have a valid OpenAI API key for GPT-4o vision
- Check browser console (web) or Metro logs (mobile) for specific error details

### "Rate limited" message

- The server limits requests to `CLIENT_RATE_LIMIT_PER_MINUTE` per IP (default: 20)
- Wait a moment and try again
- Ask the bot owner to increase the rate limit if needed

### Data not loading (Digest, Events, FAQ, etc.)

- Verify the server connection is configured correctly in Settings
- The bot must be running — these endpoints fetch live data from the bot process
- Pull to refresh (mobile) or reload the page (web)

### Bookmarks / History disappeared

- Data is stored **locally on your device** (not on the server)
- Clearing browser data (web) or app data (mobile) will erase saved items
- Different browsers/devices maintain separate storage

### Web client shows blank page

- Run `npm install` in the `web-client/` directory
- Check the browser console for JavaScript errors
- Ensure you're accessing the correct URL (`http://localhost:5173` in dev)

### Mobile app won't start

- Run `npm install` in the `app-client/` directory
- Make sure you have Expo Go installed on your phone
- Check that your phone and computer are on the same network
- Try `npx expo start --clear` to reset the bundler cache

### TypeScript / lint errors in IDE

- These are editor-only warnings — they don't affect the running app
- Run `npm install` to resolve missing module errors
- The bundlers (Vite / Expo) handle compilation and will show real errors in the terminal
