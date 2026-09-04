> **归档文档**：历史设计/阶段指南，仅供参考。现行说明见上级目录的 PROJECT_GUIDE / FEATURE_LIST / SETUP_AND_TEST 等。

# Phase 3: 新功能使用指南

---

## 目录

- [一、总览](#一总览)
- [二、Thread 自动回复 (F1)](#二thread-自动回复-f1)
- [三、每日摘要 (F2)](#三每日摘要-f2)
- [四、语音消息自动学习 (F3)](#四语音消息自动学习-f3)
- [五、图表对比分析 (F4)](#五图表对比分析-f4)
- [六、FAQ 自动生成 (F6)](#六faq-自动生成-f6)
- [七、定时数据导入 (F7)](#七定时数据导入-f7)
- [八、Webhook 数据接入 (F8)](#八webhook-数据接入-f8)
- [九、Admin 管理面板 (F10)](#九admin-管理面板-f10)
- [十、完整配置速查表](#十完整配置速查表)
- [十一、常见问题 (FAQ)](#十一常见问题-faq)

---

## 一、总览

Phase 3 新增 **8 个功能模块**，全部默认关闭（opt-in），按需在 `.env` 中开启即可。升级后无需任何配置变更即可正常运行现有功能。

### 前置条件

在使用 Phase 3 功能之前，请确认以下环境已就绪：

| 组件 | 要求 | 验证命令 |
|------|------|----------|
| Python | 3.11+ | `python --version` |
| 虚拟环境 | 已创建并激活 | `.venv\Scripts\Activate.ps1` (PowerShell) |
| Python 依赖 | 已安装 | `pip install -r requirements.txt` |
| `.env` 配置 | Phase 1/2 已配置完成 | 检查 `.env` 文件存在且包含必填项 |
| ChromaDB | 已导入数据 | `python -c "import chromadb; c=chromadb.PersistentClient('./chromadb_store'); print(c.get_collection('bigtree_knowledge').count())"` |
| Discord Bot | 已邀请到服务器且有权限 | Bot 在 Discord 服务器在线 |
| FFmpeg | 语音转录需要 (F3) | `ffmpeg -version` |

> **注意：** 如果你是从头开始部署，请先完成 [`SETUP_AND_TEST.md`](../getting-started/SETUP_AND_TEST.md)（或本目录 [`PHASE1_2_GUIDE.md`](./PHASE1_2_GUIDE.md)）中的完整安装流程。

### 环境安装（如果尚未完成）

```powershell
# 1. 安装 Python 3.11+
winget install --id Python.Python.3.11 -e

# 2. 安装 FFmpeg（语音转录需要）
winget install --id Gyan.FFmpeg -e

# 3. 创建虚拟环境
cd C:\treeProjectDiscordBot
python -m venv .venv

# 4. 激活虚拟环境
.venv\Scripts\Activate.ps1

# 5. 安装 Python 依赖
pip install -r requirements.txt
```

### 快速开始

```bash
# 1. 拉取最新代码
git pull

# 2. 激活虚拟环境
.venv\Scripts\Activate.ps1    # PowerShell
# 或 source .venv/bin/activate  # Linux/macOS

# 3. 更新依赖（确保新模块的依赖已安装）
pip install -r requirements.txt

# 4. 按需在 .env 中添加新配置（参见 .env.example）

# 5. 启动 Bot
python -m bot.main
```

### 验证启动成功

Bot 正常启动后你会看到以下日志：

```
[INFO] bot.main: OpenAI client initialized
[INFO] bot.main: ChromaDB collection loaded — XXXXX documents
[INFO] bot.main: Starting Discord bot...
[INFO] bot.listener: Bot is ready — starting message queue worker
```

如果启用了 Phase 3 功能，还会看到对应的日志：

```
[INFO] Digest scheduler started (hour=22 UTC)
[INFO] Ingestion scheduler started (every 12.0h)
[INFO] Webhook server started on port 8081
[INFO] Admin panel started on port 8082
```

### 功能开关速查

| 功能 | 环境变量 | 默认值 |
|------|----------|--------|
| Thread 回复 | `THREAD_AUTO_REPLY` | `true` (已开启) |
| 每日摘要 | `DIGEST_ENABLED` | `false` |
| 语音转录 | (自动，无开关) | 始终启用 |
| 图表对比 | (自动，无开关) | 始终启用 |
| FAQ 生成 | (按需 slash command) | 随时可用 |
| 定时导入 | `INGEST_INTERVAL_HOURS` | `0` (禁用) |
| Webhook | `WEBHOOK_ENABLED` | `false` |
| Admin 面板 | `ADMIN_ENABLED` | `false` |

---

## 二、Thread 自动回复 (F1)

### 是什么？

Bot 现在可以在 Discord Thread（讨论串）中自动回复用户提问，并保持 Thread 内的对话上下文。

### 如何工作？

1. 用户在目标频道创建一个 Thread 并提问
2. Bot 检测到 Thread 的父频道在 `TARGET_CHANNEL_IDS` 中
3. Bot 获取 Thread 中最近的消息作为对话上下文
4. 基于完整上下文生成回复

### 配置

在 `.env` 中添加：

```env
# Thread 自动回复（默认已开启）
THREAD_AUTO_REPLY=true

# Thread 中获取的上下文消息数量
THREAD_CONTEXT_MESSAGES=15
```

### 使用提示

- **Owner 在 Thread 中发言**同样会被自动学习入知识库
- 要禁用 Thread 回复：设置 `THREAD_AUTO_REPLY=false`
- `THREAD_CONTEXT_MESSAGES` 控制 Bot 在 Thread 中能"看到"多少条历史消息，建议 10-20

---

## 三、每日摘要 (F2)

### 是什么？

Bot 每天定时发送一份精美的活动摘要，包含过去 24 小时的问答统计、热门频道、最近问题和需要关注的转发/未回答问题。

### 如何开启？

在 `.env` 中添加：

```env
DIGEST_ENABLED=true

# 发送时间（UTC 小时，0-23）
# 22 = 下午 6:00 ET / 凌晨 6:00 CST
DIGEST_HOUR=22

# 可选：同时发送到某个频道（0 = 仅 DM Owner）
DIGEST_CHANNEL_ID=0
```

### 摘要包含什么？

摘要以 Discord Embed 形式发送，包含以下卡片：

1. **📈 Overview** — 总问题数、自动回复数、转发数、平均信心、平均延迟
2. **📺 Top Channels** — 最活跃的 5 个频道
3. **❓ Recent Questions** — 最近 5 个问题（✅ 自动回复 / 🟠 转发）
4. **🔴 Forwarded / Unanswered** — 需要 Owner 关注的问题
5. **💤 Quiet Day** — 如果 24h 内无问题，显示静默提示

### 使用提示

- 摘要会同时 DM 给 Owner 和发布到 `DIGEST_CHANNEL_ID`（如果设置了）
- 如果 Owner 关闭了 DM，Bot 会在日志中记录但不会报错
- 建议 `DIGEST_HOUR` 设为你下班后的时间，方便回顾当天活动

---

## 四、语音消息自动学习 (F3)

### 是什么？

当 Owner 在目标频道发送语音消息时，Bot 会自动：
1. 下载音频文件
2. 使用 OpenAI Whisper 转录为文字
3. 将文字嵌入并存入 ChromaDB 知识库

### 如何使用？

**无需任何配置** — 只要 Owner 在 `TARGET_CHANNEL_IDS` 频道中发送带音频附件的消息，Bot 就会自动处理。

### 支持的音频格式

- `.ogg` (Discord 默认语音格式)
- `.mp3`
- `.m4a`
- `.wav`
- 任何 `audio/*` content type 的附件

### 处理细节

- 转录语言默认为中文（`zh`）
- 文本太短（< 5 字符）的语音会被跳过
- 使用 `voice_{message_id}` 作为知识库文档 ID，自动去重
- 知识库中 type 标记为 `owner_voice`，source 为 `discord_live_voice`

### 日志示例

```
INFO - 自动学习: 检测到频道主语音消息 (id=1234, channel=5678)
INFO - Voice transcription complete (id=1234, len=156): 今天ES走势比较强...
INFO - Auto-learned voice message 1234 (156 chars)
```

---

## 五、图表对比分析 (F4)

### 是什么？

当用户发送图表截图并附带文字（如 "ES 怎么看"）时，Bot 不仅会用 GPT-4o 分析图表，还会从知识库中检索 Owner 过往对类似标的的历史分析，注入到 vision prompt 中。

### 如何工作？

1. 用户发送图片 + 文字（如 "NQ 4小时图"）
2. Bot 用文字在知识库中检索 3 条最相关的历史分析
3. 历史分析作为参考上下文注入 GPT-4o vision prompt
4. GPT-4o 结合图表和历史分析给出增强回复

### 使用提示

- **仅在图片 + 文字同时存在时**才会触发 RAG 检索
- 用户只发图片（无文字）时，保持原有纯视觉分析行为
- 知识库中积累的 Owner 分析越多（通过自动学习、语音转录等），对比效果越好
- 如果 RAG 检索失败（网络错误等），会自动降级为纯视觉分析

### 用户看到的区别

启用前：GPT-4o 仅基于图片内容分析
启用后：GPT-4o 会参考 Owner 历史分析风格和观点，回复更具一致性

---

## 六、FAQ 自动生成 (F6)

### 是什么？

基于用户最近的高频高信心提问，使用 GPT 自动聚类生成 FAQ 列表，方便用户自助查询。

### 使用方法

#### 用户查看 FAQ

在 Discord 中输入：

```
/faq
```

Bot 会以 Embed 形式展示当前 FAQ 列表（编号 + 问题 + 简答）。

#### Owner 生成 FAQ

在 Discord 中输入：

```
/generate_faq
```

Bot 会：
1. 从统计记录中提取信心 ≥ 7 的自动回复问题
2. 去重 + 限制最近 50 个 unique 问题
3. 调用 GPT 聚类合并为最多 10 个 FAQ 条目
4. 保存到 `data/faq.json`
5. 返回生成结果

### 高级配置

```env
# FAQ 数据文件路径（可选）
FAQ_FILE=data/faq.json

# 最低信心阈值（只有达到此分数的回复才纳入 FAQ 来源）
FAQ_MIN_CONFIDENCE=7

# 最大 FAQ 条目数
FAQ_MAX_ITEMS=10
```

### 使用提示

- FAQ 会持久化到 `data/faq.json`，重启后自动加载
- 至少需要 3 个高信心回复记录才能生成 FAQ，否则返回缓存
- 建议 Bot 运行一段时间、积累足够问答数据后再使用 `/generate_faq`
- 可以多次运行 `/generate_faq`，每次会基于最新数据重新生成

---

## 七、定时数据导入 (F7)

### 是什么？

自动定时运行知识库导入（`ingestion.ingest`）和风格分析（`ingestion.analyze_style`），保持知识库与最新数据同步。

### 如何开启？

在 `.env` 中设置间隔时间：

```env
# 每 12 小时重新导入一次
INGEST_INTERVAL_HOURS=12

# 每 24 小时重新分析风格
STYLE_INTERVAL_HOURS=24
```

设为 `0` = 禁用（默认）。

### 运行机制

- 导入和风格分析作为**独立子进程**运行，不阻塞 Bot 主事件循环
- 子进程最长运行 1 小时（超时自动终止）
- 失败时 Bot 会 **DM Owner** 错误信息
- Bot 启动后在第一个间隔结束后才开始第一次运行

### 日志示例

```
INFO - Ingestion scheduler started (every 12.0h)
INFO - Style re-analysis scheduler started (every 24.0h)
INFO - Scheduled ingestion starting...
INFO - Scheduled ingestion completed successfully
```

### 使用提示

- 确保 `EXPORT_DIR` 中有导入数据（`.json` 文件），否则导入会失败
- 如果只想自动化风格分析（较轻量），可以只设 `STYLE_INTERVAL_HOURS`，`INGEST_INTERVAL_HOURS` 保持 `0`

---

## 八、Webhook 数据接入 (F8)

### 是什么？

提供 HTTP 端点，接收外部系统（如 TradingView alerts、自定义脚本）发送的数据，自动嵌入并存入知识库。

### 如何开启？

在 `.env` 中添加：

```env
WEBHOOK_ENABLED=true
WEBHOOK_PORT=8081

# 可选：HMAC 签名密钥（建议在生产环境设置）
WEBHOOK_SECRET=your_secret_key_here
```

### API 端点

#### 健康检查

```bash
GET http://localhost:8081/webhook/health
```

响应：
```json
{"status": "ok"}
```

#### 数据导入

```bash
POST http://localhost:8081/webhook/ingest
Content-Type: application/json
X-Webhook-Signature: <hmac-sha256-hex>  # 仅设置了 WEBHOOK_SECRET 时需要

{
  "text": "ES期货突破关键压力位，成交量显著放大，短线偏多...",
  "source": "tradingview",
  "type": "alert",
  "ticker": "ES",
  "timeframe": "4h",
  "alert_name": "突破信号"
}
```

#### 批量导入

```bash
POST http://localhost:8081/webhook/ingest

[
  {"text": "NQ回踩20日均线获支撑...", "source": "tradingview", "ticker": "NQ"},
  {"text": "AAPL财报后跳空高开...", "source": "manual", "ticker": "AAPL"}
]
```

#### 响应格式

```json
{"ingested": 2, "total": 3}
```

- `ingested`: 成功入库条数
- `total`: 提交总条数（差值为跳过：太短 / 已存在）

### JSON 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `text` | 是 | 要存入知识库的文本内容（≥ 10 字符） |
| `source` | 否 | 数据来源标签（默认 `"webhook"`） |
| `type` | 否 | 文档类型标签（默认 `"external_data"`） |
| `ticker` | 否 | 股票/期货代码 |
| `timeframe` | 否 | 时间周期（如 `"4h"`, `"1d"`） |
| `alert_name` | 否 | 报警名称 |

### HMAC 签名验证

如果设置了 `WEBHOOK_SECRET`，请求必须包含签名 header：

```python
import hashlib, hmac, json, requests

secret = "your_secret_key_here"
body = json.dumps({"text": "..."}).encode()
signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

requests.post(
    "http://localhost:8081/webhook/ingest",
    data=body,
    headers={
        "Content-Type": "application/json",
        "X-Webhook-Signature": signature,
    },
)
```

### TradingView 集成示例

1. 在 TradingView 创建 Alert
2. 设置 Webhook URL: `http://your-server:8081/webhook/ingest`
3. Alert Message 格式:
```json
{
  "text": "{{exchange}}:{{ticker}} {{strategy.order.action}} @ {{close}} on {{interval}} chart. {{strategy.order.comment}}",
  "source": "tradingview",
  "type": "alert",
  "ticker": "{{ticker}}",
  "timeframe": "{{interval}}"
}
```

---

## 九、Admin 管理面板 (F10)

### 是什么？

一个基于浏览器的管理仪表盘，让 Owner 可以在 Web 界面上查看 Bot 状态、知识库、查询统计和 FAQ 管理。

### 如何开启？

在 `.env` 中添加：

```env
ADMIN_ENABLED=true
ADMIN_PORT=8082

# 可选：API 访问密钥（建议在生产环境设置）
ADMIN_SECRET=your_admin_secret_here
```

### 访问方式

打开浏览器，访问：

```
http://localhost:8082/admin/
```

### 仪表盘面板

1. **📊 Statistics** — 总查询数、自动回复数、转发数、平均信心、平均延迟、运行时间
2. **⚙️ Configuration** — 当前 Bot 配置快照（JSON 格式）
3. **📚 Knowledge Base** — 知识库文档总数 + 最近 10 条文档样本（ID、类型、内容预览）
4. **❓ Recent Queries** — 最近 10 条用户查询（问题、信心分、动作、延迟）
5. **📋 FAQ** — 当前 FAQ 列表 + "Generate FAQ" 按钮

### 自动刷新

- 统计数据每 30 秒自动刷新
- 点击右上角 **↻ Refresh** 按钮手动刷新所有数据

### REST API

如果需要以编程方式访问数据（设置了 `ADMIN_SECRET` 时需要 header `X-Admin-Secret`）：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/api/stats` | 查询统计 |
| GET | `/admin/api/config` | 当前配置 |
| GET | `/admin/api/kb` | 知识库信息 |
| GET | `/admin/api/faq` | FAQ 内容 |
| POST | `/admin/api/faq/generate` | 触发 FAQ 生成 |

```bash
# 示例
curl -H "X-Admin-Secret: your_secret" http://localhost:8082/admin/api/stats
```

---

## 十、完整配置速查表

以下是 Phase 3 新增的所有环境变量，添加到 `.env` 文件中：

```env
# ── Phase 3: 新功能 ──

# Thread 支持
THREAD_AUTO_REPLY=true
THREAD_CONTEXT_MESSAGES=15

# 每日摘要
DIGEST_ENABLED=false
DIGEST_HOUR=22
DIGEST_CHANNEL_ID=0

# 定时导入 (0 = 禁用)
INGEST_INTERVAL_HOURS=0
STYLE_INTERVAL_HOURS=0

# Webhook 数据接入
WEBHOOK_ENABLED=false
WEBHOOK_PORT=8081
WEBHOOK_SECRET=

# Admin 管理面板
ADMIN_ENABLED=false
ADMIN_PORT=8082
ADMIN_SECRET=
```

---

## 十一、常见问题 (FAQ)

### Q: 升级到 Phase 3 后需要改配置吗？

**A:** 不需要。所有新功能默认关闭（Thread 回复除外，默认开启）。你的现有 `.env` 不需要任何修改即可正常运行。

### Q: 需要安装新的 Python 依赖吗？

**A:** 不需要。Phase 3 的所有功能都使用现有依赖（`aiohttp`、`openai`、`discord.py`、`chromadb`）。

### Q: Webhook 和 Admin 面板可以同时开启吗？

**A:** 可以。它们运行在不同的端口上（默认 8081 和 8082），互不影响。

### Q: Owner 发语音消息，如果转录失败怎么办？

**A:** Bot 会在日志中记录错误但不会中断运行。消息不会被存入知识库，也不会影响其他功能。

### Q: FAQ 生成需要多少问答数据？

**A:** 至少需要 3 条信心 ≥ 7 的自动回复记录。建议 Bot 运行一周以上、积累足够数据后再使用。

### Q: 每日摘要的时间可以设为非整点吗？

**A:** 目前只支持整点（`DIGEST_HOUR` 为 0-23 的整数）。摘要在该小时的 :00 分触发。

### Q: Thread 回复和普通频道回复有什么区别？

**A:** Thread 中 Bot 会读取 Thread 历史作为上下文（最多 `THREAD_CONTEXT_MESSAGES` 条），而普通频道使用 per-channel 的对话记忆。Thread 回复通常更有上下文一致性。

### Q: Webhook 端点暴露到公网安全吗？

**A:** 建议设置 `WEBHOOK_SECRET` 并使用 HMAC 签名验证。不设密钥时任何人都可以提交数据。生产环境建议用反向代理（Nginx）+ HTTPS + IP 白名单。

### Q: Admin 面板可以修改配置吗？

**A:** 目前仅支持查看配置，不支持修改。配置变更仍需手动编辑 `.env` 并重启 Bot。未来版本可能增加热更新功能。

### Q: 定时导入会和手动导入冲突吗？

**A:** 定时导入作为独立子进程运行，与 Bot 主进程互不干扰。但不建议在手动导入运行时同时触发定时导入，可能导致 ChromaDB 并发写入问题。
