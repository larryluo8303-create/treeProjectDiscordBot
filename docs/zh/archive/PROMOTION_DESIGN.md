> **归档文档**：历史设计/阶段指南，仅供参考。现行说明见上级目录的 PROJECT_GUIDE / FEATURE_LIST / SETUP_AND_TEST 等。

# BigTreeSignal 推广系统 — 设计文档

---

## 目录

- [一、背景与目标](#一背景与目标)
- [二、系统架构](#二系统架构)
- [三、模块设计](#三模块设计)
  - [3.1 配置层](#31-配置层)
  - [3.2 推广工具库 promo_config.py](#32-推广工具库-promo_configpy)
  - [3.3 Slash Commands commands.py](#33-slash-commands-commandspy)
  - [3.4 定时排程 scheduler.py](#34-定时排程-schedulerpy)
  - [3.5 用户见证 testimonials.py](#35-用户见证-testimonialspy)
  - [3.6 消息监听扩展 listener.py](#36-消息监听扩展-listenerpy)
- [四、数据模型](#四数据模型)
- [五、频道隔离设计](#五频道隔离设计)
- [六、功能清单](#六功能清单)
- [七、文件变更清单](#七文件变更清单)
- [八、安全与合规](#八安全与合规)

---

## 一、背景与目标

### 背景

现有 Discord Bot 已具备 RAG 自动回复、Owner 审核、信号问题路由等核心能力。频道主运营 **BigTreeSignal** 信号产品（覆盖美股、ETF、加密货币），需要利用 Bot 的高质量回答建立用户信任，并在合适时机自然引导用户了解付费信号产品。

### 目标

1. **自然引导**：在用户问信号相关问题时，自动展示产品信息
2. **定时推广**：支持促销排程、免费信号回顾、教学内容推送
3. **社群增长**：新用户欢迎 + 用户好评见证收集与展示
4. **频道隔离**：所有推广行为限定在 `PROMO_CHANNEL_IDS` 指定的频道，不影响其他频道
5. **灵活配置**：所有 URL、文案、频率均可通过 `.env` 配置，支持一键开关

---

## 二、系统架构

```
用户消息
    │
    ▼
┌──────────────────────────────────────────────┐
│  listener.py (MessageListener Cog)           │
│  ┌─────────────────────────────────────────┐ │
│  │ 信号查询检测 (is_signal_query)           │ │
│  │   → 推广频道? → 发送 CTA Embed          │ │
│  ├─────────────────────────────────────────┤ │
│  │ 自动回复 (auto_reply)                    │ │
│  │   → 推广频道? → 每 N 次附带 CTA         │ │
│  ├─────────────────────────────────────────┤ │
│  │ 见证检测 (_TESTIMONIAL_PATTERNS)         │ │
│  │   → 推广频道? → collect_testimonial()   │ │
│  ├─────────────────────────────────────────┤ │
│  │ on_member_join                           │ │
│  │   → Guild 有推广频道? → 欢迎 DM         │ │
│  └─────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│  commands.py (PromotionCommands Cog)         │
│  /signal        — 产品展示                    │
│  /post_promo    — 立即发促销                  │
│  /schedule_promo — 排程促销                   │
│  /schedule_trial — 排程信号回顾               │
│  /schedule_lesson — 排程教学                  │
│  /list_promos / /cancel_promo                │
│  /list_lessons / /cancel_lesson              │
│  /testimonials  — 展示用户好评                │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│  scheduler.py (SchedulerCog)                 │
│  每 60 秒检查:                                │
│  ├─ data/promos.json  → 到时间自动发送        │
│  └─ data/lessons.json → 到时间自动发送        │
│     └─ 支持 daily / weekly 重复               │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│  testimonials.py                             │
│  collect → DM Owner 审核 → 转发 #user-wins   │
│  data/testimonials.json                      │
└──────────────────────────────────────────────┘
```

---

## 三、模块设计

### 3.1 配置层

在 `bot/config.py` 中新增以下环境变量：

| 变量 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `PROMO_ENABLED` | bool | `true` | 总开关，关闭后所有推广功能停用 |
| `PROMO_CHANNEL_IDS` | list[int] | `[]` | 推广频道 ID 列表（逗号分隔） |
| `SIGNAL_PRODUCT_NAME` | str | `BigTreeSignal` | 产品名称 |
| `SIGNAL_PRODUCT_URL` | str | `""` | 产品链接 |
| `SIGNAL_CTA_TEXT` | str | `想获取实时交易信号？了解 BigTreeSignal` | 信号查询 CTA 文案 |
| `AUTO_REPLY_CTA_TEXT` | str | `想获取实时交易信号？了解 BigTreeSignal →` | 自动回复 CTA 文案 |
| `CTA_FREQUENCY` | int | `5` | 每 N 次自动回复附带 1 次 CTA |
| `FREE_TRIAL_ENABLED` | bool | `false` | 是否显示免费试用入口 |
| `FREE_TRIAL_URL` | str | `""` | 免费试用链接 |
| `WELCOME_MESSAGE` | str | `欢迎加入！...` | 新用户欢迎文案 |
| `TESTIMONIAL_CHANNEL_ID` | int | `0` | #user-wins 频道 ID |
| `TESTIMONIAL_DETECTION_ENABLED` | bool | `true` | 是否自动检测用户见证 |

**设计原则：** `PROMO_CHANNEL_IDS` 独立于 `TARGET_CHANNEL_IDS`。Bot 可以在 A 频道回答问题但不做推广，在 B 频道既回答又推广，取决于两个列表的交集。

### 3.2 推广工具库 `promo_config.py`

纯函数模块，不持有状态，提供以下 helper：

| 函数 | 作用 |
|------|------|
| `is_promo_channel(channel_id)` | 判断频道是否在推广列表 |
| `get_signal_cta_embed()` | 生成信号查询时的 CTA Embed |
| `get_auto_reply_cta()` | 生成自动回复尾部 CTA 文本 |
| `should_append_cta(counter)` | 根据 CTA_FREQUENCY 判断是否附带 |
| `get_welcome_embed(member)` | 生成新用户欢迎 Embed |
| `get_signal_product_embed()` | 生成 /signal 命令的详细产品 Embed |

### 3.3 Slash Commands `commands.py`

注册为 `PromotionCommands` Cog，包含 10 个 Slash Command。

**权限控制：** 排程类命令（schedule/cancel/list/post）仅 Owner (`OWNER_USER_ID`) 可用，/signal 和 /testimonials 所有用户可用但限推广频道。

**时间输入：** 统一使用 `YYYY-MM-DD HH:MM` 格式，按 UTC-4 (ET) 解析。

### 3.4 定时排程 `scheduler.py`

- 使用 `discord.ext.tasks.loop(seconds=60)` 做后台轮询
- 数据持久化到 `data/promos.json` 和 `data/lessons.json`
- 写入使用 `.tmp` + `os.replace` 原子操作，防止写入中断导致数据损坏
- 促销支持 `promo` 和 `trial_signal` 两种类型，Embed 样式不同
- 教学支持 `none`（一次性）、`daily`、`weekly` 三种重复模式

### 3.5 用户见证 `testimonials.py`

**检测 → 审核 → 转发** 三步流程：

1. `listener.py` 中 `_TESTIMONIAL_PATTERNS` 正则匹配盈利/好评关键词
2. 匹配后调用 `collect_testimonial()`：存入 JSON + DM Owner
3. Owner 点 Approve → Embed 转发到 `TESTIMONIAL_CHANNEL_ID`
4. Owner 点 Reject → 标记为 rejected，不转发

**防重复：** 以 `message.id` 去重，同一消息只收集一次。

### 3.6 消息监听扩展 `listener.py`

在原有 `MessageListener` Cog 上新增：

| 功能 | 触发条件 | 行为 |
|------|----------|------|
| 信号 CTA | signal query + 推广频道 + forward_to_owner | 在频道发 CTA Embed |
| 自动回复 CTA | auto_reply + 推广频道 + 计数器命中 | 回复末尾追加 CTA 文本 |
| 见证检测 | 非 bot/owner + 推广频道 + 匹配见证正则 | 调用 collect_testimonial |
| 新用户欢迎 | on_member_join + Guild 有推广频道 + 非 bot | 发送欢迎 DM |

---

## 四、数据模型

### `data/promos.json`

```json
[
  {
    "id": "promo_a1b2c3d4",
    "type": "promo",
    "title": "新年限时7折",
    "description": "BigTreeSignal 新年特惠，订阅立减30%",
    "url": "https://...",
    "scheduled_at": "2024-01-15T10:00:00-04:00",
    "channel_ids": [123456789, 987654321],
    "posted": false,
    "cancelled": false,
    "created_by": 111222333,
    "posted_at": null
  }
]
```

### `data/lessons.json`

```json
[
  {
    "id": "lesson_e5f6g7h8",
    "title": "三个买点入门",
    "content": "今天分享缠论三个买点的基础概念...",
    "scheduled_at": "2024-01-16T09:00:00-04:00",
    "repeat": "weekly",
    "channel_ids": [123456789],
    "last_posted": null,
    "cancelled": false,
    "created_by": 111222333
  }
]
```

### `data/testimonials.json`

```json
[
  {
    "id": "test_i9j0k1l2",
    "message_id": "1234567890",
    "channel_id": "123456789",
    "author_id": "111222333",
    "author_name": "TraderWang",
    "content": "跟信号赚了不少，感谢大树！",
    "timestamp": "2024-01-15T14:30:00+00:00",
    "status": "approved",
    "jump_url": "https://discord.com/channels/...",
    "reviewed_at": "2024-01-15T15:00:00+00:00"
  }
]
```

---

## 五、频道隔离设计

```
                      TARGET_CHANNEL_IDS          PROMO_CHANNEL_IDS
                    (Bot 回答问题的频道)         (推广行为的频道)
                    ┌───────────────────┐      ┌──────────────────┐
#general-chat       │        ✅          │      │        ❌         │
#stock-analysis     │        ✅          │      │        ✅         │
#signal-promo       │        ❌          │      │        ✅         │
#random             │        ❌          │      │        ❌         │
                    └───────────────────┘      └──────────────────┘

#general-chat:    Bot 回答问题，不做推广
#stock-analysis:  Bot 回答问题 + 推广 CTA + 见证检测
#signal-promo:    不回答问题，只接受 /signal 等推广命令
#random:          Bot 完全不参与
```

---

## 六、功能清单

| # | 功能 | 阶段 | 触发方式 | 限推广频道 |
|---|------|------|----------|-----------|
| 1 | 信号查询 CTA | Phase 1 | 自动（检测到 signal query） | ✅ |
| 2 | 自动回复尾部 CTA | Phase 1 | 自动（每 N 次回复） | ✅ |
| 3 | `/signal` 产品展示 | Phase 2 | 用户执行命令 | ✅ |
| 4 | 新用户欢迎 DM | Phase 2 | 自动（on_member_join） | ✅ (Guild级) |
| 5 | `/post_promo` 立即发促销 | Phase 3 | Owner 执行命令 | ✅ |
| 6 | `/schedule_promo` 排程促销 | Phase 3 | Owner 执行命令 | ✅ |
| 7 | `/schedule_trial` 信号回顾 | Phase 3 | Owner 执行命令 | ✅ |
| 8 | `/schedule_lesson` 教学推送 | Phase 3 | Owner 执行命令 | ✅ |
| 9 | 用户见证收集与审核 | Phase 3 | 自动检测 + Owner 审核 | ✅ |
| 10 | `/testimonials` 展示好评 | Phase 3 | 用户执行命令 | ✅ |

---

## 七、文件变更清单

### 新增文件

| 文件 | 行数 | 说明 |
|------|------|------|
| `bot/promo_config.py` | ~150 | 推广 helper 函数 |
| `bot/commands.py` | ~340 | 10 个 Slash Command |
| `bot/scheduler.py` | ~260 | 定时任务 Cog + CRUD |
| `bot/testimonials.py` | ~240 | 见证收集 + 审核 UI |

### 修改文件

| 文件 | 改动 |
|------|------|
| `bot/config.py` | +13 个 env vars |
| `bot/listener.py` | +CTA 逻辑 / 见证检测 / on_member_join (~60 行) |
| `bot/main.py` | +注册 2 个 Cog / sync slash commands |
| `.env.example` | +14 行推广配置示例 |

---

## 八、安全与合规

| 机制 | 说明 |
|------|------|
| 频道隔离 | 所有推广行为严格限定在 PROMO_CHANNEL_IDS |
| Owner 权限 | 排程/发送/取消命令仅 Owner 可用 |
| 总开关 | PROMO_ENABLED=false 一键关闭所有推广 |
| 见证审核 | 用户见证必须 Owner Approve 才转发 |
| 防重复 | 见证以 message_id 去重，排程以 posted 标记防重发 |
| 原子写入 | JSON 文件使用 .tmp + os.replace 防止数据损坏 |
| CTA 频率控制 | 自动回复 CTA 按 CTA_FREQUENCY 控制，避免过度推广 |
