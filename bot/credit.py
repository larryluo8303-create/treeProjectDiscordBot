"""bigTreeSignal credit 台账（纯 ledger 逻辑，不依赖 discord）。

- 存储：``data/credits.json``
  ``{"accounts": {"<discord_id>": {"tv_username": str|None, "balance": float, "txns": [...]}}}``
- 每笔 txn：``{"ts": epoch, "type": "grant"|"use", "amount": float, "reason": str, "by": "<discord_id>"}``
- 金额单位 USD，保留 2 位小数；grant/use 金额必须 > 0。
- ``use`` 余额不足时抛 :class:`InsufficientCredit`，不扣款。

环境变量 ``CREDIT_STATE_FILE`` 可覆盖状态文件路径（测试用）。
"""

from __future__ import annotations

import logging
import os
import time

from bot.utils import atomic_json_write, data_path

logger = logging.getLogger(__name__)

CREDIT_STATE_FILE = data_path(os.getenv("CREDIT_STATE_FILE", "data/credits.json"))


class InsufficientCredit(Exception):
    """余额不足：use() 的金额超过当前余额时抛出。"""

    def __init__(self, balance: float, requested: float) -> None:
        self.balance = balance
        self.requested = requested
        super().__init__(
            f"insufficient credit: balance ${balance:.2f}, requested ${requested:.2f}"
        )


def _round2(x: float) -> float:
    return round(float(x) + 0.0, 2)  # +0.0 避免 -0.00


def _load() -> dict:
    import json

    try:
        with open(CREDIT_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, OSError):
        return {"accounts": {}}
    except Exception as exc:
        logger.warning("credit: state file unreadable, starting fresh: %s", exc)
        return {"accounts": {}}
    if not isinstance(data, dict) or not isinstance(data.get("accounts"), dict):
        logger.warning("credit: state file malformed, starting fresh")
        return {"accounts": {}}
    return data


def _save(data: dict) -> None:
    atomic_json_write(CREDIT_STATE_FILE, data, ensure_ascii=False, indent=2)


def _account(data: dict, discord_id: str | int) -> dict:
    uid = str(discord_id)
    accounts = data["accounts"]
    acc = accounts.get(uid)
    if acc is None:
        acc = {"tv_username": None, "balance": 0.0, "txns": []}
        accounts[uid] = acc
    # 兼容旧数据缺字段
    acc.setdefault("tv_username", None)
    acc.setdefault("balance", 0.0)
    acc.setdefault("txns", [])
    return acc


def _check_amount(amount: float) -> float:
    amount = _round2(amount)
    if amount <= 0:
        raise ValueError(f"amount must be > 0, got {amount}")
    return amount


def get_balance(discord_id: str | int) -> float:
    """返回用户的 credit 余额（无账户时为 0.0）。"""
    data = _load()
    acc = data["accounts"].get(str(discord_id))
    if acc is None:
        return 0.0
    return _round2(acc.get("balance", 0.0))


def grant(
    discord_id: str | int,
    amount: float,
    reason: str = "",
    by: str | int = "",
    tv_username: str | None = None,
) -> float:
    """发放 credit，返回发放后的余额。"""
    amount = _check_amount(amount)
    data = _load()
    acc = _account(data, discord_id)
    if tv_username:
        acc["tv_username"] = tv_username.strip()
    acc["balance"] = _round2(acc["balance"] + amount)
    acc["txns"].append(
        {
            "ts": time.time(),
            "type": "grant",
            "amount": amount,
            "reason": reason or "",
            "by": str(by),
        }
    )
    _save(data)
    logger.info("credit: granted $%.2f to %s (by %s, reason=%r)",
                amount, discord_id, by, reason)
    return acc["balance"]


def use(
    discord_id: str | int,
    amount: float,
    reason: str = "",
    by: str | int = "",
) -> float:
    """抵扣 credit，返回抵扣后的余额。余额不足时抛 InsufficientCredit（不扣款）。"""
    amount = _check_amount(amount)
    data = _load()
    acc = _account(data, discord_id)
    balance = _round2(acc["balance"])
    if amount > balance:
        raise InsufficientCredit(balance, amount)
    acc["balance"] = _round2(balance - amount)
    acc["txns"].append(
        {
            "ts": time.time(),
            "type": "use",
            "amount": amount,
            "reason": reason or "",
            "by": str(by),
        }
    )
    _save(data)
    logger.info("credit: used $%.2f from %s (by %s, reason=%r)",
                amount, discord_id, by, reason)
    return acc["balance"]


def link_tv(discord_id: str | int, tv_username: str) -> str:
    """绑定 TradingView 用户名，返回绑定后的值。"""
    tv_username = (tv_username or "").strip()
    if not tv_username:
        raise ValueError("tv_username must not be empty")
    if len(tv_username) > 50:
        raise ValueError("tv_username too long (max 50 chars)")
    data = _load()
    acc = _account(data, discord_id)
    acc["tv_username"] = tv_username
    _save(data)
    logger.info("credit: linked tv=%s for %s", tv_username, discord_id)
    return tv_username


def get_tv_username(discord_id: str | int) -> str | None:
    """返回绑定的 TV 用户名（未绑定时为 None）。"""
    data = _load()
    acc = data["accounts"].get(str(discord_id))
    if acc is None:
        return None
    return acc.get("tv_username")


def recent_txns(discord_id: str | int, n: int = 5) -> list[dict]:
    """返回最近 n 笔交易（新的在前）。"""
    data = _load()
    acc = data["accounts"].get(str(discord_id))
    if acc is None:
        return []
    txns = acc.get("txns", [])
    return list(reversed(txns[-n:]))
