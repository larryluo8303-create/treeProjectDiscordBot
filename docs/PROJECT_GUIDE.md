# 项目详解：Discord 自动回复 RAG Bot

---

## 目录

- [一、设计思路](#一设计思路)
- [二、技术架构](#二技术架构)
- [三、每个文件的作用](#三每个文件的作用)
  - [配置层 — bot/config.py](#配置层)
  - [数据导入层](#数据导入层离线运行一次)
    - [ingestion/preprocess.py — 数据预处理](#ingestionpreprocesspy--数据预处理)
    - [ingestion/ingest.py — 向量化存储](#ingestioningestpy--向量化存储)
    - [ingestion/analyze_style.py — 风格分析](#ingestionanalyze_stylepy--风格分析)
    - [ingestion/ingest_youtube.py — YouTube 视频导入](#ingestioningest_youtubepy--youtube-视频导入)
  - [Bot 运行层](#bot-运行层长期运行)
    - [bot/main.py — 入口文件](#botmainpy--入口文件)
    - [bot/listener.py — 消息处理](#botlistenerpy--消息处理)
    - [bot/rag.py — RAG 核心](#botragpy--rag-核心)
    - [bot/confidence.py — 路由决策](#botconfidencepy--路由决策)
    - [bot/review.py — 审核界面](#botreviewpy--审核界面)
  - [推广层（BigTreeSignal）](#推广层bigtreesignal)
    - [bot/promo_config.py — 推广工具函数](#botpromo_configpy--推广工具函数)
    - [bot/commands.py — Slash Commands](#botcommandspy--slash-commands)
    - [bot/scheduler.py — 定时排程](#botschedulerpy--定时排程)
    - [bot/testimonials.py — 用户见证](#bottestimonialspy--用户见证)
- [四、关键技术概念](#四关键技术概念)
- [五、费用结构](#五费用结构)
- [六、安全设计](#六安全设计)
- [七、项目文件结构](#七项目文件结构)
- [八、日常使用命令速查](#八日常使用命令速查)

---

## 零、环境安装与初始化

在阅读本文档之前，请确保以下开发环境已就绪。如果你只是想快速上手运行，请直接参考 [`SETUP_AND_TEST.md`](./SETUP_AND_TEST.md)。

### 前置条件

| 组件 | 要求 | 验证命令 |
|------|------|----------|
| Python | 3.11+ | `python --version` |
| Node.js | 18+（前端开发需要） | `node --version` |
| FFmpeg | YouTube/语音导入需要 | `ffmpeg -version` |
| Discord Bot Token | 从 Discord 开发者门户获取 | — |
| OpenAI API Key | 从 OpenAI 获取 | — |
| Git | 版本控制 | `git --version` |

### 安装步骤

```powershell
# 1. 安装系统工具
winget install --id Python.Python.3.11 -e
winget install --id Gyan.FFmpeg -e

# 2. 克隆项目
git clone <your-repo-url>
cd treeProjectDiscordBot

# 3. 创建并激活虚拟环境
python -m venv .venv
.venv\Scripts\Activate.ps1    # PowerShell
# 或 source .venv/bin/activate  # Linux/macOS

# 4. 安装 Python 依赖
pip install -r requirements.txt

# 5. 创建环境配置
Copy-Item .env.example .env
# 编辑 .env 填入以下必填项：
#   DISCORD_BOT_TOKEN=你的Bot Token
#   OPENAI_API_KEY=你的OpenAI Key
#   OWNER_USER_ID=你的Discord User ID
#   TARGET_CHANNEL_IDS=频道ID1,频道ID2

# 6. 导入数据到知识库
python -m ingestion.ingest

# 7. （可选）分析写作风格
python -m ingestion.analyze_style

# 8. 启动 Bot
python -m bot.main
```

### 换电脑后重建虚拟环境（Windows）

不要从旧电脑复制 `.venv`。旧环境往往指向另一台机器上的 Python（例如 `uv` 安装路径），激活后运行 `python` 会报错：

```text
error: uv trampoline failed to spawn Python child process
Caused by: entity not found (os error 2)
```

在项目根目录用 **Windows Python Launcher（`py`）** 重建，不要用 Microsoft Store 的 `python`：

```powershell
# 1. 删掉从旧电脑复制过来的坏 .venv
Remove-Item -Recurse -Force .venv

# 2. 用 py launcher 创建全新 venv（关键：用 py，不是 python）
py -m venv .venv

# 3. 激活
.venv\Scripts\Activate.ps1

# 4. 激活之后 python 就能用了，验证一下
python --version
#   应该输出: Python 3.13.13

# 5. 升级 pip
python -m pip install --upgrade pip

# 6. 安装依赖
pip install -r requirements.txt

# 7. 启动 Bot
python -m bot.main
```

激活成功后提示符前应出现 `(.venv)`，且 `python --version` 为本机已安装的 Python（3.11+）。若 `Activate.ps1` 被执行策略拦截，先运行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 验证安装

```powershell
# 运行测试（应该全部通过）
python -m pytest tests/ -v

# 检查知识库文档数
python -c "import chromadb; c=chromadb.PersistentClient('./chromadb_store'); print(c.get_collection('bigtree_knowledge').count())"
```

Bot 正常启动后你会看到：

```
[INFO] bot.main: OpenAI client initialized
[INFO] bot.main: ChromaDB collection loaded — XXXXX documents
[INFO] bot.main: Starting Discord bot...
[INFO] bot.listener: Bot is ready — starting message queue worker
```

### 前端应用安装（可选）

```powershell
# Admin 管理端（Expo）
cd app
npm install
npx expo start

# 客户端移动应用（Expo）
cd app-client
npm install
npx expo start

# 客户端网页版（Vite）
cd web-client
npm install
npm run dev    # 访问 http://localhost:5173
```

> **详细前端设置请参阅：** [`USER_GUIDE.md`](./USER_GUIDE.md)（管理端）和 [`CLIENT_USER_GUIDE.md`](./CLIENT_USER_GUIDE.md)（客户端）。

---

## 一、设计思路

### 要解决什么问题？

你有一个 5000+ 成员的 Discord 股票频道，成员经常提问。你不可能 24 小时在线回复每一个问题。

### 解决方案

用 AI 模仿你的语气自动回复，但要有**安全机制** — 不确定的回答先给你审核。

### 核心流程

```
成员提问: "AAPL怎么看？"
       ↓
① 搜索你的历史帖子，找到最相关的内容
       ↓
② 把相关内容+问题交给 GPT-4o-mini，让它模仿你的风格生成回答
       ↓
③ AI 给自己打分（1-10分，表示自信程度）
       ↓
④ 分数 ≥ 7 → 自动回复到频道
   分数 < 7 → 私信给你审核（批准/编辑/拒绝）
```

这就是 **RAG（Retrieval-Augmented Generation，检索增强生成）** 的核心思想：先检索，再生成。

---

## 二、技术架构

```
┌─────────────────────────────────────────────────┐
│                 Discord 频道                      │
│  成员发消息 ──→ Bot 接收                          │
└────────┬────────────────────────────────────────┘
         ↓
┌────────────────────────────────┐
│  bot/listener.py               │
│  ① 过滤（机器人/频道主/空消息）   │
│  ② 限速（每人30秒/全局10条/分钟） │
│  ③ 放入异步队列                  │
└────────┬───────────────────────┘
         ↓
┌────────────────────────────────┐
│  bot/rag.py — 检索阶段          │
│  ① 把问题转成向量（embedding）    │
│  ② 在 ChromaDB 中搜索最相似的8条 │
│  ③ 过滤掉不相关的（距离 > 0.8）   │
└────────┬───────────────────────┘
         ↓
┌────────────────────────────────┐
│  bot/rag.py — 生成阶段          │
│  ① 把检索结果 + 问题 + 风格指南   │
│     组装成 prompt                │
│  ② 发给 GPT-4o-mini 生成回答     │
│  ③ 从回答中提取自信度分数         │
└────────┬───────────────────────┘
         ↓
┌────────────────────────────────┐
│  bot/confidence.py — 路由决策    │
│  检查三个条件：                   │
│  • 有没有找到相关历史内容？        │
│  • 最佳匹配距离是否 ≤ 0.6？      │
│  • 自信度是否 ≥ 7？              │
│  全满足 → 自动回复               │
│  任一不满足 → 转给频道主审核      │
└────────┬───────────┬───────────┘
         ↓           ↓
    自动回复       bot/review.py
    到频道         私信频道主审核
                  [✅批准][✏️编辑][❌拒绝]
```

---

## 三、每个文件的作用

### 配置层

**bot/config.py** — 配置中心

从 `.env` 文件读取所有配置：

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `DISCORD_BOT_TOKEN` | — | Bot 登录凭证 |
| `OPENAI_API_KEY` | — | OpenAI API 密钥 |
| `OWNER_USER_ID` | — | 你的 Discord ID（识别频道主） |
| `TARGET_CHANNEL_IDS` | — | 监听哪些频道 |
| `CONFIDENCE_THRESHOLD` | 7 | 自信度阈值 |
| `RAG_TOP_K` | 8 | 每次检索多少条历史内容 |
| `RAG_MAX_DISTANCE` | 0.8 | 最大允许距离（越小越严格） |
| `USER_COOLDOWN_SECONDS` | 30 | 每用户冷却时间 |
| `GLOBAL_MAX_PER_MINUTE` | 10 | 全局每分钟最多处理条数 |
| `LLM_MODEL` | gpt-4o-mini | 用哪个 AI 模型 |
| `LLM_TEMPERATURE` | 0.7 | 回复的随机程度（0=死板，1=随意） |

还包含中文系统提示模板：告诉 AI "你是一个模仿频道主风格的助手"。

---

### 数据导入层（离线运行一次）

#### ingestion/preprocess.py — 数据预处理

把 Discord 导出的原始 JSON 变成干净的文本块：

```
原始 JSON（24,896条消息）
    ↓
① load_exports()     — 读取所有 JSON 文件
    ↓
② build_qa_pairs()   — 提取问答对（1,661对）
   找到模式：别人提问 → 你回复 → 组成 "Q: xxx\nA: xxx"
   这是最有价值的数据，因为完美展示了你如何回答问题
    ↓
③ group_consecutive() — 合并连续消息（4,270个块）
   你经常连发几条消息（间隔<2分钟），把它们合并成一个完整段落
    ↓
④ clean_message()    — 清理文本
   • <@123456> → @用户名
   • <:rocket:789> → :rocket:
   • 去除 Discord 格式标记
    ↓
⑤ chunk_text()       — 切分大文本
   把超过500 tokens的文本切成小块（按段落→句子→字符）
   支持中文标点 。！？
    ↓
最终产出：4,684 个文档，每个都适合做 embedding
```

#### ingestion/ingest.py — 向量化存储

```
4,684 个文档
    ↓
① embed_batch()      — 每100个一批发给 OpenAI
   OpenAI 把文字变成 1536 维的数字向量
   语义相似的文字 → 向量也相似
   例如 "AAPL看涨" 和 "苹果股票不错" 的向量会很接近
    ↓
② collection.add()   — 存入 ChromaDB
   ChromaDB 用余弦相似度索引这些向量
   之后搜索时，输入一个问题向量，能瞬间找到最相似的历史帖子
    ↓
存储在 chromadb_store/ 文件夹（可复制到其他电脑直接用）
```

支持**增量导入** — 重复运行不会产生重复数据。

#### ingestion/analyze_style.py — 风格分析

```
分析你的所有帖子 → 生成风格画像：
• 平均回复长度：XX 字
• 常用短语："我觉得"、"可以关注"、"注意风险"
• 表情使用频率：XX%
• 常用开头词："目前"、"这个"、"建议"
→ 保存到 data/style_profile.txt
→ Bot 回答时自动加载，模仿你的风格
```

#### ingestion/ingest_youtube.py — YouTube 视频导入

```
YouTube 视频 URL
    ↓
① 先尝试抓字幕（免费）
   ↓ 没有字幕？
② 下载音频 → Whisper API 语音转文字（$0.006/分钟）
    ↓
③ 切块 → 向量化 → 存入 ChromaDB
```

---

### Bot 运行层（长期运行）

#### bot/main.py — 入口文件

启动顺序：
1. 验证配置（Token 和 API Key 是否填写）
2. 初始化 OpenAI 客户端
3. 连接 ChromaDB（加载你的历史数据）
4. 创建 Discord Bot
5. 注册消息监听器
6. 启动 Bot（保持运行）

#### bot/listener.py — 消息处理

这是整个 Bot 的核心逻辑，分为三层：

**第一层：过滤** — `_should_skip()`

| 条件 | 处理 |
|---|---|
| 发送者是机器人 | 跳过（防止 Bot 互相回复） |
| 发送者是频道主（你） | 跳过（防止自问自答） |
| 消息不在目标频道 | 跳过 |
| 空消息/纯图片 | 跳过 |

**第二层：限速** — `_is_rate_limited()`

| 条件 | 处理 |
|---|---|
| 同一用户 30 秒内发过 | 跳过（防刷屏） |
| 1 分钟内全局已处理 10 条 | 跳过（控制 API 费用） |

**第三层：异步队列**

消息放入 `asyncio.Queue`，后台 worker 逐条处理。防止多个问题**同时处理**导致混乱和 API 超载。

#### bot/rag.py — RAG 核心

**检索阶段** `retrieve_context()`：

1. 把用户的问题用 OpenAI embedding API 转成向量
2. 在 ChromaDB 中用余弦相似度搜索最接近的 8 条历史帖子
3. 过滤掉距离 > 0.8 的不相关内容
4. 去重（避免重复内容）

**生成阶段** `generate_answer()`：

1. 加载风格指南（`data/style_profile.txt` 或默认）
2. 组装 prompt（系统提示 + 历史内容 + 问题）
3. 调用 GPT-4o-mini 生成回答
4. 从回答末尾提取 `CONFIDENCE: X` 分数
5. 返回（回答, 自信度）

#### bot/confidence.py — 路由决策

`route_answer()` 检查三重条件：

| 条件 | 不满足时 |
|---|---|
| `context_count > 0` | → 转审核（没有找到任何相关历史内容） |
| `best_distance ≤ 0.6` | → 转审核（找到的内容不够相关） |
| `confidence ≥ 7` | → 转审核（AI 自己不确定） |

三个条件**全部满足**才自动回复，**任一不满足**就转给你审核。

#### bot/review.py — 审核界面

当需要你审核时，Bot 私信你：

```
┌──────────────────────────────────┐
│  🟠 Review Required              │
│                                  │
│  Channel: #股票讨论               │
│  Asked by: User123               │
│  Confidence: 5/10                │
│                                  │
│  Question: TSLA还能买吗？        │
│  Draft Answer: TSLA波动太大...    │
│                                  │
│  [✅ Approve] [✏️ Edit] [❌ Reject]│
└──────────────────────────────────┘
```

| 按钮 | 操作 |
|---|---|
| ✅ Approve | 直接把草稿发到频道 |
| ✏️ Edit | 你在 DM 中输入修改后的回答 → 发到频道 |
| ❌ Reject | 什么都不发 |

超时 1 小时未操作自动失效。有防重复点击保护。

### 推广层（BigTreeSignal）

> 完整设计文档见 `PROMOTION_DESIGN.md`，详细使用说明见 `PROMOTION_GUIDE.md`。

#### bot/promo_config.py — 推广工具函数

纯函数模块，提供推广相关的 helper：

| 函数 | 作用 |
|---|---|
| `is_promo_channel()` | 判断频道是否在推广列表 |
| `get_signal_cta_embed()` | 生成信号查询时的 CTA Embed |
| `get_auto_reply_cta()` | 生成自动回复尾部 CTA 文本 |
| `should_append_cta()` | 根据 `CTA_FREQUENCY` 判断是否附带 CTA |
| `get_welcome_embed()` | 生成新用户欢迎 Embed |
| `get_signal_product_embed()` | 生成 `/signal` 命令的产品 Embed |

#### bot/commands.py — Slash Commands

10 个 Slash Command，注册为 `PromotionCommands` Cog：

- `/signal` — 任何人可用，展示产品信息
- `/testimonials` — 任何人可用，展示用户好评
- `/post_promo` / `/schedule_promo` / `/schedule_trial` / `/schedule_lesson` — Owner 专用，发送或排程推广内容
- `/list_promos` / `/cancel_promo` / `/list_lessons` / `/cancel_lesson` — Owner 专用，管理排程

#### bot/scheduler.py — 定时排程

`SchedulerCog` 每 60 秒检查 `data/promos.json` 和 `data/lessons.json`，到时间自动发送 Embed 到推广频道。教学帖支持每天 / 每周重复。

#### bot/testimonials.py — 用户见证

自动检测用户盈利/好评消息 → DM Owner 审核（Approve / Reject）→ 审核通过后转发到 `TESTIMONIAL_CHANNEL_ID` 频道。

---

## 四、关键技术概念

### Embedding（向量嵌入）

把文字变成数字。语义相似的文字 → 数字相近。

```
"AAPL看涨"    → [0.12, -0.34, 0.56, ...]  ← 1536个数字
"苹果股票不错"  → [0.11, -0.33, 0.55, ...]  ← 非常接近！
"今天天气好"   → [0.87, 0.21, -0.43, ...]  ← 完全不同
```

### ChromaDB（向量数据库）

专门用来存储和搜索向量的数据库。输入一个问题向量，瞬间返回最相似的 N 条记录。数据存在本地 `chromadb_store/` 文件夹，可以复制到其他电脑直接使用。

### Cosine Distance（余弦距离）

衡量两个向量有多相似：

| 距离 | 含义 |
|---|---|
| 0.0 | 完全相同 |
| 0.3 | 非常相关 |
| 0.6 | 有点关系 |
| 1.0 | 完全不相关 |

### Token（词元）

AI 处理文字的最小单位。中文大约 1 个字 = 1-2 个 token。
- GPT-4o-mini 收费按 token 计算
- text-embedding-3-small 也按 token 计算

### RAG（检索增强生成）

```
传统 AI：直接问 GPT → 可能胡说
RAG AI ：先搜索相关资料 → 基于资料回答 → 大幅减少胡说
```

---

## 五、费用结构

| 项目 | 费用 | 说明 |
|---|---|---|
| 数据导入（一次性） | ~$0.10 | 4,684 条文档的 embedding |
| 每次提问 — 检索 | ~$0.00002 | 问题 embedding（很便宜） |
| 每次提问 — 生成 | ~$0.001 | GPT-4o-mini 生成回答 |
| 每天 100 个问题 | ~$0.10/天 | |
| 每月估算 | ~$3-5/月 | 取决于提问量 |

---

## 六、安全设计

| 机制 | 说明 |
|---|---|
| 三重自信度检查 | 防止 AI 乱回答 |
| 频道主消息跳过 | 防止自问自答循环 |
| 每人 30 秒冷却 | 防止恶意刷屏 |
| 全局 10 条/分钟 | 防止 API 费用失控 |
| 2000 字符截断 | 遵守 Discord 消息长度限制 |
| `.env` 不提交 Git | 密钥安全 |
| 审核按钮防重复点击 | 防止同一回答发送两次 |
| API 超时自动重试 | 网络闪断不会崩溃 |

---

## 七、项目文件结构

```
C:\treeProjectDiscordBot\
├── .env                    ← 密钥配置（不提交 Git）
├── .env.example            ← 配置模板
├── .gitignore              ← Git 忽略规则
├── requirements.txt        ← Python 依赖列表
├── Dockerfile              ← Docker 容器构建
├── docker-compose.yml      ← Docker 一键启动
├── PLAN.md                 ← 完整实施计划
├── SETUP_AND_TEST.md       ← 本机测试指南
├── PROMOTION_DESIGN.md     ← 推广系统设计文档
├── PROMOTION_GUIDE.md      ← 推广功能使用说明
├── GROWTH_PLAYBOOK.md      ← 5000人盘活与订购转化计划书
├── keep_awake.py           ← 防休眠小工具
│
├── bot/                    ← Bot 运行代码
│   ├── config.py           ← 配置加载（含推广配置）
│   ├── main.py             ← 入口文件
│   ├── listener.py         ← 消息监听与过滤（含 CTA / 见证 / 欢迎）
│   ├── rag.py              ← RAG 检索与生成
│   ├── confidence.py       ← 自信度路由
│   ├── review.py           ← 审核界面
│   ├── promo_config.py     ← 推广工具函数
│   ├── commands.py         ← Slash Commands（/signal 等 10 个）
│   ├── scheduler.py        ← 定时排程（促销 / 教学）
│   └── testimonials.py     ← 用户见证收集与审核
│
├── ingestion/              ← 数据导入代码
│   ├── preprocess.py       ← 数据预处理
│   ├── ingest.py           ← 向量化存储
│   ├── analyze_style.py    ← 风格分析
│   └── ingest_youtube.py   ← YouTube 视频导入
│
├── tests/                  ← 测试代码（41个测试）
│   ├── test_ingestion.py
│   ├── test_confidence.py
│   └── test_rag.py
│
├── data/
│   ├── exports/            ← Discord 导出 JSON
│   ├── style_profile.txt   ← 风格分析结果
│   ├── promos.json         ← 排程促销数据（自动生成）
│   ├── lessons.json        ← 排程教学数据（自动生成）
│   └── testimonials.json   ← 用户见证数据（自动生成）
│
├── chromadb_store/          ← 向量数据库（可复制）
└── logs/
    └── bot.log             ← 运行日志
```

---

## 八、日常使用命令速查

```powershell
# 激活虚拟环境
.venv\Scripts\Activate.ps1

# 启动 Bot
python -m bot.main

# 导入 Discord 数据（增量，可重复运行）
python -m ingestion.ingest

# 导入 YouTube 视频
python -m ingestion.ingest_youtube --urls "https://youtu.be/VIDEO_ID"

# 生成风格分析
python -m ingestion.analyze_style

# 运行测试
python -m pytest tests/ -v

# 查看数据库文档数
python -c "import chromadb; c=chromadb.PersistentClient('./chromadb_store'); print(c.get_collection('discord_posts').count())"

# 防休眠（另一个窗口）
python keep_awake.py
```

### 推广功能 Slash Commands

在 Discord 中直接使用（Bot 启动后自动注册）：

```
/signal                — 查看 BigTreeSignal 产品信息
/testimonials          — 展示最近用户好评
/post_promo            — [Owner] 立即发送促销
/schedule_promo        — [Owner] 排程促销帖
/schedule_trial        — [Owner] 排程信号回顾
/schedule_lesson       — [Owner] 排程教学推送
/list_promos           — [Owner] 列出排程促销
/cancel_promo          — [Owner] 取消排程促销
/list_lessons          — [Owner] 列出排程教学
/cancel_lesson         — [Owner] 取消排程教学
```

> 详细使用说明见 `PROMOTION_GUIDE.md`。
