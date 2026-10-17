"""「免费试用30天」功能配置。

所有项都可以用环境变量覆盖。安全开关 TRIAL30_ENABLED 默认 False ——
开启前，命令与触发器全部静默跳过（STOP 退订监听除外）。
"""

from __future__ import annotations

import os

TRIAL30_ENABLED: bool = os.getenv("TRIAL30_ENABLED", "false").lower() in (
    "1", "true", "yes",
)

TRIAL30_ROLE_NAME: str = os.getenv("TRIAL30_ROLE_NAME", "信号体验")
TRIAL30_DAYS: int = int(os.getenv("TRIAL30_DAYS", "30"))
TRIAL30_EXPIRED_ROLE_NAME: str = os.getenv("TRIAL30_EXPIRED_ROLE_NAME", "体验过期")
TRIAL30_MIN_ACCOUNT_AGE_DAYS: int = int(
    os.getenv("TRIAL30_MIN_ACCOUNT_AGE_DAYS", "30")
)

# 试用领取要求分享的 Discord 邀请链接（群主在群公告/推广中使用的固定链接）。
TRIAL30_INVITE_LINK: str = os.getenv(
    "TRIAL30_INVITE_LINK", "https://discord.gg/GHXH9Xw6rn"
)

# 免费试用活动截止日期（v3：用户拍板"2027年之前有效"）。
# 格式 YYYY-MM-DD；该日期（含当天）之后 !试用/报名按钮不再发放新试用。
TRIAL_CAMPAIGN_END: str = os.getenv("TRIAL_CAMPAIGN_END", "2026-12-31")


def campaign_active(now=None) -> bool:
    """活动是否仍在有效期内。日期解析失败时默认放行（fail-open）。"""
    from datetime import datetime, timedelta, timezone

    now = now or datetime.now(timezone.utc)
    try:
        end = datetime.strptime(TRIAL_CAMPAIGN_END.strip(), "%Y-%m-%d")
    except (ValueError, AttributeError):
        return True
    end = end.replace(tzinfo=timezone.utc) + timedelta(days=1)
    return now < end


def _parse_id_set(raw: str) -> set[str]:
    """Parse a comma-separated snowflake list into a set of strings.

    Trailing ``#`` comments are stripped, mirroring bot/config.py::parse_id_list.
    """
    ids: set[str] = set()
    for part in (raw or "").split(","):
        token = part.split("#", 1)[0].strip()
        if token.lstrip("-").isdigit():
            ids.add(token)
    return ids


# 付费组 role id —— 与 ~/workspace/bot-ops/dm_broadcast.py 的 PAID_ROLE_IDS
# 同一快照（懒人🌴 / 懒人etf🌲），用于试用资格排除。
PAID_ROLE_IDS: set[str] = _parse_id_set(
    os.getenv(
        "TRIAL30_PAID_ROLE_IDS",
        "1445447888439349319,1445448090227179711",
    )
)

BOT_OPS_DIR: str = os.getenv(
    "BOT_OPS_DIR", os.path.expanduser("~/workspace/bot-ops")
)
# 群发脚本 dm_broadcast.py 的 state 文件 —— 与它共享 opted_out 退订名单。
BROADCAST_STATE_FILE: str = os.path.join(BOT_OPS_DIR, "dm_broadcast_state.json")
