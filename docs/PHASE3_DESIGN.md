# Phase 3: 新功能开发 — 设计文档

---

## 目录

- [一、背景与目标](#一背景与目标)
- [二、功能总览](#二功能总览)
- [三、系统架构变更](#三系统架构变更)
- [四、模块设计](#四模块设计)
  - [4.1 F1: Thread 自动回复](#41-f1-thread-自动回复)
  - [4.2 F2: 每日摘要 (Daily Digest)](#42-f2-每日摘要-daily-digest)
  - [4.3 F3: Owner 语音转录与自动学习](#43-f3-owner-语音转录与自动学习)
  - [4.4 F4: 多模态图表对比分析](#44-f4-多模态图表对比分析)
  - [4.5 F6: FAQ 自动生成](#45-f6-faq-自动生成)
  - [4.6 F7: 定时数据导入](#46-f7-定时数据导入)
  - [4.7 F8: Webhook 外部数据接入](#47-f8-webhook-外部数据接入)
  - [4.8 F10: Admin 管理面板](#48-f10-admin-管理面板)
- [五、数据流图](#五数据流图)
- [六、配置参数](#六配置参数)
- [七、文件变更清单](#七文件变更清单)
- [八、安全设计](#八安全设计)
- [九、依赖与兼容性](#九依赖与兼容性)

---

## 一、背景与目标

### 背景

Bot 已完成 Phase 1（核心 RAG 功能）和 Phase 2（增强功能），具备：自动回复、信心路由、Owner 审核、负反馈学习、嵌入缓存、令牌桶限流、优雅关机、多语言支持、统计追踪等能力。

### 目标

Phase 3 在现有基础上新增 **8 个功能模块**，进一步提升 Bot 的自动化水平、知识获取能力和运营管理效率：

1. 支持 Discord Thread 对话上下文
2. 每日活动摘要自动推送
3. Owner 语音消息自动转文字并入库
4. 图表分析结合历史知识对比
5. 高频 Q&A 自动生成 FAQ
6. 定时重新导入/风格分析
7. 外部 Webhook 数据接入
8. Web 管理仪表盘

---

## 二、功能总览

| ID | 功能 | 优先级 | 新文件 | 修改文件 |
|----|------|--------|--------|----------|
| F1 | Thread 自动回复 | High | — | listener.py, config.py |
| F2 | 每日摘要 | High | digest.py | main.py |
| F3 | 语音转录 & 自动学习 | High | — | listener.py |
| F4 | 多模态图表对比 | Medium | — | rag.py, listener.py |
| F6 | FAQ 自动生成 | Medium | faq.py | commands.py |
| F7 | 定时数据导入 | Medium | ingestion_scheduler.py | main.py, config.py |
| F8 | Webhook 接入 | Low | webhook.py | main.py |
| F10 | Admin 面板 | Low | admin.py | main.py |

所有新功能均为 **opt-in 设计**（默认关闭），通过环境变量控制开关，不影响现有功能。

---

## 三、系统架构变更

### 新增组件关系图

```
Discord
  │
  ├─ MessageListener (Cog)
  │    ├─ Thread 支持 (F1) ─ _is_thread / _fetch_thread_context
  │    ├─ 语音转录 (F3) ─ _handle_voice_message → Whisper API → ChromaDB
  │    └─ 图表对比 (F4) ─ retrieve_context → analyze_image (with RAG context)
  │
  ├─ DigestCog (F2) ─ 定时发送 24h 摘要 embed → Owner DM / Channel
  │
  ├─ IngestionSchedulerCog (F7) ─ 定时子进程运行 ingest / analyze_style
  │
  ├─ BotCommands (Cog) ─ /faq, /generate_faq (F6)
  │
  ├─ WebhookServer (F8) ─ HTTP POST → embed → ChromaDB
  │    └─ aiohttp on port 8081
  │
  └─ AdminServer (F10) ─ HTML Dashboard + REST API
       └─ aiohttp on port 8082
```

### 入口注册顺序 (main.py)

```python
# Cogs
MessageListener → PromotionCommands → BotCommands → SchedulerCog
→ HealthCog → IngestionSchedulerCog → DigestCog

# HTTP Servers (optional)
WebhookServer (port 8081)
AdminServer   (port 8082)
```

---

## 四、模块设计

### 4.1 F1: Thread 自动回复

**目的：** 支持在 Discord Thread 中自动回复，保持对话上下文一致性。

**设计要点：**

- **频道识别：** `_is_thread()` 判断消息是否来自 Thread，`_get_parent_channel_id()` 获取父频道 ID
- **频道过滤：** `_should_skip()` 修改为接受父频道在 `TARGET_CHANNEL_IDS` 中的 Thread
- **Thread 开关：** 通过 `THREAD_AUTO_REPLY` 环境变量控制，默认开启
- **上下文获取：** `_fetch_thread_context()` 从 Thread 历史获取最近 N 条消息（`THREAD_CONTEXT_MESSAGES`），格式化为对话历史
- **last_seen 追踪：** Thread 消息使用父频道 ID 追踪，确保离线回填正确工作
- **Owner 自动学习：** Thread 内 Owner 消息同样支持自动学习

**修改文件：**
- `bot/config.py` — 新增 `THREAD_AUTO_REPLY`、`THREAD_CONTEXT_MESSAGES`
- `bot/listener.py` — 新增 `_is_thread()`、`_get_parent_channel_id()`、`_fetch_thread_context()`；修改 `_should_skip()`、`on_message()`、`_handle_message()`

### 4.2 F2: 每日摘要 (Daily Digest)

**目的：** 每天定时向 Owner 发送频道活动摘要，帮助了解 Bot 运行状况。

**设计要点：**

- **新文件：** `bot/digest.py` 实现 `DigestCog`
- **定时机制：** `_digest_loop()` 计算距下一个 `DIGEST_HOUR` (UTC) 的秒数，`asyncio.sleep` 后触发
- **数据来源：** 从 `bot_stats.recent` 过滤最近 24 小时的 `QueryRecord`
- **摘要内容：**
  - 总问题数 / 自动回复数 / 转发数
  - 平均信心分 / 平均延迟
  - Top 5 活跃频道
  - 最近 5 个问题（含回复状态图标）
  - 转发/未回答问题列表
- **投递方式：** 以 Discord Embed 发送至 `DIGEST_CHANNEL_ID`（可选）+ Owner DM
- **静默日：** 若 24h 内无问题，显示 "Quiet Day" 提示

**配置：**
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DIGEST_ENABLED` | `false` | 总开关 |
| `DIGEST_HOUR` | `22` | UTC 小时 (0-23) |
| `DIGEST_CHANNEL_ID` | `0` | 发布频道 (0=仅 DM) |

### 4.3 F3: Owner 语音转录与自动学习

**目的：** 当 Owner 发送语音消息时，自动通过 Whisper 转文字并入库 ChromaDB，扩充知识库。

**设计要点：**

- **检测触发：** 在 `on_message` 中，当 Owner 消息无文本但有音频附件时触发
- **音频格式支持：** `.ogg`、`.mp3`、`.m4a`、`.wav` 及 `audio/*` content type
- **处理流程：**
  1. 下载音频附件 (`voice_att.read()`)
  2. 写入临时文件（保留原始扩展名）
  3. 调用 `openai.audio.transcriptions.create(model="whisper-1", language="zh")`
  4. 清理临时文件（`finally` 确保）
  5. 过滤太短文本 (< 5 字符)
  6. 嵌入并存入 ChromaDB，metadata type 为 `owner_voice`
- **去重：** 使用 `voice_{message.id}` 作为文档 ID，防止重复
- **错误处理：** 外层 try/except 捕获下载和转录错误，内层捕获存储错误

**方法：** `_handle_voice_message()` (listener.py, ~80 行)

### 4.4 F4: 多模态图表对比分析

**目的：** 用户上传图表时，除了 GPT-4o 视觉分析外，同时检索知识库中 Owner 过往对类似标的/形态的历史分析，注入到 vision prompt 中做对比参考。

**设计要点：**

- **触发条件：** 消息包含图片 + 文本（ticker 名/问题）
- **RAG 检索：** 对用户附带文本调用 `retrieve_context(top_k=3)` 获取相关历史分析
- **Prompt 注入：** 在 vision prompt 中追加 "以下是频道主过往关于类似标的/形态的历史分析，供参考对比" + context block
- **降级兼容：** 若 RAG 检索失败（异常/无结果），退回纯视觉分析（无 context）
- **无文本场景：** 用户仅传图不附文字时，不进行 RAG 检索，保持原有行为

**修改文件：**
- `bot/rag.py` — `analyze_image()` 新增 `context_chunks` 参数
- `bot/listener.py` — `_handle_message()` vision 分支增加 RAG 检索

### 4.5 F6: FAQ 自动生成

**目的：** 从高频高信心 Q&A 中自动提取 FAQ，供用户查阅。

**设计要点：**

- **新文件：** `bot/faq.py`
- **生成逻辑 (`generate_faq()`)：**
  1. 从 `bot_stats.recent` 过滤信心 ≥ `FAQ_MIN_CONFIDENCE` (默认 7) 的自动回复记录
  2. 去重 + 限制最多 50 个 unique 问题
  3. 构建 prompt 让 GPT 聚类合并，输出 JSON 数组 `[{"q": "...", "a": "..."}]`
  4. 解析 JSON、验证结构、截取 `FAQ_MAX_ITEMS` 条
  5. 持久化到 `data/faq.json`（含生成时间戳）
- **缓存读取 (`get_cached_faq()`)：** 直接读取 JSON 文件，无需 API 调用
- **最小阈值：** 高信心记录 < 3 条时返回缓存（不重新生成）

**Slash Commands：**
| 命令 | 权限 | 说明 |
|------|------|------|
| `/faq` | 所有人 | 查看当前 FAQ（Discord Embed） |
| `/generate_faq` | Owner | 立即触发 FAQ 重新生成 |

### 4.6 F7: 定时数据导入

**目的：** 自动定时重新运行数据导入和风格分析，保持知识库时效性。

**设计要点：**

- **新文件：** `bot/ingestion_scheduler.py` 实现 `IngestionSchedulerCog`
- **子进程运行：** 通过 `subprocess.run([sys.executable, "-m", module])` 执行，避免阻塞事件循环
- **两个独立循环：**
  - `_ingest_loop()` — 每 `INGEST_INTERVAL_HOURS` 小时运行 `ingestion.ingest`
  - `_style_loop()` — 每 `STYLE_INTERVAL_HOURS` 小时运行 `ingestion.analyze_style`
- **超时保护：** 子进程最长 1 小时 (`timeout=3600`)
- **失败通知：** 执行失败时 DM Owner 错误信息（截取最后 500 字符）
- **状态追踪：** 记录 `_last_ingest` / `_last_style` 时间戳，`status()` 方法供外部查询
- **默认关闭：** interval 设为 0 时不启动循环

**配置：**
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `INGEST_INTERVAL_HOURS` | `0` | 导入间隔 (0=禁用) |
| `STYLE_INTERVAL_HOURS` | `0` | 风格分析间隔 (0=禁用) |

### 4.7 F8: Webhook 外部数据接入

**目的：** 提供 HTTP 接口接收外部数据（如 TradingView alerts），自动嵌入并存入知识库。

**设计要点：**

- **新文件：** `bot/webhook.py` 实现 `WebhookServer`
- **HTTP 框架：** aiohttp（已有依赖，无需新增）
- **端点：**
  - `POST /webhook/ingest` — 接收 JSON 并入库
  - `GET /webhook/health` — 健康检查

**请求格式：**
```json
// 单条
{
  "text": "ES突破关键压力位，成交量放大...",
  "source": "tradingview",
  "type": "alert",
  "ticker": "ES",
  "timeframe": "4h",
  "alert_name": "突破信号"
}

// 批量
[
  {"text": "...", "source": "..."},
  {"text": "...", "source": "..."}
]
```

**安全机制：**
- **HMAC-SHA256 签名验证：** 设置 `WEBHOOK_SECRET` 后，请求必须包含 `X-Webhook-Signature` header
- **去重：** 使用 `webhook_{md5(text)[:12]}` 作为文档 ID
- **最小长度：** text < 10 字符自动跳过

**响应格式：**
```json
{"ingested": 2, "total": 3}
```

**配置：**
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `WEBHOOK_ENABLED` | `false` | 总开关 |
| `WEBHOOK_PORT` | `8081` | HTTP 端口 |
| `WEBHOOK_SECRET` | (空) | HMAC 密钥，空=不验证 |

### 4.8 F10: Admin 管理面板

**目的：** 提供 Web 界面查看 Bot 状态、知识库、配置和 FAQ 管理。

**设计要点：**

- **新文件：** `bot/admin.py` 实现 `AdminServer`
- **框架：** aiohttp + 内联 HTML/CSS/JS 单页应用（零前端依赖）
- **UI 风格：** 深色主题 (Slate palette)、响应式网格布局、自动刷新

**路由：**
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/` | HTML 仪表盘页面 |
| GET | `/admin/api/stats` | 查询统计 JSON |
| GET | `/admin/api/config` | 当前配置快照 |
| GET | `/admin/api/kb` | 知识库文档数 + 样本 |
| GET | `/admin/api/faq` | 当前 FAQ 内容 |
| POST | `/admin/api/faq/generate` | 触发 FAQ 重新生成 |

**Dashboard 卡片：**
1. **Statistics** — 总查询数、自动回复数、转发数、平均信心、平均延迟、运行时间
2. **Configuration** — 当前配置 JSON 展示
3. **Knowledge Base** — 文档总数 + 最近 10 条样本（ID、类型、预览）
4. **Recent Queries** — 最近 10 条查询（问题、信心、动作、延迟）
5. **FAQ** — 当前 FAQ 列表 + "Generate FAQ" 按钮

**安全：**
- **API 认证中间件：** 设置 `ADMIN_SECRET` 后，`/admin/api/*` 请求必须包含 `X-Admin-Secret` header
- Dashboard HTML 页面本身不需要认证（仅展示 UI，数据通过 API 获取）
- Stats 每 30 秒自动刷新

**配置：**
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ADMIN_ENABLED` | `false` | 总开关 |
| `ADMIN_PORT` | `8082` | HTTP 端口 |
| `ADMIN_SECRET` | (空) | API 密钥，空=不验证 |

---

## 五、数据流图

### Owner 语音消息 (F3)

```
Owner 发送语音 → on_message 检测音频附件
  → _handle_voice_message()
    → 下载附件 → 写临时文件
    → Whisper API 转录 → 文本
    → 过滤 (< 5字符)
    → embed (text-embedding-3-small) → ChromaDB (type=owner_voice)
```

### 图表对比分析 (F4)

```
用户发送 图片 + 文字("ES怎么看")
  → _handle_message()
    → retrieve_context("ES怎么看", top_k=3) → [历史分析chunk]
    → analyze_image(images, text, context_chunks=历史分析)
      → GPT-4o vision prompt 含历史对比
    → 生成增强回复
```

### Webhook 数据接入 (F8)

```
外部系统 (TradingView/脚本)
  → POST /webhook/ingest (JSON + HMAC签名)
    → 验证签名
    → 解析 JSON (单条/批量)
    → 每条: embed → ChromaDB (type=external_data)
    → 返回 {"ingested": N}
```

---

## 六、配置参数

Phase 3 新增的全部环境变量：

```env
# F1: Thread 支持
THREAD_AUTO_REPLY=true            # Thread 回复开关
THREAD_CONTEXT_MESSAGES=15        # Thread 历史消息数

# F2: 每日摘要
DIGEST_ENABLED=false              # 总开关
DIGEST_HOUR=22                    # UTC 小时
DIGEST_CHANNEL_ID=0               # 发布频道 (0=仅DM)

# F7: 定时导入
INGEST_INTERVAL_HOURS=0           # 导入间隔 (0=禁用)
STYLE_INTERVAL_HOURS=0            # 风格分析间隔 (0=禁用)

# F8: Webhook
WEBHOOK_ENABLED=false             # 总开关
WEBHOOK_PORT=8081                 # HTTP 端口
WEBHOOK_SECRET=                   # HMAC 密钥

# F10: Admin 面板
ADMIN_ENABLED=false               # 总开关
ADMIN_PORT=8082                   # HTTP 端口
ADMIN_SECRET=                     # API 密钥
```

---

## 七、文件变更清单

### 新文件 (5 个)

| 文件 | 行数 | 功能 |
|------|------|------|
| `bot/digest.py` | 190 | DigestCog — 每日摘要调度与 Embed 构建 |
| `bot/faq.py` | 125 | FAQ 生成引擎 — GPT 聚类 + JSON 持久化 |
| `bot/ingestion_scheduler.py` | 136 | IngestionSchedulerCog — 定时子进程导入 |
| `bot/webhook.py` | 133 | WebhookServer — HTTP 数据接入 |
| `bot/admin.py` | 320 | AdminServer — Web 仪表盘 + REST API |

### 修改文件 (5 个)

| 文件 | 变更 |
|------|------|
| `bot/config.py` | 新增 `THREAD_AUTO_REPLY`、`THREAD_CONTEXT_MESSAGES` |
| `bot/listener.py` | F1: Thread 支持方法；F3: `_handle_voice_message()`；F4: vision RAG 检索 |
| `bot/rag.py` | F4: `analyze_image()` 新增 `context_chunks` 参数 |
| `bot/commands.py` | F6: `/faq`、`/generate_faq` slash commands |
| `bot/main.py` | 注册 DigestCog、IngestionSchedulerCog；启动 WebhookServer、AdminServer |
| `.env.example` | 新增所有 Phase 3 配置变量 |

---

## 八、安全设计

| 组件 | 安全措施 |
|------|----------|
| Webhook | HMAC-SHA256 签名验证 (`WEBHOOK_SECRET`) |
| Admin Panel | API 密钥中间件 (`ADMIN_SECRET`，仅保护 API 路由) |
| 语音转录 | 仅 Owner 消息触发；临时文件 `finally` 清理 |
| FAQ 生成 | `/generate_faq` 仅 Owner 可用 |
| 定时导入 | 子进程 1h 超时保护；失败 DM 通知 Owner |
| 所有新功能 | 默认关闭 (opt-in)，不影响现有运行 |

---

## 九、依赖与兼容性

- **无新依赖：** 全部功能使用现有依赖 (`aiohttp`、`openai`、`discord.py`、`chromadb`)
- **Python 版本：** 3.11+（使用 `type | None` 语法）
- **测试兼容：** 所有 139 个现有测试通过，无破坏性变更
- **向后兼容：** 所有功能默认关闭，升级后无需改动 `.env` 即可正常运行
