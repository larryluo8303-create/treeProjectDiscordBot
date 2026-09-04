> **归档文档**：历史设计/阶段指南，仅供参考。现行说明见上级目录的 PROJECT_GUIDE / FEATURE_LIST / SETUP_AND_TEST 等。

# Phase 1 & Phase 2: 核心功能与增强功能 — 用户指南

---

## 目录

- [一、快速开始](#一快速开始)
- [二、从零部署完整流程](#二从零部署完整流程)
  - [2.1 创建 Discord Bot](#21-创建-discord-bot)
  - [2.2 获取 OpenAI API Key](#22-获取-openai-api-key)
  - [2.3 安装环境与依赖](#23-安装环境与依赖)
  - [2.4 配置 .env](#24-配置-env)
  - [2.5 导出 Discord 历史](#25-导出-discord-历史)
  - [2.6 导入数据](#26-导入数据)
  - [2.7 启动 Bot](#27-启动-bot)
- [三、数据导入详解](#三数据导入详解)
  - [3.1 Discord 历史导入](#31-discord-历史导入)
  - [3.2 风格分析](#32-风格分析)
  - [3.3 YouTube 视频导入](#33-youtube-视频导入)
  - [3.4 PDF 书籍导入](#34-pdf-书籍导入)
- [四、核心功能使用](#四核心功能使用)
  - [4.1 自动回复如何运作](#41-自动回复如何运作)
  - [4.2 Owner 审核流程](#42-owner-审核流程)
  - [4.3 自动学习](#43-自动学习)
  - [4.4 图片分析](#44-图片分析)
  - [4.5 离线回填](#45-离线回填)
  - [4.6 对话记忆](#46-对话记忆)
- [五、Slash 命令参考](#五slash-命令参考)
  - [5.1 通用命令](#51-通用命令)
  - [5.2 推广命令](#52-推广命令)
- [六、推广系统使用](#六推广系统使用)
  - [6.1 开启推广](#61-开启推广)
  - [6.2 CTA 触发](#62-cta-触发)
  - [6.3 排程推广帖](#63-排程推广帖)
  - [6.4 教学帖排程](#64-教学帖排程)
  - [6.5 用户见证收集](#65-用户见证收集)
  - [6.6 新成员欢迎](#66-新成员欢迎)
- [七、配置调优](#七配置调优)
  - [7.1 响应模式](#71-响应模式)
  - [7.2 信心阈值调优](#72-信心阈值调优)
  - [7.3 限流调整](#73-限流调整)
  - [7.4 多语言切换](#74-多语言切换)
- [八、监控与运维](#八监控与运维)
  - [8.1 日志系统](#81-日志系统)
  - [8.2 健康检查](#82-健康检查)
  - [8.3 统计查看](#83-统计查看)
- [九、部署方案](#九部署方案)
  - [9.1 本地运行](#91-本地运行)
  - [9.2 Docker 部署](#92-docker-部署)
  - [9.3 systemd 部署](#93-systemd-部署)
- [十、测试](#十测试)
- [十一、常见问题 (FAQ)](#十一常见问题-faq)
- [十二、配置参考总表](#十二配置参考总表)

---

## 一、快速开始

**前提条件：** Python 3.11+、Discord Bot Token、OpenAI API Key

```powershell
# 1. 创建虚拟环境
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
copy .env.example .env
# 编辑 .env 填入真实值

# 4. 导出 Discord 历史到 data/exports/（见 2.5 节）

# 5. 导入数据
python -m ingestion.ingest

# 6. （可选）分析风格
python -m ingestion.analyze_style

# 7. 启动 Bot
python -m bot.main
```

Bot 启动后你会看到：

```
[INFO] bot.main: OpenAI client initialized
[INFO] bot.main: ChromaDB collection loaded — XXXXX documents
[INFO] bot.main: Starting Discord bot...
[INFO] bot.listener: Bot is ready — starting message queue worker
```

---

## 二、从零部署完整流程

### 2.1 创建 Discord Bot

> 预计时间：~10 分钟

1. 访问 https://discord.com/developers/applications
2. 点击 **New Application** → 命名（如 "TreeBot Auto-Reply"）
3. 左侧 **Bot** → **Reset Token** → **复制并保存 Token**
4. 启用 Privileged Gateway Intents：
   - ✅ MESSAGE CONTENT INTENT（必需）
   - ✅ SERVER MEMBERS INTENT（推荐）
5. 左侧 **OAuth2 → URL Generator**：
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: Read Messages, Send Messages, Read Message History, Use Slash Commands
6. 复制生成的 URL → 在浏览器中打开 → 邀请 Bot 到你的服务器
7. 获取你的 **User ID**：Discord 设置 → 高级 → 开启开发者模式 → 右键自己名字 → Copy ID
8. 获取 **Channel ID**：右键目标频道 → Copy ID

### 2.2 获取 OpenAI API Key

> 预计时间：~5 分钟

1. 访问 https://platform.openai.com/api-keys
2. 创建新密钥 → 复制并保存
3. 设置消费限额：https://platform.openai.com/settings/organization/limits

### 2.3 安装环境与依赖

```powershell
# 确认 Python 版本
python --version    # 需要 3.11+

# 创建虚拟环境
python -m venv .venv

# 激活（PowerShell）
.venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt
```

### 2.4 配置 .env

```powershell
copy .env.example .env
```

编辑 `.env` 填入真实值：

```env
# 必填
DISCORD_BOT_TOKEN=你的Bot Token
OPENAI_API_KEY=你的OpenAI Key
OWNER_USER_ID=你的Discord User ID
TARGET_CHANNEL_IDS=频道ID1,频道ID2

# 推荐保持默认
CONFIDENCE_THRESHOLD=7
RAG_TOP_K=8
RESPOND_MODE=questions
BOT_LANGUAGE=zh
```

> **安全提醒：** `.env` 文件已在 `.gitignore` 中，绝不要提交到版本控制。

### 2.5 导出 Discord 历史

> 预计时间：15-60 分钟（取决于频道大小）

1. 下载 [DiscordChatExporter CLI](https://github.com/Tyrrrz/DiscordChatExporter/releases)
2. 导出频道历史为 JSON：

```powershell
# 单个频道
DiscordChatExporter.Cli export -t "BOT_TOKEN" -c CHANNEL_ID -f Json -o "data\exports\channel.json"

# 大频道分段导出
DiscordChatExporter.Cli export -t "BOT_TOKEN" -c CHANNEL_ID -f Json --after "2020-01-01" --before "2023-01-01" -o "data\exports\ch_2020_2022.json"
DiscordChatExporter.Cli export -t "BOT_TOKEN" -c CHANNEL_ID -f Json --after "2023-01-01" -o "data\exports\ch_2023_now.json"
```

3. 确认 `data/exports/` 目录下有 `.json` 文件

### 2.6 导入数据

```powershell
# 测试导入（100 条）
python -m ingestion.ingest --sample 100

# 完整导入
python -m ingestion.ingest

# 验证
python -c "import chromadb; c = chromadb.PersistentClient('./chromadb_store'); col = c.get_collection('bigtree_knowledge'); print(f'Documents: {col.count()}')"
```

**预计时间：** 200K 消息 → 15-30 分钟
**预计费用：** ~$1-3（一次性）

### 2.7 启动 Bot

```powershell
python -m bot.main
```

停止：按 `Ctrl+C`（会触发优雅关机，保存所有状态）

---

## 三、数据导入详解

### 3.1 Discord 历史导入

**导入流水线：**

```
data/exports/*.json
    ↓ load_exports() — 加载所有 JSON
    ↓ filter_owner_messages() — 只保留 Owner 的消息
    ↓ build_qa_pairs() — 构建 Q&A 配对（Owner 回复用户问题）
    ↓ group_consecutive() — 合并 2 分钟内连续发的消息
    ↓ clean_message() — 清理 mention、emoji 格式
    ↓ chunk_text() — 超过 500 token 的分块（50 token 重叠）
    ↓ embed → ChromaDB
```

**特性：**

- **增量导入：** 重复运行会自动跳过已导入的文档
- **Q&A 配对：** Owner 回复用户消息时，自动构建 `Q: ... A: ...` 格式，提升检索质量
- **批量处理：** 每批 100 个（`EMBED_BATCH_SIZE`），带速率保护

**CLI 参数：**

```powershell
python -m ingestion.ingest                          # 完整导入
python -m ingestion.ingest --sample 100             # 取样测试
python -m ingestion.ingest --export-dir ./my_data   # 自定义路径
python -m ingestion.ingest --owner-id 12345         # 指定 Owner ID
python -m ingestion.ingest --db-path ./my_db        # 自定义 DB 路径
```

### 3.2 风格分析

```powershell
python -m ingestion.analyze_style
```

分析 Owner 的写作风格并保存到 `data/style_profile.txt`：

- 平均回复长度
- 高频短语
- Emoji 使用习惯
- 消息长度分布
- 典型风格样本

Bot 启动时自动加载此文件，使生成的回复更接近 Owner 风格。

> **推荐：** 始终运行此步骤。你也可以手动编辑 `data/style_profile.txt` 来微调风格。

### 3.3 YouTube 视频导入

将你的 YouTube 视频内容导入知识库：

```powershell
# 单个视频
python -m ingestion.ingest_youtube --urls "https://www.youtube.com/watch?v=VIDEO_ID"

# 多个视频
python -m ingestion.ingest_youtube --urls "https://youtu.be/AAA" "https://youtu.be/BBB"

# 从文件批量导入
python -m ingestion.ingest_youtube --url-file my_videos.txt

# 指定 Whisper 语言
python -m ingestion.ingest_youtube --urls "URL" --whisper-lang zh

# 仅导入有字幕的视频（跳过 Whisper）
python -m ingestion.ingest_youtube --urls "URL" --no-whisper
```

**自动检测路径：**

- 有字幕 → 直接使用（免费）
- 无字幕 → yt-dlp 下载音频 → Whisper API 转录（~$0.006/10分钟）
- 大文件 (>24MB) → 自动分段转录

**前置要求：** 安装 ffmpeg

```powershell
winget install Gyan.FFmpeg
```

### 3.4 PDF 书籍导入

```powershell
# 单个 PDF
python -m ingestion.ingest_pdf --files "path/to/book.pdf"

# 多个 PDF
python -m ingestion.ingest_pdf --files "book1.pdf" "book2.pdf"

# 指定来源标签
python -m ingestion.ingest_pdf --files "book.pdf" --source "股市操盘圣经"

# 预览（不写入 DB）
python -m ingestion.ingest_pdf --files "book.pdf" --dry-run
```

---

## 四、核心功能使用

### 4.1 自动回复如何运作

当用户在目标频道发消息时，Bot 执行以下流程：

1. **过滤：** 跳过 Bot 消息、Owner 消息、非目标频道、垃圾广告、感谢/客气消息
2. **意图检测：** 根据 `RESPOND_MODE` 判断是否需要回复
   - `questions` — 只回复包含问号或提问词的消息（默认）
   - `mention_only` — 只回复 @mention Bot 的消息
   - `all` — 回复所有消息
3. **限流：** 每用户 30 秒冷却，全局每分钟最多 10 次
4. **RAG 检索：** 从知识库检索最相关的历史帖子
5. **生成回复：** GPT-4o-mini 基于检索到的上下文生成 Owner 风格的回复
6. **置信度路由：**
   - 信心 ≥ 7 + 有相关上下文 → **自动回复**（Owner 收到通知 DM）
   - 信心 < 7 / 无上下文 / 交易信号问题 → **转 Owner 审核**

**Bot 始终响应的情况：**

- 消息包含图片（视为图表分析请求）
- @mention Bot
- 回复 Bot 之前的消息

### 4.2 Owner 审核流程

低信心回复会以 DM 形式发送给 Owner：

**DM 内容包含：**

- 📌 频道名称
- 👤 提问者
- 📊 置信度分数（X/10）
- ❓ 原始问题
- 📝 草稿回复
- 🔗 上下文摘要（Top 3）
- 🔗 跳转到原消息链接

**三个操作按钮：**

| 按钮 | 效果 |
|------|------|
| ✅ **Approve** | 直接发布草稿到原频道，并自动学习此 Q&A |
| ✏️ **Edit** | 弹出编辑框（预填草稿），修改后发布，并自动学习 |
| ❌ **Reject** | 不发布回复，存入负反馈库供未来参考 |

**注意事项：**

- 按钮 1 小时后过期
- 同一审核只能操作一次（防重复点击）
- Bot 必须保持运行才能处理按钮点击
- 确保你的 Discord DM 已开启

**自动回复通知：** Bot 自动回复时也会 DM 你一条通知（绿色 Embed，仅供知悉）

### 4.3 自动学习

Bot 会自动从以下来源学习新知识：

| 来源 | 触发方式 | 文档类型 |
|------|----------|----------|
| Owner 在目标频道发的文字消息 | 实时自动 | `owner_post` / `qa_pair` |
| Owner 的语音消息 | 实时自动（Whisper 转录） | `owner_voice` |
| Approve/Edit 的审核回复 | Owner 操作后 | `qa_pair` (source=`owner_review`) |
| 离线回填期间的 Owner 消息 | Bot 重启时 | `owner_post` / `qa_pair` |

**自动学习规则：**

- 跳过太短的消息 (<10 字符)
- 跳过纯 emoji 消息
- 如果 Owner 是回复某人的问题 → 构建 Q&A 对格式
- 使用消息 ID 去重，同一消息不会重复导入

### 4.4 图片分析

用户在目标频道发送图片（K线图、技术指标截图等），Bot 会：

1. 提取图片 URL（支持附件 + Embed 图片，最多 4 张）
2. 如果有文字描述 → 检索 RAG 上下文供参考
3. 使用 GPT-4o Vision 分析图片
4. 回复包含技术分析（趋势、形态、指标信号）
5. 自动脱敏具体价格数字

**示例交互：**

```
用户: [上传一张K线图] 这个走势怎么看？
Bot: 从图上看，目前价格在均线附近震荡，MACD出现金叉信号...
```

### 4.5 离线回填

Bot 掉线或重启后，会自动扫描目标频道补答错过的问题。

**配置：**

```env
OFFLINE_BACKFILL_ENABLED=true           # 总开关
OFFLINE_BACKFILL_LOOKBACK_HOURS=12      # 首次启动回看小时数
OFFLINE_BACKFILL_MAX_PER_CHANNEL=100    # 每频道最大扫描数
OFFLINE_BACKFILL_OWNER_REPLY_WINDOW_MINUTES=15   # Owner 回复窗口
```

**智能跳过已答问题：**

- 被 Owner 或 Bot 明确回复过的（Discord reply）
- Owner 在问题后 15 分钟内发了实质性帖子（启发式判断 Owner 当时在线）

**状态持久化：** 每个频道最后处理的消息 ID 存在 `data/last_seen.json`，重启后从上次位置继续。

### 4.6 对话记忆

Bot 维护每个频道的短期对话记忆，支持连续对话：

```
用户: ES现在怎么看？
Bot: 目前ES在关键位附近...

用户: 那NQ呢？（Bot 理解这是接着问的）
Bot: NQ的话，技术面上...
```

**配置：**

```env
CONVERSATION_MEMORY_SIZE=10    # 保留最近 N 条
CONVERSATION_MEMORY_TTL=1800   # 过期时间（秒）= 30 分钟
```

**Thread 支持：** 在 Thread 中回复时，Bot 会获取整个 Thread 的历史作为上下文（最近 `THREAD_CONTEXT_MESSAGES` 条，默认 15）。

```env
THREAD_AUTO_REPLY=true         # 是否在 Thread 中自动回复
THREAD_CONTEXT_MESSAGES=15     # Thread 上下文消息数
```

---

## 五、Slash 命令参考

### 5.1 通用命令

| 命令 | 权限 | 说明 |
|------|------|------|
| `/ask <question>` | 所有人 | 直接向 Bot 提问（不用在聊天中发消息） |
| `/status` | 所有人 | 查看 Bot 运行状态：运行时间、队列深度、知识库文档数 |
| `/stats` | Owner | 查看详细统计：总查询数、自动回复率、平均信心、热门问题 |
| `/faq` | 所有人 | 查看自动生成的常见问题 |
| `/generate_faq` | Owner | 根据高频高信心 Q&A 自动生成 FAQ |

**`/ask` 使用示例：**

```
/ask question:ES日线怎么看？
```

Bot 会以 ephemeral 消息回复（仅你可见），适合不想在公屏发问的场景。

**`/stats` 输出示例：**

```
📊 Bot 统计
总查询: 1234
自动回复: 890 (72.1%)
转发审核: 344 (27.9%)
平均信心: 7.2
平均延迟: 1.8s

最近热门问题:
1. ES今天怎么操作 (信心: 8)
2. BTC走势分析 (信心: 7)
...
```

### 5.2 推广命令

| 命令 | 权限 | 说明 |
|------|------|------|
| `/signal` | 所有人 | 展示 BigTreeSignal 产品信息 |
| `/schedule_promo` | Owner | 排程促销帖 |
| `/list_promos` | Owner | 查看排程列表 |
| `/cancel_promo <id>` | Owner | 取消排程 |
| `/post_promo` | Owner | 立即发送促销帖 |
| `/schedule_trial` | Owner | 排程免费试用推广 |
| `/schedule_lesson` | Owner | 排程教学帖（支持重复） |
| `/list_lessons` | Owner | 查看教学排程 |
| `/cancel_lesson <id>` | Owner | 取消教学排程 |
| `/testimonials` | 所有人 | 查看用户见证 |

---

## 六、推广系统使用

### 6.1 开启推广

在 `.env` 中配置：

```env
PROMO_ENABLED=true
PROMO_CHANNEL_IDS=频道ID1,频道ID2    # 与 TARGET_CHANNEL_IDS 独立
SIGNAL_PRODUCT_NAME=BigTreeSignal
SIGNAL_PRODUCT_URL=https://your-product-url.com
```

**重要：** `PROMO_CHANNEL_IDS` 和 `TARGET_CHANNEL_IDS` 是独立的列表。你可以在同一个频道同时启用 Q&A 和推广，也可以分开。

### 6.2 CTA 触发

| 场景 | 触发条件 | 行为 |
|------|----------|------|
| 自动回复 CTA | 推广频道中每 `CTA_FREQUENCY` 次回复 | 在回复末尾附加 CTA 文本 |
| 信号查询 CTA | 推广频道中检测到交易信号问题 | 发送独立的 CTA Embed |
| 新成员欢迎 | 成员加入含推广频道的 Guild | DM 发送欢迎 Embed |

**CTA 频率配置：**

```env
CTA_FREQUENCY=5              # 每 5 次自动回复附加一次 CTA（0=禁用）
AUTO_REPLY_CTA_TEXT=想获取实时交易信号？了解 BigTreeSignal →
SIGNAL_CTA_TEXT=想获取实时交易信号？了解 BigTreeSignal
```

### 6.3 排程推广帖

```
/schedule_promo title:限时优惠 description:所有套餐8折 time:2025-01-15 10:00 url:https://...
```

**参数：**

- `title` — 促销标题
- `description` — 详细描述
- `time` — 发送时间 (YYYY-MM-DD HH:MM, UTC-4)
- `url` — 促销链接（可选，默认产品链接）
- `channel` — 目标频道（可选，默认所有推广频道）

到时间后 Bot 自动发送 Embed 到指定频道。

**查看/取消：**

```
/list_promos        → 查看所有排程
/cancel_promo id:promo_abc12345   → 取消指定排程
```

### 6.4 教学帖排程

```
/schedule_lesson title:每周技术分析 content:本周重点关注均线突破... time:2025-01-15 20:00 repeat_days:7
```

`repeat_days` 设为 7 表示每周重复。到期发送后自动安排下一次。

### 6.5 用户见证收集

**自动检测：** 当用户在推广频道发消息包含盈利/跟单关键词（如"赚了"、"翻倍"、"信号准"），Bot 自动 DM 你审核。

```env
TESTIMONIAL_DETECTION_ENABLED=true
TESTIMONIAL_CHANNEL_ID=你的user-wins频道ID
```

Approve 后自动转发到 `#user-wins` 频道。

**手动查看：**

```
/testimonials    → 展示最近的已批准见证
```

### 6.6 新成员欢迎

当新成员加入包含推广频道的 Guild，Bot 自动 DM 发送欢迎信息：

```env
WELCOME_MESSAGE=欢迎加入！这里是 BigTree 的股票分析社群。
FREE_TRIAL_ENABLED=true
FREE_TRIAL_URL=https://your-trial-url.com
```

---

## 七、配置调优

### 7.1 响应模式

```env
RESPOND_MODE=questions      # 默认：只回复提问消息
```

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `questions` | 只回复包含问号/提问词的消息 | 活跃频道，避免打扰 |
| `mention_only` | 只回复 @mention Bot 的消息 | 最保守，用户主动触发 |
| `all` | 回复所有消息（仍有过滤） | 小频道，全覆盖 |

**所有模式下始终响应的：** 图片消息、@mention、回复 Bot 的消息

### 7.2 信心阈值调优

```env
CONFIDENCE_THRESHOLD=7     # 默认：7/10
```

**调优建议：**

| 运行情况 | 建议 |
|----------|------|
| >90% 审核都 Approve | 降低到 6，让更多回复自动发送 |
| <70% 审核 Approve | 提高到 8，收紧自动回复标准 |
| 测试阶段 | 设为 5，观察自动回复质量 |
| 刚上线 | 设为 9，先以审核为主，逐步降低 |

### 7.3 限流调整

```env
USER_COOLDOWN_SECONDS=30    # 同一用户两次回复间隔
GLOBAL_MAX_PER_MINUTE=10    # 全局每分钟最大回复数
```

**场景建议：**

- **大频道（1000+ 在线）：** `USER_COOLDOWN_SECONDS=60`, `GLOBAL_MAX_PER_MINUTE=5`
- **小频道（<50 在线）：** `USER_COOLDOWN_SECONDS=15`, `GLOBAL_MAX_PER_MINUTE=20`
- **活动/教学时段：** 临时调高 `GLOBAL_MAX_PER_MINUTE`

### 7.4 多语言切换

```env
BOT_LANGUAGE=zh    # zh = 中文（默认），en = English
```

影响：限流提示、错误消息、审核通知等系统文本的语言。

---

## 八、监控与运维

### 8.1 日志系统

**输出位置：**

- **控制台：** 实时输出
- **文件：** `logs/bot.log`（RotatingFileHandler, 10MB × 5 backups）

**每条查询的结构化日志：**

```json
{
  "event": "query_processed",
  "question": "ES怎么看？",
  "author_id": 123456789,
  "channel_id": 987654321,
  "confidence": 8,
  "action": "auto_reply",
  "reason": "confidence meets threshold",
  "context_count": 5,
  "best_distance": 0.23,
  "response_time_ms": 1450
}
```

**日志级别控制：**

```env
LOG_LEVEL=INFO    # DEBUG / INFO / WARNING / ERROR
```

### 8.2 健康检查

```env
HEALTH_PORT=8080    # 设为 0 禁用
```

启用后访问 `http://localhost:8080/health`：

```json
{
  "status": "ok",
  "uptime_seconds": 3600.5,
  "guilds": 1,
  "ws_latency_ms": 45.2
}
```

- 200 = Bot 就绪
- 503 = Bot 未就绪

适用于 Docker / k8s 健康检查探针。

**心跳日志：** 每 5 分钟自动输出 uptime 和延迟信息（无需配置）。

### 8.3 统计查看

**方式一：Slash 命令**

```
/stats    → Discord 内查看统计
/status   → 查看运行状态
```

**方式二：JSON 文件**

统计数据持久化在 `data/stats.json`，可直接读取：

```json
{
  "total_queries": 1234,
  "auto_replies": 890,
  "forwards": 344,
  "total_confidence": 8765,
  "total_latency_ms": 2345678,
  "channel_counts": {"123": 456, "789": 778}
}
```

---

## 九、部署方案

### 9.1 本地运行

```powershell
.venv\Scripts\Activate.ps1
python -m bot.main
```

按 `Ctrl+C` 优雅关机（保存所有状态）。

### 9.2 Docker 部署

项目已包含 `Dockerfile` 和 `docker-compose.yml`：

```bash
# 在 VPS 上
git clone <your-repo>
cd treeProjectDiscordBot
# 创建 .env
# 复制 chromadb_store/ 和 data/ 目录

docker-compose up -d
docker-compose logs -f    # 查看日志
```

数据卷自动挂载 `chromadb_store/`、`logs/`、`data/`。

### 9.3 systemd 部署

```ini
# /etc/systemd/system/discord-bot.service
[Unit]
Description=Discord Auto-Reply Bot
After=network.target

[Service]
Type=simple
User=botuser
WorkingDirectory=/home/botuser/treeProjectDiscordBot
ExecStart=/home/botuser/treeProjectDiscordBot/.venv/bin/python -m bot.main
Restart=always
RestartSec=10
EnvironmentFile=/home/botuser/treeProjectDiscordBot/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable discord-bot
sudo systemctl start discord-bot
sudo journalctl -u discord-bot -f    # 查看日志
```

---

## 十、测试

```powershell
# 运行所有测试
python -m pytest tests/ -v

# 运行特定模块测试
python -m pytest tests/test_rag.py -v
python -m pytest tests/test_confidence.py -v
python -m pytest tests/test_ingestion.py -v
python -m pytest tests/test_listener.py -v
python -m pytest tests/test_review.py -v
python -m pytest tests/test_stats.py -v
python -m pytest tests/test_cache.py -v
python -m pytest tests/test_promotion.py -v
```

**测试覆盖范围：** 139 个测试用例

| 测试文件 | 覆盖内容 |
|----------|----------|
| `test_ingestion.py` | 消息清理、Q&A 配对、分块 |
| `test_rag.py` | RAG 检索、生成、价格脱敏 |
| `test_confidence.py` | 路由决策、信号检测、置信度解析 |
| `test_listener.py` | 消息过滤链、限流、emoji 检测 |
| `test_review.py` | 审核流程、负反馈存储 |
| `test_stats.py` | 统计记录、快照、持久化 |
| `test_cache.py` | LRU 缓存、TTL 过期、命中率 |
| `test_promotion.py` | CTA 生成、频道检查 |

**端到端测试建议：**

1. 创建私密测试频道 → 添加 Bot → 加入 `TARGET_CHANNEL_IDS`
2. 发送投资问题 → 验证自动回复
3. 发送离题问题 → 验证转发到 DM
4. 测试审核按钮（Approve / Edit / Reject）
5. 发送图片 → 验证图片分析
6. 快速连发 5 条 → 验证限流生效

---

## 十一、常见问题 (FAQ)

### Bot 上线了但不回复消息

| 可能原因 | 解决方案 |
|----------|----------|
| MESSAGE CONTENT INTENT 未开启 | Discord 开发者门户 → Bot → 开启 MESSAGE CONTENT INTENT |
| 频道 ID 不在 `TARGET_CHANNEL_IDS` | 检查 `.env` |
| 你是 Owner 在发消息 | Bot 不回复 Owner 的消息（除非 @mention Bot） |
| 被限流了 | 等待 30 秒（或检查日志中的"速率限制"提示） |
| `RESPOND_MODE=mention_only` | 改为 `questions` 或 `all`，或 @mention Bot |

### 审核 DM 按钮没反应

- Bot 必须保持运行（按钮由进程内存处理）
- 按钮 1 小时后过期
- 检查你的 DM 是否开启

### 回复质量不好

1. 确认已运行 `python -m ingestion.analyze_style`
2. 检查知识库是否有足够数据（`/status` 查看文档数）
3. 调高 `CONFIDENCE_THRESHOLD` 让更多回复走审核
4. 检查 `data/negative_samples.json` 中是否有过多负反馈

### OpenAI API 报错

| 错误 | 解决 |
|------|------|
| `RateLimitError` | 降低 `EMBED_BATCH_SIZE`，或升级 OpenAI 额度 |
| `APITimeoutError` | Bot 会自动重试一次；检查网络 |
| `AuthenticationError` | 检查 `.env` 中的 `OPENAI_API_KEY` |

### 导入数据报错 "No JSON files found"

确保 `.json` 文件放在 `data/exports/` 目录下。

### 如何重新导入数据

直接重新运行 `python -m ingestion.ingest`。脚本会自动跳过已导入的文档（增量导入）。

如果需要完全重建：删除 `chromadb_store/` 目录后重新运行。

---

## 十二、配置参考总表

### 必填参数

| 变量 | 说明 |
|------|------|
| `DISCORD_BOT_TOKEN` | Discord Bot Token |
| `OPENAI_API_KEY` | OpenAI API Key |
| `OWNER_USER_ID` | 频道主 Discord User ID |
| `TARGET_CHANNEL_IDS` | 监听频道 ID（逗号分隔） |

### 模型设置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_MODEL` | `gpt-4o-mini` | 生成模型 |
| `VISION_MODEL` | `gpt-4o` | Vision 模型 |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | 嵌入模型 |
| `LLM_MAX_TOKENS` | `500` | 最大生成 token |
| `LLM_TEMPERATURE` | `0.5` | 生成温度 |

### RAG 与路由

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RAG_TOP_K` | `8` | 检索结果数 |
| `RAG_MAX_DISTANCE` | `0.6` | 最大 cosine 距离 |
| `CONFIDENCE_THRESHOLD` | `7` | 自动回复最低信心 |
| `RESPOND_MODE` | `questions` | 响应模式 |

### 对话与限流

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CONVERSATION_MEMORY_SIZE` | `10` | 对话记忆条数 |
| `CONVERSATION_MEMORY_TTL` | `1800` | 记忆过期秒数 |
| `USER_COOLDOWN_SECONDS` | `30` | 用户冷却 |
| `GLOBAL_MAX_PER_MINUTE` | `10` | 全局每分钟限制 |

### Thread 支持

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `THREAD_AUTO_REPLY` | `true` | Thread 自动回复 |
| `THREAD_CONTEXT_MESSAGES` | `15` | Thread 上下文消息数 |

### 离线回填

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OFFLINE_BACKFILL_ENABLED` | `true` | 总开关 |
| `OFFLINE_BACKFILL_LOOKBACK_HOURS` | `12` | 首次回看小时 |
| `OFFLINE_BACKFILL_MAX_PER_CHANNEL` | `100` | 每频道最大扫描数 |
| `OFFLINE_BACKFILL_OWNER_REPLY_WINDOW_MINUTES` | `15` | Owner 回复窗口 |

### 数据路径

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CHROMADB_PATH` | `./chromadb_store` | 向量库路径 |
| `CHROMADB_COLLECTION` | `bigtree_knowledge` | Collection 名 |
| `EXPORT_DIR` | `./data/exports` | 导出文件目录 |

### 导入参数

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CHUNK_MAX_TOKENS` | `500` | 分块最大 token |
| `CHUNK_OVERLAP_TOKENS` | `50` | 分块重叠 token |
| `EMBED_BATCH_SIZE` | `100` | 批量大小 |

### 推广

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PROMO_ENABLED` | `true` | 推广总开关 |
| `PROMO_CHANNEL_IDS` | (空) | 推广频道 |
| `SIGNAL_PRODUCT_NAME` | `BigTreeSignal` | 产品名 |
| `SIGNAL_PRODUCT_URL` | (空) | 产品 URL |
| `CTA_FREQUENCY` | `5` | CTA 频率 |
| `FREE_TRIAL_ENABLED` | `false` | 免费试用 |
| `TESTIMONIAL_CHANNEL_ID` | `0` | 见证频道 |
| `TESTIMONIAL_DETECTION_ENABLED` | `true` | 自动检测见证 |

### 系统

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BOT_LANGUAGE` | `zh` | 界面语言 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `HEALTH_PORT` | `0` | 健康检查端口 |
