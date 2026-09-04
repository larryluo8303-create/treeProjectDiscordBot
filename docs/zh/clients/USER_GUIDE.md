# BigTree Bot — 管理端 App 用户指南

> **版本：** 1.0.0
> **最后更新：** 2026-08-13

本指南说明如何搭建、启动并使用 BigTree Bot 管理端 App —— 跨平台（iOS、Android、Web）控制台，用于监控与管理你的 Discord RAG Bot。

> **需要面向公众的客户端 App？** 终端用户聊天应用（移动端 + Web）见 [`CLIENT_USER_GUIDE.md`](./CLIENT_USER_GUIDE.md)；技术设计见 [`CLIENT_DESIGN.md`](./CLIENT_DESIGN.md)。

---

## 目录

1. [前置条件](#1-前置条件)
2. [后端设置](#2-后端设置)
3. [前端设置](#3-前端设置)
4. [登录](#4-登录)
5. [仪表盘](#5-仪表盘)
6. [审核队列](#6-审核队列)
7. [知识库搜索](#7-知识库搜索)
8. [配置](#8-配置)
9. [FAQ 管理](#9-faq-管理)
10. [实时更新](#10-实时更新)
11. [在移动端运行](#11-在移动端运行)
12. [在 Web 上运行](#12-在-web-上运行)
13. [API 文档](#13-api-文档)
14. [故障排查](#14-故障排查)

---

## 1. 前置条件

- **Python 3.11+**，且已配置 Bot 的虚拟环境
- **Node.js 18+** 与 **npm**（用于前端）
- Discord Bot 已配置并可运行（`.env` 已填好）
- 运行 App 的设备与运行 Bot 的机器之间网络可达

---

## 2. 后端设置

### 2.1 添加 API 配置

在 `.env` 文件中加入：

```env
API_ENABLED=true
API_PORT=8090
API_SECRET_KEY=your-strong-random-secret
API_USERNAME=admin
API_PASSWORD=your-secure-password
API_TOKEN_EXPIRE_MINUTES=1440
```

| 变量 | 说明 | 默认值 |
|---|---|---|
| `API_ENABLED` | 启用/禁用 API 服务器 | `true` |
| `API_PORT` | API 监听端口 | `8090` |
| `API_SECRET_KEY` | 用于签署 JWT 的密钥 — **生产环境务必修改** | `change-me` |
| `API_USERNAME` | 登录用户名 | `admin` |
| `API_PASSWORD` | 登录密码 | `admin` |
| `API_TOKEN_EXPIRE_MINUTES` | 登录会话时长（分钟） | `1440`（24 小时） |

> **安全：** 生产环境请使用强随机 `API_SECRET_KEY`。密码在内存中经 bcrypt 哈希 — 除 `.env` 外不会以明文存储。

### 2.2 安装依赖

```bash
pip install -r requirements.txt
```

### 2.3 启动 Bot（含 API）

正常启动 Bot — API 服务器会随之一同启动：

```bash
python -m bot.main
```

你会看到确认 API 已运行的日志：

```
INFO: API server starting on port 8090
```

此时 API 可通过 `http://<your-server-ip>:8090` 访问。

### 2.4 验证

用浏览器打开：

```
http://localhost:8090/api/health
```

应看到：

```json
{
  "status": "ok",
  "uptime_seconds": 12.3,
  "timestamp": 1691234567.89
}
```

---

## 3. 前端设置

### 3.1 安装依赖

```bash
cd app
npm install
```

### 3.2 启动开发服务器

```bash
npx expo start
```

将打开 Expo CLI，可选择：

- 按 **`w`** 在浏览器中打开 Web 版
- 用手机上的 **Expo Go** 扫描二维码（iOS/Android）
- 按 **`a`** 打开 Android 模拟器，或按 **`i`** 打开 iOS 模拟器

---

## 4. 登录

App 启动后会看到带三个字段的**登录界面**：

1. **Server URL** — Bot API 服务器的完整 URL（例如 `http://192.168.1.100:8090`）。本地开发使用 `http://localhost:8090`。
2. **Username** — `.env` 中的 `API_USERNAME`。
3. **Password** — `.env` 中的 `API_PASSWORD`。

点击 **Login** 连接。成功后进入仪表盘。

> **提示：** 若在真机上运行 App，请使用电脑的局域网 IP（不要用 `localhost`），并确保网络上可访问 8090 端口。

### 会话过期

登录会话时长由 `API_TOKEN_EXPIRE_MINUTES` 决定（默认：24 小时）。过期后 App 会自动跳回登录页。

---

## 5. 仪表盘

**Dashboard** 标签（主页）提供 Bot 的实时概览：

### 状态卡片

顶部六张卡片一览关键指标：

| 卡片 | 内容 |
|---|---|
| **Uptime** | Bot 已运行时长 |
| **Total Queries** | 启动以来处理的问题总数 |
| **Auto Replies** | 自动回答的问题数（高于置信度阈值） |
| **Pending Review** | 等待你审核的条目数 |
| **Avg Confidence** | 近期回答的平均置信度（满分 10） |
| **Avg Latency** | 平均响应时间（毫秒） |

### 近期查询动态

卡片下方显示最近的查询，包含：

- **Action badge** — 绿色 "Auto" 表示自动回复，黄色 "Fwd" 表示转发给审核
- **Confidence score** — 按颜色区分（绿 = 高，黄 = 中，红 = 低）
- **Time** — 距收到问题多久
- **Question text** — 用户问题（截断为 2 行）

**下拉**可刷新数据。

---

## 6. 审核队列

**Review** 标签是主要审核工具。当 Bot 收到置信度不足以自动回答的问题时，会显示在此处供你审核。

### 审核条目

每条待审项显示：

- **Channel name** — 问题来自哪个 Discord 频道
- **Confidence score** — Bot 对草稿回答的置信度
- **Time** — 收到问题的时间
- **Author** — 提问者
- **Question** — 完整问题文本
- **Draft Answer** — Bot 生成的回答
- **Context** — Bot 使用的知识库片段（如有）

### 操作

每条有三个按钮：

#### Approve

将草稿原样作为对原消息的回复发布到 Discord。该 Q&A 对会自动学习进知识库，供后续查询使用。

#### Edit

打开弹窗修改草稿回答。提交后：

- **修改后**的回答发布到 Discord
- 修改后的 Q&A 对学习进知识库
- 原始草稿存为**负样本**（让 Bot 从纠错中学习）

#### Reject

丢弃草稿，不向 Discord 发布任何内容。该 Q&A 对存为负样本以改进后续响应。

### 空状态

全部审完后会看到对勾与 "All caught up!" — 表示没有待审项。

> **实时：** 新审核项会经 WebSocket 自动出现 — 无需手动刷新。

---

## 7. 知识库搜索

**KB** 标签用于浏览与搜索 Bot 的知识库（ChromaDB）。

### 文档数量

顶部显示知识库中的文档总数。

### 语义搜索

在搜索框输入查询。App 使用与 Bot 相同的嵌入模型做**语义搜索**（不只是关键词匹配）。结果包含：

- **Type badge** — 文档类型（如 `qa_pair`、`owner_message`、`youtube`）
- **Distance score** — 语义接近程度（越低越相关）
- **Text** — 匹配的文档内容

### 样本文档

未输入搜索词时，界面显示知识库中的若干样本文档，便于了解存了什么。

> **用途：** 适合验证 Bot 是否有正确信息、某主题是否已覆盖，或排查异常回答。

---

## 8. 配置

**Config** 标签用于查看与调整 Bot 运行时设置。

### 只读字段

显示当前模型配置（不可通过 App 编辑）：

- **LLM Model** — 例如 `gpt-4o-mini`
- **Embedding Model** — 例如 `text-embedding-3-small`
- **Vision Model** — 例如 `gpt-4o`

### 可编辑字段

可实时调整：

| 设置 | 说明 |
|---|---|
| **Respond Mode** | `auto`（按置信度路由）或 `review`（始终转发给 Owner） |
| **Confidence Threshold** | Bot 自动回复的分数阈值（1–10） |
| **User Cooldown (s)** | 同一用户两次响应之间的最短秒数 |
| **Global Max/min** | 全用户每分钟最大 Bot 响应数 |
| **Thread Auto Reply** | 是否在线程中回复 |
| **Thread Context Messages** | 作为上下文纳入的先前线程消息数 |
| **Memory Size** | 每用户记住的对话轮数 |
| **Memory TTL (s)** | 对话记忆保留时长（秒） |

点击 **Save Changes** 应用。所有已连接客户端会实时收到变更通知。

> **重要：** 变更仅为**运行时**，Bot 重启后会重置。要永久生效，请直接编辑 `.env`。

---

## 9. FAQ 管理

**More** 标签包含 FAQ 管理：

### 查看 FAQ

当前 FAQ 项以 Q&A 卡片展示。

### 重新生成 FAQ

点击 **Regenerate FAQ**，让 GPT 分析近期高置信度查询并生成新的 FAQ 集。适合让 FAQ 跟上最常见问题。

### 退出登录

底部的 **Logout** 按钮断开与服务器的连接并返回登录页。

---

## 10. 实时更新

App 与 Bot 保持持久 WebSocket 连接，因此：

- **新审核项**即时出现 — 无需刷新
- **其他客户端**做的配置变更会立即反映
- **统计更新**在新查询到达时推送
- 连接断开后，App 会在 5 秒后**自动重连**

可在浏览器控制台（Web）或 Metro 日志（移动端）看到连接状态：

```
[WS] Connected
[WS] Disconnected — reconnecting in 5s
```

---

## 11. 在移动端运行

### 使用 Expo Go（最简单）

1. 从 [App Store](https://apps.apple.com/app/expo-go/id982107779)（iOS）或 [Google Play](https://play.google.com/store/apps/details?id=host.exp.exponent)（Android）安装 **Expo Go**
2. 在 `app/` 目录运行 `npx expo start`
3. 用手机相机（iOS）或 Expo Go（Android）扫描二维码

### 移动端要求

- 手机与 Bot 服务器须在同一网络（或服务器可公网访问）
- 使用服务器的**局域网 IP**（例如 `http://192.168.1.100:8090`），不要用 `localhost`
- 确保 8090 端口未被防火墙拦截

### 构建独立 App

构建生产应用二进制：

```bash
# For Android (.apk / .aab)
npx eas build --platform android

# For iOS (.ipa)
npx eas build --platform ios
```

需要 [Expo Application Services](https://expo.dev/eas) 账号。

---

## 12. 在 Web 上运行

App 可在任意现代浏览器中运行：

```bash
cd app
npx expo start --web
```

默认打开 `http://localhost:8081`。

生产 Web 构建：

```bash
npx expo export --platform web
```

`dist/` 中的输出可由任意静态文件托管（Nginx、Vercel、Netlify 等）提供。

---

## 13. API 文档

后端内置交互式 API 文档：

| URL | 格式 |
|---|---|
| `http://<host>:8090/api/docs` | Swagger UI（可交互试调用） |
| `http://<host>:8090/api/redoc` | ReDoc（清晰可读的参考） |

适合程序化集成或直接测试端点。

完整 API 参考见 [`./API_DESIGN.md`](./API_DESIGN.md)。

---

## 14. 故障排查

### 无法连接服务器

- 确认 Bot 在运行且 `.env` 中 `API_ENABLED=true`
- 检查 IP 与端口是否正确
- 确认端口未被防火墙拦截
- 移动端请使用局域网 IP，不要用 `localhost`
- 用 `curl http://<host>:8090/api/health` 测试

### 登录失败

- 核对 `.env` 中的 `API_USERNAME` 与 `API_PASSWORD`
- 确认已安装 `python-multipart`（`pip install python-multipart`）
- 查看 Bot 控制台日志中的错误详情

### 「Session expired」/ 自动退出

- JWT 已过期（默认：24 小时）
- 如需可调大 `.env` 中的 `API_TOKEN_EXPIRE_MINUTES`
- 重新登录即可

### 审核 Approve/Edit 未发到 Discord

- Bot 必须在运行并已连接 Discord
- Bot 需要在目标频道有发送消息权限
- 检查 Bot 控制台是否有 "Failed to post review answer" 错误

### WebSocket 不断重连

- App 与服务器之间网络不稳定
- 服务器可能在重启 — 查看 Bot 日志
- 若在反向代理后，确保允许 WebSocket 升级

### 编辑器中的 TypeScript / lint 错误

- 在 `app/` 目录运行 `npm install` — 多数错误来自缺少 `node_modules`
- 不影响运行时；由 Expo bundler 负责编译

### Bot 重启后变更丢失

- 经 App 修改的配置仅为**运行时**
- 持久变更请直接编辑 `.env`
- FAQ 重新生成会写入 `data/faq.json`，重启后仍保留

### 端口已被占用

- 另有进程占用 8090
- 在 `.env` 中将 `API_PORT` 改为其他端口
- 同步更新 App 登录页中的 Server URL
