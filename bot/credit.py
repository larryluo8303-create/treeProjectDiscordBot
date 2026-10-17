"""bigTreeSignal credit 台账（纯 ledger 逻辑，不依赖 discord）。

主键：**TradingView 用户名**（大小写不敏感，统一存 NFC+casefold 规范化形式）。
Discord ID 只是可换绑的联系方式，通过 ``discord_index`` 反查；用户换
Discord 账号时 credit 跟着 TV id 走，不丢。
无 TV 的用户退化为 ``discord:<id>`` 主键；后知其 TV 再绑定时，
退化账户的余额/流水自动并入 TV 账户（不丢账）。

存储 ``data/credits.json``::

    {"accounts": {"<tv_lower>": {"tv_username": 原始大小写,
                                 "discord_id": str|None,
                                 "balance": float, "txns": [...]},
                  "discord:<id>": {无 TV 的退化账户, "tv_username": None, ...}},
     "discord_index": {"<discord_id>": "<account_key>"}}

每笔 txn：``{"ts": epoch, "type": "grant"|"use", "amount": float,
"reason": str, "by": "<discord_id>"}``。
金额单位 USD，保留 2 位小数；grant/use 金额必须 > 0。
``use`` 余额不足时抛 :class:`InsufficientCredit`，不扣款。

并发：grant/use/link_tv/relink_discord 全程持有
``data/credits.json.lock`` 进程互斥锁，load→改→save 不可分割，
防 bot 与 import 脚本并发写丢账。

环境变量 ``CREDIT_STATE_FILE`` 可覆盖状态文件路径（测试用）。
"""

from __future__ import annotations

import fcntl
import logging
import os
import time
import unicodedata
from contextlib import contextmanager

from bot.utils import atomic_json_write, data_path

logger = logging.getLogger(__name__)

CREDIT_STATE_FILE = data_path(os.getenv("CREDIT_STATE_FILE", "data/credits.json"))

TV_MAX_LEN = 50


@contextmanager
def _exclusive():
    """进程间互斥锁：保护 load→改→save 整个临界区。

    防 bot 进程与 import 脚本（或两个管理员命令）并发写同一文件导致丢账。
    读操作不加锁——写是原子的（临时文件 + os.replace），读到的要么是旧
    快照要么是新快照，不会读到半写文件。
    """
    lock_path = CREDIT_STATE_FILE + ".lock"
    parent = os.path.dirname(lock_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(lock_path, "a") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


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


def _tv_key(tv_username: str) -> str:
    """TV 用户名 → 主键（NFC 规范化 + strip + casefold）。空值抛 ValueError。

    NFC 防止同一视觉用户名因 Unicode 分解/合成形式不同而生成两个主键；
    casefold 做大小写不敏感匹配（ASCII 用户名下等价于 lower）。
    """
    tv = unicodedata.normalize("NFC", (tv_username or "").strip())
    if not tv:
        raise ValueError("tv_username must not be empty")
    if len(tv) > TV_MAX_LEN:
        raise ValueError(f"tv_username too long (max {TV_MAX_LEN} chars)")
    return tv.casefold()


def _normalize_key(tv_or_key: str | None) -> str:
    """接受 TV 用户名或完整 account key（"discord:<id>"），返回 account key。"""
    s = (tv_or_key or "").strip()
    if not s:
        raise ValueError("tv_username must not be empty")
    if s.startswith("discord:"):
        return s
    return _tv_key(s)


def _load() -> dict:
    import json

    try:
        with open(CREDIT_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, OSError):
        return {"accounts": {}, "discord_index": {}}
    except Exception as exc:
        logger.warning("credit: state file unreadable, starting fresh: %s", exc)
        return {"accounts": {}, "discord_index": {}}
    if not isinstance(data, dict) or not isinstance(data.get("accounts"), dict):
        logger.warning("credit: state file malformed, starting fresh")
        return {"accounts": {}, "discord_index": {}}
    data.setdefault("discord_index", {})
    return data


def _save(data: dict) -> None:
    atomic_json_write(CREDIT_STATE_FILE, data, ensure_ascii=False, indent=2)


def _get_or_create(
    data: dict,
    key: str,
    tv_username: str | None = None,
    discord_id: str | int | None = None,
) -> dict:
    accounts = data["accounts"]
    acc = accounts.get(key)
    if acc is None:
        if key.startswith("discord:"):
            did = key.split(":", 1)[1]
            acc = {
                "tv_username": None,
                "discord_id": did,
                "balance": 0.0,
                "txns": [],
            }
        else:
            acc = {
                "tv_username": (tv_username or key).strip(),
                "discord_id": str(discord_id) if discord_id is not None else None,
                "balance": 0.0,
                "txns": [],
            }
        accounts[key] = acc
    # 兼容旧数据缺字段
    acc.setdefault("tv_username", None)
    acc.setdefault("discord_id", None)
    acc.setdefault("balance", 0.0)
    acc.setdefault("txns", [])
    return acc


def _merge_fallback(data: dict, tv_key: str, did: str) -> None:
    """把 ``discord:<did>`` 退化账户的余额和流水并入 TV 账户，然后删除退化账户。

    场景：import 时 TV 未知，先建了退化账户记账；后来知道了真实 TV，
    绑定时把旧账迁过来，不丢一分钱。
    """
    fb_key = f"discord:{did}"
    fb = data["accounts"].pop(fb_key, None)
    if fb is None:
        return
    tv_acc = data["accounts"][tv_key]
    tv_acc["balance"] = _round2(
        tv_acc.get("balance", 0.0) + fb.get("balance", 0.0)
    )
    merged = tv_acc.get("txns", []) + fb.get("txns", [])
    merged.sort(key=lambda t: t.get("ts", 0))
    tv_acc["txns"] = merged
    logger.info(
        "credit: merged fallback %s ($%.2f, %d txns) into %s",
        fb_key, fb.get("balance", 0.0), len(fb.get("txns", [])), tv_key,
    )


def _bind_discord(data: dict, key: str, discord_id: str | int) -> None:
    """把 discord_id 绑到 key 账户（含换绑）。

    冲突规则：
    - discord 已绑定到**另一个 TV 账户** → 抛 ValueError（避免账乱，
      请人工确认后再用 relink_discord 换绑）；
    - discord 当前绑的是**它自己的退化账户**（``discord:<id>``，无 TV，
      import 时 TV 未知建的）→ 自动把退化账户的余额/流水并入目标 TV
      账户，不抛错、不丢账。
    """
    did = str(discord_id)
    index = data["discord_index"]
    existing = index.get(did)
    if existing is not None and existing != key:
        if existing == f"discord:{did}" and not key.startswith("discord:"):
            _merge_fallback(data, key, did)
        else:
            raise ValueError(f"discord id {did} 已绑定到另一个 TV 账户")
    acc = data["accounts"][key]
    old = acc.get("discord_id")
    if old and old != did and index.get(old) == key:
        del index[old]  # 换绑：清掉旧映射
    acc["discord_id"] = did
    index[did] = key


def _check_amount(amount: float) -> float:
    amount = _round2(amount)
    if amount <= 0:
        raise ValueError(f"amount must be > 0, got {amount}")
    return amount


# ── 查询 ──────────────────────────────────────────────────────────────────

def resolve_by_discord(discord_id: str | int) -> str | None:
    """按 Discord ID 反查 account key（TV 账户返回 tv_lower），未绑定返回 None。"""
    data = _load()
    return data.get("discord_index", {}).get(str(discord_id))


def get_account_info(tv_or_key: str | None) -> dict | None:
    """返回账户摘要 {tv_username, discord_id, balance}，不存在返回 None。"""
    data = _load()
    acc = data["accounts"].get(_normalize_key(tv_or_key))
    if acc is None:
        return None
    return {
        "tv_username": acc.get("tv_username"),
        "discord_id": acc.get("discord_id"),
        "balance": _round2(acc.get("balance", 0.0)),
    }


def get_tv_username(discord_id: str | int) -> str | None:
    """按 Discord ID 查绑定的 TV 用户名（原始大小写），未绑定返回 None。"""
    data = _load()
    key = data.get("discord_index", {}).get(str(discord_id))
    if key is None:
        return None
    acc = data["accounts"].get(key)
    return acc.get("tv_username") if acc else None


def get_balance(tv_or_key: str | None) -> float:
    """返回 TV 账户的 credit 余额（无账户时为 0.0）。"""
    info = get_account_info(tv_or_key)
    return info["balance"] if info else 0.0


def recent_txns(tv_or_key: str | None, n: int = 5) -> list[dict]:
    """返回某 TV 账户最近 n 笔交易（新的在前）。"""
    data = _load()
    acc = data["accounts"].get(_normalize_key(tv_or_key))
    if acc is None:
        return []
    txns = acc.get("txns", [])
    return list(reversed(txns[-n:]))


# ── 记账 ──────────────────────────────────────────────────────────────────

def grant(
    tv_username: str | None,
    amount: float,
    reason: str = "",
    by: str | int = "",
    discord_id: str | int | None = None,
) -> float:
    """按 TV 主键发放 credit，返回发放后的余额。

    tv_username 为空时必须传 discord_id，此时退化为 ``discord:<id>`` 主键
    （兼容无 TV 的用户）。
    """
    amount = _check_amount(amount)
    tv = (tv_username or "").strip()
    if tv:
        key = _tv_key(tv)  # 规范化（NFC+casefold）+ 长度校验，单一路经
    else:
        if discord_id is None:
            raise ValueError("tv_username 为空时必须提供 discord_id")
        key = f"discord:{discord_id}"
        tv = None
    with _exclusive():
        data = _load()
        acc = _get_or_create(data, key, tv_username=tv, discord_id=discord_id)
        if discord_id is not None:
            _bind_discord(data, key, discord_id)
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
                amount, key, by, reason)
    return acc["balance"]


def use(
    tv_username: str | None,
    amount: float,
    reason: str = "",
    by: str | int = "",
) -> float:
    """按 TV 主键抵扣 credit，返回抵扣后的余额。

    余额不足时抛 InsufficientCredit（不扣款）。账户不存在视为余额 0。
    """
    amount = _check_amount(amount)
    key = _normalize_key(tv_username)
    with _exclusive():
        data = _load()
        # 注意：账户不存在时余额视为 0，必然抛 InsufficientCredit，
        # _save 不会执行——不会留下幽灵空账户。
        acc = _get_or_create(data, key)
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
                amount, key, by, reason)
    return acc["balance"]


# ── 绑定 ──────────────────────────────────────────────────────────────────

def link_tv(discord_id: str | int, tv_username: str) -> str:
    """绑定 TradingView 用户名到 Discord ID，返回绑定后的 TV 名（原始大小写）。

    该 discord 已绑定到另一个 TV 账户时抛 ValueError（避免账乱）。

    例外：如果该 discord 当前只有它自己的退化账户（``discord:<id>``，
    import 时 TV 未知建的），自动把退化账户的余额/流水并入新 TV 账户。
    """
    tv = unicodedata.normalize("NFC", (tv_username or "").strip())
    if not tv:
        raise ValueError("tv_username must not be empty")
    key = _tv_key(tv)
    did = str(discord_id)
    with _exclusive():
        data = _load()
        acc = _get_or_create(data, key, tv_username=tv, discord_id=did)
        _bind_discord(data, key, did)  # 冲突抛错；退化账户自动合并
        _save(data)
    logger.info("credit: linked tv=%s for discord %s", tv, did)
    return acc["tv_username"]


def relink_discord(tv_username: str, new_discord_id: str | int) -> str:
    """把 TV 账户换绑到新的 Discord ID。credit 跟着 TV id 走。

    TV 账户不存在时抛 ValueError；新 discord 已绑定别的 TV 时也抛 ValueError。
    新 discord 只有它自己的退化账户时自动合并（见 _bind_discord）。
    返回 TV 名（原始大小写）。
    """
    key = _tv_key(tv_username)
    did = str(new_discord_id)
    with _exclusive():
        data = _load()
        acc = data["accounts"].get(key)
        if acc is None:
            raise ValueError(f"TV 账户不存在: {tv_username}")
        _bind_discord(data, key, did)
        _save(data)
    logger.info("credit: relinked tv=%s to discord %s", key, did)
    return acc["tv_username"]
