# BigTree Bot — API 与移动端 App 设计文档

> **版本：** 1.0.0
> **最后更新：** 2026-08-13

---

## 1. 概述

BigTree Bot 管理平台在现有 Discord RAG Bot 之上扩展了：

1. **FastAPI 后端 API**（`bot/api/`）——与 Discord bot 同进程运行的 REST + WebSocket API，提供对 bot 统计、配置、知识库、审核队列、推广、课程与 FAQ 的程序化访问。
2. **Expo React Native + Web 前端**（`app/`）——跨平台移动端（iOS/Android）与 Web 管理控制台，消费上述 API。
3. **面向公众的客户端**（`app-client/` + `web-client/`）——终端用户侧的移动端与 Web 客户端，支持聊天、摘要、搜索、活动、FAQ、书签、历史与课程归档。详见 [`CLIENT_DESIGN.md`](./CLIENT_DESIGN.md) 与 [`CLIENT_USER_GUIDE.md`](./CLIENT_USER_GUIDE.md)。

由于 API 服务器运行在同一 Python 进程中，两层与 Discord bot 共享同一份数据（ChromaDB、JSON 文件、内存状态）。

---

## 2. 架构

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

## 3. 后端设计

### 3.1 依赖注入

API 服务器作为 `main.py` 内的 asyncio 任务运行。启动前，`main.py` 调用 `server.set_dependencies(collection, openai_client, bot)`，注入共享的 ChromaDB collection、OpenAI 客户端与 Discord bot 实例。路由处理通过 `server.get_collection()`、`server.get_openai_client()`、`server.get_bot()` 访问这些依赖。

### 3.2 认证

| 项目 | 说明 |
|---|---|
| **方案** | OAuth2 Password Bearer（JWT） |
| **登录** | `POST /api/auth/login`，提交 `username` + `password` 表单数据 |
| **令牌** | 使用 `API_SECRET_KEY` 签名的 JWT，包含 `sub`（用户名）与 `exp` |
| **过期** | 可通过 `API_TOKEN_EXPIRE_MINUTES` 配置（默认 1440 = 24 小时） |
| **强制校验** | 除 `/api/health` 与 `/api/auth/login` 外，所有路由需 `Authorization: Bearer <token>` |

密码对照 `.env` 中 `API_PASSWORD` 的 bcrypt 哈希进行校验。

### 3.3 WebSocket

- **端点：** `GET /api/ws?token=<jwt>`
- **认证：** 从 `token` 查询参数校验 JWT。
- **服务器推送事件：**
  - `review_request` — 有新消息转入审核
  - `review_resolved` — 条目已批准/编辑/拒绝
  - `config_changed` — 运行时配置已通过 API 更新
  - `new_query` — bot 处理了新查询
- **客户端行为：** 前端 `WSManager` 在断开后自动重连（5 秒退避），并按事件类型使相关 TanStack Query 缓存失效。

### 3.4 API 端点参考

所有端点返回 JSON。需认证的端点在无令牌或令牌无效时返回 `401`。

#### 健康检查（无需认证）

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/health` | 服务器状态、运行时长、时间戳 |

#### 认证

| 方法 | 路径 | 请求体 | 说明 |
|---|---|---|---|
| `POST` | `/api/auth/login` | `username`、`password`（表单） | 返回 `{ access_token, token_type, expires_in }` |

#### 统计

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/stats` | Bot 统计快照：总查询数、自动回复数、平均置信度、平均延迟、运行时长、近期查询列表 |

#### 配置

| 方法 | 路径 | 请求体 | 说明 |
|---|---|---|---|
| `GET` | `/api/config` | — | 完整配置快照（模型、阈值、频道等） |
| `PATCH` | `/api/config` | 含可选字段的 JSON | 更新运行时配置。字段：`confidence_threshold`、`respond_mode`、`user_cooldown_seconds`、`global_max_per_minute`、`thread_auto_reply`、`thread_context_messages`、`conversation_memory_size`、`conversation_memory_ttl`。会广播 `config_changed` WS 事件。 |

#### 摘要

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/digest` | 24 小时活动摘要：查询数、自动回复数、平均置信度、热门频道、近期查询 |

#### 知识库

| 方法 | 路径 | 查询参数 | 说明 |
|---|---|---|---|
| `GET` | `/api/kb` | — | 文档数量 + 样本文档 |
| `GET` | `/api/kb/search` | `q`（必填）、`top_k`（默认 5） | 使用 `retrieve_context` 做语义搜索。返回 `{ query, count, results: [{ text, distance, metadata }] }` |

#### 审核队列

| 方法 | 路径 | 请求体 | 说明 |
|---|---|---|---|
| `GET` | `/api/review/pending` | — | 列出待审核条目 |
| `GET` | `/api/review/all` | `?limit=50` | 列出全部条目（任意状态） |
| `GET` | `/api/review/{item_id}` | — | 获取单条审核项 |
| `POST` | `/api/review/{item_id}/approve` | — | 批准：向 Discord 发帖回复，并将 Q&A 自动学习进 ChromaDB |
| `POST` | `/api/review/{item_id}/edit` | `{ "answer": "..." }` | 编辑：发布编辑后的答案，学习编辑后的 Q&A，并将原文存为负样本 |
| `POST` | `/api/review/{item_id}/reject` | — | 拒绝：将 Q&A 存为负样本 |

每次操作都会广播 `review_resolved` WebSocket 事件。

**审核条目结构：**
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

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/faq` | 缓存的 FAQ 条目 `{ items: [{ question, answer }] }` |
| `POST` | `/api/faq/generate` | 根据近期高置信度查询，通过 GPT 重新生成 FAQ |

#### 推广

| 方法 | 路径 | 请求体 | 说明 |
|---|---|---|---|
| `GET` | `/api/promos` | — | 列出已安排的推广 |
| `POST` | `/api/promos` | `{ title, description, scheduled_at, channel_ids?, url? }` | 创建推广 |
| `DELETE` | `/api/promos/{id}` | — | 取消推广 |

#### 课程

| 方法 | 路径 | 请求体 | 说明 |
|---|---|---|---|
| `GET` | `/api/lessons` | — | 列出已安排的课程 |
| `POST` | `/api/lessons` | `{ title, content, scheduled_at, channel_ids?, repeat? }` | 创建课程（`repeat`：`none`、`daily`、`weekly`） |
| `DELETE` | `/api/lessons/{id}` | — | 取消课程 |

### 3.5 交互式 API 文档

API 服务器运行时，可在 `http://<host>:<port>/api/docs` 使用交互式 Swagger 文档，在 `/api/redoc` 使用 ReDoc。

---

## 4. 前端设计

### 4.1 技术栈

| 层级 | 技术 |
|---|---|
| 框架 | Expo SDK 52（React Native） |
| 路由 | Expo Router（基于文件） |
| 语言 | TypeScript（strict） |
| 数据获取 | TanStack React Query v5 |
| HTTP 客户端 | Axios |
| 实时 | 原生 WebSocket + 自定义 `WSManager` |
| 图标 | `@expo/vector-icons`（Ionicons） |
| 样式 | React Native StyleSheet（深色主题） |
| 平台 | iOS、Android、Web（经 Expo） |

### 4.2 项目结构

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

### 4.3 主题

深色主题，主色为蓝色强调。调色板定义于 `colors.ts`：

| Token | Hex | 用途 |
|---|---|---|
| `background` | `#0F1419` | 屏幕背景 |
| `surface` | `#1A2332` | 卡片、输入框 |
| `primary` | `#3B82F6` | 按钮、激活标签 |
| `success` | `#10B981` | 批准、自动回复徽章 |
| `warning` | `#F59E0B` | 待处理、已转发徽章 |
| `danger` | `#EF4444` | 拒绝、错误 |
| `info` | `#06B6D4` | 信息徽章 |

`confidenceColor(score)` 辅助函数根据 1–10 分返回绿/黄/红。

### 4.4 认证流程

1. 用户在登录页输入 **Server URL**、**username** 与 **password**。
2. `login()` 以表单数据发送 `POST /api/auth/login`。
3. 成功后，JWT 经 `setToken()` 存于内存，并通过 `Authorization: Bearer <token>` 注入所有 Axios 请求。
4. `WSManager.connect()` 使用该令牌打开 WebSocket。
5. 收到 401 时，Axios 拦截器清除令牌，`_layout.tsx` 中的认证守卫重定向到 `/login`。

### 4.5 实时更新

`WSManager`（`ws.ts` 中的单例）：
- 连接到 `ws://<host>:<port>/api/ws?token=<jwt>`
- 以 5 秒退避自动重连
- 收到事件时，使相关 TanStack Query 缓存失效：
  - `review_request` / `review_resolved` → 使 `['reviews']` 失效
  - `config_changed` → 使 `['config']` 失效
  - `new_query` → 使 `['stats']` 失效
- 可通过 `wsManager.onEvent(handler)` 注册自定义事件处理。

### 4.6 屏幕详情

| 屏幕 | 标签 | 主要功能 |
|---|---|---|
| **Dashboard** | Home | 6 张状态卡片（运行时长、查询、自动回复、待审核、平均置信度、平均延迟）。近期查询流含操作徽章与置信度颜色。下拉刷新。 |
| **Review** | Review | 待审核条目：问题、草稿答案、上下文片段、置信度徽章、频道信息。批准/编辑/拒绝按钮。编辑打开带文本编辑器的模态框。确认提示。 |
| **KB** | KB | 文档数量。带防抖语义搜索的文本输入。结果含距离分数与类型徽章。空闲时显示样本文档。 |
| **Config** | Config | 只读模型信息。可编辑阈值、响应模式、冷却、线程设置、记忆设置。保存按钮带仅运行时生效的警告。 |
| **More** | More | FAQ 列表与生成按钮。带确认的退出登录。App 版本。 |

---

## 5. 数据流图

### 5.1 审核流程（App）

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

### 5.2 配置更新流程

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

## 6. 安全考量

| 风险 | 缓解措施 |
|---|---|
| 凭据暴露 | 启动时对密码做 bcrypt 哈希；JWT 密钥通过 `API_SECRET_KEY` 环境变量提供 |
| 令牌被盗 | 令牌会过期（默认 24 小时）；401 拦截器清除过期令牌 |
| CORS | 当前开发环境为 `allow_origins=["*"]`；生产环境应收紧 |
| WebSocket 认证 | 连接时校验 JWT；失败时关闭码 `4001` |
| 配置变更 | 仅运行时生效；从不修改 `.env`；重启后丢失 |
| 限流 | 继承 bot 的限流器；API 本身无额外限流（生产环境应补充） |

---

## 7. 配置参考

在 `.env` 文件中添加：

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

## 8. 依赖

### 后端（Python）
- `fastapi>=0.111.0`
- `uvicorn[standard]>=0.30.0`
- `python-jose[cryptography]>=3.3.0`
- `passlib[bcrypt]>=1.7.4`
- `bcrypt==4.0.1`
- `python-multipart>=0.0.6`

### 前端（Node.js）
- `expo ~52.0.46`
- `expo-router ~4.0.0`
- `react-native 0.76.9`
- `@tanstack/react-query ^5.62.0`
- `axios ^1.7.9`
- `@react-navigation/bottom-tabs ^7.0.0`
- `@expo/vector-icons ^14.0.0`

---

## 9. 文件清单

### 后端（`bot/api/`）

| 文件 | 用途 |
|---|---|
| `__init__.py` | 模块初始化 |
| `auth.py` | JWT 认证（登录、令牌创建/校验、`get_current_user` 依赖） |
| `ws.py` | WebSocket 连接管理 + 端点 |
| `server.py` | FastAPI 应用工厂、依赖注入、uvicorn 运行器 |
| `routes_stats.py` | `GET /api/stats` |
| `routes_config.py` | `GET/PATCH /api/config` |
| `routes_digest.py` | `GET /api/digest` |
| `routes_kb.py` | `GET /api/kb`、`GET /api/kb/search` |
| `routes_review.py` | 审核 CRUD + Discord 回复 + 自动学习 |
| `routes_faq.py` | `GET /api/faq`、`POST /api/faq/generate` |
| `routes_promo.py` | 推广 + 课程 CRUD |

### 支撑（`bot/`）

| 文件 | 用途 |
|---|---|
| `review_queue.py` | `ReviewItem` 数据类 + 带 JSON 持久化的 `ReviewQueue`（`data/review_queue.json`） |

### 前端（`app/src/`）

| 文件 | 用途 |
|---|---|
| `theme/colors.ts` | 深色主题调色板与 `confidenceColor()` 辅助函数 |
| `api/client.ts` | Axios 实例、base URL + JWT 令牌管理、401 拦截器 |
| `api/auth.ts` | `login()` / `logout()` 函数 |
| `api/stats.ts` | `useStats()` React Query hook |
| `api/config.ts` | `useConfig()` / `usePatchConfig()` hooks |
| `api/review.ts` | `usePendingReviews()`、`useApproveReview()`、`useEditReview()`、`useRejectReview()` |
| `api/kb.ts` | `useKBInfo()` / `useKBSearch(query)` hooks |
| `api/faq.ts` | `useFAQ()` / `useGenerateFAQ()` hooks |
| `api/ws.ts` | `WSManager` 单例 — 连接、重连、分发、缓存失效 |
| `app/_layout.tsx` | 根布局：`QueryClientProvider` + 认证守卫 |
| `app/login.tsx` | 登录页 |
| `app/(tabs)/_layout.tsx` | 底部标签导航（5 个标签） |
| `app/(tabs)/index.tsx` | 仪表盘 |
| `app/(tabs)/review.tsx` | 审核队列页 |
| `app/(tabs)/kb.tsx` | 知识库搜索页 |
| `app/(tabs)/config.tsx` | 配置编辑页 |
| `app/(tabs)/more.tsx` | FAQ + 退出登录页 |

---

## 10. 公开客户端 API

另一组**公开端点**（无需管理员 JWT）为面向客户端的 App 提供能力。位于 `/api/public/`，可选地由简单 API 密钥门控。

### 10.1 配置

```env
CLIENT_API_ENABLED=true              # Enable/disable public API
CLIENT_API_KEY=                       # Empty = open access; set a key to require x-api-key header
CLIENT_RATE_LIMIT_PER_MINUTE=20       # Per-IP rate limit
```

### 10.2 认证

- 若 `CLIENT_API_KEY` 为空，所有公开端点开放访问。
- 若已设置，客户端须发送 `x-api-key: <key>` 请求头。不匹配返回 `403`。
- 按 IP 限流：超出时返回 `429`。

### 10.3 公开端点

| 方法 | 路径 | 请求体/参数 | 说明 |
|---|---|---|---|
| `POST` | `/api/public/chat` | `{ "message": "...", "conversation_history?": [...] }` | RAG 驱动的聊天。返回 `{ answer, confidence, sources }`。最多 2000 字符。 |
| `GET` | `/api/public/faq` | — | 缓存的 FAQ 条目 |
| `GET` | `/api/public/kb/search` | `?q=...&top_k=5` | 语义知识库搜索 |
| `GET` | `/api/public/promos` | — | 即将到来的推广 |
| `GET` | `/api/public/lessons` | — | 即将到来的课程 |

### 10.4 客户端 App（`app-client/`）

面向终端用户的独立 Expo 项目（无需 Discord 账号）。

| 屏幕 | 标签 | 功能 |
|---|---|---|
| **Chat** | Chat | 完整 RAG 对话：消息气泡、置信度徽章、来源引用、建议芯片、输入中指示 |
| **FAQ** | FAQ | 来自缓存条目的可展开 FAQ 手风琴 |
| **Search** | Search | 语义知识库搜索，含类型徽章与匹配分数 |
| **Events** | Events | 即将到来的推广（带链接）与课程（带重复徽章） |

### 10.5 客户端 App 文件

| 文件 | 用途 |
|---|---|
| `app-client/src/api/client.ts` | 带 base URL + API 密钥管理的 Axios 实例 |
| `app-client/src/api/chat.ts` | `useSendMessage()` mutation hook |
| `app-client/src/api/faq.ts` | `useFAQ()` query hook |
| `app-client/src/api/kb.ts` | `useKBSearch(query)` query hook |
| `app-client/src/api/promos.ts` | `usePromos()` / `useLessons()` query hooks |
| `app-client/src/app/_layout.tsx` | 带 QueryClientProvider 的根布局 |
| `app-client/src/app/(tabs)/_layout.tsx` | 底部标签导航（4 个标签） |
| `app-client/src/app/(tabs)/index.tsx` | 聊天页 |
| `app-client/src/app/(tabs)/faq.tsx` | FAQ 页 |
| `app-client/src/app/(tabs)/search.tsx` | 知识库搜索页 |
| `app-client/src/app/(tabs)/promos.tsx` | 推广与课程页 |
