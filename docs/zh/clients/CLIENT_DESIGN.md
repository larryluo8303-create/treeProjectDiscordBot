# BigTree — 客户端应用设计文档

> **版本：** 1.0.0
> **最后更新：** 2026-08-13

本文档描述两个面向公众的客户端应用的架构、技术选型与实现细节：**Expo React Native 移动端**（`app-client/`）与 **React Web SPA**（`web-client/`）。两者共用同一套公开 API，功能集一致。

---

## 1. 概述

BigTree 客户端应用为终端用户提供与 BigTree RAG Bot 对话的聊天界面，以及每日摘要、知识库搜索、活动列表、FAQ、书签与聊天历史等补充功能。与管理端 App（`app/`）不同，这些客户端**无需登录**——使用未认证的公开 API 端点，并可选用 API Key。

### 1.1 两个客户端，一套 API

| | 移动端 App（`app-client/`） | Web 客户端（`web-client/`） |
|---|---|---|
| **框架** | Expo SDK 52 + React Native | Vite 6 + React 18 |
| **语言** | TypeScript | TypeScript |
| **样式** | React Native StyleSheet | TailwindCSS 3 |
| **导航** | expo-router（基于文件） | React Router 6（侧边栏） |
| **数据获取** | TanStack React Query 5 | TanStack React Query 5 |
| **HTTP 客户端** | Axios | Axios |
| **图标** | Ionicons (@expo/vector-icons) | Lucide React |
| **持久化** | AsyncStorage | localStorage |
| **图片上传** | expo-image-picker | HTML File Input API |
| **推送通知** | expo-notifications | 不适用（仅浏览器） |
| **平台** | iOS、Android、Web（经 Expo） | 任意现代浏览器 |

---

## 2. 架构

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

### 2.1 数据流

1. **用户输入** → React 组件状态
2. **API 调用** → TanStack React Query mutation/query → Axios → `POST/GET /api/public/*`
3. **响应** → Query 缓存更新 → UI 重渲染
4. **持久化** → 每条消息后将聊天会话与书签保存到 AsyncStorage（移动端）或 localStorage（Web）

### 2.2 共享模式

尽管 UI 框架不同，两个客户端采用相同的架构模式：

- **API 客户端单例** — 可配置 `baseURL` 与可选 `x-api-key` 头的 Axios 实例，并持久化到本地存储
- **React Query hooks** — 每个 API 端点一个 hook，配置合适的 `staleTime` 与 `refetchInterval`
- **存储层** — 聊天会话（最多 50）与书签（最多 100）的 CRUD
- **辅助工具** — 置信度颜色映射、日期/时间格式化

---

## 3. 项目结构

### 3.1 移动端 App（`app-client/`）

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

### 3.2 Web 客户端（`web-client/`）

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

## 4. 功能矩阵

| 功能 | 移动端 App | Web 客户端 | API 端点 |
|---|---|---|---|
| **聊天** | Tab 1（index.tsx） | /chat | POST /api/public/chat |
| **图片/图表分析** | expo-image-picker | File input | POST /api/public/analyze-image |
| **收藏 Bot 回答** | AsyncStorage | localStorage | 仅客户端 |
| **会话持久化** | AsyncStorage（最多 50） | localStorage（最多 50） | 仅客户端 |
| **每日摘要** | Tab 2（digest.tsx） | /digest | GET /api/public/digest |
| **知识库搜索** | Tab 3（search.tsx） | /search | GET /api/public/kb/search |
| **促销活动** | Tab 4（promos.tsx） | /events | GET /api/public/promos |
| **即将到来的课程** | Tab 4（promos.tsx） | /events | GET /api/public/lessons |
| **FAQ** | More → FAQ | /faq | GET /api/public/faq |
| **书签** | More → Bookmarks | /bookmarks | 仅客户端 |
| **聊天历史** | More → History | /history | 仅客户端 |
| **课程归档** | More → Lessons | /lessons | GET /api/public/lessons/archive |
| **服务器设置** | More → Settings | /settings | 仅客户端 |
| **推送通知** | expo-notifications | 不适用 | — |

---

## 5. API 层设计

### 5.1 API 客户端

两个客户端都配置 Axios 实例，行为如下：

1. 从持久化存储读取 `baseURL`（默认：`http://localhost:8090`）
2. 从持久化存储读取可选的 `apiKey`
3. 若存在 key，则设置 `x-api-key` 请求头
4. 默认超时 30 秒（图片分析为 60 秒）

```typescript
// Web client example (web-client/src/api/client.ts)
export const api = axios.create({
  baseURL: localStorage.getItem('bigtree_server_url') || 'http://localhost:8090',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});
```

### 5.2 React Query Hooks

每个 API 端点包装为带合适缓存策略的 React Query hook：

| Hook | 类型 | Stale Time | Refetch Interval |
|---|---|---|---|
| `useSendMessage` | Mutation | — | — |
| `useAnalyzeImage` | Mutation | — | — |
| `useFAQ` | Query | 5 min | — |
| `useKBSearch(q)` | Query | 1 min | — |
| `usePromos` | Query | 5 min | — |
| `useLessons` | Query | 5 min | — |
| `useDigest` | Query | 5 min | 5 min |
| `useLessonArchive` | Query | 10 min | — |

### 5.3 后端约束

- **速率限制：** 每个 IP `CLIENT_RATE_LIMIT_PER_MINUTE`（默认 20）
- **聊天消息限制：** 最多 2000 字符
- **图片上传限制：** 10 MB，仅 JPEG/PNG/GIF/WebP
- **认证：** 可选 `x-api-key` 头（对照 `CLIENT_API_KEY` 配置校验）
- **CORS：** `allow_origins=["*"]` — 允许任意 Web 客户端来源

---

## 6. 持久化设计

### 6.1 聊天会话

```typescript
interface ChatSession {
  id: string;        // Generated via Date.now().toString(36)
  title: string;     // First user message, truncated to 40 chars
  messages: ChatMessage[];
  createdAt: number; // Unix timestamp (ms)
  updatedAt: number;
}
```

- **存储键：** `bigtree_chat_history`
- **最大会话数：** 50（保存时裁剪最旧）
- **自动保存：** 每次消息交换后

### 6.2 书签

```typescript
interface Bookmark {
  id: string;
  question: string;     // Previous user message
  answer: string;       // Bot answer text
  confidence: number;   // Bot confidence score (1–10)
  savedAt: number;
}
```

- **存储键：** `bigtree_bookmarks`
- **最大书签数：** 100

### 6.3 服务器配置

- **存储键：** `bigtree_server_url`、`bigtree_api_key`
- 跨会话持久化；可通过设置页编辑

---

## 7. UI 设计

### 7.1 调色板

两个客户端使用一致的深色主题：

| Token | 值 | 用途 |
|---|---|---|
| `background` | `#0f172a` | 页面背景 |
| `surface` | `#1e293b` | 卡片、侧边栏 |
| `surface-light` | `#334155` | 悬停状态 |
| `border` | `#334155` | 边框 |
| `primary` | `#3b82f6` | 强调色、活跃导航、按钮 |
| `success` | `#22c55e` | 高置信度、正向 |
| `warning` | `#eab308` | 中等置信度 |
| `danger` | `#ef4444` | 低置信度、错误 |
| `info` | `#06b6d4` | 信息类徽章 |
| `text-main` | `#f1f5f9` | 主文本 |
| `text-secondary` | `#94a3b8` | 次要文本 |
| `text-muted` | `#64748b` | 弱化文本 |

### 7.2 导航

**移动端：** 底部 5 Tab 导航（Chat、Digest、Search、Events、More），隐藏子页（FAQ、Bookmarks、History、Lessons Archive）从 More 菜单进入。

**Web：** 左侧边栏 9 个直达链接（Chat、Digest、Search、Events、FAQ、Bookmarks、History、Lessons、Settings）。宽度小于 `lg` 断点（1024px）时侧边栏折叠为仅图标。

### 7.3 聊天 UI

- **用户消息：** 右对齐，蓝色圆角气泡
- **Bot 消息：** 左对齐，深色表面气泡，包含：
  - BigTree 图标 + 名称标题
  - 置信度徽章（按颜色区分）
  - 书签按钮
  - 来源引用（可折叠，最多显示 3 条）
  - 时间戳
- **图片上传：** 在用户气泡中内联预览
- **加载状态：** 旋转指示器 + 上下文文案（"BigTree is thinking..." / "Analyzing chart..."）
- **空状态：** Logo、标语、建议 chips、上传按钮

### 7.4 置信度可视化

| 分数 | 颜色 | CSS Class |
|---|---|---|
| 7–10 | 绿 | `text-success` / `bg-success/20` |
| 4–6 | 黄 | `text-warning` / `bg-warning/20` |
| 1–3 | 红 | `text-danger` / `bg-danger/20` |

---

## 8. 构建与部署

### 8.1 移动端 App

```bash
cd app-client
npm install
npx expo start          # Development (Expo Go)
npx eas build --platform android   # Production APK/AAB
npx eas build --platform ios       # Production IPA
```

### 8.2 Web 客户端

```bash
cd web-client
npm install
npm run dev             # Development (http://localhost:5173)
npm run build           # Production (outputs to dist/)
npm run preview         # Preview production build
```

**生产构建产物：** 约 95 KB gzipped（JS + CSS）。可由任意静态托管服务（Nginx、Vercel、Netlify、Cloudflare Pages 等）提供。

### 8.3 环境配置

无需构建期环境变量。两个客户端均通过设置页在运行时配置：

| 设置 | 默认值 | 存储位置 |
|---|---|---|
| Server URL | `http://localhost:8090` | AsyncStorage / localStorage |
| API Key | （空） | AsyncStorage / localStorage |

---

## 9. 安全考虑

1. **无需认证** — 面向公众的客户端。速率限制与可选 API Key 提供基础保护。
2. **API Key 存于客户端** — 可在浏览器 DevTools / App 存储中看到。用作轻量门禁，而非密钥。
3. **CORS 通配** — 后端允许 `*` 来源。因公开 API 设计为开放访问，可接受。
4. **图片上传** — 后端在处理前校验类型（JPEG/PNG/GIF/WebP）与大小（10 MB）。
5. **输入净化** — 聊天消息由后端限制为最多 2000 字符。
6. **不存储 PII** — 聊天会话与书签仅保存在用户设备本地。

---

## 10. 与管理端 App 的差异

| 方面 | 管理端 App（`app/`） | 客户端（`app-client/`、`web-client/`） |
|---|---|---|
| **用途** | Bot 管理与审核 | 终端用户聊天与信息 |
| **认证** | 需要 JWT 登录 | 无需登录 |
| **API 端点** | `/api/*`（需认证） | `/api/public/*`（未认证） |
| **功能** | 统计、审核队列、知识库、配置、FAQ 管理 | 聊天、摘要、搜索、活动、FAQ（只读） |
| **实时性** | WebSocket 推送更新 | 经 React Query 轮询 |
| **目标用户** | Bot 所有者 / 管理员 | 社群成员 |
