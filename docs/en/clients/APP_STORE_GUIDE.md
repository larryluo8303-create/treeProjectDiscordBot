# BigTree Chat App — App Store Publishing Guide

This guide explains how to publish the BigTree Chat mobile app to the Apple App Store and Google Play Store so customers can download and use it directly.

---

## Architecture Overview

```
Customer phone (BigTree Chat App)
        │
        ▼  HTTPS
Your server (Bot + API Server, port 8090)
        │
        ├── /api/public/chat    ← App chat requests
        ├── /api/public/faq     ← Fetch FAQ
        ├── /api/public/kb/search ← Knowledge-base search
        └── /api/public/...     ← Other public APIs
```

The app is a standalone mobile client that calls the API on your server over HTTPS. The bot runs in the background on the server and serves both Discord and the mobile app.

---

## Prerequisites

| Item | Notes |
|------|------|
| **Apple Developer Account** | $99/year, https://developer.apple.com/programs/ |
| **Google Play Console** | $25 one-time fee, https://play.google.com/console/ |
| **Expo account** | Free, https://expo.dev/signup |
| **EAS CLI** | `npm install -g eas-cli` |
| **Node.js** | >= 18 |
| **Server** | VPS with a public IP, Bot + API already deployed (see below) |

---

## Step 1: Deploy the Backend Server

The app needs an API server that is reachable from the public internet.

### 1.1 Deploy to a VPS

```bash
# On the server
git clone <your-repo> && cd treeProjectDiscordBot
python -m venv .venv && .venv/bin/pip install -r requirements.txt

# Configure .env (important security settings)
cp .env.example .env
# Edit at least the following keys:
#   DISCORD_BOT_TOKEN=<your Bot Token>
#   OPENAI_API_KEY=<your OpenAI Key>
#   OWNER_USER_ID=<your Discord ID>
#   API_SECRET_KEY=<random 32-character strong password>
#   CLIENT_API_KEY=<API Key for clients>

# Start
nohup .venv/bin/python -m bot.main &
```

### 1.2 Configure HTTPS (required)

The App Store requires all network requests to use HTTPS. Use Nginx + Let's Encrypt:

```bash
sudo apt install nginx certbot python3-certbot-nginx
sudo certbot --nginx -d api.yourdomain.com
```

Nginx configuration:

```nginx
server {
    listen 443 ssl;
    server_name api.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8090;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Verify: `curl https://api.yourdomain.com/api/health` should return `{"status": "ok", ...}`

---

## Step 2: Configure the App Default Server URL

Edit `app-client/src/api/client.ts` and change the default URL to your production server:

```typescript
let _baseURL = 'https://api.yourdomain.com';  // ← change to your domain
```

This way, customers can open the app after download and use it immediately without manual configuration.

---

## Step 3: Prepare App Assets

### 3.1 App Icons

Replace the files under `app-client/assets/`:

| File | Size | Purpose |
|------|------|------|
| `icon.png` | 1024x1024 | App Store / main icon |
| `adaptive-icon.png` | 1024x1024 | Android adaptive icon foreground |
| `splash.png` | 1284x2778 | Splash screen |
| `favicon.png` | 48x48 | Web icon |

You can generate placeholder images with the provided script (for development):

```bash
cd app-client
node scripts/generate-icons.js
# Then convert the SVG files to PNG
```

**Before a production release, use professionally designed brand icons.**

### 3.2 Update app.json

Edit `app-client/app.json`:

```json
{
  "expo": {
    "name": "BigTree Chat",           // App Store display name
    "version": "1.0.0",               // Version number
    "ios": {
      "bundleIdentifier": "com.yourcompany.bigtree"  // Your Bundle ID
    },
    "android": {
      "package": "com.yourcompany.bigtree"           // Your Package Name
    }
  }
}
```

---

## Step 4: EAS Build

### 4.1 Initialize EAS

```bash
cd app-client
npm install -g eas-cli
eas login                    # Log in to your Expo account
eas init                     # Link the project (fills projectId automatically)
```

### 4.2 Build for iOS (submit to App Store)

```bash
# Preview build (internal testing)
eas build --platform ios --profile preview

# Production build (submit to App Store)
eas build --platform ios --profile production
```

On the first build, EAS will prompt you to:
- Create an iOS Distribution Certificate
- Create a Provisioning Profile
- You can let EAS handle these automatically

### 4.3 Build for Android (submit to Google Play)

```bash
# Production build
eas build --platform android --profile production
```

---

## Step 5: Submit to the Stores

### 5.1 Submit to the Apple App Store

```bash
# Submit directly from EAS to App Store Connect
eas submit --platform ios --profile production
```

Or manually:
1. Download the `.ipa` file from the EAS Dashboard
2. Open Transporter (macOS) → upload the `.ipa`
3. Sign in to App Store Connect → create the App → fill in the details → submit for review

**App Store review checklist:**
- Must use HTTPS
- Privacy policy URL required
- Screenshots required (iPhone 6.7", 5.5", iPad)
- Clear description of App features

### 5.2 Submit to Google Play

```bash
eas submit --platform android --profile production
```

Or manually:
1. Download the `.aab` file from the EAS Dashboard
2. Sign in to Google Play Console → create the app → upload the `.aab`
3. Fill in store listing details → submit for review

---

## Step 6: Customer Usage Flow

Customers only need three steps:

1. **Download the App** → Search for "BigTree Chat" on the App Store / Google Play
2. **Open the App** → Automatically connects to your server
3. **Start asking questions** → The RAG Bot answers automatically

If you set `CLIENT_API_KEY`, customers need to do this on first use:
- Open the App → More → Server Settings → enter the API Key you provide → Save

---

## App Feature Overview

| Tab | Features |
|-----|------|
| **Chat** | Chat UI: ask questions → RAG Bot answers automatically; supports image upload for analysis |
| **Digest** | Daily activity summary (query count, auto-reply rate, popular questions) |
| **Search** | Search historical knowledge-base content |
| **Events** | View upcoming promo events and teaching sessions |
| **More** | FAQ, bookmarks, chat history, teaching archive, server settings |

---

## Updating the App Version

```bash
# 1. Change the code
# 2. Update version in app.json
# 3. Rebuild
eas build --platform all --profile production

# 4. Resubmit
eas submit --platform all --profile production
```

EAS automatically increments `buildNumber` (iOS) and `versionCode` (Android).

---

## OTA Hot Updates (No Resubmission Required)

For JS updates that do not touch native code, you can push directly with EAS Update:

```bash
# Publish an OTA update (users get it automatically when they open the App; no store re-download)
eas update --branch production --message "Fix XX issue"
```

This is a major Expo advantage — most updates do not need to wait for Apple review.

---

## FAQ

### Q: Do I need a Mac to publish for iOS?
**No.** EAS Build runs in the Expo cloud, so Windows works too. A Mac is only needed for local simulator debugging.

### Q: Do builds cost money?
The EAS free plan includes 30 builds per month, which is enough. Paid plans get faster queue priority.

### Q: How long does review take?
- Apple: typically 1–3 business days
- Google: typically a few hours to 1 day

### Q: Can I do internal testing first?
Yes. Build with the `preview` profile and distribute to testers via TestFlight (iOS) or the internal testing track (Android).
