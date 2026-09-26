# 增长三件套：邀请奖励 / 新人 onboarding / 15 天只读体验

> 上线：2026-09-26。代码：`bot/acquisition.py`、`bot/acquisition_cog.py`、`bot/timed_roles.py`、`bot/welcome_flow.py`、`bot/commands.py`。测试：`tests/test_growth.py`。

三件套互相独立：邀请追踪、限时身份组引擎、新人 DM 序列。Bot 缺权限时只记日志降级，不崩溃（启动时会打一行权限自检日志）。

---

## 1. 邀请追踪 + 排行榜 + 奖励

**成员指令**

| 指令 | 说明 |
|---|---|
| `/invite` | 生成专属邀请链接（仅自己可见），附带当前邀请数与奖励说明 |
| `/invite_leaderboard` | 近 30 天 Top10 排行榜 + 自己的排名（仅自己可见） |
| `/my_invites` | 累计邀请数、近 30 天排名、ETF 奖励进度（还差几人 / 生效中） |

**奖励规则（当前线上配置）**

| 条件 | 奖励 | 有效期 |
|---|---|---|
| 累计成功邀请 ≥ **5** 人 | **懒人etf🌲**（ETF 版会员） | 30 天，DM 通知；过期 30 天后可重复获得 |
| 每月 1 号结算近 30 天 **Top5** | **懒人🌴**（full 版会员） | 30 天，DM 通知 |

- 计数按邀请码 `uses` 增量归因（`on_member_join` 时对比快照），数据在 `data/invites.json`（`attributions` 带时间戳，`counts` 为累计）。
- 排行榜按**近 30 天**归因统计；月度结算只取 TopN 且至少邀请 1 人，已有付费 cohort 身份组（名字形如 `懒人🌴22`）的成员跳过（已是付费用户，不重复发奖）。
- 结算幂等：同一月份只结算一次（`data/invite_settlement.json`）；若发放失败（缺权限等），本月**不**标记为已结算，24 小时后循环会重试，已发放的人不会重复发放。

**配置（环境变量）**

| 变量 | 默认值 | 说明 |
|---|---|---|
| `INVITE_TRACKING_ENABLED` | `true` | 总开关 |
| `INVITE_ETF_REWARD_ROLE_ID` | `1445448090227179711` | 邀请奖励：懒人etf🌲 |
| `INVITE_ETF_MIN_COUNT` | `5` | 拿 ETF 奖励所需累计邀请数 |
| `INVITE_FULL_REWARD_ROLE_ID` | `1445447888439349319` | 月度 TopN 奖励：懒人🌴 |
| `INVITE_TOPN_COUNT` | `5` | 月度结算 TopN |
| `INVITE_REWARD_DAYS` | `30` | 奖励有效期（天） |

**需要的 Discord 权限**：`管理服务器`（读邀请列表）、`管理身份组`（发/收身份组）、`创建邀请`（`/invite`）。且 Bot 的身份组必须**拖到**奖励身份组之上，否则即使有权限也发不出去。

---

## 2. 新人 onboarding DM（三步）

| 时机 | 内容 |
|---|---|
| Day 0（加入即刻） | 欢迎 + 精华帖（`#信号说明`、`/faq`、`/ask`、`/signal`）+ 告知已开通 15 天只读体验 |
| Day 1（+24h） | 🎁 免费体验信号（取最新一条价值内容） |
| Day 3（+72h） | 付费 CTA（产品介绍 + 评价 + 购买按钮） |

- 任务持久化在 `data/welcome_drip.json`，重启不丢失；成员退群自动取消未发送的任务。
- DM 被拒（用户关了私信）只记日志，不重试、不打扰。

**配置**

| 变量 | 默认值 | 说明 |
|---|---|---|
| `WELCOME_FLOW_ENABLED` | `false` | 总开关（建议开启） |
| `ONBOARD_DAY1_DELAY_SECONDS` | `86400` | Day1 延迟（秒） |
| `ONBOARD_DAY3_DELAY_SECONDS` | `259200` | Day3 延迟（秒） |

---

## 3. 新人 15 天只读体验

- 新人加入 → 自动获得身份组 **`新人体验15天`**（Bot 启动时自动创建），同时写入限时发放记录（`data/timed_roles.json`）。
- 该身份组在会员频道（默认 `fullversion小队`、`etf小队`）的权限：**可看、不可发言**（`view_channel=True, send_messages=False`，幂等设置）。
- **15 天后自动收回**（每 5 分钟检查一次）。已有付费 cohort 身份组的成员**不会**被收回正式身份组（付费保护：名字匹配 `^懒人.*\d` 的组会被跳过并记日志）。
- 已是付费会员的新人（重进等情况）不会重复发放体验组。
- 成员退群时，未到期的发放记录标记取消（保留审计）。

**配置**

| 变量 | 默认值 | 说明 |
|---|---|---|
| `TRIAL_ROLE_NAME` | `新人体验15天` | 体验身份组名（改名会新建，请勿随意改） |
| `TRIAL_MEMBER_CHANNEL_IDS` | `912366231112282172,923449257711763466` | 只读体验的会员频道 |
| `TRIAL_GRANT_DAYS` | `15` | 体验有效期（天） |

---

## 运维要点

1. **权限**：`管理服务器` + `管理身份组` 是刚需；Bot 身份组位置必须高于 `懒人etf🌲` / `懒人🌴` / `新人体验15天`。
2. **改规则不用改代码**：门槛人数、TopN、有效天数、延迟都是环境变量。
3. **数据文件**（勿手动改，勿提交脏数据）：`data/invites.json`、`data/timed_roles.json`、`data/invite_settlement.json`、`data/welcome_drip.json`。
4. **已知边界**：排行榜是近 30 天窗口，`counts` 是累计值；`attributions` 只保留最近 500 条（超量后排行榜窗口会缩短）。
