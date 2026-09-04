# BigTree Bot — Management App User Guide

> **Version:** 1.0.0
> **Last updated:** 2026-08-13

This guide covers how to set up, launch, and use the BigTree Bot Management App — a cross-platform (iOS, Android, Web) console for monitoring and managing your Discord RAG bot.

> **Looking for the public-facing client apps?** See [`CLIENT_USER_GUIDE.md`](./CLIENT_USER_GUIDE.md) for the end-user chat app (mobile + web) and [`CLIENT_DESIGN.md`](./CLIENT_DESIGN.md) for the technical design.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Backend Setup](#2-backend-setup)
3. [Frontend Setup](#3-frontend-setup)
4. [Logging In](#4-logging-in)
5. [Dashboard](#5-dashboard)
6. [Review Queue](#6-review-queue)
7. [Knowledge Base Search](#7-knowledge-base-search)
8. [Configuration](#8-configuration)
9. [FAQ Management](#9-faq-management)
10. [Real-Time Updates](#10-real-time-updates)
11. [Running on Mobile](#11-running-on-mobile)
12. [Running on Web](#12-running-on-web)
13. [API Documentation](#13-api-documentation)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Prerequisites

- **Python 3.11+** with the bot's virtual environment set up
- **Node.js 18+** and **npm** (for the frontend)
- The Discord bot already configured and able to run (`.env` populated)
- A network path between the device running the app and the machine running the bot

---

## 2. Backend Setup

### 2.1 Add API Configuration

Add the following to your `.env` file:

```env
API_ENABLED=true
API_PORT=8090
API_SECRET_KEY=your-strong-random-secret
API_USERNAME=admin
API_PASSWORD=your-secure-password
API_TOKEN_EXPIRE_MINUTES=1440
```

| Variable | Description | Default |
|---|---|---|
| `API_ENABLED` | Enable/disable the API server | `true` |
| `API_PORT` | Port the API listens on | `8090` |
| `API_SECRET_KEY` | Secret key for signing JWT tokens — **change this in production** | `change-me` |
| `API_USERNAME` | Login username | `admin` |
| `API_PASSWORD` | Login password | `admin` |
| `API_TOKEN_EXPIRE_MINUTES` | How long a login session lasts (minutes) | `1440` (24 hours) |

> **Security:** Use a strong, random `API_SECRET_KEY` in production. The password is bcrypt-hashed in memory — it is never stored in plaintext beyond the `.env` file.

### 2.2 Install Dependencies

```bash
pip install -r requirements.txt
```

### 2.3 Start the Bot (with API)

Start the bot normally — the API server launches automatically alongside it:

```bash
python -m bot.main
```

You will see a log line confirming the API is running:

```
INFO: API server starting on port 8090
```

The API is now accessible at `http://<your-server-ip>:8090`.

### 2.4 Verify

Open a browser and visit:

```
http://localhost:8090/api/health
```

You should see:

```json
{
  "status": "ok",
  "uptime_seconds": 12.3,
  "timestamp": 1691234567.89
}
```

---

## 3. Frontend Setup

### 3.1 Install Dependencies

```bash
cd app
npm install
```

### 3.2 Start the Dev Server

```bash
npx expo start
```

This opens the Expo CLI with options:

- Press **`w`** to open the web version in your browser
- Scan the QR code with the **Expo Go** app on your phone (iOS/Android)
- Press **`a`** for Android emulator or **`i`** for iOS simulator

---

## 4. Logging In

When the app launches, you'll see the **Login screen** with three fields:

1. **Server URL** — The full URL of your bot's API server (e.g., `http://192.168.1.100:8090`). For local development, use `http://localhost:8090`.
2. **Username** — The `API_USERNAME` from your `.env` file.
3. **Password** — The `API_PASSWORD` from your `.env` file.

Tap **Login** to connect. On success, you'll be taken to the Dashboard.

> **Tip:** If running the app on a physical phone, make sure to use your computer's LAN IP address (not `localhost`), and ensure port 8090 is accessible on your network.

### Session Expiry

Your login session lasts for the duration set by `API_TOKEN_EXPIRE_MINUTES` (default: 24 hours). When it expires, the app will automatically redirect you back to the Login screen.

---

## 5. Dashboard

The **Dashboard** tab (home screen) gives you a real-time overview of your bot:

### Status Cards

Six cards at the top show key metrics at a glance:

| Card | What It Shows |
|---|---|
| **Uptime** | How long the bot has been running |
| **Total Queries** | Total questions processed since startup |
| **Auto Replies** | Questions answered automatically (above confidence threshold) |
| **Pending Review** | Number of items waiting for your review |
| **Avg Confidence** | Average confidence score of recent answers (out of 10) |
| **Avg Latency** | Average response time in milliseconds |

### Recent Query Feed

Below the cards, you'll see the most recent queries with:

- **Action badge** — Green "Auto" for auto-replied, yellow "Fwd" for forwarded to review
- **Confidence score** — Color-coded (green = high, yellow = medium, red = low)
- **Time** — How long ago the query was received
- **Question text** — The user's question (truncated to 2 lines)

**Pull down** to refresh the data.

---

## 6. Review Queue

The **Review** tab is your primary moderation tool. When the bot receives a question it isn't confident enough to answer automatically, it appears here for your review.

### Review Item

Each pending item shows:

- **Channel name** — Which Discord channel the question came from
- **Confidence score** — The bot's confidence in its draft answer
- **Time** — When the question was received
- **Author** — Who asked the question
- **Question** — The full question text
- **Draft Answer** — The bot's generated answer
- **Context** — Knowledge base snippets the bot used (if any)

### Actions

Each item has three buttons:

#### Approve

Posts the draft answer as-is to Discord as a reply to the original message. The Q&A pair is automatically learned into the knowledge base for future queries.

#### Edit

Opens a modal where you can modify the draft answer. After submitting:

- The **edited** answer is posted to Discord
- The edited Q&A pair is learned into the knowledge base
- The original draft is stored as a **negative sample** (so the bot learns from the correction)

#### Reject

Discards the draft answer without posting anything to Discord. The Q&A pair is stored as a negative sample to improve future responses.

### Empty State

When all items are reviewed, you'll see a checkmark with "All caught up!" — this means there are no pending reviews.

> **Real-time:** New review items appear automatically via WebSocket — no need to manually refresh.

---

## 7. Knowledge Base Search

The **KB** tab lets you explore and search the bot's knowledge base (ChromaDB).

### Document Count

At the top, you'll see the total number of documents in the knowledge base.

### Semantic Search

Type a query in the search box. The app performs a **semantic search** (not just keyword matching) using the same embedding model as the bot. Results include:

- **Type badge** — Document type (e.g., `qa_pair`, `owner_message`, `youtube`)
- **Distance score** — How semantically close the result is (lower = more relevant)
- **Text** — The matching document content

### Sample Documents

When no search query is entered, the screen shows a few sample documents from the knowledge base so you can see what's stored.

> **Use case:** This is useful for verifying the bot has the right information, checking if a topic is covered, or debugging unexpected answers.

---

## 8. Configuration

The **Config** tab lets you view and adjust the bot's runtime settings.

### Read-Only Fields

These show the current model configuration (not editable via the app):

- **LLM Model** — e.g., `gpt-4o-mini`
- **Embedding Model** — e.g., `text-embedding-3-small`
- **Vision Model** — e.g., `gpt-4o`

### Editable Fields

You can adjust these settings in real-time:

| Setting | Description |
|---|---|
| **Respond Mode** | `auto` (confidence-based routing) or `review` (always forward to owner) |
| **Confidence Threshold** | Score (1–10) above which the bot auto-replies |
| **User Cooldown (s)** | Minimum seconds between responses to the same user |
| **Global Max/min** | Maximum bot responses per minute across all users |
| **Thread Auto Reply** | Whether the bot replies in threads |
| **Thread Context Messages** | Number of previous thread messages to include as context |
| **Memory Size** | Number of conversation turns to remember per user |
| **Memory TTL (s)** | How long conversation memory persists (seconds) |

Tap **Save Changes** to apply. All connected clients are notified of the change in real-time.

> **Important:** Changes are **runtime-only** and will reset when the bot restarts. To make permanent changes, edit your `.env` file directly.

---

## 9. FAQ Management

The **More** tab includes FAQ management:

### Viewing FAQ

Current FAQ items are displayed as Q&A cards.

### Regenerating FAQ

Tap **Regenerate FAQ** to have GPT analyze recent high-confidence queries and generate a fresh set of FAQ items. This is useful for keeping your FAQ up-to-date with the most common questions.

### Logging Out

The **Logout** button at the bottom disconnects from the server and returns you to the Login screen.

---

## 10. Real-Time Updates

The app maintains a persistent WebSocket connection to the bot. This means:

- **New review items** appear instantly — no need to refresh
- **Config changes** made by other clients are reflected immediately
- **Stats updates** are pushed when new queries arrive
- If the connection drops, the app **auto-reconnects** after 5 seconds

You can see the connection status in the browser console (web) or Metro logs (mobile):

```
[WS] Connected
[WS] Disconnected — reconnecting in 5s
```

---

## 11. Running on Mobile

### Using Expo Go (Easiest)

1. Install **Expo Go** from the [App Store](https://apps.apple.com/app/expo-go/id982107779) (iOS) or [Google Play](https://play.google.com/store/apps/details?id=host.exp.exponent) (Android)
2. Run `npx expo start` in the `app/` directory
3. Scan the QR code with your phone's camera (iOS) or the Expo Go app (Android)

### Requirements for Mobile

- Your phone and the bot server must be on the same network (or the server must be publicly accessible)
- Use the server's **LAN IP address** (e.g., `http://192.168.1.100:8090`), not `localhost`
- Ensure port 8090 is not blocked by a firewall

### Building a Standalone App

To build a production app binary:

```bash
# For Android (.apk / .aab)
npx eas build --platform android

# For iOS (.ipa)
npx eas build --platform ios
```

This requires an [Expo Application Services](https://expo.dev/eas) account.

---

## 12. Running on Web

The app works in any modern browser:

```bash
cd app
npx expo start --web
```

This opens the app at `http://localhost:8081` by default.

For a production web build:

```bash
npx expo export --platform web
```

The output in `dist/` can be served by any static file host (Nginx, Vercel, Netlify, etc.).

---

## 13. API Documentation

The backend includes built-in interactive API documentation:

| URL | Format |
|---|---|
| `http://<host>:8090/api/docs` | Swagger UI (interactive, try endpoints) |
| `http://<host>:8090/api/redoc` | ReDoc (clean, readable reference) |

These are useful if you want to integrate with the API programmatically or test endpoints directly.

For the full API reference, see [`./API_DESIGN.md`](./API_DESIGN.md).

---

## 14. Troubleshooting

### Cannot connect to server

- Verify the bot is running and `API_ENABLED=true` is set in `.env`
- Check that you're using the correct IP and port
- Ensure the port is not blocked by a firewall
- On mobile, make sure you're using the LAN IP, not `localhost`
- Test with `curl http://<host>:8090/api/health`

### Login fails

- Double-check `API_USERNAME` and `API_PASSWORD` in `.env`
- Ensure `python-multipart` is installed (`pip install python-multipart`)
- Check the bot's console logs for error details

### "Session expired" / automatic logout

- The JWT token has expired (default: 24 hours)
- Increase `API_TOKEN_EXPIRE_MINUTES` in `.env` if needed
- Simply log in again

### Review approve/edit doesn't post to Discord

- The bot must be running and connected to Discord
- The bot needs permission to send messages in the target channel
- Check bot console logs for "Failed to post review answer" errors

### WebSocket keeps reconnecting

- Intermittent network between app and server
- Server might be restarting — check bot logs
- If behind a reverse proxy, ensure WebSocket upgrade is allowed

### TypeScript / lint errors in the editor

- Run `npm install` in the `app/` directory — most errors are caused by missing `node_modules`
- These do not affect runtime; the Expo bundler handles compilation

### Changes reset on bot restart

- Config changes made via the app are **runtime-only**
- Edit `.env` directly for persistent changes
- FAQ regeneration is persisted to `data/faq.json` and survives restarts

### Port already in use

- Another process is using port 8090
- Change `API_PORT` in `.env` to a different port
- Update the Server URL in the app's Login screen accordingly
