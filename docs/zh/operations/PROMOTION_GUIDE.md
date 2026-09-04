# BigTreeSignal 推广功能 — 使用说明

---

## 目录

- [一、快速开始](#一快速开始)
- [二、环境变量配置详解](#二环境变量配置详解)
- [三、功能使用说明](#三功能使用说明)
  - [3.1 信号查询自动引导](#31-信号查询自动引导)
  - [3.2 自动回复尾部 CTA](#32-自动回复尾部-cta)
  - [3.3 /signal 命令](#33-signal-命令)
  - [3.4 新用户欢迎 DM](#34-新用户欢迎-dm)
  - [3.5 立即发送促销 /post_promo](#35-立即发送促销-post_promo)
  - [3.6 排程促销 /schedule_promo](#36-排程促销-schedule_promo)
  - [3.7 排程信号回顾 /schedule_trial](#37-排程信号回顾-schedule_trial)
  - [3.8 排程教学推送 /schedule_lesson](#38-排程教学推送-schedule_lesson)
  - [3.9 管理排程](#39-管理排程)
  - [3.10 用户见证收集](#310-用户见证收集)
  - [3.11 展示用户好评 /testimonials](#311-展示用户好评-testimonials)
  - [3.12 自愿通知身份组促销私信](#312-自愿通知身份组促销私信)
- [四、Slash Command 速查表](#四slash-command-速查表)
- [五、常见场景示例](#五常见场景示例)
- [六、数据文件位置](#六数据文件位置)
- [七、故障排查](#七故障排查)

---

## 一、快速开始

### 前置条件

在使用推广功能之前，请确认以下环境已就绪：

| 组件 | 要求 | 说明 |
|------|------|------|
| Python | 3.11+ | `python --version` 验证 |
| 虚拟环境 | 已创建并激活 | `.venv\Scripts\Activate.ps1` (PowerShell) |
| Python 依赖 | 已安装 | `pip install -r requirements.txt` |
| `.env` 文件 | 核心配置已完成 | 必须包含 `DISCORD_BOT_TOKEN`、`OPENAI_API_KEY`、`OWNER_USER_ID`、`TARGET_CHANNEL_IDS` |
| Discord Bot | 已邀请到服务器 | 需要 `bot` + `applications.commands` scope |
| 知识库数据 | 已导入 ChromaDB | `python -m ingestion.ingest` 已运行 |

> **注意：** 如果 Bot 尚未部署，请先完成 [`SETUP_AND_TEST.md`](../getting-started/SETUP_AND_TEST.md)（或归档文档 [`PHASE1_2_GUIDE.md`](../archive/PHASE1_2_GUIDE.md)）中的完整安装流程，再回来开启推广功能。

### 环境安装（如果尚未完成）

```powershell
# 1. 安装 Python 3.11+
winget install --id Python.Python.3.11 -e

# 2. 创建虚拟环境
cd C:\treeProjectDiscordBot
python -m venv .venv

# 3. 激活虚拟环境
.venv\Scripts\Activate.ps1

# 4. 安装依赖
pip install -r requirements.txt

# 5. 创建 .env（如果不存在）
Copy-Item .env.example .env
# 编辑 .env 填入核心配置
```

### 1. 配置 `.env`

在已有的 `.env` 文件末尾添加推广配置：

```env
# ── BigTreeSignal 推广 ──
PROMO_ENABLED=true
PROMO_CHANNEL_IDS=你的推广频道ID1,推广频道ID2
SIGNAL_PRODUCT_NAME=BigTreeSignal
SIGNAL_PRODUCT_URL=https://你的产品链接.com
TESTIMONIAL_CHANNEL_ID=你的user-wins频道ID
```

### 2. 获取频道 ID

在 Discord 中：
1. 打开 **用户设置 → 高级 → 开发者模式**（开启）
2. 右键点击目标频道 → **复制频道 ID**

### 3. 启动 Bot

```powershell
# 激活虚拟环境
.venv\Scripts\Activate.ps1

# 启动 Bot
python -m bot.main

# 如果使用 Docker
docker-compose restart
```

### 4. 验证启动

Bot 正常启动后你会看到以下日志：

```
[INFO] bot.main: OpenAI client initialized
[INFO] bot.main: ChromaDB collection loaded — XXXXX documents
[INFO] bot.main: Starting Discord bot...
[INFO] bot.listener: Bot is ready — starting message queue worker
```

Bot 启动后会自动同步 Slash Commands（首次同步可能需要等待几分钟才能在 Discord 中显示）。

确认推广功能就绪：在 Discord 推广频道输入 `/signal`，如果 Bot 回复了产品 Embed，说明推广功能已正常工作。

---

## 二、环境变量配置详解

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `PROMO_ENABLED` | 否 | `true` | 推广总开关。设为 `false` 关闭所有推广功能 |
| `PROMO_CHANNEL_IDS` | **是** | `""` | 推广频道 ID，逗号分隔。**未设置则推广功能不生效** |
| `SIGNAL_PRODUCT_NAME` | 否 | `BigTreeSignal` | 产品名称，显示在 Embed 标题中 |
| `SIGNAL_PRODUCT_URL` | 推荐 | `""` | 产品链接。未设置则 CTA 不含链接 |
| `SIGNAL_CTA_TEXT` | 否 | `想获取实时交易信号？了解 BigTreeSignal` | 信号查询时的引导文案 |
| `AUTO_REPLY_CTA_TEXT` | 否 | `想获取实时交易信号？了解 BigTreeSignal →` | 自动回复尾部 CTA 文案 |
| `CTA_FREQUENCY` | 否 | `5` | 每 N 次自动回复附带 1 次 CTA。设为 `0` 禁用 |
| `FREE_TRIAL_ENABLED` | 否 | `false` | 是否在产品展示中显示免费试用入口 |
| `FREE_TRIAL_URL` | 否 | `""` | 免费试用链接 |
| `WELCOME_MESSAGE` | 否 | `欢迎加入！...` | 新用户欢迎 DM 的正文 |
| `TESTIMONIAL_CHANNEL_ID` | 推荐 | `0` | #user-wins 频道 ID。未设置则见证审核通过后不转发 |
| `TESTIMONIAL_DETECTION_ENABLED` | 否 | `true` | 是否自动检测用户见证消息 |
| `PROMO_NOTIFY_ROLE_IDS` | 私信功能必填 | `""` | 自愿领取的「活动通知」身份组 ID，逗号分隔。**不是**运营/兴趣标签。未设置则不能发促销私信 |
| `PROMO_DM_DELAY_SECONDS` | 否 | `1.2` | 两条促销私信之间的间隔（秒） |
| `PROMO_DM_MAX_RECIPIENTS` | 否 | `200` | 单次私信人数上限，超限会拒绝发送 |

### 配置示例

**最小配置**（只开启基础 CTA）：

```env
PROMO_CHANNEL_IDS=123456789012345678
SIGNAL_PRODUCT_URL=https://bigtreesignal.com
```

**完整配置**：

```env
PROMO_ENABLED=true
PROMO_CHANNEL_IDS=123456789012345678,987654321098765432
SIGNAL_PRODUCT_NAME=BigTreeSignal
SIGNAL_PRODUCT_URL=https://bigtreesignal.com
SIGNAL_CTA_TEXT=想获取实时交易信号？了解 BigTreeSignal
AUTO_REPLY_CTA_TEXT=想获取实时交易信号？了解 BigTreeSignal →
CTA_FREQUENCY=5
FREE_TRIAL_ENABLED=true
FREE_TRIAL_URL=https://bigtreesignal.com/trial
WELCOME_MESSAGE=欢迎加入大树社群！这里有专业的股票分析和交易信号服务。
TESTIMONIAL_CHANNEL_ID=111222333444555666
TESTIMONIAL_DETECTION_ENABLED=true
PROMO_NOTIFY_ROLE_IDS=777888999000111222
PROMO_DM_DELAY_SECONDS=1.2
PROMO_DM_MAX_RECIPIENTS=200
```

---

## 三、功能使用说明

### 3.1 信号查询自动引导

**无需操作，自动触发。**

当用户在推广频道中问信号相关问题（如"有信号吗？"、"可以买吗？"、"买点在哪？"），Bot 会：
1. 按照正常流程将问题转发给 Owner 审核
2. **同时**在频道发送一条产品引导 Embed

Embed 示例：
```
🌳 BigTreeSignal
想获取实时交易信号？了解 BigTreeSignal

📊 覆盖市场: 美股 · ETF · 加密货币
🔗 了解更多: 点击查看
```

### 3.2 自动回复尾部 CTA

**无需操作，自动触发。**

在推广频道中，Bot 每自动回复 N 次（由 `CTA_FREQUENCY` 控制），会在回复末尾追加一行 CTA：

```
（Bot 的正常回答内容）

💡 想获取实时交易信号？了解 BigTreeSignal →
```

- 默认每 5 次附带 1 次
- 设置 `CTA_FREQUENCY=0` 可完全禁用
- 只在推广频道生效

### 3.3 /signal 命令

**任何用户**可以在推广频道中输入 `/signal` 查看产品信息。

```
/signal
```

Bot 会回复一个精美 Embed，展示：
- 产品名称和简介
- 覆盖市场
- 推送方式
- 订阅链接
- 免费试用（如果启用）

在非推广频道使用会收到提示："此频道未开启推广功能。"

### 3.4 新用户欢迎 DM

**无需操作，自动触发。**

当新用户加入到包含推广频道的 Server 时，Bot 自动发送欢迎私信 Embed，包含：
- 欢迎语（`WELCOME_MESSAGE`）
- `/faq` `/ask` `/signal` 提示
- 产品链接 + 免费试用按钮（如果已配置真实 URL）
- 若已配置 `PROMO_NOTIFY_ROLE_IDS`：文案邀请领取活动私信，并带「领取通知」「取消订阅」按钮

> 注意：如果用户关闭了 DM，Bot 会静默跳过，不会报错。点「领取通知」才会进入促销私信名单，不会自动加入。

### 3.5 立即发送促销 /post_promo

**仅 Owner 可用。** 立即向推广频道发送促销帖。

```
/post_promo title:"新年限时7折" description:"BigTreeSignal 新年特惠，即日起至1月31日订阅立减30%"
```

可选参数：
- `url` — 促销链接（不填则使用 `SIGNAL_PRODUCT_URL`）
- `channel` — 指定某个频道（不填则发送到所有推广频道）
- `dm_role` — 同步私信给**白名单通知身份组**（运营标签会被拒绝）。频道帖先发出，再确认人数后发私信

### 3.6 排程促销 /schedule_promo

**仅 Owner 可用。** 排程一条促销帖，到时间自动发送。

```
/schedule_promo title:"周末特惠" description:"限时3天，订阅8折优惠" time:"2024-01-20 10:00"
```

可选参数：
- `url` — 促销链接
- `channel` — 指定频道
- `dm_role` — 到期发频道帖时，同步私信给白名单通知身份组

**时间格式：** `YYYY-MM-DD HH:MM`（按 UTC-4 / ET 时区解析）

Bot 回复确认：
```
✅ 促销已排程！
ID: promo_a1b2c3d4
标题: 周末特惠
发送时间: 2024-01-20 10:00 (ET)
频道: 2 个
```

### 3.7 排程信号回顾 /schedule_trial

**仅 Owner 可用。** 排程一条免费信号回顾帖（展示历史信号的延迟结果）。

```
/schedule_trial title:"今日免费信号回顾" content:"昨日 AAPL 看多信号，开盘价 xxx → 收盘 xxx，盈利 +2.3%" time:"2024-01-16 20:00"
```

信号回顾帖使用绿色 Embed，带 "免费信号回顾" 标签，与普通促销区分。

### 3.8 排程教学推送 /schedule_lesson

**仅 Owner 可用。** 排程教学内容，支持重复推送。

```
/schedule_lesson title:"三个买点入门" content:"今天分享缠论三个买点..." time:"2024-01-16 09:00" repeat:每周
```

重复模式：
- **不重复**（默认）— 只发送一次
- **每天** — 每天同一时间发送
- **每周** — 每周同一天同一时间发送

教学帖使用蓝色 Embed，带 "📚 教学" 标签。

### 3.9 管理排程

```
/list_promos         — 查看所有排程促销（最近10条）
/cancel_promo id     — 取消排程（输入促销 ID）
/list_lessons        — 查看所有排程教学（最近10条）
/cancel_lesson id    — 取消排程（输入教学 ID）
```

示例：
```
/list_promos
```
Bot 回复：
```
排程促销列表：
⏳ 待发送 promo_a1b2c3d4 — 周末特惠 — 2024-01-20 10:00
✅ 已发送 promo_e5f6g7h8 — 新年优惠 — 2024-01-15 10:00
```

```
/cancel_promo promo_id:promo_a1b2c3d4
```
Bot 回复：
```
✅ 促销 promo_a1b2c3d4 已取消。
```

### 3.10 用户见证收集

**无需操作，自动触发。**

当推广频道中有用户发送包含盈利/好评关键词的消息时（如"跟信号赚了不少"、"信号准"、"翻倍了"），Bot 会：

1. 自动收集消息并存入 `data/testimonials.json`
2. DM Owner 发送审核请求，包含：
   - 用户信息
   - 消息内容
   - 原始消息链接
   - **✅ 通过** / **❌ 拒绝** 按钮

3. Owner 点击 **✅ 通过**：
   - 消息被格式化为 Embed 转发到 `TESTIMONIAL_CHANNEL_ID` 频道
   - Embed 包含用户名、头像、原始内容、时间戳

4. Owner 点击 **❌ 拒绝**：
   - 消息标记为 rejected，不转发

**检测关键词（中/英文）：**
赚了、盈利、翻倍、大赚、跟单、跟信号、信号准、赚到、出金、回本、赚钱、收益不错、profit、gains、made money、signal works、great signal、good signal

### 3.11 展示用户好评 /testimonials

**任何用户**可以在推广频道中使用：

```
/testimonials
```

Bot 展示最近 5 条已审核通过的用户好评 Embed：
```
🌟 用户好评
来自社群成员的真实反馈

💬 TraderWang — 2024-01-15
跟信号赚了不少，感谢大树！

💬 StockFan — 2024-01-14
信号真的准，上周收益 +5%
```

### 3.12 自愿通知身份组促销私信

**不能**用你手动打的运营/兴趣标签给全员或某分组群发私信。Discord 会把未征得同意的群发当垃圾。私信只发给成员自己领取的通知身份组。

**一次性准备**

1. 在服务器新建身份组「活动通知」（不要给管理权限）。
2. 复制身份组 ID，写入 `.env` 的 `PROMO_NOTIFY_ROLE_IDS`。
3. 把 Bot 身份组排在「活动通知」上面，并给 Bot「管理身份组」权限。
4. 重启 Bot。

**发订阅面板（Owner，在公告频道做一次）**

```
/promo_notify_panel
```

建议置顶该消息，并可在频道里 `@everyone` 提醒一次（这是频道公告，不是私信群发）。成员点「领取通知」才进入私信名单；点「取消订阅」只去掉通知身份组，现有运营标签不动。成员也可以用 `/promo_notify`。新成员加入时，欢迎私信里也会出现同一对按钮（需已配置 `PROMO_NOTIFY_ROLE_IDS` 并开启欢迎流程）。

**发送活动私信（Owner）**

```
/dm_role role:@活动通知 title:"周末特惠" description:"限时 8 折"
```

Bot 先显示将发给多少人，确认后才限速发送。也可在 `/post_promo` / `/schedule_promo` 里加可选参数 `dm_role`（必须是白名单身份组，否则命令拒绝）。

单次超过 `PROMO_DM_MAX_RECIPIENTS`（默认 200）会拒绝发送，请拆批或提高上限。

---

## 四、Slash Command 速查表

| 命令 | 权限 | 说明 |
|------|------|------|
| `/signal` | 所有人 | 查看 BigTreeSignal 产品信息 |
| `/testimonials` | 所有人 | 查看最近用户好评 |
| `/promo_notify` | 所有人 | 领取或取消活动私信通知 |
| `/post_promo` | Owner | 立即发送促销帖（可选同步私信） |
| `/schedule_promo` | Owner | 排程促销帖（可选同步私信） |
| `/dm_role` | Owner | 向自愿通知身份组发送促销私信 |
| `/promo_notify_panel` | Owner | 在频道发布活动私信订阅面板 |
| `/schedule_trial` | Owner | 排程信号回顾帖 |
| `/schedule_lesson` | Owner | 排程教学推送 |
| `/list_promos` | Owner | 列出排程促销 |
| `/cancel_promo` | Owner | 取消排程促销 |
| `/list_lessons` | Owner | 列出排程教学 |
| `/cancel_lesson` | Owner | 取消排程教学 |

---

## 五、常见场景示例

### 场景 1：用户问买卖信号

```
用户：AAPL 现在可以买吗？有信号吗？

Bot：（转发给 Owner 审核）
Bot：🌳 BigTreeSignal
     想获取实时交易信号？了解 BigTreeSignal
     📊 覆盖市场: 美股 · ETF · 加密货币
     🔗 了解更多: 点击查看
```

### 场景 2：Bot 自动回复普通问题（第 5 次）

```
用户：MACD 背驰怎么看？

Bot：MACD 背驰主要看价格和 MACD 柱子的方向不一致...
     （正常分析内容）

     💡 想获取实时交易信号？了解 BigTreeSignal →
```

### 场景 3：Owner 排程周末促销

```
Owner 输入：/schedule_promo title:"周末限时8折" description:"BigTreeSignal 周末特惠" time:"2024-01-20 10:00"

Bot 回复（仅 Owner 可见）：
✅ 促销已排程！
ID: promo_a1b2c3d4
发送时间: 2024-01-20 10:00 (ET)

→ 到了周六上午 10 点，Bot 自动在推广频道发送促销 Embed
```

### 场景 4：用户分享盈利

```
用户：跟信号赚了不少，感谢大树！🔥

→ Bot 不回复（这是 courtesy 消息，会被跳过）
→ 但 Bot 自动收集为见证，DM Owner 审核
→ Owner 点 ✅ 通过
→ Bot 在 #user-wins 频道发送 Embed：

🌟 用户好评
TraderWang: 跟信号赚了不少，感谢大树！🔥
时间: 2024-01-15
🌳 BigTreeSignal
```

---

## 六、数据文件位置

| 文件 | 路径 | 说明 |
|------|------|------|
| 促销排程 | `data/promos.json` | 所有排程/已发送的促销 |
| 教学排程 | `data/lessons.json` | 所有排程/已发送的教学 |
| 用户见证 | `data/testimonials.json` | 所有收集到的见证 |

这些文件会自动创建，无需手动管理。如需清理，可以删除文件或编辑 JSON。

---

## 七、故障排查

### Slash Commands 没出现

- 首次添加 Slash Commands 需要 Discord 同步，**最多等 1 小时**
- 检查日志 `logs/bot.log` 是否有 "Synced X slash command(s)"
- 确保 Bot 有 `applications.commands` scope（在 Discord Developer Portal 设置）

### CTA 没有显示

- 确认频道 ID 在 `PROMO_CHANNEL_IDS` 中
- 确认 `PROMO_ENABLED=true`
- 自动回复 CTA 需要计数器命中（默认每 5 次一次）

### 见证没有被检测到

- 确认 `TESTIMONIAL_DETECTION_ENABLED=true`
- 确认消息在推广频道中
- 确认消息包含检测关键词
- Owner 本人的消息不会被检测

### 排程促销没有发送

- 检查时间是否已过（按 UTC-4 解析）
- 检查 `data/promos.json` 中是否标记为 `cancelled`
- 检查日志是否有 "Failed to post promo" 错误
- 确认 Bot 有目标频道的发送权限

### 新用户欢迎 DM 没有发送

- 确认 Bot 有 `members` Intent（已在代码中启用）
- 确认 Server 中至少有一个频道在 `PROMO_CHANNEL_IDS` 中
- 用户可能关闭了 DM（Bot 会静默跳过）
