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
- **说明：** 导入 YouTube 视频字幕到 ChromaDB（字幕 API 优先；无字幕时 Whisper 回退：yt-dlp 下载音频 → ffmpeg 转码 → OpenAI Whisper）
- **使用：** `python -m ingestion.ingest_youtube --urls "URL"`
- **依赖：** `pip install 'yt-dlp[default]' imageio-ffmpeg`；无系统 ffmpeg 时可将 `ffmpeg`/`ffprobe`（及新版 yt-dlp 所需的 `deno`）放到 venv 的 `Scripts/` 或 `bin/` 目录。代码通过完整路径解析二进制，不依赖系统 PATH

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
| `/resend_summary` | 补发 YouTube 视频 GPT 摘要（缺转录时自动入库） | `/resend_summary` 或 `/resend_summary video_url:链接` |

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
| `/resend_summary` | [Owner] 补发 YouTube 视频摘要（自动查库/入库） | `/resend_summary` 或 `video_url:https://youtu.be/xxx` |

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
- **说明：** 每 30 秒轮询金十数据 Flash API，将重要市场快讯（如央行决议、非农数据、突发事件）自动推送到指定 Discord 频道。重要快讯以 Embed 富文本格式展示，普通快讯以纯文本发送。支持去重、广告过滤、多频道推送。Bot 重新上线或 Discord 重连时自动回填离线期间（默认 24 小时内，最多 50 条）错过的重要快讯；发帖成功后才推进 `last_id`，避免漏发
- **配置：** `NEWS_FEED_ENABLED=true`, `NEWS_CHANNEL_IDS=频道ID1,频道ID2`, `NEWS_POLL_INTERVAL_SECONDS=30`, `NEWS_IMPORTANT_ONLY=true`, `NEWS_BACKFILL_HOURS=24`（离线超过 24 小时或单次超过 50 条重要快讯时，更早的不会补发）
- **当前路由（2026-09-29）：** 新闻频道 = `#时事新闻`（1554564605047476336），只收金十快讯；盘前简报、宏观提醒、公司公告、个股异动发 `#bigtreesignal_ai`（各自显式指定频道 ID，不再跟随新闻频道）

### 50. 每周重點總結（Weekly Summary）

- **文件：** `bot/weekly_summary.py`, `bot/config.py`
- **说明：** 每周六（可配置）在指定 ET 时间自动收集指定频道内本周所有群主消息和群主回复，使用 GPT 生成重点总结，以 Embed 格式发送到指定频道并 @everyone。回复消息会自动抓取原始问题作为上下文。支持多频道扫描和多频道发布。**可靠性：** 频道读取/网络失败不会再被误判为「本周无消息」；失败后每 30 分钟重试；错过预定时间后 18 小时内仍会补跑；睡眠采用分片计时，减轻电脑休眠导致的睡过点
- **配置：** `WEEKLY_SUMMARY_ENABLED=true`, `WEEKLY_SUMMARY_CHANNELS=频道ID1,频道ID2`（扫描来源）, `WEEKLY_SUMMARY_DAY=5`（0=Mon, 5=Sat）, `WEEKLY_SUMMARY_HOUR=20`（ET）, `WEEKLY_SUMMARY_MINUTE=5`, `WEEKLY_SUMMARY_POST_CHANNELS=频道ID`（发布目标，留空则用 SUMMARY_CHANNELS）
- **命令：** `/weekly_summary`（Owner 手动触发；可立即补发上周未发出的总结）

### 51. 活動推廣自動排程（Promo Monitor）

- **文件：** `bot/promo_monitor.py`, `bot/scheduler.py`, `bot/config.py`
- **说明：** Owner 在指定的來源頻道發送活動信息時，Bot 自動取消舊的推廣排程，創建新的每日重複 `schedule_promo`，附帶 `@everyone` 提及，在指定時間（默認下午 4 點 ET）推送到目標頻道，有效期 3 個月（可配置）。到期後自動取消。支持圖片附件自動嵌入 Embed
- **配置：** `PROMO_MONITOR_ENABLED=true`, `PROMO_SOURCE_CHANNEL_ID=頻道ID`, `PROMO_PUSH_HOUR=16`, `PROMO_DURATION_DAYS=90`, `PROMO_PUSH_CHANNELS=頻道ID1,頻道ID2`

### 52. YouTube 新影片自動推送（YouTube Monitor）

- **文件：** `bot/youtube_monitor.py`, `bot/config.py`
- **说明：** 每天在指定时间轮询 YouTube 频道 RSS feed，检测到新影片时自动取消旧的 YouTube 教学排程，并创建新的每日重复 `schedule_lesson`，在指定时间（默认下午 4 点 ET）推送到 Discord 频道。推送内容包含影片标题和观看链接。若开启自动导入，会将字幕/Whisper 转录写入知识库，并用 GPT 生成摘要推送到 `YOUTUBE_SUMMARY_CHANNELS`。若转录失败仍会发送「新视频通知」Embed；已记录过的视频需用 `/resend_summary` 补发摘要（见第 56 项）
- **配置：** `YOUTUBE_MONITOR_ENABLED=true`, `YOUTUBE_CHANNEL_ID=UCxxxxxxxxxx`, `YOUTUBE_CHECK_HOUR=11`, `YOUTUBE_CHECK_MINUTE=05`, `YOUTUBE_LESSON_PUSH_HOUR=16`, `YOUTUBE_LESSON_PUSH_CHANNELS=频道ID1,频道ID2`, `YOUTUBE_AUTO_INGEST=true`, `YOUTUBE_SUMMARY_CHANNELS=频道ID`

### 53. 每日重點總結（Daily Summary）

- **文件：** `bot/daily_summary.py`, `bot/config.py`
- **说明：** 每个工作日（周一至周五，可配置）在指定时间自动收集当天群主消息和回复，使用 GPT 生成今日重点总结，以 Embed 格式发送到指定频道并 @everyone。与 Weekly Summary 完全独立。每天只推送一次：若定时器提前触发（如 15:59）后已发送，不会在同一分钟再次发送
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

### 56. YouTube 摘要补发（Resend YouTube Summary）

- **文件：** `bot/youtube_monitor.py`, `scripts/resend_youtube_summary.py`, `ingestion/ingest_youtube.py`
- **命令：** `/resend_summary`
- **说明：** Owner 用 slash 命令补发 YouTube 视频 GPT 摘要到 `YOUTUBE_SUMMARY_CHANNELS`。自动检查 ChromaDB：已有转录则直接摘要；没有则 Whisper 入库后再摘要；仍失败则基于标题生成预告式摘要（金色 Embed + footer 标明）。进度在同一条 ephemeral 消息上更新；发送失败不会误报成功。同一时间只允许一个补发任务。Monitor 关闭时仍可用。`scripts/resend_youtube_summary.py` 为命令行备用（仅支持已入库视频）
- **配置：** `YOUTUBE_SUMMARY_CHANNELS=频道ID`, `OPENAI_API_KEY`, `LLM_MODEL`, `OWNER_USER_ID`
- **Whisper 依赖（无字幕时必需）：** `pip install 'yt-dlp[default]' imageio-ffmpeg`；Windows 建议将 `ffmpeg.exe`、`ffprobe.exe`、`deno.exe` 放到 `.venv/Scripts/`（新版 yt-dlp 下载 YouTube 需要 JS runtime）
- **使用（Slash 命令）：**
  ```
  /resend_summary                                    — 补发最近检测到的视频
  /resend_summary video_url:https://youtu.be/xxxxx   — 补发指定视频
  /resend_summary video_url:... title:自定义标题      — 覆盖标题
  ```
- **使用（脚本备用）：**
  ```
  python scripts/resend_youtube_summary.py
  python scripts/resend_youtube_summary.py --video-id nTWo8Wv7Jao
  python scripts/resend_youtube_summary.py --video-id nTWo8Wv7Jao --dry-run
  ```
- **流程：** ChromaDB 已有转录 → 直接生成摘要；未入库 → 自动 Whisper 转录入库 → 生成摘要；转录失败 → 基于标题生成预告式摘要 → 发到摘要频道（带获客 CTA 按钮，见第 59 项）

### 57. 购买意向自动转化

- **文件：** `bot/acquisition.py`, `bot/listener.py`
- **说明：** 用户询问订阅、价格、试用、VIP、怎么买时，Bot 不走普通 RAG，立即回复产品 Embed + CTA 按钮（了解产品 / 申请试用 / 查看 FAQ），并 DM 通知 Owner。可选给该用户加上「咨询中」身份组，方便跟进
- **配置：** `INTENT_CONVERT_ENABLED=true`, `INTENT_NOTIFY_OWNER=true`, `INTENT_LEAD_ROLE_ID=身份组ID`（0 表示不加身份组）, `SIGNAL_PRODUCT_URL`, `FREE_TRIAL_ENABLED`, `FREE_TRIAL_URL`
- **使用：** 自动触发。占位链接（如 `your-product-url.com`）不会生成按钮，需换成真实 URL

### 58. 新人 onboarding DM 序列（Day 0 / 1 / 3）

- **文件：** `bot/welcome_flow.py`, `bot/acquisition.py`, `bot/acquisition_cog.py`
- **说明：** Day 0 加入即刻欢迎 DM（精华入口：`#信号说明`、`/faq`、`/ask`、`/signal`，附 15 天试用说明；配置了 `PROMO_NOTIFY_ROLE_IDS` 时带「领取通知 / 取消订阅」按钮）。Day 1 发免费体验信号（最新价值内容）。Day 3 发付费 CTA + 用户评价。任务写入 `data/welcome_drip.json`，Bot 重启不丢失；成员退群自动取消未发送任务；已有 VIP 身份组则停止后续 drip
- **配置：** `WELCOME_FLOW_ENABLED=true`, `ONBOARD_DAY1_DELAY_SECONDS=86400`（第 1 天）, `ONBOARD_DAY3_DELAY_SECONDS=259200`（第 3 天）
- **使用：** 打开 `WELCOME_FLOW_ENABLED` 后自动对每位新成员执行。延迟单位为秒，从加入时刻起算
- **运维手册：** [`INVITE_REWARDS_TRIAL.md`](../growth/INVITE_REWARDS_TRIAL.md)

### 59. YouTube 摘要转化按钮

- **文件：** `bot/youtube_monitor.py`, `bot/acquisition.py`, `scripts/resend_youtube_summary.py`
- **说明：** 视频摘要 Embed 底部附带「了解 BigTreeSignal / 申请试用 / 查看 FAQ」按钮，教育内容同时完成获客。自动推送与 `/resend_summary`（及补发脚本）发出的摘要均带这些按钮
- **配置：** `SIGNAL_PRODUCT_URL`, `FREE_TRIAL_ENABLED`, `FREE_TRIAL_URL`, `YOUTUBE_SUMMARY_CHANNELS`
- **使用：** 新视频自动 ingest 后随摘要发出；补发见第 56 项

### 60. 邀请追踪 / 排行榜 / 奖励

- **文件：** `bot/acquisition.py`, `bot/acquisition_cog.py`, `bot/commands.py`, `bot/timed_roles.py`
- **说明：** 成员用 `/invite` 生成专属邀请链接；有人加入时 Bot 对比邀请码 `uses` 增量归因。奖励：累计邀请 ≥ `INVITE_ETF_MIN_COUNT`（默认 5）→ ETF 会员身份组 30 天（DM 通知，过期 30 天后可重复获得）；每月 1 号结算近 30 天 Top `INVITE_TOPN_COUNT`（默认 5）→ full 会员身份组 30 天（幂等结算，失败重试）。已有付费 cohort 身份组的成员跳过。需要 Bot 具备「管理服务器」（读邀请列表）、「管理身份组」、「创建邀请」权限，且 Bot 身份组位置高于奖励身份组
- **配置：** `INVITE_TRACKING_ENABLED=true`, `INVITE_ETF_REWARD_ROLE_ID`, `INVITE_ETF_MIN_COUNT=5`, `INVITE_FULL_REWARD_ROLE_ID`, `INVITE_TOPN_COUNT=5`, `INVITE_REWARD_DAYS=30`
- **命令：** `/invite`、`/invite_leaderboard`、`/my_invites`
- **使用：** 成员在任意服务器频道执行 `/invite`，获得仅自己可见的专属链接
- **运维手册：** [`INVITE_REWARDS_TRIAL.md`](../growth/INVITE_REWARDS_TRIAL.md)

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
- **盘活与订购计划书：** [`GROWTH_PLAYBOOK.md`](../growth/GROWTH_PLAYBOOK.md)

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

### 64. 限时身份组引擎与 15 天只读体验

- **文件：** `bot/timed_roles.py`, `bot/acquisition_cog.py`
- **说明：** 通用的过期身份组引擎：发放记录持久化在 `data/timed_roles.json`，每 5 分钟扫一次回收到期身份组。支撑 (a) 邀请奖励 与 (b) 新人试用：新人加入自动获得 `新人体验15天` 身份组（Bot 启动时自动创建），在会员频道只读（`view_channel` 允许、`send_messages` 拒绝），`TRIAL_GRANT_DAYS`（默认 15）天后自动收回。名字匹配 `^懒人.*\d` 的付费 cohort 身份组受保护，不会被过期回收误删；退群成员的未到期记录标记取消。缺「管理身份组」权限时所有特权调用只记警告日志、不崩溃
- **配置：** `TRIAL_ROLE_NAME=新人体验15天`, `TRIAL_MEMBER_CHANNEL_IDS`（逗号分隔）, `TRIAL_GRANT_DAYS=15`
- **运维手册：** [`INVITE_REWARDS_TRIAL.md`](../growth/INVITE_REWARDS_TRIAL.md)


### 65. 财报速读（Earnings Digest）

- **文件：** `bot/earnings.py`
- **说明：** 金十快讯轮询时扫描**全部**快讯（不受 important 过滤限制），匹配到关注公司的财报快讯（含 EPS/营收等硬指标数字）后，用 LLM 提取 EPS vs 预期、营收 vs 预期、超预期百分比、下季度/全年指引，生成中文速读发到 `#财报速读` 频道。同公司同财报季只发一次（`data/earnings_posted.json` 去重）。点评只做事实总结，不给买卖建议
- **配置：** `EARNINGS_ENABLED=true`, `EARNINGS_CHANNEL_ID`, `EARNINGS_TICKERS`（逗号分隔，如 `NVDA,AAPL,MSFT,AMZN,GOOGL,META,TSLA,AMD,AVGO,MU,COIN,MSTR`）

### 66. 财报日历提醒（Earnings Calendar Reminders）

- **文件：** `bot/earnings.py`（`EarningsCalendarCog`）
- **说明：** 每 6 小时查 Nasdaq 财报日历 API，关注公司在**财报前 1 天**发预告、**当天早上**再提醒一次，内容含发布日期、财季、市场预期 EPS（及机构家数）、盘前/盘后，发到 `#财报速读`。去重记录 `data/earnings_calendar_reminded.json`
- **配置：** 沿用 `EARNINGS_ENABLED` / `EARNINGS_CHANNEL_ID` / `EARNINGS_TICKERS`

### 67. 个股异动推送（Movers Alerts）

- **文件：** `bot/movers.py`（`MoversCog`）
- **说明：** 美股盘中（周一至周五 9:30–16:00 ET）每 15 分钟查 Yahoo 行情，关注公司相对昨收涨跌达到阈值即推送（默认 ±3% 首报、±5% 升级），附带金十相关快讯标题作可能原因。每天每档阈值只推一次（`data/movers_alerted.json`，7 天自动清理）。休市日自动跳过（用报价时间戳判断，避免 stale 价格误报）
- **配置：** `MOVERS_ENABLED=true`, `MOVERS_CHANNEL_ID`（默认用新闻频道；2026-09-29 起显式指定 `#bigtreesignal_ai`，异动推送作为信号留在原频道）, `MOVERS_THRESHOLD_PCT=3.0`, `MOVERS_ESCALATE_PCT=5.0`, `MOVERS_POLL_MINUTES=15`

### 68. 持仓诊断小工具（/持仓诊断）

- **文件：** `bot/portfolio.py`（`PortfolioCog`）
- **说明：** 群员执行 `/持仓诊断` 并输入如 `NVDA:30,TSLA:20,AAPL:50`（代码:权重%，2–10 只），Bot 拉取 6 个月日线（优先复权价）计算 HHI 集中度、平均两两相关性、组合年化波动率、近 6 个月回报、行业分布，再由 LLM 生成中文结构化诊断（集中度/相关性/波动率/行业偏向 + 风格总结 + 风险点）。结果 **ephemeral 仅自己可见**，不给买卖建议，强制附带「不构成投资建议」声明
- **使用：** `/持仓诊断 持仓:NVDA:30,TSLA:20,AAPL:50`
- **命令：** `/持仓诊断`

### 69. 盘前简报（Pre-market Briefing）

- **文件：** `bot/premarket.py`（`PremarketCog`）
- **说明：** 每个交易日 8:30 ET 自动发一条盘前简报到 `#bigtreesignal_ai`：股指期货（标普/纳指）+ VIX、今日宏观事件、今日关注公司财报、关注公司盘前异动（默认 ±2%）。休市日自动改为发一条"今日休市"短消息。每天只发一次（`data/premarket_briefed.json` 去重）。期货数据时间戳非当日则判定为休市
- **配置：** `PREMARKET_ENABLED=true`, `PREMARKET_CHANNEL_ID`（默认用新闻频道）, `PREMARKET_THRESHOLD_PCT=2.0`

### 70. 宏观事件日历提醒（Macro Calendar Reminders）

- **文件：** `bot/macro.py`（`MacroCog`）
- **说明：** 内置 FOMC 议息决议、CPI、非农、PCE 的发布日历（2026-09-29 按 federalreserve.gov / BLS / BEA 官网日历核实：2026 年无政府停摆，BLS/BEA 日历正常；2025 年 43 天停摆的影响不要套用到 2026），每个事件**前 1 天发预告、当天早上再提醒一次**，发到 `#bigtreesignal_ai`。去重记录 `data/macro_reminded.json`（7 天自动清理）。BLS/BEA 更新日期后需同步修改 `EVENTS` 列表
- **配置：** `MACRO_ENABLED=true`, `MACRO_CHANNEL_ID`（默认用新闻频道）

### 71. 个股技术面速览（/技术面）

- **文件：** `bot/technicals.py`（`TechnicalsCog`）
- **说明：** 群员执行 `/技术面` 输入股票代码，Bot 拉取 1 年日线计算 RSI(14)、MACD(12,26,9)、股价相对 MA20/MA50/MA200 位置、最新成交量相对 20 日均量倍数，纯客观指标展示（附超买/超卖等中性标签；金叉/死叉只在刚形成交叉的 K 线标注，其余显示 DIF 在 DEA 上方/下方），不给结论、不给买卖建议。结果 **ephemeral 仅自己可见**，强制附带「不构成投资建议」声明
- **命令：** `/技术面 代码:NVDA`

### 72. 快速报价（/报价）

- **文件：** `bot/technicals.py`（`TechnicalsCog`）
- **说明：** 群员执行 `/报价` 输入股票代码，返回现价、相对昨收涨跌幅、今开/最高/最低/成交量，以及盘前/盘后价格（如有）。结果 **ephemeral 仅自己可见**，强制附带「不构成投资建议」声明
- **命令：** `/报价 代码:NVDA`

### 73. 公司公告监控（Corporate Announcements）

- **文件：** `bot/announcements.py`（挂在 `NewsFeedCog` 快讯扫描链上）
- **说明：** 金十快讯轮询时扫描**全部**快讯（不受 important 过滤限制），匹配到关注公司的**股票回购、增发/配股/融资、分析师评级变化**（上调/下调评级、目标价调整）即发短提醒到 `#bigtreesignal_ai`，附快讯原文摘要。财报类快讯由财报速读处理，此处自动跳过避免重复。股票代码按独立词匹配（`MU` 不会命中 `musk`，`COIN` 不会命中 `bitcoin`）；央行逆回购操作不计入"股票回购"。按快讯 ID 去重（`data/announcements_posted.json`）
- **配置：** `ANNOUNCE_ENABLED=true`, `ANNOUNCE_CHANNEL_ID`（默认用新闻频道），沿用 `EARNINGS_TICKERS` 关注列表

### 74. ⭐ 私信 DM 群发触达（DM Broadcast）【本期重点】

- **文件：** `bot-ops/dm_broadcast.py`（独立脚本，不依赖线上 Bot）、`bot/trial_cog.py`（按钮交互）
- **说明：** 群公告（含 @everyone）实测只能触达几十人，本功能是"让一条推广消息触达每一个成员"的标准打法：Bot 给全员逐个发推广私信，附 ✅ 按钮，点击即参与。四层触达：①分批 DM（主力，节流 8–12 秒/条、每天上限 400 条，约 10 天发完 5000 人，429 按 Retry-After 退避）；②行为触发 DM（新加入/首条发言/首次 reaction 时各发一次，打开率最高）；③群公告备份（覆盖关闭私信的人）；④推广大使人传人。合规红线：每条 DM 带退订（回复 STOP 永久退订）、同一主题每人最多 1 次群发 + 1 次触发。状态文件断点续跑、幂等，DM 关闭名单单独输出走公告补。详见 `docs/zh/growth/DM_OUTREACH_PLAN.md`
- **配置：** 独立脚本读 `~/workspace/user/files/env.txt` 的 Token；`--dry-run` 预览不真发
- **使用：** `python3 bot-ops/dm_broadcast.py --dry-run` 预览 → `python3 bot-ops/dm_broadcast.py` 正式分批发送

### 75. 免费试用一个月（信号体验 / Trial30）

- **文件：** `bot/trial_cog.py`, `bot/trial_config.py`
- **说明：** 为期一个月的免费信号体验活动。用户在群里发 `!试用` 或点击推广 DM 中的 ✅ 按钮 → Bot 查资格（非付费会员、终身一次、Discord 账号注册 ≥30 天）→ 立即发放「信号体验」身份组（7 个会员频道只读，2026-12-31 前有效）→ 30 天计时启动。随后 Bot DM 引导用户私信群主发送分享截图 + TradingView 用户名，群主在 TradingView 手动开通 ETF 指标权限后执行 `!tvdone @用户 <TV用户名>` 标记。六次转化 drip（Day1/7/14/21/25/30）自动推进转付费；30 天到期自动收回身份组并挂「体验过期」标记。安全开关 `TRIAL30_ENABLED`（默认 false）
- **配置：** `TRIAL30_ENABLED=true`, `TRIAL_CAMPAIGN_END=2026-12-31`, `TRIAL30_INVITE_LINK`
- **命令：** `!试用`（用户）、`!tvdone @用户 TV用户名`（管理员）

### 76. bigTreeSignal Credit 台账（Credit Ledger）

- **文件：** `bot/credit.py`（纯 ledger 逻辑）、`bot/credit_cog.py`（命令）、`bot-ops/import_credits.py`（批量导入脚本）
- **说明：** 订阅为手动收款（PayPal/支付宝/微信），促销返的 credit 需要一个不会扯皮的账本。以 Discord ID 为主键（可绑定 TradingView ID），每笔发放/抵扣都记账（时间、金额、原因、操作人），余额 2 位小数。管理员命令：`!grant_credit @成员 金额 原因`（发放，自动 DM 通知用户）、`!use_credit @成员 金额 原因`（续费抵扣，余额不足报错不扣款）、`!link_tv @成员 TV用户名`（绑定 TV）；用户自查：`/my_credit`（ephemeral 仅自己可见，显示余额 + TV 绑定 + 最近 5 笔）。促销结束后 owner 提供 ID 名单（discord_id,tv_username,amount,reason CSV），`import_credits.py --dry-run` 预览后批量导入
- **配置：** 无（`CREDIT_STATE_FILE` 环境变量可覆盖存储路径，仅测试用）
- **命令：** `!grant_credit` / `!use_credit` / `!link_tv`（管理员）、`/my_credit`（所有用户）
