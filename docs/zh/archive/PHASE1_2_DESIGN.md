> **归档文档**：历史设计/阶段指南，仅供参考。现行说明见上级目录的 PROJECT_GUIDE / FEATURE_LIST / SETUP_AND_TEST 等。

# Phase 1 & Phase 2: 核心功能与增强功能 — 设计文档

---

## 目录

- [一、背景与目标](#一背景与目标)
- [二、系统总架构](#二系统总架构)
- [三、技术栈](#三技术栈)
- [四、Phase 1 — 核心功能设计](#四phase-1--核心功能设计)
  - [4.1 配置层 (config.py)](#41-配置层-configpy)
  - [4.2 数据导入层 (ingestion/)](#42-数据导入层-ingestion)
  - [4.3 RAG 核心引擎 (rag.py)](#43-rag-核心引擎-ragpy)
  - [4.4 置信度路由 (confidence.py)](#44-置信度路由-confidencepy)
  - [4.5 消息监听器 (listener.py)](#45-消息监听器-listenerpy)
  - [4.6 Owner 审核界面 (review.py)](#46-owner-审核界面-reviewpy)
  - [4.7 ChromaDB 异步封装 (chromadb_async.py)](#47-chromadb-异步封装-chromadb_asyncpy)
  - [4.8 Bot 入口 (main.py)](#48-bot-入口-mainpy)
- [五、Phase 2 — 增强功能设计](#五phase-2--增强功能设计)
  - [5.1 E1: Slash Commands (commands.py)](#51-e1-slash-commands-commandspy)
  - [5.2 E2: 统计追踪 (stats.py)](#52-e2-统计追踪-statspy)
  - [5.3 E3: 负反馈学习](#53-e3-负反馈学习)
  - [5.4 E4: 嵌入缓存 (cache.py)](#54-e4-嵌入缓存-cachepy)
  - [5.5 E5: 令牌桶限流](#55-e5-令牌桶限流)
  - [5.6 E7: 优雅关机](#56-e7-优雅关机)
  - [5.7 E8: 多语言支持 (i18n)](#57-e8-多语言支持-i18n)
  - [5.8 E10: 测试覆盖提升](#58-e10-测试覆盖提升)
  - [5.9 BigTreeSignal 推广系统](#59-bigtreesignal-推广系统)
  - [5.10 离线回填 (Offline Backfill)](#510-离线回填-offline-backfill)
  - [5.11 多源数据导入 (YouTube / PDF)](#511-多源数据导入-youtube--pdf)
  - [5.12 Vision 图片分析](#512-vision-图片分析)
  - [5.13 健康检查 (health.py)](#513-健康检查-healthpy)
- [六、数据流架构](#六数据流架构)
- [七、文件清单](#七文件清单)
- [八、配置参数总表](#八配置参数总表)
- [九、安全设计](#九安全设计)
- [十、依赖清单](#十依赖清单)

---

## 一、背景与目标

### 背景

运营一个 5000+ 成员的 Discord 股票/投资频道。频道主不可能 24 小时在线回复每一个问题。需要一个 AI 助手：
- 用频道主自己的语气和知识自动回复
- 不确定的问题转给频道主人工审核
- 绝不编造投资建议

### Phase 1 目标 — 核心 RAG 自动回复

1. 导入 200K+ 历史 Discord 消息作为知识库
2. 使用 OpenAI embedding + ChromaDB 构建向量检索
3. 使用 GPT-4o-mini 生成模仿频道主风格的回复
4. 自信度路由：高信心自动回复，低信心转人工审核
5. Owner DM 审核界面（Approve / Edit / Reject）

### Phase 2 目标 — 增强与运营

1. Slash Commands（`/ask`、`/status`、`/stats`）
2. 统计追踪与持久化
3. 负反馈闭环（被拒回复作为反面教材）
4. 嵌入缓存减少 API 调用
5. Token Bucket 高级限流
6. 优雅关机（信号处理 + 状态保存）
7. 多语言支持（中/英）
8. BigTreeSignal 推广系统
9. 离线回填（掉线后补答未回问题）
10. 多源数据导入（YouTube 视频、PDF 书籍）
11. GPT-4o Vision 图片分析
12. 健康检查端点
13. 测试覆盖提升（96 → 139 tests）

---

## 二、系统总架构

```
┌─────────────────────────────────────────────────────────────┐
│                    离线数据导入层                              │
│  ingestion/preprocess.py → ingestion/ingest.py → ChromaDB   │
│  ingestion/analyze_style.py → data/style_profile.txt        │
│  ingestion/ingest_youtube.py → ChromaDB                     │
│  ingestion/ingest_pdf.py → ChromaDB                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    Bot 运行层 (main.py)                      │
│                                                              │
│  MessageListener (Cog)                                       │
│  ├─ on_message → 过滤 → 限流 → 队列 → _handle_message       │
│  ├─ RAG Pipeline: retrieve_context → generate_answer         │
│  ├─ Confidence Router: route_answer                          │
│  ├─ Auto-reply OR send_for_review (Owner DM)                │
│  ├─ Vision: analyze_image (GPT-4o)                          │
│  ├─ Auto-learn: _learn_owner_message → ChromaDB             │
│  ├─ Offline backfill: _backfill_offline_messages            │
│  └─ Promotion: CTA / Signal query / Welcome / Testimonial   │
│                                                              │
│  BotCommands (Cog) — /ask, /status, /stats, /faq            │
│  PromotionCommands (Cog) — /signal, /schedule_promo, ...    │
│  SchedulerCog (Cog) — 定时推广帖                              │
│  HealthCog (Cog) — Heartbeat + HTTP /health                 │
│                                                              │
│  支撑模块:                                                    │
│  ├─ stats.py — BotStats 统计 singleton                       │
│  ├─ cache.py — EmbeddingCache LRU                           │
│  ├─ review.py — ReviewView (Approve/Edit/Reject)            │
│  ├─ confidence.py — 路由决策 + 信号检测                       │
│  ├─ promo_config.py — 推广工具函数                            │
│  ├─ testimonials.py — 用户见证收集                            │
│  └─ chromadb_async.py — AsyncCollection 封装                 │
└──────────────────────────────────────────────────────────────┘
```

---

## 三、技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| 语言 | Python 3.11+ | 使用 `type \| None` 语法 |
| Discord | discord.py 2.3+ | Cog 架构、Slash Commands、UI Views |
| LLM | OpenAI GPT-4o-mini | 生成回复 (~$0.15/1M input tokens) |
| Vision | OpenAI GPT-4o | 图片分析 |
| Embeddings | text-embedding-3-small | 向量化 (~$0.02/1M tokens) |
| 向量数据库 | ChromaDB (local persistent) | 零部署成本 |
| Tokenizer | tiktoken (cl100k_base) | 分块计算 |
| HTTP | aiohttp | 健康检查端点 |
| 配置 | python-dotenv | `.env` 文件管理 |
| 音视频 | yt-dlp + Whisper API | YouTube 视频导入 |
| PDF | PyMuPDF (fitz) | PDF 书籍导入 |

**月度运行成本：** ~$30-50（1000 问/天），一次性导入 ~$1-3（200K 帖子）

---

## 四、Phase 1 — 核心功能设计

### 4.1 配置层 (config.py)

**职责：** 集中管理所有配置参数，从 `.env` 文件加载。

**设计要点：**

- 使用 `python-dotenv` 的 `load_dotenv()` 在模块加载时读取 `.env`
- 所有配置变量为模块级常量，带类型注解和默认值
- `TARGET_CHANNEL_IDS` / `PROMO_CHANNEL_IDS` 解析为 `list[int]`
- 系统 Prompt 模板（`SYSTEM_PROMPT_TEMPLATE`）内嵌中文投资领域专用规则：
  - 点位脱敏（禁止输出具体价格数字）
  - 风格匹配（模仿频道主简洁直接的语气）
  - 不确定就不回答（低信心给 1-3 分）
  - 严格评分标准（CONFIDENCE: 1-10）
- `LOCALE` 字典支持 `zh` / `en` 两种语言
- 日志配置：RotatingFileHandler (10MB × 5 backups) + StreamHandler

**关键配置项：** 55+ 环境变量（参见第八节完整配置表）

### 4.2 数据导入层 (ingestion/)

#### 4.2.1 数据预处理 (preprocess.py)

**职责：** 将 DiscordChatExporter 导出的 JSON 转为可嵌入的文档块。

**处理流程：**

```
load_exports() → build_qa_pairs() + group_consecutive()
       ↓                    ↓
  filter_owner_messages    Q&A 配对 (问题+回复)
       ↓                    ↓
  clean_message()          合并连续消息 (2分钟窗口)
       ↓                    ↓
  chunk_text()             输出: [{id, text, metadata}]
```

**核心函数：**

- `load_exports(dir)` — 加载所有 `.json` 文件，提取消息和用户信息
- `build_qa_pairs(msgs, owner_id)` — 将 Owner 对用户问题的回复构建为 `Q: ... A: ...` 格式
- `group_consecutive(msgs, owner_id, window=120s)` — 合并 2 分钟内连续发的消息
- `clean_message(content, users)` — 解析 `<@USER_ID>` mention、清理自定义 emoji
- `chunk_text(text, max_tokens=500, overlap=50)` — 在段落/句子边界分块，50 token 重叠
- `filter_owner_messages(msgs, owner_id)` — 过滤仅 Owner 的消息
- `preprocess_all(dir, owner_id)` — 完整流水线

**输出文档格式：**
```python
{
    "id": "msg_123456",
    "text": "做ES的话主要看4小时图...",
    "metadata": {
        "type": "qa_pair" | "standalone" | "grouped",
        "source_message_id": "123456",
        "timestamp": "2023-01-15T10:30:00",
        "channel_id": "...",
        "chunk_index": 0,
        "total_chunks": 1,
    }
}
```

#### 4.2.2 向量化存储 (ingest.py)

**职责：** 将预处理后的文档嵌入并存入 ChromaDB。

**设计要点：**

- **ChromaDB 持久化：** `PersistentClient(path="./chromadb_store")`，cosine 相似度空间
- **增量导入：** 查询已有 ID，跳过已导入文档
- **批量处理：** 每批 100 个文档（`EMBED_BATCH_SIZE`）
- **Token 截断：** 超过 8191 token 的文本自动截断（embedding 模型硬限制）
- **速率保护：** 批次间 0.25s 延迟，`RateLimitError` 时 30s 退避重试
- **进度显示：** tqdm 进度条
- **CLI 参数：** `--sample N`（测试取样）、`--export-dir`、`--owner-id`、`--db-path`

#### 4.2.3 风格分析 (analyze_style.py)

**职责：** 分析 Owner 历史消息的写作风格特征。

**分析维度：**
- 平均回复长度（字/词数）
- 高频短语（bigram / trigram）
- Emoji 使用模式
- 消息长度分布
- 常用开头词
- 中位长度附近的典型消息样本

**输出：** `data/style_profile.txt`，RAG 生成时自动加载入 system prompt。

### 4.3 RAG 核心引擎 (rag.py)

**职责：** 完整的 RAG 流水线 — 检索 → 生成 → 后处理。

#### 检索阶段 (`retrieve_context`)

```python
async def retrieve_context(question, collection, openai_client,
                           top_k=8, max_distance=0.6) -> list[dict]:
```

1. **嵌入查询：** 对问题文本调用 `text-embedding-3-small`（含 LRU 缓存）
2. **向量检索：** ChromaDB `query(n_results=top_k)`
3. **距离过滤：** cosine distance > `RAG_MAX_DISTANCE` 的结果丢弃
4. **去重：** 基于文本头尾 hash 去除近似重复
5. **返回：** `[{text, score, distance, metadata}]` 按相关度排序

#### 生成阶段 (`generate_answer`)

1. **加载风格指南：** 优先读 `data/style_profile.txt`，5 分钟缓存 TTL
2. **构建 System Prompt：** 模板 + 风格 + 负反馈指导
3. **构建 User Prompt：** 检索上下文（区分 Q&A 对和独立帖） + 对话历史 + 问题
4. **调用 GPT-4o-mini：** `temperature=0.5`，`max_tokens=500`
5. **解析置信度：** 正则提取 `CONFIDENCE: X`，解析失败默认 3
6. **价格脱敏：** 正则替换回复中泄露的具体价格数字

#### 价格脱敏 (`_redact_price_levels`)

即使 prompt 规则要求不提价格，LLM 偶尔仍会泄露。后处理层用 10+ 条正则规则做安全网：

- `支撑 3900` → `支撑附近`
- `突破 18000` → `突破关键位`
- `目标价 250` → `目标位`
- `止损 3850` → `止损位`
- `区间 3900-3950` → `对应区间`
- 保留指标参数（EMA13、MA200、RSI 70）和百分比

#### 重试机制 (`_openai_chat_with_retry`)

- `APITimeoutError` / `APIConnectionError` 时自动重试一次
- 二次失败返回 `None`，上层降级为"无法回复"

#### Vision 分析 (`analyze_image`)

```python
async def analyze_image(image_urls, user_text, openai_client,
                        conversation_history="", context_chunks=None):
```

- 使用 GPT-4o Vision 模型分析图表截图
- 支持最多 4 张图片（GPT-4o 限制）
- Vision 专用 system prompt 包含技术分析指导
- 同样应用价格脱敏后处理

### 4.4 置信度路由 (confidence.py)

**职责：** 决定每条回复是自动发送还是转给 Owner 审核。

**路由矩阵：**

| 条件 | 动作 | 原因 |
|------|------|------|
| 信号/交易查询 (`is_signal_query`) | 转 Owner | 需要实时盘面确认 |
| "不确定等频道主" 回复 (`is_fallback_answer`) | 自动回复 | 安全的兜底回复 |
| 无相关上下文 (`context_count == 0`) | 转 Owner | 知识库无覆盖 |
| 上下文距离过高 (`best_distance > 0.95`) | 转 Owner | 匹配质量差 |
| 信心低于阈值 (`confidence < threshold`) | 转 Owner | LLM 不确定 |
| 以上都不满足 | 自动回复 | 高信心 + 高质量上下文 |

**信号查询检测 (`is_signal_query`)：**

多模式正则匹配交易相关问题（中文简繁体），包括：
- 买/卖/做多/做空/开仓/平仓/入场/出场
- 信号/讯号 + 疑问词
- 买点/卖点/入场点/止损点
- "现在可以买吗"、"能不能做多" 等变体

### 4.5 消息监听器 (listener.py)

**职责：** Discord on_message 事件处理、过滤、限流、队列、完整回复流程。

**架构：** `MessageListener(commands.Cog)` — 约 1000+ 行核心模块

#### 消息过滤链 (`_should_skip`)

```
消息进入
  ├─ Bot 消息? → 跳过
  ├─ Owner 消息（非 @bot）? → 跳过（改走自动学习）
  ├─ 频道不在 TARGET_CHANNEL_IDS? → 跳过
  ├─ Thread 且 THREAD_AUTO_REPLY=false? → 跳过
  ├─ 空消息（无文字无图片）? → 跳过
  ├─ 垃圾广告关键词? → 跳过
  ├─ 客气/感谢消息? → 跳过
  └─ 非提问/闲聊（RESPOND_MODE gate）? → 跳过
```

#### 响应触发判断 (`_is_response_warranted`)

| 条件 | 始终响应 |
|------|----------|
| 消息包含图片 | ✅ |
| @mention Bot | ✅ |
| 回复 Bot 的消息 | ✅ |
| 包含问号/提问词 (questions mode) | ✅ |
| 纯聊天 (mention_only mode) | ❌ |

#### 限流机制

- **Per-user Token Bucket：** 1 token / `USER_COOLDOWN_SECONDS` (默认 30s)，burst=1
- **Global Token Bucket：** `GLOBAL_MAX_PER_MINUTE` tokens/min（默认 10），refill_rate = N/60 per sec
- 回复后消耗两个 bucket 各一个 token

#### 对话记忆 (`_channel_memory`)

- **Per-channel 滚动窗口：** `{channel_id: [(timestamp, role, text), ...]}`
- 最多保留 `CONVERSATION_MEMORY_SIZE` 条（默认 10），TTL `CONVERSATION_MEMORY_TTL` 秒（默认 1800）
- 每条消息截断 500 字符
- 自动清理过期频道（超过 50 个频道时触发）

#### 消息处理队列

- `asyncio.Queue` 单 worker 顺序处理（避免并发 API 调用）
- 关机时 best-effort drain 剩余消息
- 每条消息处理完更新 `_last_seen`

#### 自动学习 (`_learn_owner_message`)

Owner 在目标频道发的消息自动嵌入入库：
- 跳过短消息 (<10 字符)、纯 emoji
- 若是对用户问题的回复，构建 Q&A 对格式
- 使用 `live_{message_id}` 作为文档 ID（去重）
- 异步 fire-and-forget，不阻塞主流程

#### 完整处理流程 (`_handle_message`)

```
消息出队 → 构建对话历史
  ├─ Thread? → _fetch_thread_context()
  └─ 普通频道? → _format_memory()
  ↓
  检测图片
  ├─ 有图片? → analyze_image() (Vision)
  └─ 纯文字? → run_rag_pipeline() (RAG)
  ↓
  route_answer() → {action, answer, confidence, reason}
  ↓
  record_query() → BotStats
  ↓
  结构化日志 (JSON)
  ↓
  ├─ auto_reply → message.reply()
  │    ├─ 推广频道? → 附加 CTA (每 N 次)
  │    ├─ Discord 2000 字符截断
  │    ├─ 记入对话记忆
  │    └─ DM Owner 通知
  └─ forward → send_for_review()
       └─ 信号查询 + 推广频道? → 发送 CTA Embed
```

### 4.6 Owner 审核界面 (review.py)

**职责：** 低信心回复的 DM 审核流程。

#### ReviewView (discord.ui.View)

三个按钮：

| 按钮 | 行为 |
|------|------|
| ✅ Approve | 发布草稿到原频道 → 自动学习 Q&A → 停止 View |
| ✏️ Edit | 弹出 Modal（预填草稿 4000 字限制）→ 发布编辑版 → 自动学习 |
| ❌ Reject | 不发布 → 存入负反馈样本 → 停止 View |

**审核 DM Embed 包含：**
- 频道、提问者、置信度
- 原始问题文本
- 草稿回复
- Top 3 检索上下文摘要
- 跳转到原消息链接

**自动学习 (`_learn_qa`)：** Approve/Edit 后将 Q&A 对嵌入存入 ChromaDB（type=`qa_pair`，source=`owner_review`）

**负反馈存储 (`_store_negative_sample`)：** Reject 时将被拒的 Q&A 存入 `data/negative_samples.json`（最多保留 50 条最近的）

**超时：** 1 小时无操作静默过期

**自动回复通知 (`notify_owner_auto_reply`)：** Bot 自动回复时也 DM Owner 一条通知（仅供知悉，无需操作）

### 4.7 ChromaDB 异步封装 (chromadb_async.py)

**职责：** 将 ChromaDB 同步 API 包装为 async。

ChromaDB Python 客户端是同步的，直接在 async 代码中调用会阻塞事件循环。`AsyncCollection` 使用 `asyncio.to_thread` 代理所有调用：

```python
class AsyncCollection:
    async def query(**kwargs) → dict
    async def get(**kwargs) → dict
    async def count() → int
    async def add(**kwargs)
    async def upsert(**kwargs)
    async def delete(**kwargs)
    async def update(**kwargs)
```

### 4.8 Bot 入口 (main.py)

**职责：** 初始化所有组件，注册 Cog，启动 Bot。

**启动顺序：**
1. 验证配置（`DISCORD_BOT_TOKEN`、`OPENAI_API_KEY`）
2. 创建 OpenAI AsyncClient（timeout=60s，retries=0）
3. 加载/创建 ChromaDB collection → AsyncCollection 封装
4. 创建 Discord Bot（intents: message_content + members）
5. 注册 Cog：MessageListener → PromotionCommands → BotCommands → SchedulerCog → HealthCog → ...
6. 启动可选 HTTP 服务（WebhookServer、AdminServer）
7. 注册信号处理（SIGINT/SIGTERM，Windows 兼容）
8. `asyncio.wait` 等待 Bot 运行或 shutdown 信号

**关机流程：**
1. 收到信号 → 设置 `shutdown_event`
2. 停止 HTTP 服务
3. 逐个卸载 Cog（触发各 `cog_unload` 保存状态）
4. 关闭 Bot 连接

---

## 五、Phase 2 — 增强功能设计

### 5.1 E1: Slash Commands (commands.py)

**新文件：** `bot/commands.py`

**BotCommands Cog — 通用命令：**

| 命令 | 权限 | 说明 |
|------|------|------|
| `/ask <question>` | 所有人 | 通过 Slash Command 发起 RAG 查询 |
| `/status` | 所有人 | 显示 Bot 运行时间、队列深度、知识库文档数 |
| `/stats` | Owner | 查询统计（总数、自动回复率、平均信心、热门问题） |

**PromotionCommands Cog — 推广命令（详见 5.9 节）**

### 5.2 E2: 统计追踪 (stats.py)

**新文件：** `bot/stats.py`

**BotStats 类 — 模块级 singleton：**

**追踪指标：**
- `total_queries` — 总查询数
- `auto_replies` / `forwards` — 自动回复 / 转发数
- `total_confidence` / `total_latency_ms` — 累计信心分 / 延迟
- `channel_counts` — 按频道统计 `{channel_id: count}`
- `recent` — 最近 200 条 `QueryRecord`（deque）

**QueryRecord 数据类：**
```python
@dataclass
class QueryRecord:
    question: str
    channel_id: int
    confidence: int
    action: str          # "auto_reply" or "forward"
    latency_ms: int
    timestamp: float
```

**持久化：**
- 每 60 秒异步保存到 `data/stats.json`（脏标记优化）
- 原子写入：先写 `.tmp` 再 `os.replace`
- 启动时自动加载

**API：**
- `record_query(...)` — 记录一次查询
- `snapshot()` → `dict` — JSON 可序列化的统计快照
- `top_questions(limit)` → `list[dict]` — 最近热门问题
- `start_periodic_save()` / `stop()` — 生命周期管理

### 5.3 E3: 负反馈学习

**修改文件：** `bot/review.py`、`bot/rag.py`

**流程：**
1. Owner 点击 ❌ Reject → `_store_negative_sample(question, bad_answer)` → `data/negative_samples.json`
2. 下次生成回复时：`_build_negative_guidance()` 取最近 5 条负样本
3. 注入 System Prompt：`【以下是被频道主拒绝的回答示例，请避免类似的回答方式：】`
4. LLM 参考这些反面教材，避免重复相同错误

**存储格式：** JSON 数组，每条 `{question, bad_answer, timestamp}`，最多 50 条

### 5.4 E4: 嵌入缓存 (cache.py)

**新文件：** `bot/cache.py`

**EmbeddingCache — 模块级 singleton：**

- **LRU 策略：** `OrderedDict`，最多 256 条（`_DEFAULT_MAX_SIZE`）
- **TTL 过期：** 10 分钟（`_DEFAULT_TTL`），`time.monotonic` 计时
- **Key 生成：** `SHA-256(text.strip().lower())`
- **集成点：** `rag.py` 的 `retrieve_context` 在调用 embedding API 前先查缓存
- **统计：** `hits` / `misses` / `hit_rate` — 供 `/status` 命令展示

### 5.5 E5: 令牌桶限流

**修改文件：** `bot/listener.py`

替换原有的简单冷却计时器，改为双层 Token Bucket：

**Per-user Bucket：**
- 容量 1 token，refill rate = 1 / `USER_COOLDOWN_SECONDS`
- 每次消息检查 token 是否 ≥ 1，不足则限流

**Global Bucket：**
- 容量 `GLOBAL_MAX_PER_MINUTE` tokens
- Refill rate = `GLOBAL_MAX_PER_MINUTE` / 60 per second
- 所有用户共享

两个 bucket 均满足后才允许处理消息，回复后各消耗 1 token。

### 5.6 E7: 优雅关机

**修改文件：** `bot/main.py`

**信号处理：**
- SIGINT / SIGTERM → 设置 `shutdown_event` → `asyncio.wait` 返回
- Windows 兼容：`signal.signal` fallback（不支持 `add_signal_handler`）

**关机流程：**
1. 停止 HTTP 服务器（WebhookServer、AdminServer）
2. 逐个卸载 Cog → 触发 `cog_unload()`：
   - `MessageListener.cog_unload()` → 取消 worker/save task → 保存 `last_seen` → `bot_stats.stop()`
   - `SchedulerCog.cog_unload()` → 停止调度循环
   - `HealthCog.cog_unload()` → 停止心跳 → 清理 HTTP runner
3. 关闭 Bot 连接

### 5.7 E8: 多语言支持 (i18n)

**修改文件：** `bot/config.py`

**实现：**
- `BOT_LANGUAGE` 环境变量（`zh` / `en`）
- `LOCALE` 字典：`{lang: {key: string}}`
- `get_locale(key)` 函数，带 fallback 到 `zh`

**已翻译的字符串：**
- 限流提示、无法回复、不确定回复
- Owner 专用提示、频道禁用提示
- 推广相关提示
- 审核按钮结果
- 对话标签（"成员" / "Member"）

### 5.8 E10: 测试覆盖提升

**新文件：** `tests/test_stats.py`、`tests/test_cache.py`、`tests/test_listener.py`、`tests/test_review.py`

| 测试文件 | 覆盖模块 | 说明 |
|----------|----------|------|
| `test_ingestion.py` | preprocess.py | 消息清理、分块、Q&A 配对 |
| `test_rag.py` | rag.py | 检索、生成、价格脱敏 |
| `test_confidence.py` | confidence.py | 路由决策、信号检测、置信度解析 |
| `test_promotion.py` | promo_config.py | CTA 生成、频道检查 |
| `test_stats.py` | stats.py | 记录、快照、持久化 |
| `test_cache.py` | cache.py | LRU、TTL、命中率 |
| `test_listener.py` | listener.py | 过滤链、限流、队列 |
| `test_review.py` | review.py | 审核流程、负反馈 |

**总计：** 139 个测试用例，全部通过

### 5.9 BigTreeSignal 推广系统

**新文件：** `bot/promo_config.py`、`bot/commands.py`（PromotionCommands）、`bot/scheduler.py`、`bot/testimonials.py`

**设计原则：** 推广行为完全隔离在 `PROMO_CHANNEL_IDS`，不影响 `TARGET_CHANNEL_IDS` 的 Q&A 功能。`PROMO_ENABLED` 总开关。

#### 推广工具 (promo_config.py)

- `is_promo_channel(channel_id)` — 频道是否在推广列表
- `get_signal_cta_embed()` — 信号查询 CTA Embed
- `get_auto_reply_cta()` — 自动回复附加 CTA 文本
- `should_append_cta(counter)` — 每 N 次（`CTA_FREQUENCY`）回复附加一次
- `get_welcome_embed(member)` — 新成员欢迎 Embed
- `get_signal_product_embed()` — `/signal` 产品信息 Embed

#### 推广 Slash Commands

| 命令 | 权限 | 说明 |
|------|------|------|
| `/signal` | 所有人 | 展示 BigTreeSignal 产品信息 |
| `/schedule_promo` | Owner | 排程促销帖 |
| `/list_promos` | Owner | 查看排程列表 |
| `/cancel_promo` | Owner | 取消排程 |
| `/post_promo` | Owner | 立即发送促销帖 |
| `/schedule_trial` | Owner | 排程免费试用推广 |
| `/schedule_lesson` | Owner | 排程教学帖（支持重复） |
| `/list_lessons` | Owner | 查看教学排程 |
| `/cancel_lesson` | Owner | 取消教学排程 |
| `/testimonials` | 所有人 | 展示用户见证 |

#### 定时排程 (scheduler.py)

- `SchedulerCog` — 60 秒循环检查 `data/promos.json` 和 `data/lessons.json`
- 到期自动发送 Embed 到指定频道
- 教学帖支持重复（`repeat_days`），到期后自动生成下一次
- CRUD 函数：`add_promo/list_promos/cancel_promo` + `add_lesson/list_lessons/cancel_lesson`

#### 用户见证 (testimonials.py)

- 自动检测用户发的盈利/跟单消息（`_TESTIMONIAL_PATTERNS`）
- DM Owner 审核（Approve / Reject）
- Approve 后转发到 `TESTIMONIAL_CHANNEL_ID`
- 持久化到 `data/testimonials.json`

#### CTA 触发时机

| 场景 | 行为 |
|------|------|
| 自动回复（推广频道） | 每 `CTA_FREQUENCY` 次附加 CTA 文本 |
| 信号查询转发（推广频道） | 发送 Signal CTA Embed |
| 新成员加入（含推广频道的 Guild） | DM 欢迎 Embed |

### 5.10 离线回填 (Offline Backfill)

**修改文件：** `bot/listener.py`

**目的：** Bot 掉线/重启后，自动扫描目标频道，找出下线期间未回答的问题并补答。

**流程：**

1. `on_ready` → `_backfill_offline_messages()`（带 asyncio.Lock 防重复）
2. 确定扫描起点：
   - 有 `last_seen[channel_id]`? → 从该消息 ID 之后开始
   - 首次运行? → 回看 `OFFLINE_BACKFILL_LOOKBACK_HOURS` 小时
3. 获取消息历史（最多 `OFFLINE_BACKFILL_MAX_PER_CHANNEL` 条/频道）
4. 标记已回答的问题：
   - 方式一：Discord 明确回复（message reference）
   - 方式二：Owner 在问题后 N 分钟内发帖（`OWNER_REPLY_WINDOW_MINUTES` 启发式）
5. 未回答的问题入队处理
6. Owner 的离线消息走自动学习入库

**状态持久化：** `data/last_seen.json` — 每 30 秒定期保存 + 关机保存

### 5.11 多源数据导入 (YouTube / PDF)

#### YouTube 视频导入 (ingest_youtube.py)

**流程：**
```
视频 URL → 尝试获取字幕 (youtube_transcript_api)
  ├─ 有字幕 → 直接使用（免费、即时）
  └─ 无字幕 → 下载音频 (yt-dlp, 32K mono MP3)
       ├─ < 24MB → 直接 Whisper API 转录
       └─ > 24MB → 10 分钟分段 → 逐段转录 → 合并
  ↓
  chunk → embed → ChromaDB（增量，已导入的自动跳过）
```

**CLI：** `--urls "URL1" "URL2"` / `--url-file list.txt` / `--whisper-lang zh` / `--no-whisper`

**成本：** Whisper ~$0.006/10 分钟

#### PDF 书籍导入 (ingest_pdf.py)

**流程：**
```
PDF 文件 → PyMuPDF 逐页提取文本
  → 清理（去页眉页脚、合并连字符换行）
  → chunk → embed → ChromaDB
```

**CLI：** `--files "book.pdf"` / `--source "书名"` / `--dry-run`

**特性：** MD5 hash 生成文档 ID，支持增量导入

### 5.12 Vision 图片分析

**集成在：** `bot/rag.py` + `bot/listener.py`

- 检测消息中的图片附件和 Embed 图片（最多 4 张）
- 使用 GPT-4o Vision 模型分析
- Vision 专用 system prompt（技术分析导向）
- 同样应用价格脱敏
- 纳入置信度路由流程

### 5.13 健康检查 (health.py)

**新文件：** `bot/health.py`

**HealthCog 提供：**

1. **心跳日志：** 每 5 分钟输出 uptime、guild 数、WebSocket 延迟
2. **HTTP /health 端点（可选）：** 设置 `HEALTH_PORT` 后启用
   - `GET /health` → `{status, uptime_seconds, guilds, ws_latency_ms}`
   - 200 = 就绪，503 = 未就绪
   - 用于 Docker / k8s 健康检查

---

## 六、数据流架构

### 完整消息处理流

```
用户发消息
  ↓
  on_message()
  ├─ Owner 消息? → _learn_owner_message() → ChromaDB
  ├─ Owner 语音? → _handle_voice_message() → Whisper → ChromaDB
  ├─ 用户见证? → _handle_testimonial() → DM Owner 审核
  ├─ _should_skip()? → 丢弃
  └─ _is_rate_limited()? → 丢弃
  ↓
  _queue.put(message)
  ↓
  _process_queue() → _handle_message()
  ├─ 构建对话历史 (Thread / Channel memory)
  ├─ 检测图片
  │  ├─ 有图片 → analyze_image() (GPT-4o Vision)
  │  └─ 纯文字 → run_rag_pipeline()
  │       ├─ retrieve_context() → ChromaDB
  │       └─ generate_answer() → GPT-4o-mini
  ├─ route_answer() → auto_reply / forward_to_owner
  ├─ bot_stats.record_query()
  ├─ 结构化 JSON 日志
  └─ 发送回复 / DM 审核
```

### 知识库增长路径

```
1. 离线导入 (一次性)
   Discord JSON → preprocess → ingest → ChromaDB

2. YouTube 导入 (一次性)
   Video → transcript/whisper → chunk → ingest → ChromaDB

3. PDF 导入 (一次性)
   PDF → PyMuPDF → chunk → ingest → ChromaDB

4. 实时自动学习 (持续)
   Owner 文字消息 → embed → ChromaDB (type=owner_post / qa_pair)
   Owner 语音消息 → Whisper → embed → ChromaDB (type=owner_voice)

5. 审核学习 (持续)
   Approve/Edit → embed Q&A pair → ChromaDB (type=qa_pair, source=owner_review)
```

---

## 七、文件清单

### Bot 运行层 (`bot/`)

| 文件 | 行数 | 说明 |
|------|------|------|
| `main.py` | 175 | Bot 入口：初始化、Cog 注册、信号处理、优雅关机 |
| `config.py` | 265 | 全部配置、System Prompt 模板、Locale 字典 |
| `listener.py` | 1038 | 消息监听：过滤、限流、队列、RAG 流程、自动学习、回填 |
| `rag.py` | 457 | RAG 核心：检索、生成、Vision、价格脱敏 |
| `confidence.py` | 134 | 置信度路由、信号查询检测 |
| `review.py` | 395 | Owner DM 审核（Approve/Edit/Reject）、负反馈存储 |
| `commands.py` | 624 | Slash Commands（通用 + 推广 + FAQ） |
| `stats.py` | 183 | BotStats 统计 singleton、持久化 |
| `cache.py` | 73 | EmbeddingCache LRU + TTL |
| `chromadb_async.py` | 44 | ChromaDB async 封装 |
| `health.py` | 101 | 心跳日志 + HTTP /health |
| `promo_config.py` | 144 | 推广工具函数 |
| `scheduler.py` | 287 | 定时推广/教学帖调度 |
| `testimonials.py` | 244 | 用户见证收集与审核 |

### 数据导入层 (`ingestion/`)

| 文件 | 行数 | 说明 |
|------|------|------|
| `preprocess.py` | 335 | 消息预处理：加载、Q&A 配对、分组、清理、分块 |
| `ingest.py` | 221 | 嵌入 + ChromaDB 存储（批量、增量） |
| `analyze_style.py` | 147 | 风格特征分析 |
| `ingest_youtube.py` | 530 | YouTube 视频导入（字幕 + Whisper） |
| `ingest_pdf.py` | 210 | PDF 书籍导入 |

### 测试 (`tests/`)

| 文件 | 说明 |
|------|------|
| `test_ingestion.py` | 预处理逻辑测试 |
| `test_rag.py` | RAG 流水线测试 |
| `test_confidence.py` | 路由决策测试 |
| `test_promotion.py` | 推广功能测试 |
| `test_stats.py` | 统计模块测试 |
| `test_cache.py` | 缓存模块测试 |
| `test_listener.py` | 监听器过滤/限流测试 |
| `test_review.py` | 审核流程测试 |

---

## 八、配置参数总表

### 必填

| 变量 | 说明 |
|------|------|
| `DISCORD_BOT_TOKEN` | Discord Bot Token |
| `OPENAI_API_KEY` | OpenAI API Key |
| `OWNER_USER_ID` | 频道主 Discord 用户 ID |
| `TARGET_CHANNEL_IDS` | 监听频道 ID（逗号分隔） |

### OpenAI 模型

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_MODEL` | `gpt-4o-mini` | 生成模型 |
| `VISION_MODEL` | `gpt-4o` | Vision 模型 |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | 嵌入模型 |
| `LLM_MAX_TOKENS` | `500` | 最大生成 token 数 |
| `LLM_TEMPERATURE` | `0.5` | 生成温度 |

### RAG

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RAG_TOP_K` | `8` | 检索结果数 |
| `RAG_MAX_DISTANCE` | `0.6` | 最大 cosine distance |
| `CONFIDENCE_THRESHOLD` | `7` | 自动回复最低信心 |

### 对话与限流

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CONVERSATION_MEMORY_SIZE` | `10` | 对话记忆条数 |
| `CONVERSATION_MEMORY_TTL` | `1800` | 对话记忆过期秒数 |
| `USER_COOLDOWN_SECONDS` | `30` | 用户冷却秒数 |
| `GLOBAL_MAX_PER_MINUTE` | `10` | 全局每分钟最大回复数 |
| `RESPOND_MODE` | `questions` | 响应模式 (questions/mention_only/all) |

### 离线回填

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OFFLINE_BACKFILL_ENABLED` | `true` | 总开关 |
| `OFFLINE_BACKFILL_LOOKBACK_HOURS` | `24` | 首次回看小时数 |
| `OFFLINE_BACKFILL_MAX_PER_CHANNEL` | `100` | 每频道最大扫描消息数 |
| `OFFLINE_BACKFILL_OWNER_REPLY_WINDOW_MINUTES` | `10` | Owner 回复窗口分钟数 |
| `OFFLINE_LAST_SEEN_FILE` | `data/last_seen.json` | 状态持久化文件 |

### 数据导入

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CHROMADB_PATH` | `./chromadb_store` | ChromaDB 存储路径 |
| `EXPORT_DIR` | `./data/exports` | 导出文件目录 |
| `CHUNK_MAX_TOKENS` | `500` | 分块最大 token 数 |
| `CHUNK_OVERLAP_TOKENS` | `50` | 分块重叠 token 数 |
| `EMBED_BATCH_SIZE` | `100` | 嵌入批量大小 |

### 推广

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PROMO_ENABLED` | `true` | 推广总开关 |
| `PROMO_CHANNEL_IDS` | (空) | 推广频道 ID 列表 |
| `SIGNAL_PRODUCT_NAME` | `BigTreeSignal` | 产品名称 |
| `SIGNAL_PRODUCT_URL` | (空) | 产品链接 |
| `SIGNAL_CTA_TEXT` | 想获取实时交易信号？... | CTA 文本 |
| `AUTO_REPLY_CTA_TEXT` | 想获取实时交易信号？... | 自动回复 CTA |
| `CTA_FREQUENCY` | `5` | 每 N 次回复附加 CTA |
| `FREE_TRIAL_ENABLED` | `false` | 免费试用开关 |
| `FREE_TRIAL_URL` | (空) | 试用链接 |
| `WELCOME_MESSAGE` | 欢迎加入！... | 新成员欢迎语 |
| `TESTIMONIAL_CHANNEL_ID` | `0` | 见证频道 ID |
| `TESTIMONIAL_DETECTION_ENABLED` | `true` | 自动检测见证 |

### 其他

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BOT_LANGUAGE` | `zh` | 界面语言 (zh/en) |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `HEALTH_PORT` | `0` | 健康检查端口 (0=禁用) |

---

## 九、安全设计

| 层面 | 措施 |
|------|------|
| API 密钥 | `.env` 文件管理，`.gitignore` 排除，Docker 用 `env_file` |
| 输入注入 | 用户消息包装在 context framing 中，不直接注入 system prompt |
| 限流 | 双层 Token Bucket 防滥用和成本失控 |
| 金融安全 | System prompt 严禁编造投资建议；价格脱敏后处理 |
| 信号查询 | 强制转 Owner 审核，不自动回复交易指令 |
| 权限最小化 | Bot 仅需 Read/Send Messages + Read History + Slash Commands |
| 频道隔离 | `TARGET_CHANNEL_IDS`（Q&A）与 `PROMO_CHANNEL_IDS`（推广）完全独立 |
| 原子写入 | 所有 JSON 持久化使用 `.tmp` → `os.replace` 原子操作 |
| Docker 安全 | 不在镜像中烘焙密钥 |

---

## 十、依赖清单

```
discord.py>=2.3.0         # Discord API
openai>=1.30.0            # GPT / Embedding / Whisper
chromadb>=0.5.0            # 向量数据库
python-dotenv>=1.0.0       # .env 配置
tiktoken>=0.7.0            # Token 计数
aiohttp>=3.9.0             # HTTP 服务 (health/webhook/admin)
tqdm>=4.66.0               # 进度条 (ingestion)
youtube-transcript-api>=0.6.0  # YouTube 字幕获取
yt-dlp>=2024.1.0           # YouTube 音频下载
pymupdf>=1.24.0            # PDF 文本提取
```

**运行环境：** Python 3.11+（使用 `type | None` 联合类型语法）
