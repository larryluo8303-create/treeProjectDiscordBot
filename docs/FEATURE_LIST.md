# BigTreeASignalAiBot — 全部功能清单

## 🔴 核心功能（必需）

### 1. RAG 智能问答

- **文件：** `bot/rag.py`, `bot/listener.py`, `bot/confidence.py`
- **说明：** 用户在 Discord 频道提问，Bot 从 ChromaDB 知识库检索相关内容，用 GPT 生成模仿频道主风格的回答
- **配置：** `OPENAI_API_KEY`, `LLM_MODEL`, `RAG_TOP_K`, `RAG_MAX_DISTANCE`, `CONFIDENCE_THRESHOLD`
- **使用：** 自动触发，用户在目标频道发消息即可

### 2. 置信度路由

- **文件：** `bot/confidence.py`
- **说明：** 根据置信度分数决定自动回复（≥阈值）还是转发给 Owner 审核（<阈值）
- **配置：** `CONFIDENCE_THRESHOLD=7`（默认），`RESPOND_MODE=auto|review|questions|mention_only`

### 3. Owner 审核系统

- **文件：** `bot/review.py`, `bot/review_queue.py`
- **说明：** 低置信度回答通过 DM 发送给 Owner，附带 Approve / Edit / Reject 按钮
- **使用：** Owner 在 DM 中点击按钮操作，Approve 的内容自动学习到知识库

### 4. 知识库导入

- **文件：** `ingestion/ingest.py`, `ingestion/preprocess.py`
- **说明：** 将 Discord 导出的 JSON 数据预处理、分块、向量化，存入 ChromaDB
- **使用：** `python -m ingestion.ingest`

### 5. 频道监听 & 消息处理

- **文件：** `bot/listener.py`
- **说明：** 监听目标频道消息，过滤垃圾/礼貌用语，检测是否为问题，维护对话记忆
- **配置：** `TARGET_CHANNEL_IDS`, `EXCLUDED_CHANNEL_IDS`, `CONVERSATION_MEMORY_SIZE`, `CONVERSATION_MEMORY_TTL`

---

## 🟡 重要功能（强烈建议启用）

### 6. 速率限制

- **文件：** `bot/listener.py`
- **说明：** 用户冷却 + 全局每分钟上限，防止滥用
- **配置：** `USER_COOLDOWN_SECONDS=30`, `GLOBAL_MAX_PER_MINUTE=10`

### 7. 离线回填

- **文件：** `bot/listener.py`
- **说明：** Bot 重启后自动扫描离线期间未回答的问题
- **配置：** `OFFLINE_BACKFILL_ENABLED=true`, `OFFLINE_BACKFILL_LOOKBACK_HOURS=24`

### 8. 自动学习 Owner 消息

- **文件：** `bot/listener.py`
- **说明：** Owner 在频道发帖自动入库 ChromaDB，知识库持续增长
- **使用：** 自动触发，Owner 正常发帖即可

### 9. Thread 回复支持

- **文件：** `bot/listener.py`
- **说明：** 在 Thread 中也能回复，自动拉取 Thread 上下文
- **配置：** `THREAD_AUTO_REPLY=true`, `THREAD_CONTEXT_MESSAGES=15`

### 10. 图片/图表分析

- **文件：** `bot/rag.py`, `bot/listener.py`
- **说明：** 用户发送图片（如 K 线图），用 GPT-4o Vision 分析
- **配置：** `VISION_MODEL=gpt-4o`

### 11. 语音消息转录与回复

- **文件：** `bot/listener.py`
- **说明：**
  - **频道主语音：** Discord 语音条经 Whisper 转录后自动学习到知识库（不公开回复）
  - **群友语音：** 仅处理 Discord **语音条**（不是任意 mp3/歌曲）。Whisper 转写后走 RAG 回复；转写中频道显示「正在输入」
  - **限制：** 超过约 2MB 或 90 秒会提示改用文字；转写后像「谢谢/好的」或非提问的闲聊语音会静默跳过，不跑完整回复
- **使用：** 在目标频道直接发 Discord 语音消息；也可语音 + 文字说明一起发
- **注意：** 需 Bot 能读取附件；转写依赖 OpenAI Whisper

### 12. 统计追踪

- **文件：** `bot/stats.py`
- **说明：** 记录总查询数、自动回复数、转发数、置信度、延迟等，支持按时间段筛选
- **使用：** `/stats` 命令或 Admin 面板查看

### 13. 嵌入缓存

- **文件：** `bot/cache.py`
- **说明：** LRU + TTL 缓存 embedding 结果，减少重复 API 调用
- **使用：** 自动启用

---

## 🟢 可选功能（按需启用）

### 14. Admin Web 面板

- **文件：** `bot/admin.py`
- **说明：** 浏览器访问的管理面板，查看统计/配置/知识库/FAQ
- **配置：** `ADMIN_ENABLED=true`, `ADMIN_PORT=8082`, `ADMIN_SECRET`
- **使用：** 浏览器访问 `http://host:8082/admin/`

### 15. FastAPI 管理 API

- **文件：** `bot/api/` 目录
- **说明：** RESTful API + WebSocket，提供统计/配置/审核/知识库/FAQ/促销管理
- **配置：** `API_ENABLED=true`, `API_PORT=8090`, `API_USERNAME`, `API_PASSWORD`
- **使用：** Admin 移动端 App (`app/`) 通过此 API 管理 Bot

### 16. 公开 Client API

- **文件：** `bot/api/routes_public.py`
- **说明：** 面向终端用户的公开 API（聊天、图片分析、FAQ、搜索、摘要等）
- **配置：** `CLIENT_API_ENABLED=true`, `CLIENT_API_KEY`, `CLIENT_RATE_LIMIT_PER_MINUTE=20`
- **使用：** Web 客户端 (`web-client/`) 和移动客户端 (`app-client/`) 通过此 API 交互

### 17. Web 客户端

- **文件：** `web-client/` 目录
- **说明：** React Web App — 聊天、搜索、摘要、FAQ、书签、历史记录
- **使用：** `npm run dev`（开发）或 `npm run build`（生产）

### 18. 移动客户端

- **文件：** `app-client/` 目录
- **说明：** Expo React Native App — 功能同 Web 客户端
- **使用：** EAS Build 发布到 App Store / Google Play

### 19. Admin 移动 App

- **文件：** `app/` 目录
- **说明：** Expo App 用于 Owner 远程管理（审核、统计、配置、知识库）
- **使用：** 通过 FastAPI 管理 API 连接

### 20. 每日摘要

- **文件：** `bot/digest.py`
- **说明：** 每天定时生成 24 小时活动摘要，发到指定频道 + DM 给 Owner
- **配置：** `DIGEST_ENABLED=true`, `DIGEST_HOUR=22`（UTC），`DIGEST_CHANNEL_ID`

### 21. FAQ 自动生成

- **文件：** `bot/faq.py`
- **说明：** 根据高置信度查询自动用 GPT 聚类生成 FAQ
- **使用：** `/generate_faq` 命令或 Admin 面板的 Generate FAQ 按钮

### 22. 促销排程系统

- **文件：** `bot/scheduler.py`, `bot/commands.py`, `bot/promo_config.py`
- **说明：** 排程促销帖/信号回顾/教学内容，支持重复（每小时/每天/每周/每月）
- **配置：** `PROMO_ENABLED=true`, `PROMO_CHANNEL_IDS`, `SIGNAL_PRODUCT_NAME`, `SIGNAL_PRODUCT_URL`
- **使用：** `/schedule_promo`（可选 `dm_role` 同步私信给自愿通知身份组）、`/schedule_trial`、`/schedule_lesson`

### 23. 用户评价收集

- **文件：** `bot/testimonials.py`
- **说明：** 自动检测用户好评消息，转发给 Owner 审核（Approve/Reject），展示已批准的评价
- **配置：** `TESTIMONIAL_DETECTION_ENABLED=true`, `TESTIMONIAL_CHANNEL_ID`
- **使用：** `/testimonials` 查看

### 24. Webhook 导入

- **文件：** `bot/webhook.py`
- **说明：** 外部系统通过 HTTP POST 导入文本到知识库
- **配置：** `WEBHOOK_ENABLED=true`, `WEBHOOK_PORT=8081`, `WEBHOOK_SECRET`

### 25. YouTube 导入

- **文件：** `ingestion/ingest_youtube.py`
- **说明：** 导入 YouTube 视频字幕（字幕优先，Whisper 回退）
- **使用：** `python -m ingestion.ingest_youtube --urls "URL"`

### 26. PDF 导入

- **文件：** `ingestion/ingest_pdf.py`
- **说明：** 导入 PDF 文档到知识库
- **使用：** `python -m ingestion.ingest_pdf --files "file.pdf"`

### 27. 风格分析

- **文件：** `ingestion/analyze_style.py`
- **说明：** 分析 Owner 的写作风格，生成风格指南供 RAG 使用
- **使用：** `python -m ingestion.analyze_style`

### 28. 定时导入

- **文件：** `bot/ingestion_scheduler.py`
- **说明：** 后台定时运行导入和风格分析
- **配置：** `INGEST_INTERVAL_HOURS`, `STYLE_INTERVAL_HOURS`

### 29. 多语言支持

- **文件：** `bot/config.py`
- **说明：** 支持中文 (zh) 和英文 (en) 界面文字
- **配置：** `BOT_LANGUAGE=zh`

### 30. 负反馈学习

- **文件：** `bot/review.py`, `bot/rag.py`
- **说明：** Owner Reject 的回答保存为负面样本，注入后续 prompt 避免重复错误
- **使用：** 自动触发，存储在 `data/negative_samples.json`

---

## Slash Commands 汇总

### 公开命令（所有用户可用）

| 命令 | 说明 | 用法 |
| --- | --- | --- |
| `/ask` | 向 AI 助手提问（RAG 知识库） | `/ask question:你的问题` |
| `/signal` | 查看 BigTreeSignal 产品介绍（不限推广频道） | `/signal` |
| `/invite` | 生成专属邀请链接 | `/invite` |
| `/testimonials` | 展示最近用户好评 | `/testimonials` |
| `/faq` | 查看常见问题 | `/faq` |
| `/promo_notify` | 领取或取消活动私信通知 | `/promo_notify action:领取` |

### Owner 专用命令

**促销管理：**

| 命令 | 说明 | 用法 |
| --- | --- | --- |
| `/post_promo` | 立即发送促销帖（可选同步私信） | `/post_promo title:标题 description:内容 dm_role:@活动通知` |
| `/schedule_promo` | 排程促销帖（支持重复，可选同步私信） | `/schedule_promo title:标题 description:描述 time:时间 repeat:重复模式 dm_role:@活动通知` |
| `/dm_role` | 向自愿通知身份组发送促销私信 | `/dm_role role:@活动通知 title:标题 description:内容` |
| `/promo_notify_panel` | 在频道发布活动私信订阅面板 | `/promo_notify_panel` |
| `/list_promos` | 列出所有排程促销 | `/list_promos` |
| `/cancel_promo` | 取消排程促销 | `/cancel_promo promo_id:ID` |
| `/schedule_trial` | 排程免费信号回顾帖（支持重复） | `/schedule_trial title:标题 content:内容 time:时间 repeat:重复模式` |

**教学管理：**

| 命令 | 说明 | 用法 |
| --- | --- | --- |
| `/schedule_lesson` | 排程教学推送（支持重复） | `/schedule_lesson title:标题 content:内容 time:时间 repeat:重复模式` |
| `/list_lessons` | 列出所有排程教学 | `/list_lessons` |
| `/cancel_lesson` | 取消排程教学 | `/cancel_lesson lesson_id:ID` |

**开发/运维：**

| 命令 | 说明 | 用法 |
| --- | --- | --- |
| `/status` | 查看 Bot 状态（uptime、队列、知识库数量） | `/status` |
| `/stats` | 查看查询统计（总数、置信度、热门问题） | `/stats` |
| `/search_kb` | 搜索知识库文档 | `/search_kb query:关键词 top_k:数量` |
| `/generate_faq` | 根据高频问题自动生成 FAQ | `/generate_faq` |
| `/weekly_summary` | 立即生成并推送本周总结 | `/weekly_summary` |
| `/daily_summary` | 立即生成并推送今日总结 | `/daily_summary` |
| `/views` | [Owner] 扫描全服频道主发言，简短总结并发到本频道 | `/views hours:24` |
| `/funnel` | 查看获客转化漏斗 | `/funnel days:7` |

---

## 重复模式选项

排程命令（`/schedule_promo`, `/schedule_trial`, `/schedule_lesson`）均支持以下重复模式：

| 选项 | 说明 |
| --- | --- |
| 不重复 | 发送一次后结束（默认） |
| 每小时 | 每小时自动重发 |
| 每天 | 每天自动重发 |
| 每周 | 每周自动重发 |
| 每月 | 每 30 天自动重发 |

---

## 🆕 新增功能

### 31. 多语言自动检测 & 回复

- **文件：** `bot/lang_detect.py`, `bot/listener.py`
- **说明：** 自动检测用户消息语言（中/英/日/韩），并指示 LLM 使用对应语言回复
- **配置：** `AUTO_LANG_DETECT=true`（默认开启）
- **使用：** 用户用任意支持的语言提问，Bot 自动用同语言回答

### 32. 知识库质量报告 & /kb_report 命令

- **文件：** `bot/commands.py`, `bot/feedback.py`, `bot/leaderboard.py`
- **说明：** Owner 可查看知识库质量报告：文档总数、30天查询数、低置信度比例、满意度、高频问题
- **命令：** `/kb_report`

### 33. 用户满意度反馈（拇指/踩 反应）

- **文件：** `bot/feedback.py`, `bot/listener.py`
- **说明：** 用户对 Bot 回复添加拇指/踩反应时自动记录，Owner 可通过 `/satisfaction` 查看满意度统计
- **配置：** `FEEDBACK_ENABLED=true`（默认开启）
- **命令：** `/satisfaction days:30`

### 34. 对话摘要 & /pin_summary 命令

- **文件：** `bot/commands.py`
- **说明：** Owner 使用 `/pin_summary` 命令自动总结频道最近的讨论，生成摘要并钉到频道
- **命令：** `/pin_summary count:20`

### 35. 排程提醒 /schedule_reminder

- **文件：** `bot/reminders.py`, `bot/scheduler.py`, `bot/commands.py`
- **说明：** Owner 可排程自定义提醒消息（如市场开盘提醒、数据发布提醒），支持重复
- **命令：** `/schedule_reminder`, `/list_reminders`, `/cancel_reminder`

### 36. VIP 角色识别

- **文件：** `bot/listener.py`, `bot/config.py`
- **说明：** 配置 VIP 角色 ID，拥有该角色的用户不受速率限制
- **配置：** `VIP_ROLE_IDS=角色ID1,角色ID2`

### 37. 关键词监控 & 告警

- **文件：** `bot/keyword_alert.py`, `bot/listener.py`, `bot/commands.py`
- **说明：** Owner 可配置监控关键词，当用户消息包含关键词时，Bot 立即 DM 通知 Owner
- **配置：** `KEYWORD_ALERT_ENABLED=true`（默认开启）
- **命令：** `/add_alert`, `/remove_alert`, `/list_alerts`

### 38. 知识库版本管理 & 回滚

- **文件：** `bot/kb_versioning.py`, `bot/commands.py`
- **说明：** 支持知识库快照管理，每次入库前可创建快照，Owner 可查看历史快照
- **命令：** `/kb_snapshots`

### 39. 增强型欢迎流程

- **文件：** `bot/welcome_flow.py`, `bot/listener.py`
- **说明：** 新成员加入时执行多步骤欢迎 DM：立即欢迎（含 `/faq` `/ask` `/signal`）。若已配置 `PROMO_NOTIFY_ROLE_IDS`，同一条欢迎私信会带「领取通知 / 取消订阅」按钮，成员点了才进入促销私信名单
- **配置：** `WELCOME_FLOW_ENABLED=true`（建议开启），`WELCOME_STEP2_DELAY` 已由 drip 延迟替代：`WELCOME_VALUE_DELAY_SECONDS=14400`（4 小时价值内容）、`WELCOME_CTA_DELAY_SECONDS=86400`（次日产品 CTA）、`WELCOME_REMINDER_DELAY_SECONDS=259200`（第 3 天提醒）

### 40. 排行榜命令

- **文件：** `bot/leaderboard.py`, `bot/commands.py`
- **说明：** 查看最活跃频道、置信度分布等统计排行
- **命令：** `/leaderboard days:30`

### 41. A/B 测试回复风格

- **文件：** `bot/ab_test.py`, `bot/commands.py`
- **说明：** 启用后，每次回复随机选用不同风格变体，并追踪各变体的满意度
- **配置：** `AB_TEST_ENABLED=false`（默认关闭），`AB_TEST_VARIANTS=casual:style_a.txt,formal:style_b.txt`
- **命令：** `/ab_results`

### 42. 导出对话记录

- **文件：** `bot/export.py`, `bot/commands.py`
- **说明：** Owner 可将对话记录导出为 JSON 或 CSV 文件
- **命令：** `/export_conversations format:JSON days:30`

---

## 新增 Slash 命令速查

| 命令 | 说明 | 用法 |
| --- | --- | --- |
| `/schedule_reminder` | 排程提醒消息 | `/schedule_reminder title:标题 message:内容 time:2025-01-01 09:00` |
| `/list_reminders` | 列出所有提醒 | `/list_reminders` |
| `/cancel_reminder` | 取消提醒 | `/cancel_reminder reminder_id:ID` |
| `/add_alert` | 添加关键词监控 | `/add_alert keyword:关键词` |
| `/remove_alert` | 移除关键词监控 | `/remove_alert keyword:关键词` |
| `/list_alerts` | 列出监控关键词 | `/list_alerts` |
| `/kb_report` | 知识库质量报告 | `/kb_report` |
| `/kb_snapshots` | 查看知识库快照 | `/kb_snapshots` |
| `/leaderboard` | 活跃度排行榜 | `/leaderboard days:30` |
| `/ab_results` | A/B 测试结果 | `/ab_results` |
| `/export_conversations` | 导出对话 | `/export_conversations format:JSON days:30` |
| `/pin_summary` | 频道讨论摘要 | `/pin_summary count:20` |
| `/satisfaction` | 满意度统计 | `/satisfaction days:30` |
| `/weekly_summary` | 立即生成并推送本周总结 | `/weekly_summary` |
| `/daily_summary` | 立即生成并推送今日总结 | `/daily_summary` |
| `/views` | [Owner] 扫描全服频道主发言，简短总结并发到本频道 | `/views hours:24` |
| `/funnel` | 获客转化漏斗 | `/funnel days:7` |
| `/invite` | 生成专属邀请链接 | `/invite` |
| `/promo_notify` | 领取或取消活动私信通知 | `/promo_notify action:领取` |
| `/promo_notify_panel` | [Owner] 发布活动私信订阅面板 | `/promo_notify_panel` |
| `/dm_role` | [Owner] 向自愿通知身份组发送促销私信 | `/dm_role role:@活动通知 title:标题 description:内容` |

---

## 环境变量速查

所有配置项均通过 `.env` 文件设置，完整示例见 `.env.example`。

---

## 🚀 进阶增强功能（Enhancements）

### 43. 自動回覆後追問機制（Clarification Follow-up）

- **文件：** `bot/clarification.py`, `bot/listener.py`, `bot/config.py`
- **说明：** 当回复置信度较低但仍可自动回复时，先发 1 个澄清问题（如时间框架/风险偏好），避免直接输出模糊结论
- **配置：** `FEATURE_CLARIFICATION_FOLLOWUP`, `CLARIFICATION_CONFIDENCE_MAX`, `FEATURE_CLARIFICATION_CANARY_CHANNEL_IDS`

### 44. 對話級記憶摘要（Session Memory Summary）

- **文件：** `bot/session_summary.py`, `bot/listener.py`, `bot/config.py`
- **说明：** 长对话中自动把较旧消息压缩为简短摘要，再保留最近若干轮原文，提升上下文稳定性并降低 token 消耗
- **配置：** `FEATURE_SESSION_SUMMARY`, `SESSION_SUMMARY_TRIGGER_MESSAGES`, `SESSION_SUMMARY_KEEP_RECENT`, `FEATURE_SESSION_SUMMARY_CANARY_CHANNEL_IDS`

### 45. Feature Flags + Canary Channels

- **文件：** `bot/feature_flags.py`, `bot/config.py`
- **说明：** 支持按频道灰度发布功能。若 canary 列表为空则全量启用，否则仅在 canary 频道启用
- **示例：** `FEATURE_LANG_DETECT=true`, `FEATURE_LANG_DETECT_CANARY_CHANNEL_IDS=123,456`

### 46. 高風險回答防呆（Safety Guardrails）

- **文件：** `bot/guardrails.py`, `bot/listener.py`, `bot/config.py`
- **说明：** 检测高风险表述（如 all-in、保證收益、重仓/满仓等），命中后可强制走 owner review，或追加风险提示模板
- **配置：** `FEATURE_SAFETY_GUARDRAILS`, `GUARDRAIL_MODE=force_review|disclaimer`, `GUARDRAIL_DISCLAIMER`, `FEATURE_SAFETY_GUARDRAILS_CANARY_CHANNEL_IDS`

### 47. 主動學習閉環（Feedback-to-Ingestion Pipeline）

- **文件：** `bot/feedback_learning.py`, `bot/listener.py`, `bot/review.py`, `bot/scheduler.py`
- **说明：** 自动收集 👎 反馈与 owner 编辑过的回复，形成「待补 KB 问题池」，并每日汇总 Top 10 缺口问题
- **配置：** `FEATURE_FEEDBACK_LEARNING`, `FEATURE_FEEDBACK_LEARNING_CANARY_CHANNEL_IDS`

### 48. SLA / 可靠性監控

- **文件：** `bot/reliability.py`, `bot/rag.py`, `bot/scheduler.py`, `bot/config.py`
- **说明：** 监控 p95 延迟、OpenAI 错误率、review queue 堆积、scheduler tick 延迟；超阈值自动告警给 owner
- **配置：** `FEATURE_SLA_MONITORING`, `SLA_P95_LATENCY_MS_THRESHOLD`, `SLA_OPENAI_ERROR_RATE_THRESHOLD`, `SLA_REVIEW_QUEUE_BACKLOG_THRESHOLD`, `SLA_SCHEDULER_MISS_SECONDS`, `SLA_ALERT_COOLDOWN_SECONDS`

### 49. 金十市場快訊推送（Jin10 News Feed）

- **文件：** `bot/news_feed.py`, `bot/config.py`
- **说明：** 每 30 秒轮询金十数据 Flash API，将重要市场快讯（如央行决议、非农数据、突发事件）自动推送到指定 Discord 频道。重要快讯以 Embed 富文本格式展示，普通快讯以纯文本发送。支持去重、广告过滤、多频道推送。Bot 重新上线时自动回填离线期间（默认 24 小时内）错过的重要快讯
- **配置：** `NEWS_FEED_ENABLED=true`, `NEWS_CHANNEL_IDS=频道ID1,频道ID2`, `NEWS_POLL_INTERVAL_SECONDS=30`, `NEWS_IMPORTANT_ONLY=true`, `NEWS_BACKFILL_HOURS=24`

### 50. 每周重點總結（Weekly Summary）

- **文件：** `bot/weekly_summary.py`, `bot/config.py`
- **说明：** 每周六下午 2 點（ET，可配置）自動收集指定頻道內本周所有群主消息和群主回復，使用 GPT 生成重點總結，以 Embed 格式發送到指定頻道。總結包括群主分享的觀點、對成員問題的關鍵回復、重要市場動態提及。回復消息會自動抓取原始問題作為上下文。支持多頻道掃描和多頻道發佈
- **配置：** `WEEKLY_SUMMARY_ENABLED=true`, `WEEKLY_SUMMARY_CHANNELS=頻道ID1,頻道ID2`（掃描來源）, `WEEKLY_SUMMARY_DAY=5`（0=Mon, 5=Sat）, `WEEKLY_SUMMARY_HOUR=14`（ET）, `WEEKLY_SUMMARY_MINUTE=0`, `WEEKLY_SUMMARY_POST_CHANNELS=頻道ID`（發佈目標，留空則用 SUMMARY_CHANNELS）
- **命令：** `/weekly_summary`（Owner 手動觸發）

### 51. 活動推廣自動排程（Promo Monitor）

- **文件：** `bot/promo_monitor.py`, `bot/scheduler.py`, `bot/config.py`
- **说明：** Owner 在指定的來源頻道發送活動信息時，Bot 自動取消舊的推廣排程，創建新的每日重複 `schedule_promo`，附帶 `@everyone` 提及，在指定時間（默認下午 4 點 ET）推送到目標頻道，有效期 3 個月（可配置）。到期後自動取消。支持圖片附件自動嵌入 Embed
- **配置：** `PROMO_MONITOR_ENABLED=true`, `PROMO_SOURCE_CHANNEL_ID=頻道ID`, `PROMO_PUSH_HOUR=16`, `PROMO_DURATION_DAYS=90`, `PROMO_PUSH_CHANNELS=頻道ID1,頻道ID2`

### 52. YouTube 新影片自動推送（YouTube Monitor）

- **文件：** `bot/youtube_monitor.py`, `bot/config.py`
- **说明：** 每天在指定时间轮询 YouTube 频道 RSS feed，检测到新影片时自动取消旧的 YouTube 教学排程，并创建新的每日重复 `schedule_lesson`，在指定时间（默认下午 4 点 ET）推送到 Discord 频道。推送内容包含影片标题和观看链接。若开启自动导入，会将字幕/Whisper 转录写入知识库，并用 GPT 生成摘要推送到 `YOUTUBE_SUMMARY_CHANNELS`
- **配置：** `YOUTUBE_MONITOR_ENABLED=true`, `YOUTUBE_CHANNEL_ID=UCxxxxxxxxxx`, `YOUTUBE_CHECK_HOUR=11`, `YOUTUBE_CHECK_MINUTE=05`, `YOUTUBE_LESSON_PUSH_HOUR=16`, `YOUTUBE_LESSON_PUSH_CHANNELS=频道ID1,频道ID2`, `YOUTUBE_AUTO_INGEST=true`, `YOUTUBE_SUMMARY_CHANNELS=频道ID`

### 53. 每日重點總結（Daily Summary）

- **文件：** `bot/daily_summary.py`, `bot/config.py`
- **说明：** 每個工作日（週一至週五，可配置）在指定時間自動收集當天群主消息和回復，使用 GPT 生成今日重點總結，以 Embed 格式發送到指定頻道並 @everyone。與 Weekly Summary 完全獨立，可同時啟用。收集範圍為當天午夜（ET）起的所有消息
- **配置：** `DAILY_SUMMARY_ENABLED=true`, `DAILY_SUMMARY_CHANNELS=頻道ID1,頻道ID2`（掃描來源）, `DAILY_SUMMARY_DAYS=0,1,2,3,4`（0=Mon..6=Sun，默認週一到週五）, `DAILY_SUMMARY_HOUR=16`（ET）, `DAILY_SUMMARY_MINUTE=0`, `DAILY_SUMMARY_POST_CHANNELS=頻道ID`（發佈目標，留空則用 DAILY_SUMMARY_CHANNELS）
- **命令：** `/daily_summary`（Owner 手動觸發）

### 54. 自動審核（Auto Moderation）

- **文件：** `bot/auto_mod.py`, `bot/ban_words.py`, `bot/config.py`
- **说明：** 自動偵測並刪除垃圾消息、詐騙信息和廣告。支持 7 層檢測：
  1. **關鍵詞匹配** — 中英文垃圾/詐騙/廣告短語（免費帶單、穩賺不賠、guaranteed profit 等）
  2. **禁止詞列表（精確匹配）** — Owner 可通過 `/add_ban_word` 動態添加禁止詞，消息包含禁止詞即自動刪除
  3. **禁止詞列表（語義匹配）** — 使用 OpenAI 嵌入向量計算語義相似度，即使用不同措辭表達相同意思也會被攔截（閾值可配置，默認 0.82）
  4. **外部平台連結** — Telegram、WhatsApp、Line、短鏈接等
  5. **Discord 邀請連結** — 非豁免用戶發送的 discord.gg 連結
  6. **大量 @ 提及 / 連結刷屏** — 超過閾值即攔截
  7. **重複刷屏** — 同一用戶在短時間內重複發送相同內容
- **禁止詞管理命令：**
  - `/add_ban_word <word>` — 添加禁止詞（自動計算嵌入向量用於語義匹配）
  - `/remove_ban_word <word>` — 移除禁止詞
  - `/list_ban_words` — 查看所有禁止詞
- **豁免：** 群主（OWNER_USER_ID）、Bot、指定身份組（AUTO_MOD_EXEMPT_ROLE_IDS）自動豁免
- **日誌：** 刪除操作以 Embed 格式記錄到指定的 log 頻道（包含作者、頻道、原因、消息內容預覽），同時 DM 通知頻道主（含被刪消息內容和發送者 Discord ID）
- **配置：** `AUTO_MOD_ENABLED=true`, `AUTO_MOD_LOG_CHANNEL_ID=頻道ID`, `AUTO_MOD_EXEMPT_ROLE_IDS=身份組ID1,身份組ID2`, `AUTO_MOD_MAX_MENTIONS=8`, `AUTO_MOD_MAX_LINKS=5`, `AUTO_MOD_DUP_WINDOW=60`（秒）, `AUTO_MOD_DUP_THRESHOLD=3`, `AUTO_MOD_BAN_WORDS_FILE=data/ban_words.json`, `AUTO_MOD_BAN_WORDS_SIMILARITY=0.82`
- **權限要求：** Bot 需要 `Manage Messages` 權限
- **持久化：** 禁止詞列表存儲在 `data/ban_words.json`，含詞語及其嵌入向量，Bot 重啟自動加載

### 55. 頻道主題限制（Topic Guard）

- **文件：** `bot/topic_guard.py`, `bot/auto_mod.py`, `bot/config.py`
- **说明：** 為指定頻道強制執行主題限制——只允許與交易、信號、股票、外匯、加密貨幣、技術分析等投資相關的討論。閒聊、無意義消息、攻擊性發言自動刪除
- **分類方式：** 使用 GPT-4o-mini 將每條消息分類為 `on_topic`（允許）、`off_topic`（刪除）或 `offensive`（刪除），結果緩存 5 分鐘避免重複 API 調用
- **預過濾：** 純 emoji、1-2 字符的短消息直接判定為 off_topic，不調用 GPT
- **容錯：** GPT 調用失敗時默認放行（on_topic），避免誤刪
- **豁免：** 群主、Bot、指定身份組自動豁免（繼承 Auto Moderation 的豁免機制）
- **配置：** `TOPIC_RESTRICTED_CHANNEL_IDS=頻道ID1,頻道ID2`（留空則不啟用）
- **與 Auto Mod 的關係：** Topic Guard 作為 Auto Moderation 的最後一層檢測，先經過全站垃圾/禁止詞過濾後，再對受限頻道進行主題檢查

### 56. YouTube 摘要補發（Resend YouTube Summary）

- **文件：** `scripts/resend_youtube_summary.py`
- **说明：** 针对已经入库但未推送 GPT 摘要的 YouTube 视频，从 ChromaDB 读取转录文本，生成摘要并发送到 `YOUTUBE_SUMMARY_CHANNELS`。Monitor 只在检测到**新视频**时自动生成摘要；已记录过的视频需要用此脚本补发。不写 `--video-id` 时，会默认使用 `data/youtube_last_video.json` 里记录的最新视频
- **配置：** `YOUTUBE_SUMMARY_CHANNELS=频道ID`, `OPENAI_API_KEY`, `DISCORD_BOT_TOKEN`, `LLM_MODEL`
- **使用：**
  ```
  # 不写 --video-id：默认补发 data/youtube_last_video.json 里记录的最新视频
  python scripts/resend_youtube_summary.py

  # 补发指定视频
  python scripts/resend_youtube_summary.py --video-id nTWo8Wv7Jao

  # 只生成摘要、不发送到 Discord
  python scripts/resend_youtube_summary.py --video-id nTWo8Wv7Jao --dry-run

  # 覆盖标题（可选）
  python scripts/resend_youtube_summary.py --video-id nTWo8Wv7Jao --title "自定义标题"
  ```
- **前置条件：** 该视频必须已通过 YouTube 导入写入 ChromaDB（文档 metadata 含 `video_id`）。脚本不会重新下载或转录视频

### 57. 购买意向自动转化

- **文件：** `bot/acquisition.py`, `bot/listener.py`
- **说明：** 用户询问订阅、价格、试用、VIP、怎么买时，Bot 不走普通 RAG，立即回复产品 Embed + CTA 按钮（了解产品 / 申请试用 / 查看 FAQ），并 DM 通知 Owner。可选给该用户加上「咨询中」身份组，方便跟进
- **配置：** `INTENT_CONVERT_ENABLED=true`, `INTENT_NOTIFY_OWNER=true`, `INTENT_LEAD_ROLE_ID=身份组ID`（0 表示不加身份组）, `SIGNAL_PRODUCT_URL`, `FREE_TRIAL_ENABLED`, `FREE_TRIAL_URL`
- **使用：** 自动触发。占位链接（如 `your-product-url.com`）不会生成按钮，需换成真实 URL

### 58. 新人 24–72 小时转化 drip

- **文件：** `bot/welcome_flow.py`, `bot/acquisition.py`, `bot/acquisition_cog.py`
- **说明：** 新成员加入后立即欢迎 DM（含 `/faq` `/ask` `/signal`）。若已配置 `PROMO_NOTIFY_ROLE_IDS`，欢迎私信会带「领取通知 / 取消订阅」按钮。之后按延迟发送：最新日/视频摘要（证明有价值）→ 产品 CTA + 用户评价 → 第 3 天轻量提醒。任务写入 `data/welcome_drip.json`，Bot 重启不会丢失。已有 VIP 身份组则停止后续 drip
- **配置：** `WELCOME_FLOW_ENABLED=true`, `WELCOME_VALUE_DELAY_SECONDS=14400`（4 小时）, `WELCOME_CTA_DELAY_SECONDS=86400`（次日）, `WELCOME_REMINDER_DELAY_SECONDS=259200`（第 3 天）
- **使用：** 打开 `WELCOME_FLOW_ENABLED` 后自动对每位新成员执行。延迟单位为秒，从加入时刻起算

### 59. YouTube 摘要转化按钮

- **文件：** `bot/youtube_monitor.py`, `bot/acquisition.py`, `scripts/resend_youtube_summary.py`
- **说明：** 视频摘要 Embed 底部附带「了解 BigTreeSignal / 申请试用 / 查看 FAQ」按钮，教育内容同时完成获客。补发脚本同样带这些按钮
- **配置：** `SIGNAL_PRODUCT_URL`, `FREE_TRIAL_ENABLED`, `FREE_TRIAL_URL`, `YOUTUBE_SUMMARY_CHANNELS`
- **使用：** 新视频自动 ingest 后随摘要发出；补发见第 56 项

### 60. 邀请裂变 / 专属邀请链接

- **文件：** `bot/acquisition.py`, `bot/acquisition_cog.py`, `bot/commands.py`
- **说明：** 成员使用 `/invite` 生成专属 Discord 邀请。Bot 在有人加入时对比邀请码使用次数，记录邀请人。达到阈值可自动授予奖励身份组。需要 Bot 具备创建/查看邀请权限，并开启 Server Members Intent
- **配置：** `INVITE_TRACKING_ENABLED=true`, `INVITE_REWARD_THRESHOLD=3`, `INVITE_REWARD_ROLE_ID=身份组ID`（0 表示不发奖励身份组）
- **命令：** `/invite`
- **使用：** 成员在任意服务器频道执行 `/invite`，获得仅自己可见的专属链接

### 61. 转化漏斗看板

- **文件：** `bot/acquisition.py`, `bot/commands.py`
- **说明：** 统计新加入、欢迎 DM 成功/被拒、`/signal` 次数、购买意向命中、CTA 发送、邀请加入。数据在 `data/funnel.json`
- **命令：** `/funnel days:7`（Owner）
- **使用：** Owner 私密查看近 N 天（1–90）漏斗与上线以来累计。`/signal` 已公开化，不限 `PROMO_CHANNEL_IDS`

### 62. 自愿通知身份组促销私信

- **文件：** `bot/role_dm.py`, `bot/commands.py`, `bot/scheduler.py`, `bot/welcome_flow.py`
- **说明：** 只给成员**自愿领取**的通知身份组发促销私信。不能用手动打的运营/兴趣标签群发（Discord 会把未征得同意的群发当垃圾）。白名单外的身份组，命令会直接拒绝。
- **配置：** `PROMO_NOTIFY_ROLE_IDS`（自愿「活动通知」身份组 ID，逗号分隔），`PROMO_DM_DELAY_SECONDS=1.2`，`PROMO_DM_MAX_RECIPIENTS=200`
- **使用：**
  1. 在 Discord 新建「活动通知」身份组（不要给管理权限），ID 写入 `PROMO_NOTIFY_ROLE_IDS`；Bot 身份组须排在它上面，并有「管理身份组」权限
  2. Owner 在公告频道执行 `/promo_notify_panel`（建议置顶）；成员点「领取通知」才进名单
  3. 新成员加入时，欢迎私信也会带同一对「领取通知 / 取消订阅」按钮（需 `WELCOME_FLOW_ENABLED=true`）
  4. 发活动：`/dm_role` 只发私信（先确认人数）；或 `/post_promo` / `/schedule_promo` 加可选 `dm_role` 同步私信
  5. 「取消订阅」只去掉通知身份组，现有运营标签不动。单次超过 `PROMO_DM_MAX_RECIPIENTS` 会拒绝发送
- **命令：** `/promo_notify_panel`、`/promo_notify`、`/dm_role`；`/post_promo` 与 `/schedule_promo` 的 `dm_role` 参数
- **盘活与订购计划书：** [`GROWTH_PLAYBOOK.md`](./GROWTH_PLAYBOOK.md)

### 63. 频道主观点总结（/views）

- **文件：** `bot/commands.py`, `bot/views_summary.py`, `bot/weekly_summary.py`, `bot/listener.py`
- **说明：** Owner 在服务器文字频道或帖子执行 `/views`，Bot 扫描**整个服务器**里你最近一段时间的发言，用 GPT 生成**尽量简短、清楚**的要点总结（约 1200 字以内，最多 3 个小标题）并公开发到当前频道，不 @everyone。收集范围：
  - 本服务器全部文字频道 / 论坛帖 / 公开帖：你的发帖，以及对成员的回复（回复对象匿名为「成员」，不带昵称）
  - 你参与过的私密帖 / Bot 可见群私信：以你的发言为主，对方只保留极短匿名上下文，公开总结不点名、不原文粘贴
  - Discord **不允许** Bot 读取你与成员之间的一对一私信；若要把一对一交流纳入总结，请在服务器开私密帖并让 Bot 可见
  - 每个频道从新往旧翻页直到时间窗口结束，按**群主消息条数**计数，避免活跃频道把你的发言挤掉
  - 排除频道（`EXCLUDED_CHANNEL_IDS`）和促销源频道（`PROMO_SOURCE_CHANNEL_ID`）不扫描
- **使用：** `/views`（默认最近 24 小时）；`/views hours:48`（1–168 小时）。仅 Owner，仅服务器文字频道/帖子
- **命令：** `/views hours:24`
- **注意：** 与 `/daily_summary`、`/pin_summary` 不同：只总结频道主观点，当场发到执行命令的频道

