# 本机测试运行指南

---

## 当前环境状态

| 组件 | 状态 |
|---|---|
| Python 3.11 + 虚拟环境 + 依赖包 | ✅ 已就绪 |
| `.env` 配置文件 | ❌ 需要创建 |
| Discord 导出数据 | ❌ `data/exports/` 为空 |
| ChromaDB 向量数据库 | ❌ 0条文档 |
| 风格分析文件 | ❌ 未生成 |

---

## 前置条件：安装系统工具

以下工具是**系统级**的，不包含在 Python 依赖中，需要单独安装。

### Python 3.11+

```powershell
winget install --id Python.Python.3.11 -e
```

### FFmpeg（YouTube 音频转录需要）

```powershell
winget install --id Gyan.FFmpeg -e
```

### Deno（yt-dlp 解析 YouTube 页面需要）

```powershell
winget install --id DenoLand.Deno -e
```

> **重要：** 安装完以上工具后需要**重新打开 PowerShell** 让 PATH 生效。

### 验证安装

```powershell
python --version    # 应显示 3.11.x 或更高
ffmpeg -version     # 应显示版本号
deno --version      # 应显示版本号
```

### 创建虚拟环境并安装 Python 依赖

```powershell
cd C:\treeProjectDiscordBot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

---

## 第一步：创建 `.env` 配置文件

```powershell
Copy-Item .env.example .env
notepad .env
```

在 Notepad 中修改以下 **4个必填项**，其他保持默认即可：

```
DISCORD_BOT_TOKEN=你的Bot Token
OPENAI_API_KEY=你的OpenAI API Key
OWNER_USER_ID=你的Discord用户ID
TARGET_CHANNEL_IDS=要监听的频道ID
```

**如何获取这些值：**

| 值 | 获取方式 |
|---|---|
| `DISCORD_BOT_TOKEN` | https://discord.com/developers/applications → 你的应用 → 左侧 Bot → 点 "Reset Token" → 复制 |
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys → 创建新key → 复制 |
| `OWNER_USER_ID` | Discord设置 → 高级 → 打开"开发者模式" → 右键点自己的头像 → "复制用户ID" |
| `TARGET_CHANNEL_IDS` | 右键点频道名 → "复制频道ID"（多个频道用逗号分隔） |

填好后保存关闭 Notepad。

---

## 第二步：确保 Bot 已被邀请到你的 Discord 服务器

Bot 邀请链接格式（替换 `YOUR_CLIENT_ID`）：

```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=274877975552&scope=bot
```

`YOUR_CLIENT_ID` 在 Discord Developer Portal → 你的应用 → OAuth2 → 页面顶部的 "CLIENT ID"。

**必须勾选的权限（已包含在上面的链接中）：**
- Send Messages
- Read Message History
- Read Messages / View Channels

---

## 第三步：准备 Discord 历史消息数据

### 方案 A — 导出真实数据（正式使用）

使用 [DiscordChatExporter](https://github.com/Tyrrrz/DiscordChatExporter/releases) 工具：

1. 下载解压 DiscordChatExporter（选 `.zip` 版本）
2. 运行导出命令（替换用户 Token 和频道 ID）：

```powershell
DiscordChatExporter.Cli.exe export -t "你的Discord用户Token" -c 频道ID -f Json -o data\exports\channel_export.json
```

> **注意**：这里用的是你的**用户 Token**（不是 Bot Token）。可在浏览器开发者工具 Network 标签中获取。

3. 导出完成后确认 JSON 文件已在 `data\exports\` 目录下

---

### 方案 B — 用模拟数据快速测试（推荐先用这个）

激活虚拟环境后运行以下命令（**将 `你的用户ID` 替换为 `.env` 中的 `OWNER_USER_ID`**）：

```powershell
.venv\Scripts\activate
```

```powershell
python -c "
import json
owner_id = '你的用户ID'
data = {
    'channel': {'id': '123456'},
    'messages': [
        {'id': '1', 'content': '请问AAPL怎么看？', 'timestamp': '2024-01-01T00:00:00+00:00', 'author': {'id': '999', 'name': 'Member', 'nickname': 'Member'}},
        {'id': '2', 'content': 'AAPL目前在关键支撑位180附近，我觉得可以关注一下', 'timestamp': '2024-01-01T00:01:00+00:00', 'author': {'id': owner_id, 'name': 'Owner', 'nickname': 'Owner'}, 'reference': {'messageId': '1'}},
        {'id': '3', 'content': '从技术面来看，均线多头排列，MACD金叉，短期看涨', 'timestamp': '2024-01-01T00:01:30+00:00', 'author': {'id': owner_id, 'name': 'Owner', 'nickname': 'Owner'}},
        {'id': '4', 'content': 'TSLA能买吗？', 'timestamp': '2024-01-02T00:00:00+00:00', 'author': {'id': '888', 'name': 'User2', 'nickname': 'User2'}},
        {'id': '5', 'content': 'TSLA波动太大了，除非你能承受20%的回撤，不然别碰', 'timestamp': '2024-01-02T00:01:00+00:00', 'author': {'id': owner_id, 'name': 'Owner', 'nickname': 'Owner'}, 'reference': {'messageId': '4'}},
        {'id': '6', 'content': '今天大盘走势很弱，建议观望为主，不要追高', 'timestamp': '2024-01-03T00:00:00+00:00', 'author': {'id': owner_id, 'name': 'Owner', 'nickname': 'Owner'}},
        {'id': '7', 'content': 'SPY跌破了5日均线，注意风险控制', 'timestamp': '2024-01-03T00:05:00+00:00', 'author': {'id': owner_id, 'name': 'Owner', 'nickname': 'Owner'}},
    ]
}
with open('data/exports/test_export.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print('测试数据已创建: data/exports/test_export.json')
"
```

---

## 第四步：运行数据导入

```powershell
.venv\Scripts\activate
python -m ingestion.ingest
```

正常输出如下：
```
Starting ingestion pipeline
  Export dir : ./data/exports
  Owner ID  : 你的用户ID
Embedding & storing: 100%|████████| 1/1
Ingestion complete: X documents stored in ChromaDB
Done — total documents in collection: X
```

---

## 第五步（可选）：生成风格分析

分析你的写作风格，让模型回复更像你本人：

```powershell
python -m ingestion.analyze_style
```

分析结果保存在 `data/style_profile.txt`，下次启动 Bot 时自动加载。

---

## 第六步：启动 Bot

```powershell
python -m bot.main
```

**正常启动**会看到：

```
INFO  OpenAI client initialized
INFO  ChromaDB collection 'discord_posts' loaded — X documents
INFO  Logged in as 你的Bot名字#1234
INFO  Serving 1 guild(s)
INFO  Bot is ready — starting message queue worker
```

按 `Ctrl+C` 停止 Bot。

---

## 第七步：测试 Bot 回复

1. 打开你在 `TARGET_CHANNEL_IDS` 中配置的 Discord 频道
2. **用另一个账号**（不是频道主账号）发消息提问，例如：
   - `AAPL现在能买吗？`
   - `大盘走势怎么看？`
3. 观察 Bot 行为：
   - **自信度 ≥ 7** → Bot 自动回复
   - **自信度 < 7** → Bot 通过 DM 发给你审核，有以下按钮：
     - ✅ **Approve** — 直接发送草稿回复
     - ✏️ **Edit** — 你在 DM 中输入修改后的内容再发送
     - ❌ **Reject** — 不回复，丢弃

4. 在运行 Bot 的终端窗口中可以看到实时日志，日志也写入 `logs/bot.log`

---

## 常见问题排查

| 问题 | 原因 | 解决方法 |
|---|---|---|
| `DISCORD_BOT_TOKEN is not set` | `.env` 未创建或 Token 未填写 | 重做第一步 |
| `ChromaDB collection not found` | 数据未导入 | 重做第四步 |
| Bot 上线但不回复消息 | 频道 ID 配置错误，或发消息的是频道主账号 | 确认 `TARGET_CHANNEL_IDS` 正确，用其他账号测试 |
| `Forbidden 403` | Bot 缺少频道权限 | 用第二步的邀请链接重新邀请 Bot |
| 回复内容不准确 | 测试数据太少 | 导入更多真实历史消息（方案 A） |
| DM 审核消息收不到 | `OWNER_USER_ID` 填错 | 确认是你自己的 Discord 用户 ID |
| `No JSON files found` | 导出文件没放对目录 | 确认 JSON 文件在 `data\exports\` 目录下 |

---

## 日常使用命令速查

```powershell
# 激活虚拟环境（每次打开终端后先运行这个）
.venv\Scripts\activate

# 启动 Bot
python -m bot.main

# 新增数据后重新导入（增量，不会重复）
python -m ingestion.ingest

# 重新生成风格分析
python -m ingestion.analyze_style

# 运行测试确认代码正常
python -m pytest tests/ -v
```
