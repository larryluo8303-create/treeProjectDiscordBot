> **归档文档**：历史设计/阶段指南，仅供参考。现行说明见上级目录的 PROJECT_GUIDE / FEATURE_LIST / SETUP_AND_TEST 等。

# Discord 自动回复 RAG Bot — 完整实现计划

---

## 目录

- [概述](#概述)
- [快速开始（分步指南）](#快速开始分步指南)
  - [前置条件](#前置条件)
  - [步骤 A：创建 Discord Bot 应用](#步骤-a创建-discord-bot-应用)
  - [步骤 B：获取 OpenAI API Key](#步骤-b获取-openai-api-key)
  - [步骤 C：安装 Python 并搭建项目](#步骤-c安装-python-并搭建项目)
  - [步骤 D：配置环境变量](#步骤-d配置环境变量)
  - [步骤 E：导出 Discord 历史](#步骤-e导出-discord-历史)
  - [步骤 F：导入数据](#步骤-f导入数据)
  - [步骤 G：（可选）分析写作风格](#步骤-g可选分析写作风格)
  - [步骤 G2：（可选）导入 YouTube 视频](#步骤-g2可选导入-youtube-视频)
  - [步骤 H：启动 Bot](#步骤-h启动-bot)
  - [步骤 I：测试 Bot](#步骤-i测试-bot)
  - [步骤 J：部署以实现 7×24 运行](#步骤-j部署以实现-724-运行)
- [架构](#架构)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [阶段 1：搭建与数据采集](#阶段-1搭建与数据采集)
  - [步骤 1：创建 Discord Bot 应用](#步骤-1创建-discord-bot-应用)
  - [步骤 2：导出历史消息](#步骤-2导出历史消息)
  - [步骤 3：项目脚手架](#步骤-3项目脚手架)
- [阶段 2：数据导入流水线](#阶段-2数据导入流水线)
  - [步骤 4：预处理消息](#步骤-4预处理消息)
  - [步骤 5：生成嵌入并写入 ChromaDB](#步骤-5生成嵌入并写入-chromadb)
  - [步骤 5b：分析风格（可选）](#步骤-5b可选分析风格)
- [阶段 3：RAG 流水线](#阶段-3rag-流水线)
  - [步骤 6：构建检索模块](#步骤-6构建检索模块)
  - [步骤 7：构建生成模块](#步骤-7构建生成模块)
  - [步骤 8：置信度路由](#步骤-8置信度路由)
- [阶段 4：Discord Bot 集成](#阶段-4discord-bot-集成)
  - [步骤 9：Bot 监听器](#步骤-9bot-监听器)
  - [步骤 10：将 RAG 流水线接入 Bot](#步骤-10将-rag-流水线接入-bot)
  - [步骤 11：Owner 审核界面](#步骤-11owner-审核界面)
- [阶段 5：打磨与部署](#阶段-5打磨与部署)
  - [步骤 12：日志与监控](#步骤-12日志与监控)
  - [步骤 13：反馈闭环（未来）](#步骤-13反馈闭环未来增强)
  - [步骤 14：部署](#步骤-14部署)
- [实现顺序与依赖](#实现顺序与依赖)
- [验证清单](#验证清单)
- [故障排查](#故障排查)
- [安全考虑](#安全考虑)
- [配置参考](#配置参考)
- [决策与范围](#决策与范围)

---

## 概述

本文件是 Discord 自动回复 RAG Bot 的完整实现计划归档译文。它对应早期从零到上线的全量实施方案，便于中英文对照查阅。

构建一个 Python Discord Bot，用于完成以下目标：
1. 导入 200K+ 条历史 Discord 帖子（仅你本人的消息）
2. 以向量嵌入（vector embeddings）形式存入本地 ChromaDB 数据库
3. 通过 RAG（检索增强生成）使用 OpenAI GPT-4o-mini，以**你的风格**生成回答
4. 在你的 Discord 频道中自动回复
5. 将低信心（low-confidence）回答通过私信（DM）转发给你，供审批

本计划既包含面向新手的完整分步上手流程，也包含后续各实现阶段的详细设计说明。你可以按「快速开始」直接落地，也可以按「阶段 1–5」理解每个模块为什么这样实现、依赖关系是什么，以及如何验证与排错。

阅读建议：第一次落地时按「快速开始」顺序做；排错时跳「故障排查」；要改参数时查「配置参考」；若要理解模块边界再读「阶段 1–5」。归档文档可能与当前代码细节略有出入，冲突时以现行 PROJECT_GUIDE / FEATURE_LIST / SETUP_AND_TEST 为准。

---

## 快速开始（分步指南）

> **本节会从零到可用 Bot，逐步带你走完全部流程。**
> 内容覆盖：创建 Discord Bot、申请 OpenAI Key、安装依赖、配置 `.env`、导出历史、导入向量库、可选风格分析与 YouTube 导入、启动与测试，以及 7×24 部署。
> 如果你已经熟悉整体流程，可以直接跳到 [快速开始摘要](#快速开始摘要)。

### 前置条件

开始之前，请确认你已经具备以下条件。如果缺任何一项，后面的步骤都可能在中途卡住（例如没有管理员权限就邀请不了 Bot，没有 OpenAI 账单就调不了 API）：

| 要求 | 获取方式 |
|-------------|----------------|
| **Discord 账号** | https://discord.com |
| **所在 Discord 服务器的管理员权限** | 邀请 Bot 进入服务器时需要 |
| **Python 3.11 或更高版本** | https://www.python.org/downloads/ — 用 `python --version` 检查 |
| **OpenAI 账号** | https://platform.openai.com/signup |
| **OpenAI 已绑定信用卡** | API 访问需要（按量付费 / pay-as-you-go） |
| **Git**（可选） | https://git-scm.com/downloads |

[↑ 返回目录](#目录)

---

### 步骤 A：创建 Discord Bot 应用

> **预计时间：** 约 10 分钟
> **你将得到：** Bot Token，以及你自己的用户 ID
>
> 这一步是后续所有配置的基础：没有 Token 就无法登录 Discord；没有 User ID / Channel ID，就无法正确填写 `.env`。

1. **打开 Discord 开发者门户（Developer Portal）**
   - 访问 https://discord.com/developers/applications
   - 使用你的 Discord 账号登录

2. **创建新应用（Application）**
   - 点击右上角的 **"New Application"** 按钮
   - 命名为类似 **"TreeBot Auto-Reply"** 的名称
   - 点击 **"Create"**

3. **配置 Bot**
   - 在左侧边栏点击 **"Bot"**
   - 点击 **"Reset Token"** → 再点击 **"Yes, do it!"**
   - **立即复制 Token** — 之后不会再完整显示
   - 把它保存在安全位置（稍后会粘贴到 `.env`）

4. **启用必需的 Gateway Intents**
   - 向下滚动到 **"Privileged Gateway Intents"**
   - 打开：✅ **MESSAGE CONTENT INTENT**（必需 — 没有它 Bot 无法读取消息正文）
   - 打开：✅ **SERVER MEMBERS INTENT**（可选，但强烈推荐）
   - 点击 **"Save Changes"**

5. **生成邀请 URL**
   - 在左侧边栏点击 **"OAuth2"** → **"URL Generator"**
   - 在 **Scopes** 中勾选：`bot` 和 `applications.commands`
   - 在 **Bot Permissions** 中勾选：
     - ✅ Read Messages/View Channels
     - ✅ Send Messages
     - ✅ Read Message History
     - ✅ Use Slash Commands
   - 复制页面底部的 **Generated URL**

6. **邀请 Bot 到你的服务器**
   - 把该 URL 粘贴到浏览器中打开
   - 从下拉列表选择你的服务器
   - 点击 **"Authorize"**
   - 完成 CAPTCHA 验证
   - 你应该能在服务器成员列表中看到 Bot（此时为离线状态）

7. **获取你自己的用户 ID**
   - 在 Discord 中进入 **Settings → Advanced → 开启 Developer Mode（开发者模式）**
   - 在任意聊天中右键你自己的名字 → **"Copy User ID"**
   - 保存该 ID — 配置 `.env` 时会用到

8. **获取频道 ID**
   - 右键你希望 Bot 监听的一个或多个频道 → **"Copy Channel ID"**
   - 保存这些 ID — 配置 `.env` 时会用到

> **到这一步，你应该已经有了：** Bot Token、你的 User ID、一个或多个 Channel ID
>
> 建议把这三项先临时记在本地笔记里，下一步配置 `.env` 时直接粘贴，可减少来回切换页面造成的抄写错误。

[↑ 返回目录](#目录)

---

### 步骤 B：获取 OpenAI API Key

> **预计时间：** 约 5 分钟
> **你将得到：** 一个 OpenAI API Key
>
> Bot 的嵌入、生成、（可选）Whisper 转录都依赖这个 Key。建议同时设好月度用量上限，避免测试阶段意外超支。

1. 访问 https://platform.openai.com/api-keys
2. 点击 **"Create new secret key"**
3. 给密钥命名（例如 "Discord Bot"），然后点击 **"Create"**
4. **立即复制密钥** — 之后不会再完整显示
5. 把它保存在安全位置（稍后粘贴到 `.env`）

**账单设置**（如果尚未完成）：
- 访问 https://platform.openai.com/settings/organization/billing/overview
- 添加支付方式
- 在 https://platform.openai.com/settings/organization/limits 设置月度用量上限（例如 $50），以避免意外超支

> **预估费用：** 一次性导入约 200K 帖子大约 $1–3；之后按问题量回答，中等用量大约 $30–50/月。
>
> 实际费用会随提问量、是否开启 Vision / Whisper、以及阈值高低而变化。上线初期可先把 `CONFIDENCE_THRESHOLD` 设高一点，减少无效自动回复带来的调用。

[↑ 返回目录](#目录)

---

### 步骤 C：安装 Python 并搭建项目

> **预计时间：** 约 5 分钟
> **你将得到：** 已安装全部依赖、可正常工作的 Python 环境
>
> 请务必使用虚拟环境，避免与系统全局 Python 包冲突。后面所有 `python -m ...` 命令都默认你已激活 `.venv`。

1. **确认已安装 Python：**
   ```bash
   python --version
   # Should show Python 3.11.x or newer
   ```
   如果尚未安装，请从 https://www.python.org/downloads/ 下载
   > **Windows 用户：** 安装过程中请勾选 ✅ "Add Python to PATH"

2. **打开终端**，并进入项目目录：
   ```bash
   cd c:\treeProjectDiscordBot
   ```

3. **创建虚拟环境（virtual environment）：**
   ```bash
   python -m venv .venv
   ```

4. **激活虚拟环境：**
   ```bash
   # Windows (PowerShell):
   .venv\Scripts\Activate.ps1

   # Windows (CMD):
   .venv\Scripts\activate.bat

   # macOS/Linux:
   source .venv/bin/activate
   ```
   激活成功后，你的提示符前面应出现 `(.venv)`。如果 PowerShell 提示执行策略限制，可先对当前用户放开脚本执行，或改用 CMD 的 `activate.bat`。

5. **安装全部依赖：**
   ```bash
   pip install -r requirements.txt
   ```
   这将安装：`discord.py`、`openai`、`chromadb`、`tiktoken`、`python-dotenv`、`tqdm`、`aiohttp`

[↑ 返回目录](#目录)

---

### 步骤 D：配置环境变量

> **预计时间：** 约 2 分钟
> **你将得到：** 已填入全部凭证的 `.env` 配置文件
>
> `.env` 是运行时配置的唯一来源。Token / Key / 频道 ID 写错时，最常见表现是 Bot 起不来，或者能起来但不回复。

1. **复制示例配置：**
   ```bash
   # Windows:
   copy .env.example .env

   # macOS/Linux:
   cp .env.example .env
   ```

2. **编辑 `.env`**，填入真实值：
   ```env
   DISCORD_BOT_TOKEN=MTIzNDU2Nzg5MDEyMzQ1Njc4OQ.XXXXXX.XXXXXXXXXXXXXXXXXXXXXXXXXX
   OPENAI_API_KEY=sk-proj-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
   OWNER_USER_ID=123456789012345678
   TARGET_CHANNEL_IDS=111111111111111111,222222222222222222
   CONFIDENCE_THRESHOLD=7
   CHROMADB_PATH=./chromadb_store
   LOG_LEVEL=INFO
   ```

   | 字段 | 去哪里找 |
   |-------|-----------------|
   | `DISCORD_BOT_TOKEN` | 来自 [步骤 A.3](#步骤-a创建-discord-bot-应用) |
   | `OPENAI_API_KEY` | 来自 [步骤 B.4](#步骤-b获取-openai-api-key) |
   | `OWNER_USER_ID` | 来自 [步骤 A.7](#步骤-a创建-discord-bot-应用) |
   | `TARGET_CHANNEL_IDS` | 来自 [步骤 A.8](#步骤-a创建-discord-bot-应用)（逗号分隔，不要加空格） |

   > **重要：** 绝不要分享你的 `.env` 文件，也绝不要把它提交到 git。该文件已经写在 `.gitignore` 中。
>
> `TARGET_CHANNEL_IDS` 请使用英文逗号分隔、不要加空格；若先放测试频道 ID，后续切正式频道时记得同步修改并重启 Bot。

[↑ 返回目录](#目录)

---

### 步骤 E：导出 Discord 历史

> **预计时间：** 约 15–60 分钟（取决于频道大小）
> **你将得到：** 位于 `data/exports/` 下、包含全部历史消息的 JSON 文件
>
> 导出质量直接决定知识库质量。大频道请按日期分段，并确认 JSON 里能看到你自己的消息与引用关系。

1. **下载 DiscordChatExporter**
   - 访问 https://github.com/Tyrrrz/DiscordChatExporter/releases
   - 下载最新的 **CLI** 版本：
     - Windows: `DiscordChatExporter.Cli.win-x64.zip`
     - macOS: `DiscordChatExporter.Cli.osx-x64.zip`
     - Linux: `DiscordChatExporter.Cli.linux-x64.zip`
   - 将 zip 解压到方便使用的位置

2. **导出你的频道：**
   ```bash
   # Single channel export:
   DiscordChatExporter.Cli export ^
     -t "YOUR_BOT_TOKEN" ^
     -c CHANNEL_ID ^
     -f Json ^
     -o "c:\treeProjectDiscordBot\data\exports\channel_export.json"
   ```

   > **注意：** 请使用你的 **Bot Token**（Bot 必须已在服务器中，并且具备 Read Message History 权限）。你也可以使用个人用户 Token 做自导出（self-export）。

   对于非常大的频道（200K+ 消息），请按日期范围分段导出，以避免超时：
   ```bash
   DiscordChatExporter.Cli export ^
     -t "YOUR_BOT_TOKEN" ^
     -c CHANNEL_ID ^
     -f Json ^
     --after "2020-01-01" --before "2022-01-01" ^
     -o "c:\treeProjectDiscordBot\data\exports\channel_2020_2021.json"

   DiscordChatExporter.Cli export ^
     -t "YOUR_BOT_TOKEN" ^
     -c CHANNEL_ID ^
     -f Json ^
     --after "2022-01-01" --before "2024-01-01" ^
     -o "c:\treeProjectDiscordBot\data\exports\channel_2022_2023.json"

   DiscordChatExporter.Cli export ^
     -t "YOUR_BOT_TOKEN" ^
     -c CHANNEL_ID ^
     -f Json ^
     --after "2024-01-01" ^
     -o "c:\treeProjectDiscordBot\data\exports\channel_2024_present.json"
   ```

3. **验证导出结果：**
   - 检查 `data/exports/` 目录中是否出现了 `.json` 文件
   - 打开其中一个文件 — 你应该能看到包含你帖子的 `"messages"` 数组
   - 导入脚本会自动加载该文件夹中的全部 `.json` 文件

> **有多个频道？** 对每个频道重复导出即可。导入脚本会自动处理多个文件。
>
> 导出完成后抽查几条消息：确认作者 ID、时间戳、正文，以及（如有）`reference.messageId` 都正常，这样后续 Q&A 配对才可靠。

[↑ 返回目录](#目录)

---

### 步骤 F：导入数据

> **预计时间：** 200K 消息大约需要 15–30 分钟
> **你将得到：** 一个已填充你的帖子、可供 RAG 使用的 ChromaDB 向量数据库
>
> 建议先 `--sample 100` 确认 OpenAI / ChromaDB 通路正常，再跑全量。脚本支持增量导入，重复执行是安全的。

1. **确认虚拟环境已激活**（提示符中应能看到 `(.venv)`）

2. **先用小样本快速测试：**
   ```bash
   python -m ingestion.ingest --sample 100
   ```
   你应该能看到进度条，以及类似这样的提示：`Done — total documents in collection: 100`

3. **如果测试通过，再运行完整导入：**
   ```bash
   python -m ingestion.ingest
   ```
   完整导入会执行以下操作：
   - 解析 `data/exports/` 中的全部 JSON 文件
   - 按 `OWNER_USER_ID` 过滤，只保留你自己的消息
   - 从你的回复构建问答对（Q&A pairs）
   - 将连续消息合并成回答块（answer blocks）
   - 清理文本并按 token 分块（chunk）
   - 通过 OpenAI API 生成嵌入（embeddings）
   - 把一切存入位于 `./chromadb_store/` 的 ChromaDB

   > **进度提示：** 你会看到 `tqdm` 进度条。对于 200K 消息，预计大约 15–30 分钟。

4. **验证导入是否成功：**
   ```bash
   python -c "import chromadb; c = chromadb.PersistentClient('./chromadb_store'); col = c.get_collection('discord_posts'); print(f'Documents stored: {col.count()}')"
   ```

> **重复运行导入：** 脚本支持增量导入（incremental ingestion）— 以后若再导出更多消息，直接再跑一次即可。已经在数据库中的文档会被自动跳过。
>
> 若你改了 Owner ID 或想彻底重建知识库，删除 `chromadb_store/` 后再全量导入即可。日常追加数据则不必删除。

[↑ 返回目录](#目录)

---

### 步骤 G：（可选）分析写作风格

> **预计时间：** 约 1 分钟
> **你将得到：** 一份风格档案，让 Bot 的回答更贴近你的写作风格
>
> 这一步不是硬性依赖，但强烈建议执行。生成出的 `data/style_profile.txt`也会被 RAG system prompt 自动加载。

```bash
python -m ingestion.analyze_style
```

该命令会分析你的消息，并把风格档案保存到 `data/style_profile.txt`，其中包含：
- 你的平均回复长度
- 你最常用的短语
- 你的 emoji 使用模式
- 能够代表你典型风格的样本消息

Bot 在生成回答时会自动加载这个文件。你也可以手动编辑 `data/style_profile.txt`，对风格做进一步微调。

> **推荐：** 请运行这一步。它通常能显著提升生成回答的质量与“像你本人”的程度。

[↑ 返回目录](#目录)

---

### 步骤 G2：（可选）导入 YouTube 视频

> **预计时间：** 约 5 分钟准备 + 每个视频的转录时间
> **你将得到：** 把你的 YouTube 视频内容加入知识库，使 Bot 能基于你在视频中说过的内容回答问题
>
> 有字幕的视频几乎零成本；无字幕时才会走 Whisper。请先装好 ffmpeg，否则音频下载与切分会失败。

脚本 `ingestion/ingest_youtube.py` 会自动处理两种情形：
- **视频已有字幕 / captions** → 直接拉取字幕（免费、即时）
- **视频没有字幕（仅音频）** → 用 `yt-dlp` 下载音频，再用 OpenAI Whisper API 转录（大约 $0.006/分钟）

#### 前置要求

1. **安装 ffmpeg**（下载音频与切分音频时必需）：
   ```powershell
   # Check if already installed:
   ffmpeg -version

   # If not, install with winget:
   winget install Gyan.FFmpeg
   ```
   安装完成后，请重启终端。

2. **确认依赖已安装**（这些依赖已经写在 `requirements.txt` 中）：
   ```powershell
   pip install -r requirements.txt
   ```

#### 用法

**单个视频（自动检测字幕；若无字幕则回退到 Whisper）：**
```powershell
python -m ingestion.ingest_youtube --urls "https://www.youtube.com/watch?v=VIDEO_ID"
```

**一次导入多个视频：**
```powershell
python -m ingestion.ingest_youtube --urls "https://youtu.be/AAA" "https://youtu.be/BBB" "https://youtu.be/CCC"
```

**从文本文件批量导入**（每行一个 URL；视频很多时推荐）：

创建 `my_videos.txt`：
```
https://www.youtube.com/watch?v=AAA
https://www.youtube.com/watch?v=BBB
# Lines starting with # are ignored
https://youtu.be/CCC
```

然后运行：
```powershell
python -m ingestion.ingest_youtube --url-file my_videos.txt
```

**指定 Whisper 转录语言**（默认是中文 `zh`）：
```powershell
python -m ingestion.ingest_youtube --urls "https://youtu.be/AAA" --whisper-lang zh
```

**跳过没有字幕的视频**（禁用 Whisper 回退）：
```powershell
python -m ingestion.ingest_youtube --urls "https://youtu.be/AAA" --no-whisper
```

#### 流水线内部如何工作

```
For each video URL:
    ↓
    1. Try youtube_transcript_api to fetch existing subtitles
       ✅ Found → use directly (free)
       ❌ Not found → go to step 2
    ↓
    2. Download audio via yt-dlp (32K mono MP3, ~14 MB/hr)
       If file < 24 MB → send directly to Whisper API
       If file > 24 MB → split into 10-minute chunks → transcribe each → merge
    ↓
    3. Chunk transcript text → embed via OpenAI → store in ChromaDB
       (incremental — already-ingested videos are skipped)
```

#### 费用估算（Whisper API）

| 视频时长 | 费用 |
|---|---|
| 10 分钟 | ~$0.006 |
| 1 小时 | ~$0.036 |
| 合计 10 小时 | ~$0.36 |

> **增量导入：** 对同一批视频 ID 重复运行命令是安全的 — 已导入的视频会自动跳过。

[↑ 返回目录](#目录)

---

### 步骤 H：启动 Bot

> **预计时间：** 约 1 分钟
> **你将得到：** 一个正在运行、并能在 Discord 频道中自动回复的 Bot
>
> 启动日志里应能看到 OpenAI 初始化、ChromaDB 文档数，以及 listener worker 已启动。若 collection 为空，请先回到导入步骤。

1. **确认虚拟环境已激活**

2. **启动 Bot：**
   ```bash
   python -m bot.main
   ```

3. **检查输出 — 你应该能看到：**
   ```
   2026-05-05 10:30:00 [INFO] bot.main: OpenAI client initialized
   2026-05-05 10:30:00 [INFO] bot.main: ChromaDB collection 'discord_posts' loaded — 150000 documents
   2026-05-05 10:30:00 [INFO] bot.main: Starting Discord bot...
   2026-05-05 10:30:02 [INFO] bot.main: Logged in as TreeBot Auto-Reply#1234 (ID: 999999999999999999)
   2026-05-05 10:30:02 [INFO] bot.main: Serving 1 guild(s)
   2026-05-05 10:30:02 [INFO] bot.listener: Bot is ready — starting message queue worker
   ```

4. **Bot 现在已上线！** 去你的 Discord 频道试着发送一个问题。

> **停止 Bot：** 在终端中按下 `Ctrl+C`。
>
> 正式使用时不要频繁强制杀进程；正常 `Ctrl+C` 可以走优雅退出路径，有利于保存运行状态与日志完整性。

[↑ 返回目录](#目录)

---

### 步骤 I：测试 Bot

> **预计时间：** 约 10 分钟
> **你将得到：** 在正式上线前，确认 Bot 行为正确的信心
>
> 至少覆盖：高信心自动回复、低信心转审核、按钮三态、限流，以及单元测试。测试完成后再切回正式频道。

1. **在你的 Discord 服务器中创建一个私密测试频道**
   - 把 Bot 的角色加入该频道，使其可见可读
   - 把测试频道 ID 加入 `.env` 的 `TARGET_CHANNEL_IDS`
   - 重启 Bot

2. **测试自动回复** — 问一个你知道历史记录里出现过的股票问题：
   ```
   What do you think about AAPL?
   ```
   Bot 应该在几秒内以你的风格回复。

3. **测试置信度路由** — 问一个完全离题的问题：
   ```
   What's the best recipe for chocolate cake?
   ```
   Bot **不应该**在频道里直接回复。相反，你应收到一条 DM，其中包含：
   - 原问题
   - 一份草稿回答
   - Approve / Edit / Reject 三个按钮

4. **测试审核按钮：**
   - 点击 ✅ **Approve** → 草稿会作为回复发到原频道
   - （下次）点击 ✏️ **Edit** → 输入修正后的回答 → 发布该版本
   - （下次）点击 ❌ **Reject** → 不发布任何内容

5. **测试限流** — 快速连续发送 5 条消息。通常只有第一条会得到回复（每用户 30 秒冷却）。

6. **运行单元测试：**
   ```bash
   python -m pytest tests/ -v
   ```

> **测试满意后，从 `TARGET_CHANNEL_IDS` 中移除测试频道，把正式频道加回去，然后重启 Bot。**

[↑ 返回目录](#目录)

---

### 步骤 J：部署以实现 7×24 运行

> **预计时间：** 约 30 分钟
> **你将得到：** 一个无需你的电脑常开即可持续运行的 Bot
>
> 生产推荐 Docker on VPS；若服务器没有 Docker，再用 systemd。部署时记得同步 `chromadb_store/` 与 `.env`。

请参阅 [步骤 14：部署](#步骤-14部署)，其中详细说明了三种方案：

| 方案 | 最适合 | 费用 |
|--------|----------|------|
| **[本机运行](#步骤-14部署)** | 仅用于测试 | 免费（但电脑必须保持开机） |
| **[VPS 上的 Docker](#步骤-14部署)** | 生产环境（推荐） | $4–10/月 |
| **[VPS 上的 systemd](#步骤-14部署)** | 没有 Docker 的 Linux 服务器 | $4–10/月 |

**快速 Docker 部署：**
```bash
# On your VPS:
git clone <your-repo-url>
cd treeProjectDiscordBot
# Create .env with your credentials
# Copy your chromadb_store/ folder from local
docker-compose up -d
```

[↑ 返回目录](#目录)

---

## 架构

整体数据流非常直观：Discord 入站消息先经过过滤，再进入 RAG 流水线完成「嵌入 → 检索 → 生成」，最后依据置信度决定自动回复还是转交 Owner 审核。下面用 ASCII 图把这条主链路画出来（实现细节见后文各阶段）：

```
Discord Channel (incoming message)
       ↓
discord.py bot listener (on_message)
       ↓
Filter (ignore bots, own messages)
       ↓
RAG Pipeline:
  1. Embed the question → OpenAI text-embedding-3-small
  2. Query ChromaDB for top-K (5-10) relevant historical posts
  3. Build prompt: system (style guide) + retrieved context + question
  4. Call GPT-4o-mini → get answer + confidence score
       ↓
Confidence Check:
  ≥ 7/10 → Auto-reply in channel
  < 7/10 → DM owner with question + draft + Approve/Reject buttons
```

---

## 技术栈

| 组件       | 选型                      | 费用                         |
|-----------------|-----------------------------|------------------------------|
| 语言        | Python 3.11+                | 免费                         |
| Discord 库 | discord.py v2.x             | 免费                         |
| LLM             | OpenAI GPT-4o-mini          | ~$0.15/1M input tokens       |
| 嵌入模型      | text-embedding-3-small      | ~$0.02/1M tokens             |
| 向量数据库       | ChromaDB（本地持久化）| 免费                         |
| 数据导出工具     | DiscordChatExporter CLI     | 免费                         |

**预估月度费用**：在中等用量下（最多约 1000 问/天）大约 $30–50/月。
**一次性导入费用**：导入约 200K 帖子大约 $1–3。

选型原则是：尽量使用本地可持久化的向量库（ChromaDB）降低运维成本；用便宜的 embedding 模型与 GPT-4o-mini 控制生成成本；用 DiscordChatExporter 完成一次性历史导出，而不引入额外 SaaS 依赖。

这也意味着你可以把知识库与 Bot 一起备份/迁移：复制 `chromadb_store/`、`data/` 与 `.env`，在新机器上恢复后即可继续服务。注意备份时不要把真实 Token 发到公开渠道；迁移后先在测试频道验证，再切正式流量。

[↑ 返回目录](#目录)

---

## 项目结构

仓库按「运行层 / 导入层 / 数据与测试」划分。`bot/` 负责在线回复与审核；`ingestion/` 负责离线把历史数据写入 ChromaDB；`data/exports/` 放导出的 JSON；`tests/` 覆盖核心模块。`logs/` 与 `chromadb_store/` 属于运行期产物，通常不应提交到版本库。

```
treeProjectDiscordBot/
├── bot/
│   ├── __init__.py
│   ├── main.py              # Bot entry point & startup
│   ├── config.py            # Settings, env vars, constants
│   ├── listener.py          # on_message handler & message filtering
│   ├── rag.py               # RAG pipeline: embed → retrieve → generate
│   ├── confidence.py        # Confidence scoring & routing logic
│   └── review.py            # Owner DM review interface (approve/reject)
├── ingestion/
│   ├── __init__.py
│   ├── ingest.py            # Main ingestion script: JSON → ChromaDB
│   ├── preprocess.py        # Message cleaning, grouping, chunking
│   └── analyze_style.py     # Analyze posts for style patterns
├── data/
│   └── exports/             # Place exported JSON files here
├── chromadb_store/           # Persisted ChromaDB data (auto-created)
├── logs/                     # Runtime logs
├── tests/
│   ├── __init__.py
│   ├── test_ingestion.py
│   ├── test_rag.py
│   └── test_confidence.py
├── .env                      # API keys & bot token (NEVER commit)
├── .env.example              # Template for .env
├── .gitignore
├── requirements.txt
├── Dockerfile                # For containerized deployment
├── docker-compose.yml        # For containerized deployment
└── PLAN.md                   # ← This file
```

[↑ 返回目录](#目录)

---

## 阶段 1：搭建与数据采集

本阶段的目标是把「能登录 Discord 的 Bot」「可导出的历史数据」「可运行的项目脚手架」三件事准备好。完成之后，你就具备进入数据导入与 RAG 开发的全部前置条件。如果你已经按「快速开始」做过步骤 A–D，本阶段可主要当作实现细节对照表来读。

### 步骤 1：创建 Discord Bot 应用

**操作说明：**

1. 访问 https://discord.com/developers/applications
2. 点击 "New Application" → 命名（例如 "TreeBot Auto-Reply"）
3. 进入左侧边栏的 **Bot** 区段
4. 点击 "Reset Token" → 复制并妥善保存 Token
5. 在 **Privileged Gateway Intents** 下启用：
   - ✅ MESSAGE CONTENT INTENT（读取消息文本所必需）
   - ✅ SERVER MEMBERS INTENT（可选，用于 mention 解析）
6. 进入 **OAuth2 → URL Generator**：
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Read Messages/View Channels`, `Send Messages`, `Read Message History`, `Use Slash Commands`
7. 复制生成的 URL → 在浏览器中打开 → 邀请 Bot 到你的服务器
8. 记下你自己的 Discord User ID（在 Discord 设置中开启开发者模式 → 右键你的名字 → Copy ID）

**产出：** Bot Token + 你的 User ID

这一步与「快速开始」中的步骤 A 对应；如果你已经按分步指南创建过 Bot，可以直接复用同一套 Token 与 ID。

### 步骤 2：导出历史消息

**操作说明：**

1. 从 https://github.com/Tyrrrz/DiscordChatExporter/releases 下载 DiscordChatExporter CLI
2. 你需要 **用户 Token**（用于自导出）或者具备 Read Message History 权限的 Bot Token
3. 找到你的频道 ID（开启开发者模式后，右键频道 → Copy ID）
4. 运行导出命令：

```bash
# Using bot token:
DiscordChatExporter.Cli export \
  -t "YOUR_BOT_TOKEN" \
  -c CHANNEL_ID \
  -f Json \
  -o data/exports/channel_export.json

# If the channel is very large, export in date ranges:
DiscordChatExporter.Cli export \
  -t "YOUR_BOT_TOKEN" \
  -c CHANNEL_ID \
  -f Json \
  --after "2020-01-01" \
  --before "2023-01-01" \
  -o data/exports/channel_2020_2022.json
```

5. 如果有多个频道，对每个频道重复上述步骤
6. 把所有 JSON 文件放到 `data/exports/`

**产出：** `data/exports/` 中包含全部消息的 JSON 文件

如果频道非常大，优先按年份或半年度切分导出，再把多个 JSON 一起放进 `data/exports/`。导入脚本会自动读取目录下全部文件。

**JSON 结构**（DiscordChatExporter 格式）：
```json
{
  "messages": [
    {
      "id": "123456789",
      "timestamp": "2023-01-15T10:30:00+00:00",
      "content": "The message text...",
      "author": {
        "id": "YOUR_USER_ID",
        "name": "YourName",
        "nickname": "YourNick"
      },
      "reference": {
        "messageId": "original_message_id"
      }
    }
  ]
}
```

### 步骤 3：项目脚手架

**已经创建。** 项目结构与全部文件已经就位。

如果你是从空目录开始，确认仓库文件齐全后再继续；下面两步会把运行环境与密钥配置补齐。

1. 搭建虚拟环境：

```bash
python -m venv .venv
.venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

2. 将 `.env.example` 复制为 `.env`，并填入真实值：

```env
DISCORD_BOT_TOKEN=your_bot_token_here
OPENAI_API_KEY=your_openai_api_key_here
OWNER_USER_ID=your_discord_user_id_here
TARGET_CHANNEL_IDS=channel_id_1,channel_id_2
CONFIDENCE_THRESHOLD=7
CHROMADB_PATH=./chromadb_store
LOG_LEVEL=INFO
```

> **需要更详细的帮助？** 参见分步指南：[步骤 A（Discord Bot）](#步骤-a创建-discord-bot-应用) | [步骤 B（OpenAI Key）](#步骤-b获取-openai-api-key) | [步骤 C（Python 搭建）](#步骤-c安装-python-并搭建项目) | [步骤 D（配置 .env）](#步骤-d配置环境变量) | [步骤 E（导出历史）](#步骤-e导出-discord-历史)

[↑ 返回目录](#目录)

---

## 阶段 2：数据导入流水线

本阶段把原始 Discord JSON 变成可检索的向量知识库：先清洗与重组消息，再调用 OpenAI 生成嵌入，最后写入本地 ChromaDB。建议先用 `--sample 100` 验证通路，再跑全量导入。全量导入属于一次性成本，但知识库质量会长期影响自动回复命中率。

### 步骤 4：预处理消息

**文件：** `ingestion/preprocess.py` *(已实现)*

该模块读取 DiscordChatExporter 导出的原始 JSON，并把它们准备成可用于嵌入的文档。预处理质量会直接影响后续检索相关性，因此会同时做问答配对、连续消息合并与分块。

**它具体做什么：**

1. **加载 JSON 导出** — 读取 `data/exports/` 下全部 `.json` 文件，提取消息与用户信息
2. **构建 Q&A 对** — 对 Owner 回复其他用户问题的每条消息，创建配对文档：
   ```
   Q: What stock should I buy?
   A: I like AAPL right now, support at 180
   ```
   这些是最有价值的训练数据 — 真实问答，而且完全是你的风格。
3. **合并连续消息** — 将 2 分钟内连续发出的多条 Owner 消息合并成单个“回答块”
4. **清理消息** — 将 `<@USER_ID>` mention 解析为可读名字，把自定义 emoji 转为 `:name:` 格式，并移除频道 / 角色 mention 残留
5. **过滤琐碎消息** — 移除少于 10 个字符的消息，以及内容只是 URL 的消息
6. **长消息分块** — 在段落 / 句子边界处切分超过 500 token 的文本，块与块之间保留 50 token 重叠

**关键函数：**
- `load_exports(export_dir)` → `(messages, users)` — 加载全部 JSON 文件
- `build_qa_pairs(messages, owner_id)` → `[{text, metadata}]` — 提取问答对
- `group_consecutive(messages, owner_id, window_seconds=120)` → `[{text, metadata}]` — 合并连续帖子
- `clean_message(content, users)` → `str` — 清理格式
- `chunk_text(text, max_tokens=500, overlap=50)` → `[str]` — 切分长文本
- `preprocess_all(export_dir, owner_id)` → `[{id, text, metadata}]` — 完整流水线

**输出格式**（每一项都已准备好可直接嵌入）：
```python
{
    "id": "123456",          # message ID (or message_id_chunkN)
    "text": "The text to embed",
    "metadata": {
        "source_message_id": "123456",
        "timestamp": "2023-01-15T10:30:00",
        "type": "qa_pair" | "standalone" | "grouped",
        "question": "What was asked",  # only for qa_pair type
        "channel_id": "channel_id",
        "chunk_index": 0,
        "total_chunks": 1
    }
}
```

### 步骤 5：生成嵌入并写入 ChromaDB

**文件：** `ingestion/ingest.py` *(已实现)*

该脚本接收预处理后的文档，通过 OpenAI 生成嵌入，并把全部内容存入持久化的 ChromaDB collection。它支持去重与增量导入，因此你可以反复追加新导出，而不必每次重建整个库。

**它具体做什么：**

1. **初始化 ChromaDB**，使用基于余弦相似度（cosine similarity）的持久化存储：
   ```python
   client = chromadb.PersistentClient(path="./chromadb_store")
   collection = client.get_or_create_collection(
       name="discord_posts",
       metadata={"hnsw:space": "cosine"}
   )
   ```

2. **去重检查** — 查询 collection 中已有的 ID，跳过已经导入的文档（从而支持增量导入）

3. **批量嵌入与存储** — 按每批 100 条文档处理：
   - 调用 `openai.embeddings.create(model="text-embedding-3-small", input=batch_texts)`
   - 把嵌入、文档正文与元数据一起写入 ChromaDB
   - 用 `tqdm` 显示进度条
   - 批次之间延迟 0.25 秒，用于限速
   - 遇到 `RateLimitError` 时以 30 秒退避重试一次

4. **错误处理** — 记录并跳过失败批次，避免整个导入过程崩溃

**运行命令：**
```bash
# Full ingestion
python -m ingestion.ingest

# Test with a small sample
python -m ingestion.ingest --sample 100

# Custom paths
python -m ingestion.ingest --export-dir ./data/exports --owner-id YOUR_ID --db-path ./chromadb_store
```

**预计耗时**：200K 消息 → 大约 150–250K 个 chunk → 嵌入 + 存储大约需要 15–30 分钟。

导入过程中如果频繁触发 `RateLimitError`，可把 `EMBED_BATCH_SIZE` 调小，或检查 OpenAI 组织额度；脚本本身已带退避重试，通常短暂限流后会继续。

### 步骤 5b（可选）：分析风格

**文件：** `ingestion/analyze_style.py` *(已实现)*

分析 Owner 的历史消息，自动提取风格特征。输出会用于 system prompt，从而实现更准确的风格匹配。你也可以在生成后手动编辑 `data/style_profile.txt`，进一步约束语气与用词。

**它会分析什么：**
- 平均回复长度（按词数 / 句数）
- 常用短语（top bigram 与 trigram）
- emoji 使用模式（用哪些、多频繁）
- 消息长度分布（短 / 中 / 长）
- 常用开头词
- 中位长度附近的样本消息，作为语气参考

**运行命令：**
```bash
python -m ingestion.analyze_style
```

**产出：** 将风格档案保存到 `data/style_profile.txt`。Bot 的 RAG 流水线（`bot/rag.py`）如果发现该文件存在，会自动加载，并把它写入 system prompt。

> **需要更详细的帮助？** 参见分步指南：[步骤 F（导入数据）](#步骤-f导入数据) | [步骤 G（分析风格）](#步骤-g可选分析写作风格)

[↑ 返回目录](#目录)

---

## 阶段 3：RAG 流水线

RAG（Retrieval-Augmented Generation）是 Bot「像你一样回答」的核心：先检索最相关的历史帖，再让 LLM 只基于这些上下文生成，并输出可路由的置信度分数。本阶段拆成检索、生成、路由三步。三者必须联调：只测生成不够，还要确认检索距离与路由阈值在真实问题上表现合理。

### 步骤 6：构建检索模块

**文件：** `bot/rag.py` — `retrieve_context()` 函数 *(已实现)*

**工作原理：**

1. **嵌入入站问题**，使用同一个 `text-embedding-3-small` 模型（通过 `openai.AsyncOpenAI` 异步调用）
2. **查询 ChromaDB**，取 top-K（默认 8）条最相似文档：
   ```python
   results = collection.query(
       query_embeddings=[question_embedding],
       n_results=8,
       include=["documents", "metadatas", "distances"]
   )
   ```
3. **后处理结果：**
   - 过滤掉 cosine distance 大于 0.8 的结果（可通过 `RAG_MAX_DISTANCE` 配置）
   - 按文本前 100 个字符去重近似相同的内容
   - 返回按相关度排序的 `{text, score, distance, metadata}` 列表

**配置**（通过 `.env` 或 `bot/config.py`）：
- `RAG_TOP_K=8` — 要检索的结果数量
- `RAG_MAX_DISTANCE=0.8` — 最大 cosine distance 阈值

如果检索结果经常被距离阈值过滤掉，先检查知识库是否覆盖该类问题，再考虑略微放宽 `RAG_MAX_DISTANCE`，而不是直接降低生成温度。

### 步骤 7：构建生成模块

**文件：** `bot/rag.py` — `generate_answer()` 函数 *(已实现)*

**工作原理：**

1. **加载风格指南** — 优先读取 `data/style_profile.txt`；若不存在则回退到默认指南
2. **构建 system prompt**，使用 `bot/config.py` 中的模板：
   ```
   You are an AI assistant that responds EXACTLY in the style of the channel owner.
   You are answering questions in a Discord stock/investing channel.

   STYLE GUIDELINES:
   {loaded from style_profile.txt or defaults}

   RULES:
   1. ONLY answer based on the provided context from historical posts
   2. If the context doesn't contain enough information, say so
   3. Do NOT make up financial advice — only relay what was previously said
   4. Match the tone, length, and vocabulary exactly
   5. Do NOT add disclaimers unless the original style includes them

   At the end, output EXACTLY:
   CONFIDENCE: X  (1-10 scale)
   ```

3. **构建 user prompt**，把检索到的上下文块格式化为编号示例，并区分 Q&A 对与独立帖

4. **调用 GPT-4o-mini**，使用 `temperature=0.7`、`max_tokens=500`

5. **解析响应** — 用正则提取回答正文与 `CONFIDENCE: X` 分数。如果解析失败，则默认 confidence=3（一个偏安全的低值）

6. **遇到 `APITimeoutError` 时重试一次**

**完整流水线函数：** `run_rag_pipeline(question, collection, openai_client)` → `(answer, confidence, context_chunks)`

生成阶段的关键约束是：回答必须来自检索上下文，不能凭空编造投资建议；同时末尾的 `CONFIDENCE: X` 会成为下一步路由的核心输入。

### 步骤 8：置信度路由

**文件：** `bot/confidence.py` *(已实现)*

**路由逻辑：**

| 条件 | 动作 | 原因 |
|-----------|--------|--------|
| `confidence >= 7` AND `best_distance <= 0.6` AND `context_count > 0` | `auto_reply` | 高信心，且上下文足够相关 |
| `confidence < 7` | `forward_to_owner` | 低于阈值 |
| `context_count == 0` | `forward_to_owner` | 没有找到相关上下文 |
| `best_distance > 0.6` | `forward_to_owner` | 上下文差异过大（即使 LLM 自称有信心） |

**函数：** `route_answer(answer, confidence, threshold=7, context_count=0, best_distance=1.0)` → `{action, answer, confidence, reason}`

阈值可通过 `.env` 中的 `CONFIDENCE_THRESHOLD` 进行配置。

上线初期建议先偏保守（例如 8–9），观察审核通过率后再逐步下调；如果几乎所有转发都被 Approve，说明可以安全地让更多回答自动发出。

[↑ 返回目录](#目录)

---

## 阶段 4：Discord Bot 集成

本阶段把已经可用的 RAG 能力接到真实 Discord 事件上：监听消息、限流排队、自动回复，以及在低信心时把草稿发给 Owner 审核。完成后，Bot 就可以在测试频道里端到端工作。建议先在私密频道验证，再把 TARGET_CHANNEL_IDS 切到正式频道，避免初期阈值或风格未调准时打扰真实用户。 正式切换前保留测试频道 ID 以便回滚。 观察至少一天的自动回复率与审核负载后再扩大监听范围。

### 步骤 9：Bot 监听器

**文件：** `bot/listener.py` *(已实现)*

`MessageListener` Cog 负责处理全部入站消息，并完成过滤、限流以及异步队列处理。设计重点是：不要阻塞 Discord 事件循环，也不要让突发消息打爆 OpenAI 配额。

**消息过滤器**（任一条件匹配即跳过）：
- `message.author.bot` — 忽略所有 Bot（包括自身）
- `message.author.id == OWNER_USER_ID` — 不要回复 Owner
- `message.channel.id not in TARGET_CHANNEL_IDS` — 忽略非目标频道
- 空消息，或者没有任何文本内容的消息

**限流机制：**
- **每用户冷却：** 每位用户最多每 30 秒收到 1 次回复（可通过 `USER_COOLDOWN_SECONDS` 配置）
- **全局冷却：** 全局最多每分钟 10 次回复（可通过 `GLOBAL_MAX_PER_MINUTE` 配置）

**处理队列：**
- 使用 `asyncio.Queue`，避免阻塞事件循环
- 单个后台 worker 任务按顺序处理消息
- 防止并发 OpenAI API 调用把 Bot 压垮

**消息处理流程：**
1. 处理期间显示 typing 指示器
2. 调用 `run_rag_pipeline(question)` — 检索上下文并生成回答
3. 调用 `route_answer()` — 决定自动回复还是转发审核
4. 若自动回复：调用 `message.reply(answer)`（截断到 2000 字符，以符合 Discord 限制）
5. 若转发：调用 `send_for_review()` — 向 Owner 发送带 approve / edit / reject 按钮的 DM
6. 为每次交互记录结构化 JSON 日志（问题、信心、动作、响应时间）

这条链路保证了「可读、可限流、可审计」：用户侧有 typing 反馈，系统侧有队列与日志，Owner 侧在低信心时仍可人工接管。

### 步骤 10：将 RAG 流水线接入 Bot

**文件：** `bot/main.py` *(已实现)*

这是把所有部件串在一起的入口程序。它负责校验配置、初始化外部依赖、注册 Cog，并真正启动 Discord 连接：

1. **验证配置** — 检查已经设置 `DISCORD_BOT_TOKEN` 与 `OPENAI_API_KEY`
2. **初始化 OpenAI** 异步客户端
3. **初始化 ChromaDB** — 加载已有 collection，若不存在则创建空 collection（并给出需要先运行导入的警告）
4. **创建 Discord Bot**，并启用必需 intents（`message_content`、`members`）
5. **注册 MessageListener Cog**
6. **启动 Bot**

**运行命令：**
```bash
python -m bot.main
```

### 步骤 11：Owner 审核界面

**文件：** `bot/review.py` *(已实现)*

当信心低于阈值时，Bot 会向 Owner 发送一条包含富文本 Embed 与交互按钮的私信。这样可以在自动回复不够稳妥时，仍保留人工发布的最终控制权。

**这条 DM 包含：**
- 问题是在哪个频道提出的
- 提问者是谁
- 置信度分数（X/10）
- 完整的问题文本
- 草稿回答
- 使用过的 Top 3 上下文片段（缩略版）
- 跳转到原始消息的链接

**三个按钮：**
| 按钮 | 动作 |
|--------|--------|
| ✅ **Approve** | 把草稿回答作为回复发到原频道 |
| ✏️ **Edit** | 提示 Owner 输入编辑后的回答（5 分钟超时），然后发布该版本 |
| ❌ **Reject** | 丢弃草稿 — 不发送任何回复 |

**超时：** 如果 Owner 在 1 小时内没有响应，审核会静默过期（不会发送回复）。

**防双击保护：** `handled` 标志可以防止同一条审核被操作两次。

另外请注意：审核按钮依赖 Bot 进程内存中的 View 状态。如果 Bot 重启，未处理完的旧按钮通常会失效，需要重新触发一次审核。

> **需要更详细的帮助？** 参见分步指南：[步骤 H（启动 Bot）](#步骤-h启动-bot) | [步骤 I（测试 Bot）](#步骤-i测试-bot)

[↑ 返回目录](#目录)

---

## 阶段 5：打磨与部署

当核心链路能跑通之后，本阶段补齐可观测性、后续反馈闭环思路，以及 7×24 部署方案。生产上线前，至少要确认日志可读、限流有效、审核按钮可用，并选择一种可持续运行的部署方式。若只是本地验证，本机运行即可；一旦准备对外服务，优先选择带卷挂载的 Docker 方案，便于备份知识库与日志。 systemd 适合已经熟悉 Linux 服务管理、且不想引入容器层的场景。

### 步骤 12：日志与监控

**已集成到各个模块中。**

- **Python logging** 同时输出到控制台与 `logs/bot.log`（在 `bot/config.py` 中配置）
- **结构化 JSON 日志**，覆盖每一次处理过的查询：
  ```json
  {
    "event": "query_processed",
    "question": "What about AAPL?",
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
- 路由决策会带着原因一起记录
- 错误条件会带着完整 traceback 一起记录

有了这些日志，你就能统计自动回复率、平均信心、慢查询，并在排错时快速定位是检索太差、阈值过严，还是外部 API 超时。

### 步骤 13：反馈闭环（未来增强）

在 Bot 稳定运行之后，可以继续完善反馈闭环，让系统越用越贴近你的真实口径：

1. **自动导入已批准的回答** — 当 Owner 批准一条被转发的回答时，把它嵌入并写入 ChromaDB
2. **追踪拒绝模式** — 如果某类问题总是被拒绝，考虑增加显式处理逻辑
3. **定期重新导入** — 随着 Owner 继续手动发帖，定期导出并导入新消息
4. **阈值调优** — 在积累 100+ 次交互后分析批准率：
   - 如果超过 90% 被批准 → 把阈值降到 6
   - 如果低于 70% 被批准 → 把阈值升到 8

这些增强项不是上线阻塞项；先保证自动回复安全可控，再根据真实审核数据迭代，通常更稳。

### 步骤 14：部署

**方案 A：本机运行（先从这里开始）**
```bash
cd treeProjectDiscordBot
.venv\Scripts\activate
python -m bot.main
```
- 保持终端打开，或者使用进程管理器
- 并不理想：电脑必须 7×24 保持开机

**方案 B：VPS 上的 Docker（生产环境推荐）**

项目已经包含 `Dockerfile` 与 `docker-compose.yml`。

1. 获取一台 VPS：DigitalOcean（$6/月）、Hetzner（$4/月）或 Railway（按用量计费）
2. 把仓库 clone 到服务器
3. 用你的凭证创建 `.env` 文件
4. 运行：
```bash
docker-compose up -d
```

该 Docker 配置会把 `chromadb_store/`、`logs/` 与 `data/` 挂载为卷，因此容器重启后数据仍然保留。首次部署时记得把本机已经导入好的 `chromadb_store/` 一并拷到服务器，否则容器里会是空库。同时确认服务器时区与系统时间正确，避免排程类功能出现偏差。

**方案 C：systemd（没有 Docker 的 Linux VPS）**
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
```

> **需要更详细的帮助？** 参见 [步骤 J（部署以实现 7×24）](#步骤-j部署以实现-724-运行)

[↑ 返回目录](#目录)

---

## 实现顺序与依赖

```
Step 1 (Discord Bot App) ──────────────────────────────┐
Step 2 (Export Data) ──→ Step 4 (Preprocess) ──→ Step 5 (Ingest) ──→ Step 6 (Retrieve) ──→ Step 7 (Generate) ──→ Step 8 (Confidence)
Step 3 (Scaffold) ─────→ Step 9 (Listener) ──────────────────────────────────────────────────────────────┘
                                                                                                          ↓
                                                                                              Step 10 (Wire Together)
                                                                                                          ↓
                                                                                              Step 11 (Review UI)
                                                                                                          ↓
                                                                                              Step 12 (Logging)
                                                                                                          ↓
                                                                                              Step 14 (Deploy)
```

- 步骤 1、2、3 可以并行完成（彼此独立的搭建任务）
- 步骤 4–8 需要按顺序执行（数据流水线）
- 步骤 9 可以与步骤 4–8 并行（Bot 监听器独立于 RAG 流水线）
- 步骤 10 及之后同时需要 RAG 流水线与 Bot 监听器都已就绪

实践建议：先并行完成账号 / 导出 / 脚手架，再一口气跑通预处理与导入；与此同时可以先把监听器 Cog 搭好。两边都就绪后，再做接线、审核 UI、日志与部署，返工成本最低。

[↑ 返回目录](#目录)

---

## 快速开始摘要

> 已经懂了？这里是精简版。更详细的走查请看对应链接。
> 建议按表中顺序执行；其中风格分析与 YouTube 导入可选，但不影响最小可用路径。

| # | 动作 | 命令 / 链接 | 时间 |
|---|--------|---------------|------|
| 1 | 创建 Discord Bot 并获取 Token | [步骤 A](#步骤-a创建-discord-bot-应用) | ~10 分钟 |
| 2 | 获取 OpenAI API Key | [步骤 B](#步骤-b获取-openai-api-key) | ~5 分钟 |
| 3 | 搭建 Python 并安装依赖 | [步骤 C](#步骤-c安装-python-并搭建项目) — `pip install -r requirements.txt` | ~5 分钟 |
| 4 | 配置 `.env` | [步骤 D](#步骤-d配置环境变量) — `copy .env.example .env` | ~2 分钟 |
| 5 | 导出 Discord 历史 | [步骤 E](#步骤-e导出-discord-历史) — DiscordChatExporter CLI | ~15–60 分钟 |
| 6 | 导入数据到向量库 | [步骤 F](#步骤-f导入数据) — `python -m ingestion.ingest` | ~15–30 分钟 |
| 7 | 分析风格（可选） | [步骤 G](#步骤-g可选分析写作风格) — `python -m ingestion.analyze_style` | ~1 分钟 |
| 8 | 启动 Bot | [步骤 H](#步骤-h启动-bot) — `python -m bot.main` | ~1 分钟 |
| 9 | 测试 Bot | [步骤 I](#步骤-i测试-bot) | ~10 分钟 |
| 10 | 部署以实现 7×24 | [步骤 J](#步骤-j部署以实现-724-运行) | ~30 分钟 |

```bash
# Quick copy-paste version:
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env                    # then edit .env with your real values
# ... export Discord history to data/exports/ ...
python -m ingestion.ingest
python -m ingestion.analyze_style         # optional
python -m bot.main
```

把上面当作最小可用路径即可：先导入、再（可选）分析风格、最后启动。若中途失败，优先回到对应分步章节，而不是跳过检查直接部署。YouTube 导入与 7x24 部署可在最小可用验证通过后再做。

[↑ 返回目录](#目录)

---

## 验证清单

上线前请至少完成下面这些检查。它们分别覆盖数据导入、RAG 质量、路由决策、端到端交互与稳定性。不必一次做完美，但自动回复、审核按钮与限流这三项必须通过后再对外。

1. **导入测试** — 导入 100 条样本消息 → 查询 ChromaDB → 验证返回结果相关
   ```bash
   python -m ingestion.ingest --sample 100
   python -c "import chromadb; c = chromadb.PersistentClient('./chromadb_store'); col = c.get_collection('discord_posts'); print(col.count()); print(col.query(query_texts=['what stock should I buy'], n_results=3))"
   ```

2. **RAG 质量测试** — 从真实频道历史准备 10 个问题 → 跑一遍 RAG 流水线 → 与真实回答对比
   ```bash
   python -m pytest tests/test_rag.py -v
   ```

3. **置信度路由测试** — 运行单元测试
   ```bash
   python -m pytest tests/test_confidence.py -v
   ```

4. **导入单元测试**
   ```bash
   python -m pytest tests/test_ingestion.py -v
   ```

5. **风格一致性测试** — 让熟悉你频道的人盲读 5 条生成回答 — 他们能不能看出这不是你写的？

6. **端到端测试** — 创建私密测试频道 → 加入 Bot → 发送消息 → 验证出现回复

7. **限流测试** — 同一用户快速发送 10 条消息 → 验证通常只有 1 条得到回复（冷却生效）

8. **Owner 审核测试** — 触发一条低信心响应 → 验证收到带按钮的 DM → 分别测试 approve、edit、reject 流程

9. **稳定性测试** — 连续运行 Bot 24 小时 → 验证没有崩溃、没有内存泄漏、没有连接中断

若第 5 项风格不像，优先重跑 `analyze_style` 并检查 system prompt；若第 8 项按钮无响应，先确认 Bot 进程未重启且 DM 权限正常。

[↑ 返回目录](#目录)

---

## 故障排查

大多数问题都可以归到四类：权限 / Intent 未开、`.env` 配错、知识库还没导入、限流或阈值过严。先看 `logs/bot.log`，再按下面表格逐项排查。若日志里完全没有 query 事件，优先查频道过滤与 Intent；若有 query 但总是 forward，再调阈值与检索。

### Bot 已连接，但不回复消息

| 可能原因 | 修复方法 |
|---------------|-----|
| 未启用 MESSAGE CONTENT INTENT | 前往 Discord 开发者门户 → Bot → 启用 ✅ MESSAGE CONTENT INTENT。参见 [步骤 A.4](#步骤-a创建-discord-bot-应用) |
| 频道 ID 不在 `TARGET_CHANNEL_IDS` 中 | 检查 `.env` — 必须列出该频道 ID。参见 [步骤 D](#步骤-d配置环境变量) |
| Bot 没有 Read Messages 权限 | 用正确权限重新邀请。参见 [步骤 A.5](#步骤-a创建-discord-bot-应用) |
| 你是 Owner，正在自己发消息 | Bot 按设计会忽略来自 `OWNER_USER_ID` 的消息。请用另一个账号测试，或临时修改该 ID |
| 限流正在生效 | 等待 30 秒（每用户冷却）。同时检查 `logs/bot.log` |

### `DISCORD_BOT_TOKEN is not set` 错误

你的 `.env` 文件缺失，或者 Token 字段为空。先确认文件名确实是 `.env`（不是 `.env.txt`），并且 `DISCORD_BOT_TOKEN=` 后面有值。参见 [步骤 D](#步骤-d配置环境变量)。

### `OPENAI_API_KEY is not set` 错误

你的 `.env` 文件缺少 OpenAI Key。常见错误是复制时带了空格，或误用了占位符文本。参见 [步骤 B](#步骤-b获取-openai-api-key)。

### `ChromaDB collection 'discord_posts' not found` 警告

你还没有运行导入步骤，或 ChromaDB 路径与 `.env` 中的 `CHROMADB_PATH` 不一致。参见 [步骤 F](#步骤-f导入数据)：
```bash
python -m ingestion.ingest
```

### 导入时出现 `No JSON files found`

导出文件不在正确的目录中。请把 `.json` 文件放到 `data/exports/`，并确认扩展名是 `.json`。参见 [步骤 E](#步骤-e导出-discord-历史)。

### 导入时出现来自 OpenAI 的 `RateLimitError`

脚本会以 30 秒退避自动重试。如果问题持续存在：
- 减小批量大小：在 `.env` 中加入 `EMBED_BATCH_SIZE=50`
- 到 https://platform.openai.com/settings/organization/limits 检查你的用量限制

### Bot 回复一切 / 什么都不回复

- **回复一切：** 检查 `TARGET_CHANNEL_IDS` — 如果为空，Bot 会监听全部频道。请设置具体的频道 ID。
- **什么都不回复：** 检查 `CONFIDENCE_THRESHOLD` — 如果设得过高（例如 10），Bot 会把几乎一切都转发给你。测试时可以先降到 `5`。

也可以结合日志里的 `action` / `reason` 字段判断：若大量是 `forward_to_owner`，多半是阈值或检索距离过严；若根本没有 `query_processed` 记录，则更可能是频道过滤或 Intent 问题。

### DM 审核按钮无效

- Bot 必须保持运行，按钮才能工作（它们是在进程内处理的）
- 按钮会在 1 小时后过期
- 确认你的 DM 已开启（Discord Settings → Privacy → Allow direct messages）
- 若刚刚重启过 Bot，请重新触发一次低信心问题以生成新的审核消息

### `pip install` 失败

- 确认你使用的是 Python 3.11+（`python --version`）
- 确认虚拟环境已激活（提示符中应有 `(.venv)`）
- 在 Windows 上如果找不到 `pip`，请尝试 `python -m pip install -r requirements.txt`
- 若公司网络或代理导致下载失败，可临时配置 pip 镜像源后再重试
- 个别包编译失败时，先升级 `pip` / `setuptools` / `wheel`，再重新安装

[↑ 返回目录](#目录)

---

## 安全考虑

- **绝不要提交 `.env`** — Bot Token 与 API Key 必须留在版本控制之外（项目已配置 `.gitignore`）
- **输入清理** — 用户消息会被包在 context framing 中，绝不会以原始形式注入 system prompt
- **限流** — 每用户冷却与全局冷却用于防止滥用，以及 API 费用失控
- **金融安全** — Bot 从不生成“新颖”的投资建议 — 只转述历史上已经说过的内容（由 system prompt 强制约束）
- **最小权限** — Bot 只需要 Read Messages、Send Messages、Read Message History（不需要 admin，也不需要 manage channels）
- **Docker 中的密钥** — 在 docker-compose 中使用 `env_file`，绝不要把密钥烘焙进镜像

总之：把密钥当密钥管，把用户输入当不可信输入处理，把自动回复限制在「历史已说过」的范围内，并始终给 Owner 保留低信心人工闸门。

[↑ 返回目录](#目录)

---

## 配置参考

全部设置都通过 `.env` 配置（参见 `.env.example`）。下表列出本计划涉及的核心变量；改完后通常需要重启 Bot 才会生效。生产环境请用环境变量或 `env_file` 注入，不要把真实密钥写进镜像或文档示例：

| 变量 | 默认值 | 说明 |
|----------|---------|-------------|
| `DISCORD_BOT_TOKEN` | — | 你的 Discord Bot Token |
| `OPENAI_API_KEY` | — | 你的 OpenAI API Key |
| `OWNER_USER_ID` | — | 你的 Discord 用户 ID |
| `TARGET_CHANNEL_IDS` | — | 要监听的频道 ID（逗号分隔） |
| `CONFIDENCE_THRESHOLD` | `7` | 自动回复的最低信心（1–10） |
| `CHROMADB_PATH` | `./chromadb_store` | ChromaDB 持久化存储路径 |
| `LOG_LEVEL` | `INFO` | Python 日志级别 |
| `LLM_MODEL` | `gpt-4o-mini` | 用于生成的 OpenAI 模型 |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | 用于嵌入的 OpenAI 模型 |
| `LLM_MAX_TOKENS` | `500` | 生成响应的最大 token 数 |
| `LLM_TEMPERATURE` | `0.7` | 生成温度 |
| `RAG_TOP_K` | `8` | 要检索的上下文块数量 |
| `RAG_MAX_DISTANCE` | `0.8` | 上下文过滤的最大 cosine distance |
| `USER_COOLDOWN_SECONDS` | `30` | 每用户回复冷却时间（秒） |
| `GLOBAL_MAX_PER_MINUTE` | `10` | 全局每分钟最大回复数 |
| `CHUNK_MAX_TOKENS` | `500` | 导入时每个 chunk 的最大 token 数 |
| `CHUNK_OVERLAP_TOKENS` | `50` | chunk 之间的 token 重叠 |
| `EMBED_BATCH_SIZE` | `100` | 嵌入 API 调用的批量大小 |

[↑ 返回目录](#目录)

---

## 决策与范围

### 包含
- 完整数据流水线：导出 → 预处理 → 嵌入 → 存储
- RAG 检索与 LLM 生成
- 带置信度路由的自动回复
- 通过 DM 完成的 Owner 审核（approve / edit / reject）
- 基础日志与监控
- Docker 部署选项
- 核心模块的单元测试

以上范围足以支撑「先上线、再迭代」：你可以从单频道自动回复起步，再按真实流量决定是否加强审核、调阈值或补更多知识来源。

### 排除（未来增强）
- 用于分析的 Web 仪表盘
- 用于 Bot 管理的 Slash Commands
- 多服务器支持
- 自动定期重新导入
- 在你的数据上微调模型（起步阶段 RAG 已经足够）
- 情感分析或主题分类

这些能力被刻意放到后续，是为了先把正确性、成本与人工闸门做稳；等核心体验稳定后，再按运营需要逐项引入会更划算。

如果你现在只想尽快上线，请优先完成：导出历史 → 导入 ChromaDB → 启动 Bot → 在私密频道完成自动回复与审核按钮验证。等这些稳定后，再回头看部署、阈值调优与未来增强项。

本归档文档描述的是早期完整实现计划，现行运维与功能说明请以上级目录的 PROJECT_GUIDE / FEATURE_LIST / SETUP_AND_TEST 为准。若中英文归档并存，请以同目录配对文件交叉核对术语与命令；命令、路径与环境变量名保持英文原样，不要翻译。表格与代码块结构也应与英文源文档保持一致，便于对照维护。更新归档时请同步两边目录锚点，这样中英文跳转都能继续可用。完成对照后即可归档冻结：后续只改现行文档，勿回写归档正文，请务必保持此份历史快照原文内容不变。

[↑ 返回目录](#目录)
