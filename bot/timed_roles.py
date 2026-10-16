"""Timed role grants — invite rewards and 15-day trial access.

Grants are persisted in ``data/timed_roles.json`` so they survive restarts.
A background loop calls :func:`revoke_due_timed_roles` every few minutes to
remove expired roles.

The bot may not have MANAGE_ROLES / MANAGE_GUILD (the owner enables them
later): every privileged Discord call is wrapped in try/except
discord.Forbidden and degrades to a warning log — it never raises.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

import discord

from bot.config import TRIAL_MEMBER_CHANNEL_IDS, TRIAL_ROLE_NAME
from bot.utils import atomic_json_write, data_path

logger = logging.getLogger(__name__)

TIMED_ROLES_FILE = data_path(os.getenv("TIMED_ROLES_FILE", "data/timed_roles.json"))

# Paid cohort roles look like 懒人🌴22 / 懒人etf25🌲 — the name starts with
# 懒人 and contains exactly one contiguous run of digits (the batch number).
# Reward roles (懒人etf🌲 / 懒人🌴) carry no digit, and non-paid groups whose
# names merely contain digits mixed with letters (e.g. 懒人26Q1) must NOT
# match, so the digit run is the only numeric part allowed.
_PAID_COHORT_RE = re.compile(r"^懒人[^\d]*\d+[^\d]*$")

# A failed revoke (usually missing MANAGE_ROLES) is retried at most once a day
# to avoid warning-spam every loop.
_REVOKE_RETRY_SECONDS = 24 * 3600


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: object) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        ts = datetime.fromisoformat(value)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def _load_grants() -> list[dict]:
    try:
        with open(TIMED_ROLES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _save_grants(grants: list[dict]) -> None:
    atomic_json_write(TIMED_ROLES_FILE, grants, ensure_ascii=False, indent=2)


def is_paid_member(member: discord.Member) -> bool:
    """True if the member holds a paid cohort role (name like 懒人🌴22)."""
    roles = getattr(member, "roles", None) or []
    return any(
        _PAID_COHORT_RE.match(getattr(r, "name", "") or "")
        for r in roles
    )


def has_active_grant(user_id: int, role_id: int) -> dict | None:
    """Return the unexpired, non-revoked grant for (user, role), if any."""
    now = _utcnow()
    for g in _load_grants():
        if (
            int(g.get("user_id") or 0) == user_id
            and int(g.get("role_id") or 0) == role_id
            and not g.get("revoked")
            and not g.get("cancelled")
            and not g.get("skipped_paid")
        ):
            exp = _parse_ts(g.get("expires_at"))
            if exp and exp > now:
                return g
    return None


def last_grant(user_id: int, role_id: int, reason: str | None = None) -> dict | None:
    """Most recent grant record for (user, role[, reason]), or None."""
    best: dict | None = None
    best_ts: datetime | None = None
    for g in _load_grants():
        if int(g.get("user_id") or 0) != user_id:
            continue
        if int(g.get("role_id") or 0) != role_id:
            continue
        if reason is not None and g.get("reason") != reason:
            continue
        ts = _parse_ts(g.get("granted_at")) or datetime.min.replace(tzinfo=timezone.utc)
        if best_ts is None or ts > best_ts:
            best, best_ts = g, ts
    return best


async def _resolve_member(
    bot: discord.Client, guild_id: int, user_id: int
) -> tuple[discord.Guild | None, discord.Member | None]:
    guild = bot.get_guild(guild_id)
    if guild is None:
        return None, None
    member = guild.get_member(user_id)
    if member is None:
        try:
            member = await guild.fetch_member(user_id)
        except Exception:
            member = None
    return guild, member


async def grant_timed_role(
    bot: discord.Client,
    user_id: int,
    guild_id: int,
    role_id: int,
    days: int,
    reason: str,
) -> bool:
    """Assign *role_id* to the user and record the grant.

    Returns True when the role was assigned (or already present) and the
    grant was recorded. Returns False — without raising — when the guild,
    member, or role is missing, or when Discord denies the operation
    (typically missing MANAGE_ROLES).
    """
    if not role_id or days <= 0:
        return False
    guild, member = await _resolve_member(bot, guild_id, user_id)
    if guild is None:
        logger.warning("timed_roles: guild %s not found, skip grant", guild_id)
        return False
    if member is None:
        logger.warning("timed_roles: member %s not in guild %s, skip grant", user_id, guild_id)
        return False
    role = guild.get_role(role_id)
    if role is None:
        logger.warning("timed_roles: role %s not found in guild %s", role_id, guild_id)
        return False
    try:
        if role not in member.roles:
            await member.add_roles(role, reason=f"timed grant: {reason} ({days}d)")
            logger.info(
                "timed_roles: granted role %s to user %s for %dd (reason=%s)",
                role_id, user_id, days, reason,
            )
    except discord.Forbidden:
        logger.warning(
            "timed_roles: missing MANAGE_ROLES — cannot grant role %s to user %s",
            role_id, user_id,
        )
        return False
    except Exception as exc:
        logger.warning("timed_roles: grant role %s to %s failed: %s", role_id, user_id, exc)
        return False

    now = _utcnow()
    grants = _load_grants()
    grants.append({
        "user_id": user_id,
        "guild_id": guild_id,
        "role_id": role_id,
        "reason": reason,
        "days": days,
        "granted_at": now.isoformat(),
        "expires_at": (now + timedelta(days=days)).isoformat(),
        "revoked": False,
    })
    _save_grants(grants)
    return True


async def _revoke_one(bot: discord.Client, grant: dict, now: datetime) -> bool:
    """Revoke a single due grant. Mutates *grant*; returns True if closed."""
    guild_id = int(grant.get("guild_id") or 0)
    user_id = int(grant.get("user_id") or 0)
    role_id = int(grant.get("role_id") or 0)

    guild, member = await _resolve_member(bot, guild_id, user_id)
    role = guild.get_role(role_id) if guild else None
    if guild is None or member is None or role is None or role not in member.roles:
        grant["revoked"] = True
        grant["revoked_at"] = now.isoformat()
        grant["revoke_note"] = "guild/member/role gone"
        return True

    # Paid-member protection: if the member still holds a paid cohort role
    # (other than the role being revoked), keep the reward role and stop.
    paid = [
        r for r in (member.roles or [])
        if r.id != role.id and _PAID_COHORT_RE.match(getattr(r, "name", "") or "")
    ]
    if paid:
        grant["skipped_paid"] = True
        grant["skipped_at"] = now.isoformat()
        logger.info(
            "timed_roles: skip revoking role %s from user %s — paid cohort role(s) present: %s",
            role_id, user_id, ",".join(getattr(r, "name", "?") for r in paid),
        )
        return False

    try:
        await member.remove_roles(role, reason=f"timed grant expired: {grant.get('reason')}")
    except discord.Forbidden:
        grant["revoke_failed"] = True
        grant["last_revoke_attempt"] = now.isoformat()
        logger.warning(
            "timed_roles: missing MANAGE_ROLES — cannot revoke role %s from user %s",
            role_id, user_id,
        )
        return False
    except Exception as exc:
        grant["revoke_failed"] = True
        grant["last_revoke_attempt"] = now.isoformat()
        logger.warning("timed_roles: revoke role %s from %s failed: %s", role_id, user_id, exc)
        return False

    grant["revoked"] = True
    grant["revoked_at"] = now.isoformat()
    logger.info(
        "timed_roles: revoked expired role %s from user %s (reason=%s)",
        role_id, user_id, grant.get("reason"),
    )
    return True


async def revoke_due_timed_roles(bot: discord.Client) -> int:
    """Revoke all expired grants. Returns the number of grants closed."""
    now = _utcnow()
    grants = _load_grants()
    closed = 0
    changed = False
    for grant in grants:
        if grant.get("revoked") or grant.get("cancelled") or grant.get("skipped_paid"):
            continue
        exp = _parse_ts(grant.get("expires_at"))
        if not exp or exp > now:
            continue
        if grant.get("revoke_failed"):
            last_attempt = _parse_ts(grant.get("last_revoke_attempt"))
            if last_attempt and (now - last_attempt).total_seconds() < _REVOKE_RETRY_SECONDS:
                continue
        if await _revoke_one(bot, grant, now):
            closed += 1
        changed = True
    if changed:
        _save_grants(grants)
    return closed


def cancel_grants_for_user(user_id: int) -> int:
    """Mark a user's open grants cancelled (e.g. they left the guild)."""
    grants = _load_grants()
    n = 0
    for g in grants:
        if (
            int(g.get("user_id") or 0) == user_id
            and not g.get("revoked")
            and not g.get("cancelled")
        ):
            g["cancelled"] = True
            n += 1
    if n:
        _save_grants(grants)
        logger.info("timed_roles: cancelled %d grant(s) for user %s", n, user_id)
    return n


# ── 15-day trial role ──────────────────────────────────────────────────────


async def ensure_trial_role(guild: discord.Guild) -> discord.Role | None:
    """Get-or-create the trial role. None when creation is not permitted."""
    for role in guild.roles:
        if role.name == TRIAL_ROLE_NAME:
            return role
    try:
        role = await guild.create_role(
            name=TRIAL_ROLE_NAME,
            mentionable=False,
            reason="15-day read-only trial role",
        )
        logger.info("trial: created role %r in guild %s", TRIAL_ROLE_NAME, guild.id)
        return role
    except discord.Forbidden:
        logger.warning(
            "trial: missing MANAGE_ROLES — cannot create trial role %r; trial access disabled",
            TRIAL_ROLE_NAME,
        )
        return None
    except Exception as exc:
        logger.warning("trial: create_role failed: %s", exc)
        return None


async def ensure_trial_overwrites(
    guild: discord.Guild, trial_role: discord.Role | None = None
) -> None:
    """Idempotently grant the trial role read-only access to member channels."""
    role = trial_role or discord.utils.get(guild.roles, name=TRIAL_ROLE_NAME)
    if role is None:
        logger.warning("trial: trial role missing in guild %s, skip channel overwrites", guild.id)
        return
    for channel_id in TRIAL_MEMBER_CHANNEL_IDS:
        channel = guild.get_channel(channel_id)
        if channel is None:
            logger.warning("trial: channel %s not found in guild %s", channel_id, guild.id)
            continue
        current = channel.overwrites_for(role)
        if current.view_channel is True and current.send_messages is False:
            continue  # already as expected
        try:
            await channel.set_permissions(
                role,
                view_channel=True,
                send_messages=False,
                reason="15-day trial read-only access",
            )
            logger.info(
                "trial: set read-only overwrite for role %s in channel %s",
                role.id, channel_id,
            )
        except discord.Forbidden:
            logger.warning(
                "trial: missing MANAGE_ROLES — cannot set overwrites in channel %s",
                channel_id,
            )
        except Exception as exc:
            logger.warning("trial: set_permissions failed in channel %s: %s", channel_id, exc)
