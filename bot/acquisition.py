"""Acquisition helpers — purchase intent, CTA buttons, funnel stats, welcome drip, invites."""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import discord

from bot.config import (
    FREE_TRIAL_ENABLED,
    FREE_TRIAL_URL,
    INTENT_LEAD_ROLE_ID,
    INTENT_NOTIFY_OWNER,
    INVITE_ETF_REWARD_ROLE_ID,
    INVITE_FULL_REWARD_ROLE_ID,
    INVITE_REWARD_ROLE_ID,
    INVITE_REWARD_THRESHOLD,
    ONBOARD_DAY1_DELAY_SECONDS,
    ONBOARD_DAY3_DELAY_SECONDS,
    OWNER_USER_ID,
    SIGNAL_PRODUCT_NAME,
    SIGNAL_PRODUCT_URL,
    VIP_ROLE_IDS,
    WELCOME_CTA_DELAY_SECONDS,
)
from bot.utils import atomic_json_write, data_path, load_summaries

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

FUNNEL_FILE = data_path(os.getenv("FUNNEL_FILE", "data/funnel.json"))
DRIP_FILE = data_path(os.getenv("WELCOME_DRIP_FILE", "data/welcome_drip.json"))
INVITES_FILE = data_path(os.getenv("INVITES_FILE", "data/invites.json"))
SETTLEMENT_FILE = data_path(os.getenv("INVITE_SETTLEMENT_FILE", "data/invite_settlement.json"))

_PLACEHOLDER_HOSTS = ("your-product-url.com", "your-trial-url.com")

# Buying / trial / pricing intent (not live-trade "有没有信号").
_PURCHASE_INTENT_PATTERN = re.compile(
    r"("
    r"怎么订|怎麼訂|如何订|如何訂|怎么买|怎麼買|如何买|如何買|"
    r"多少钱|多少錢|什么价格|什麼價格|怎么收费|怎麼收費|年费|年費|月费|月費|"
    r"开通|開通|订阅|訂閱|试用|試用|vip|会员|會員|"
    r"信号怎么买|信號怎麼買|怎么加入vip|怎麼加入vip|"
    r"subscribe|subscription|pricing|how much|free trial|sign up"
    r")",
    re.IGNORECASE,
)


def is_valid_cta_url(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    lower = url.lower()
    return not any(host in lower for host in _PLACEHOLDER_HOSTS)


def is_purchase_intent(text: str) -> list[str]:
    """Return matched intent phrases, or empty list if not a purchase question."""
    if not text:
        return []
    matches = [m.group(0) for m in _PURCHASE_INTENT_PATTERN.finditer(text)]
    # Dedupe while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for m in matches:
        key = m.lower()
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out


# ── Funnel stats ───────────────────────────────────────────────────────────


def _empty_funnel() -> dict:
    return {
        "joins": 0,
        "welcome_dm_ok": 0,
        "welcome_dm_blocked": 0,
        "signal_cmd": 0,
        "intent_hits": 0,
        "cta_posts": 0,
        "invite_joins": 0,
        "daily": {},
    }


def _load_funnel() -> dict:
    try:
        with open(FUNNEL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            base = _empty_funnel()
            base.update(data)
            base.setdefault("daily", {})
            return base
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return _empty_funnel()


def _save_funnel(data: dict) -> None:
    atomic_json_write(FUNNEL_FILE, data, ensure_ascii=False, indent=2)


def record_funnel(metric: str, amount: int = 1) -> None:
    """Increment a funnel counter (lifetime + today's ET bucket)."""
    if metric not in _empty_funnel() or metric == "daily":
        logger.warning("Unknown funnel metric: %s", metric)
        return
    data = _load_funnel()
    data[metric] = int(data.get(metric, 0)) + amount
    day = datetime.now(_ET).strftime("%Y-%m-%d")
    daily = data.setdefault("daily", {})
    bucket = daily.setdefault(day, {})
    bucket[metric] = int(bucket.get(metric, 0)) + amount
    # Keep ~90 days of daily buckets
    if len(daily) > 90:
        for old in sorted(daily.keys())[:-90]:
            daily.pop(old, None)
    _save_funnel(data)


def funnel_snapshot(days: int = 7) -> dict:
    data = _load_funnel()
    today = datetime.now(_ET).date()
    window: dict[str, int] = {k: 0 for k in _empty_funnel() if k != "daily"}
    for i in range(max(1, days)):
        key = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        bucket = data.get("daily", {}).get(key, {})
        for metric in window:
            window[metric] += int(bucket.get(metric, 0))
    return {"lifetime": {k: data.get(k, 0) for k in window}, "window": window, "days": days}


# ── CTA view ───────────────────────────────────────────────────────────────


def build_cta_view() -> discord.ui.View | None:
    """Link buttons for product / trial plus a FAQ button. None if nothing to show."""
    view = AcquisitionCtaView()
    return view if len(view.children) > 0 else None


class AcquisitionCtaView(discord.ui.View):
    """Persistent CTA row used on YouTube summaries, intent replies, and drip DMs."""

    def __init__(self) -> None:
        super().__init__(timeout=None)
        if is_valid_cta_url(SIGNAL_PRODUCT_URL):
            self.add_item(discord.ui.Button(
                label=f"了解 {SIGNAL_PRODUCT_NAME}",
                style=discord.ButtonStyle.link,
                url=SIGNAL_PRODUCT_URL,
            ))
        if FREE_TRIAL_ENABLED and is_valid_cta_url(FREE_TRIAL_URL):
            self.add_item(discord.ui.Button(
                label="申请试用",
                style=discord.ButtonStyle.link,
                url=FREE_TRIAL_URL,
            ))

    @discord.ui.button(
        label="查看 FAQ",
        style=discord.ButtonStyle.secondary,
        custom_id="acq:faq",
    )
    async def faq_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from bot.faq import get_cached_faq

        items = get_cached_faq()
        if not items:
            await interaction.response.send_message(
                "暂无 FAQ。也可以在频道使用 `/faq` 或 `/ask` 提问。",
                ephemeral=True,
            )
            return
        embed = discord.Embed(title="📋 常见问题 FAQ", color=discord.Color.teal())
        for i, item in enumerate(items[:8], 1):
            embed.add_field(name=f"{i}. {item.get('q', '')}", value=str(item.get("a", ""))[:1024], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


def rest_cta_components() -> list[dict]:
    """Discord REST component rows for scripts that post without discord.py Views."""
    links: list[dict] = []
    if is_valid_cta_url(SIGNAL_PRODUCT_URL):
        links.append({
            "type": 2,
            "style": 5,
            "label": f"了解 {SIGNAL_PRODUCT_NAME}"[:80],
            "url": SIGNAL_PRODUCT_URL,
        })
    if FREE_TRIAL_ENABLED and is_valid_cta_url(FREE_TRIAL_URL):
        links.append({
            "type": 2,
            "style": 5,
            "label": "申请试用",
            "url": FREE_TRIAL_URL,
        })
    if not links:
        return []
    return [{"type": 1, "components": links[:5]}]


# ── Welcome drip jobs ──────────────────────────────────────────────────────


def _load_drip() -> list[dict]:
    try:
        with open(DRIP_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _save_drip(jobs: list[dict]) -> None:
    atomic_json_write(DRIP_FILE, jobs, ensure_ascii=False, indent=2)


def schedule_welcome_drip(user_id: int, guild_id: int) -> list[dict]:
    """Enqueue the onboarding drip relative to now.

    Two steps: day-1 free trial signal, day-3 paid CTA.
    (Legacy "value"/"reminder" steps from older versions are still handled
    by send_drip_job for jobs already persisted.)
    """
    now = datetime.now(timezone.utc)
    steps = [
        ("trial_signal", ONBOARD_DAY1_DELAY_SECONDS),
        ("cta", ONBOARD_DAY3_DELAY_SECONDS),
    ]
    jobs = _load_drip()
    created: list[dict] = []
    for step, delay in steps:
        if delay <= 0:
            continue
        job = {
            "id": f"drip_{uuid.uuid4().hex[:8]}",
            "user_id": user_id,
            "guild_id": guild_id,
            "step": step,
            "due_at": (now + timedelta(seconds=delay)).isoformat(),
            "sent": False,
        }
        jobs.append(job)
        created.append(job)
    _save_drip(jobs)
    logger.info("Scheduled %d welcome-drip job(s) for user %s", len(created), user_id)
    return created


def due_drip_jobs(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    due: list[dict] = []
    for job in _load_drip():
        if job.get("sent") or job.get("cancelled"):
            continue
        try:
            due_at = datetime.fromisoformat(job["due_at"])
        except (KeyError, ValueError):
            continue
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=timezone.utc)
        if due_at <= now:
            due.append(job)
    return due


def mark_drip_sent(job_id: str) -> None:
    jobs = _load_drip()
    for job in jobs:
        if job.get("id") == job_id:
            job["sent"] = True
            break
    _save_drip(jobs)


def cancel_drip_for_user(user_id: int) -> int:
    jobs = _load_drip()
    n = 0
    for job in jobs:
        if job.get("user_id") == user_id and not job.get("sent"):
            job["cancelled"] = True
            n += 1
    if n:
        _save_drip(jobs)
    return n


def _member_is_vip(member: discord.Member) -> bool:
    if not VIP_ROLE_IDS:
        return False
    return any(role.id in VIP_ROLE_IDS for role in member.roles)


def latest_value_content() -> tuple[str, str]:
    """Return (title, description) from the newest stored daily/youtube summary."""
    items = load_summaries(limit=20)
    for item in items:
        content = (item.get("content") or "").strip()
        if content:
            title = item.get("title") or "社群最新内容"
            return title, content[:1800]
    return (
        "📚 快速入门",
        "欢迎先用 `/faq` 看常见问题，或用 `/ask` 向 AI 助手提问。\n"
        f"想了解 {SIGNAL_PRODUCT_NAME} 可使用 `/signal`。",
    )


async def send_drip_job(bot: discord.Client, job: dict) -> bool:
    """Send one drip DM. Returns True if sent or skipped as complete."""
    user = bot.get_user(int(job["user_id"]))
    if user is None:
        try:
            user = await bot.fetch_user(int(job["user_id"]))
        except Exception:
            return False

    guild = bot.get_guild(int(job["guild_id"]))
    member = guild.get_member(user.id) if guild else None
    if member and _member_is_vip(member):
        cancel_drip_for_user(user.id)
        return True

    step = job.get("step")
    view = build_cta_view()
    try:
        if step == "trial_signal":
            title, body = latest_value_content()
            embed = discord.Embed(
                title=f"🎁 免费体验信号：{title}",
                description=body,
                color=discord.Color.green(),
            )
            embed.set_footer(text="这是新人专属的免费体验信号 · 完整实时信号请看会员频道")
            await user.send(embed=embed, view=view)
        elif step == "value":
            title, body = latest_value_content()
            embed = discord.Embed(title=title, description=body, color=discord.Color.blue())
            embed.set_footer(text="有问题随时在频道用 /ask 提问")
            await user.send(embed=embed, view=view)
        elif step == "cta":
            from bot.promo_config import get_signal_product_embed
            from bot.testimonials import get_approved_testimonials

            embed = get_signal_product_embed()
            quotes = get_approved_testimonials(limit=2)
            if quotes:
                lines = [f"“{t.get('content', '')[:180]}” — {t.get('author_name', '')}" for t in quotes]
                embed.add_field(name="🌟 用户反馈", value="\n".join(lines)[:1024], inline=False)
            await user.send(embed=embed, view=view)
        elif step == "reminder":
            embed = discord.Embed(
                title=f"还在了解 {SIGNAL_PRODUCT_NAME} 吗？",
                description=(
                    "上次给你发过产品介绍。如果已经在看信号或暂时不需要，忽略这条即可。\n\n"
                    "想试用或订阅，点下面按钮，或在频道输入 `/signal`。"
                ),
                color=discord.Color.gold(),
            )
            await user.send(embed=embed, view=view)
        else:
            return True
        logger.info("Welcome drip step=%s sent to %s", step, user.id)
        return True
    except discord.Forbidden:
        logger.info("Welcome drip: cannot DM user %s", user.id)
        cancel_drip_for_user(user.id)
        return True
    except Exception as exc:
        logger.warning("Welcome drip step=%s failed for %s: %s", step, user.id, exc)
        return False


# ── Owner notify + lead role ───────────────────────────────────────────────


async def notify_owner_intent(bot: discord.Client, message: discord.Message, phrases: list[str]) -> None:
    if not INTENT_NOTIFY_OWNER or not OWNER_USER_ID:
        return
    owner = bot.get_user(OWNER_USER_ID)
    if owner is None:
        try:
            owner = await bot.fetch_user(OWNER_USER_ID)
        except Exception:
            return
    jump = getattr(message, "jump_url", "")
    text = (
        f"🛒 **购买意向** from {message.author} (`{message.author.id}`)\n"
        f"匹配: {', '.join(phrases[:8])}\n"
        f"{message.content[:300]}\n"
        f"{jump}"
    )
    try:
        await owner.send(text[:1900])
    except Exception as exc:
        logger.warning("Failed to DM owner about purchase intent: %s", exc)


async def assign_lead_role(member: discord.Member | discord.User) -> None:
    if not INTENT_LEAD_ROLE_ID or not isinstance(member, discord.Member):
        return
    role = member.guild.get_role(INTENT_LEAD_ROLE_ID)
    if role is None or role in member.roles:
        return
    try:
        await member.add_roles(role, reason="Purchase-intent lead")
        logger.info("Assigned lead role to %s", member.id)
    except Exception as exc:
        logger.warning("Failed to assign lead role to %s: %s", member.id, exc)


# ── Invite tracking ────────────────────────────────────────────────────────


def _load_invites() -> dict:
    try:
        with open(INVITES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("codes", {})
            data.setdefault("counts", {})
            data.setdefault("attributions", [])
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {"codes": {}, "counts": {}, "attributions": []}


def _save_invites(data: dict) -> None:
    atomic_json_write(INVITES_FILE, data, ensure_ascii=False, indent=2)


def snapshot_invite_codes(invites: list[discord.Invite]) -> dict[str, dict]:
    codes: dict[str, dict] = {}
    for inv in invites:
        inviter_id = inv.inviter.id if inv.inviter else 0
        codes[inv.code] = {
            "uses": int(inv.uses or 0),
            "inviter_id": inviter_id,
            "guild_id": inv.guild.id if inv.guild else 0,
        }
    return codes


def diff_invite_attribution(
    previous: dict[str, dict],
    current: dict[str, dict],
) -> tuple[str, int] | None:
    """Return (code, inviter_id) for the invite whose uses increased, if unique."""
    hits: list[tuple[str, int]] = []
    for code, cur in current.items():
        prev_uses = int((previous.get(code) or {}).get("uses", 0))
        if int(cur.get("uses", 0)) > prev_uses:
            hits.append((code, int(cur.get("inviter_id") or 0)))
    if len(hits) == 1:
        return hits[0]
    return None


def record_invite_join(code: str, inviter_id: int, joiner_id: int, guild_id: int) -> int:
    """Record attribution. Returns the inviter's new total count."""
    data = _load_invites()
    data["attributions"].append({
        "code": code,
        "inviter_id": inviter_id,
        "joiner_id": joiner_id,
        "guild_id": guild_id,
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    data["attributions"] = data["attributions"][-500:]
    key = str(inviter_id)
    data["counts"][key] = int(data["counts"].get(key, 0)) + 1
    _save_invites(data)
    record_funnel("invite_joins")
    return data["counts"][key]


def invite_count_for(user_id: int) -> int:
    data = _load_invites()
    return int(data.get("counts", {}).get(str(user_id), 0))


def save_invite_code_snapshot(codes: dict[str, dict]) -> None:
    data = _load_invites()
    data["codes"] = codes
    _save_invites(data)


def load_invite_code_snapshot() -> dict[str, dict]:
    return _load_invites().get("codes", {})


def should_grant_invite_reward(count: int) -> bool:
    return INVITE_REWARD_THRESHOLD > 0 and count >= INVITE_REWARD_THRESHOLD and INVITE_REWARD_ROLE_ID > 0


# ── Invite leaderboard + monthly settlement ────────────────────────────────


def monthly_top_inviters(n: int) -> list[tuple[int, int]]:
    """Top inviters over the trailing 30 days.

    Returns [(inviter_id, count)] sorted by count desc, at most max(1, n).
    """
    data = _load_invites()
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    counts: dict[int, int] = {}
    for attr in data.get("attributions", []):
        try:
            ts = datetime.fromisoformat(attr["ts"])
        except (KeyError, ValueError):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts < cutoff:
            continue
        inviter_id = int(attr.get("inviter_id") or 0)
        if not inviter_id:
            continue
        counts[inviter_id] = counts.get(inviter_id, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return ranked[:max(1, n)]


def invite_rank_for(user_id: int) -> tuple[int, int]:
    """(rank, count) for a user in the trailing-30d window; (0, 0) if unranked."""
    ranked = monthly_top_inviters(10_000)
    for i, (uid, count) in enumerate(ranked, 1):
        if uid == user_id:
            return i, count
    return 0, 0


def _load_settlement() -> dict:
    try:
        with open(SETTLEMENT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("settled_months", [])
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {"settled_months": []}


def _save_settlement(data: dict) -> None:
    atomic_json_write(SETTLEMENT_FILE, data, ensure_ascii=False, indent=2)


def is_month_settled(month_key: str) -> bool:
    """month_key like '2026-09'."""
    return month_key in _load_settlement().get("settled_months", [])


def mark_month_settled(month_key: str) -> None:
    data = _load_settlement()
    if month_key not in data["settled_months"]:
        data["settled_months"].append(month_key)
        _save_settlement(data)


# ── Ambassador tiered rewards ──────────────────────────────────────────────
# 推广大使：按累计（核验后）邀请数发放阶梯奖励，每档独立记录上次发放时的
# 邀请数；只有新增了至少一档阈值的人数、且距上次发放同档超过冷却期，才再发。

_AMBASSADOR_ROLE_IDS = {
    "etf": lambda: INVITE_ETF_REWARD_ROLE_ID,    # 懒人etf🌲
    "full": lambda: INVITE_FULL_REWARD_ROLE_ID,  # 懒人🌴
}
_AMBASSADOR_ROLE_NAMES = {"etf": "懒人etf🌲", "full": "懒人🌴"}
_AMBASSADOR_ROLE_LABELS = {"etf": "ETF 版会员", "full": "full 版会员"}


def ambassador_role_id(tier: dict) -> int:
    """Resolve a tier's role key ('etf'/'full') to the Discord role id."""
    resolver = _AMBASSADOR_ROLE_IDS.get(str(tier.get("role")))
    return int(resolver()) if resolver else 0


def ambassador_tier_reason(tier: dict) -> str:
    return f"ambassador_{int(tier['invites'])}"


def ambassador_role_label(tier: dict) -> str:
    """Display label for a tier's reward role, e.g. 'ETF 版会员'."""
    return _AMBASSADOR_ROLE_LABELS.get(str(tier.get("role")), "")


def ambassador_role_name(tier: dict) -> str:
    """Discord role name for a tier's reward role, e.g. '懒人etf🌲'."""
    return _AMBASSADOR_ROLE_NAMES.get(str(tier.get("role")), "")


def _ambassador_tiers() -> list[dict]:
    # Imported lazily so tests can patch bot.config.AMBASSADOR_TIERS and have
    # the change take effect here.
    from bot.config import AMBASSADOR_TIERS, AMBASSADOR_COOLDOWN_DAYS
    return AMBASSADOR_TIERS, AMBASSADOR_COOLDOWN_DAYS


def ambassador_due_tiers(
    user_id: int,
    verified_count: int,
    now: datetime | None = None,
) -> list[dict]:
    """Tiers eligible for a grant right now.

    A tier is due when the *marginal* invite count since that tier's last
    grant reaches the tier threshold, and the per-tier cooldown has elapsed.
    """
    from bot.timed_roles import _parse_ts, last_grant

    tiers, cooldown_days = _ambassador_tiers()
    now = now or datetime.now(timezone.utc)
    due: list[dict] = []
    for tier in tiers:
        role_id = ambassador_role_id(tier)
        if not role_id:
            continue
        reason = ambassador_tier_reason(tier)
        last = last_grant(int(user_id), role_id, reason=reason)
        count_at_last = 0
        if last:
            granted_at = _parse_ts(last.get("granted_at"))
            if granted_at and (now - granted_at).total_seconds() < cooldown_days * 86400:
                continue  # 冷却期内：不重复发
            count_at_last = int((last.get("meta") or {}).get("count_at_grant") or 0)
        if verified_count - count_at_last >= int(tier["invites"]):
            due.append(tier)
    return due


def ambassador_progress(user_id: int, verified_count: int) -> list[dict]:
    """Per-tier progress for /my_invites display.

    Each entry: tier dict fields + role_id, last_granted_at (ISO str or None),
    count_at_last, marginal (verified - count_at_last), due_now (bool).
    """
    from bot.timed_roles import last_grant

    tiers, _ = _ambassador_tiers()
    due = ambassador_due_tiers(int(user_id), verified_count, None)
    due_reasons = {ambassador_tier_reason(t) for t in due}
    out: list[dict] = []
    for tier in tiers:
        role_id = ambassador_role_id(tier)
        last = last_grant(int(user_id), role_id, reason=ambassador_tier_reason(tier))
        count_at_last = int((last.get("meta") or {}).get("count_at_grant") or 0) if last else 0
        marginal = verified_count - count_at_last
        out.append({
            "invites": int(tier["invites"]),
            "days": int(tier["days"]),
            "role": str(tier["role"]),
            "role_id": role_id,
            "role_name": _AMBASSADOR_ROLE_NAMES.get(str(tier["role"]), ""),
            "role_label": _AMBASSADOR_ROLE_LABELS.get(str(tier["role"]), ""),
            "last_granted_at": (last.get("granted_at") or "") if last else "",
            "count_at_last": count_at_last,
            "marginal": marginal,
            "due_now": ambassador_tier_reason(tier) in due_reasons,
        })
    return out


def next_ambassador_tier_gap(user_id: int, verified_count: int) -> tuple[int, int] | None:
    """(threshold, missing) for the nearest tier not yet reached; None if all due/met."""
    tiers, _ = _ambassador_tiers()
    due_thresholds = {int(t["invites"]) for t in ambassador_due_tiers(user_id, verified_count)}
    for tier in sorted(tiers, key=lambda t: int(t["invites"])):
        threshold = int(tier["invites"])
        if threshold in due_thresholds:
            return threshold, 0
        # Marginal progress against this tier's own last-grant baseline.
        from bot.timed_roles import last_grant
        last = last_grant(int(user_id), ambassador_role_id(tier), reason=ambassador_tier_reason(tier))
        count_at_last = int((last.get("meta") or {}).get("count_at_grant") or 0) if last else 0
        if verified_count - count_at_last < threshold:
            return threshold, threshold - (verified_count - count_at_last)
    return None


async def verified_invite_count(guild: discord.Guild, inviter_id: int) -> int:
    """防刷：只统计受邀人**仍在服务器内**的邀请数。

    invites.json 的 counts 累计了所有 join 事件（含已退群的）；这里逐个
    核验 joiner 是否仍是成员，已退群的不计入。
    """
    data = _load_invites()
    n = 0
    for attr in data.get("attributions", []):
        try:
            if int(attr.get("inviter_id") or 0) != int(inviter_id):
                continue
            joiner_id = int(attr.get("joiner_id") or 0)
        except (TypeError, ValueError):
            continue
        if not joiner_id:
            continue
        member = guild.get_member(joiner_id)
        if member is None:
            try:
                member = await guild.fetch_member(joiner_id)
            except Exception:
                member = None
        if member is not None:
            n += 1
    return n
