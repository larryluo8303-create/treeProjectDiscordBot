"""Candidate-strategy backtest for bigTreeSignal2027 v2 design.

Reuses indicator machinery from backtest_spx_bigtree.py, then evaluates several
distinct execution logics (A..F) against SPX (^GSPC) daily bars.

Fill model:
    signal on close of bar i -> fill at open of bar i+1 (same as v1 backtest).
Capital: 1_000_000. Commission 0.01% per fill. Slippage 1 tick (0.01).
Weekly signals fire on the daily bar aligned to the completed weekly bar.

Notes on assumptions (defaults where the spec was ambiguous):
- "Rainbow 2203 fan-down filters (auto-on by default)" is emulated with a
  simplified EMA13/34/55 stack proxy on daily and weekly. The full EMA 3..60
  rainbow needs the same close series, so the shape is identical qualitatively;
  the proxy is used only for the "weekly fan-down blocks daily buys" gate to
  keep the 5-toggle contract honest at daily resolution. This is documented in
  the rationale.
- "Weekly BB upper reversal" = daily bar aligned to the completed weekly bar in
  which the weekly close crossed under upper56, no upper touch in prior 8 weeks,
  and weekly candle is red. Same as v1 sell_w.
- Win rate is computed on partial sells vs weighted-average entry (each SELL
  order counted as one trade; win if exit_px > avg_entry_px).
"""

from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

import backtest_spx_bigtree as base

CAPITAL = 1_000_000.0
COMMISSION = 0.0001
SLIPPAGE = 0.01

END = dt.date(2026, 9, 1)
START_20Y = "2005-01-01"
START_10Y = "2015-09-01"
END_STR = "2026-09-01"


@dataclass
class Trade:
    kind: str
    date: pd.Timestamp
    price: float
    shares: float
    note: str = ""


@dataclass
class Result:
    label: str
    strategy: str
    start: pd.Timestamp
    end: pd.Timestamp
    equity: float
    max_dd: float
    trades: int
    wins: int
    losses: int
    gross_win: float
    gross_loss: float
    bh_return: float
    fills: list[Trade] = field(default_factory=list)

    @property
    def ret(self) -> float:
        return self.equity / CAPITAL - 1.0

    @property
    def win_rate(self) -> float:
        n = self.wins + self.losses
        return self.wins / n if n else float("nan")

    @property
    def pf(self) -> float:
        if self.gross_loss == 0:
            return float("inf") if self.gross_win > 0 else float("nan")
        return self.gross_win / self.gross_loss


def add_extra(df: pd.DataFrame) -> pd.DataFrame:
    """Add columns the candidate logics need beyond base.add_indicators."""
    c, h, l, o = df["Close"], df["High"], df["Low"], df["Open"]

    df["d_basis_rising"] = (df["basis56"].shift(1) >= df["basis56"].shift(2)).fillna(False)
    df["d_basis_rising_now"] = (df["basis56"] >= df["basis56"].shift(1)).fillna(False)

    weekly = df.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    wc = weekly["Close"]
    w_basis = wc.rolling(56).mean()
    w_dev = wc.rolling(56).std(ddof=0) * 2.0
    w_upper = (w_basis + w_dev).reindex(df.index, method="ffill")
    df["w_upper_now"] = w_upper

    lower = df["lower56"]
    df["dip1"] = ((c >= lower) & (l <= lower) & df["ma200trend"].fillna(False) & (c - o >= 0)).fillna(False)
    df["dip1_fresh"] = (
        df["dip1"]
        & ~df["dip1"].shift(1, fill_value=False)
        & ~df["dip1"].shift(2, fill_value=False)
        & ~df["dip1"].shift(3, fill_value=False)
        & ~df["dip1"].shift(4, fill_value=False)
    )
    bblcross = ((l < lower) & (l.shift(1) >= lower.shift(1))) & df["ma200trend"].fillna(False)
    df["dip"] = (bblcross & (c - o >= 0)).fillna(False)
    df["bblunder"] = ((l.shift(1) <= lower.shift(1)) & (c.shift(1) - o.shift(1) < 0) & (c - o >= 0)).fillna(False)

    df["dip1_L"] = ((c >= lower) & (l <= lower) & (c - o >= 0)).fillna(False)
    df["dip1_fresh_L"] = (
        df["dip1_L"]
        & ~df["dip1_L"].shift(1, fill_value=False)
        & ~df["dip1_L"].shift(2, fill_value=False)
        & ~df["dip1_L"].shift(3, fill_value=False)
        & ~df["dip1_L"].shift(4, fill_value=False)
    )
    bblcross_L = (l < lower) & (l.shift(1) >= lower.shift(1))
    df["dip_L"] = (bblcross_L & (c - o >= 0)).fillna(False)

    df["e13"] = base.ema(c, 13)
    df["e34"] = df["ema34"]
    df["e55"] = df["ema55"]
    stacked_down_d = (df["e13"].shift(1) < df["e34"].shift(1)) & (df["e34"].shift(1) < df["e55"].shift(1))
    falling_d = (df["e13"].shift(1) < df["e13"].shift(2)) & (df["e34"].shift(1) < df["e34"].shift(2)) & (df["e55"].shift(1) < df["e55"].shift(2))
    df["rainbow_down_d"] = (stacked_down_d & falling_d).fillna(False)
    stacked_up_d = (df["e13"].shift(1) > df["e34"].shift(1)) & (df["e34"].shift(1) > df["e55"].shift(1))
    rising_d_all = (df["e13"].shift(1) > df["e13"].shift(2)) & (df["e34"].shift(1) > df["e34"].shift(2)) & (df["e55"].shift(1) > df["e55"].shift(2))
    df["rainbow_up_d"] = (stacked_up_d & rising_d_all).fillna(False)

    e13w = base.ema(weekly["Close"], 13)
    e34w = base.ema(weekly["Close"], 34)
    e55w = base.ema(weekly["Close"], 55)
    w_stack = (e13w.shift(1) < e34w.shift(1)) & (e34w.shift(1) < e55w.shift(1))
    w_fall = (e13w.shift(1) < e13w.shift(2)) & (e34w.shift(1) < e34w.shift(2)) & (e55w.shift(1) < e55w.shift(2))
    w_rainbow_down = (w_stack & w_fall).reindex(df.index, method="ffill").fillna(False)
    df["rainbow_down_w"] = w_rainbow_down

    basis = df["basis56"].replace(0, np.nan)
    df["bb_width_pct"] = ((df["upper56"] - df["lower56"]) / basis * 100.0).fillna(0.0)

    return df


@dataclass
class Config:
    name: str
    daily_buy: float = 0.0
    weekly_buy: float = 0.0
    dip_buy: float = 0.0
    daily_sell_pct: float = 0.0
    weekly_sell_shares_frac: float = 0.0
    weekly_sell_pct_acct: float = 0.0
    weekly_basis_flip_sell_pct: float = 0.0
    core_lot_frac: float = 0.0
    require_weekly_up: bool = False
    require_daily_up: bool = False
    rainbow_block_daily: bool = True
    # If True, dip_buy still fires even when weekly rainbow is fanning down.
    # Standalone daily_buy still blocked.
    dip_bypass_rainbow: bool = False
    # If True, use loose ma200 gate (ma200 >= ma200[3]) for dip signals
    # instead of strict rising-6-bars.
    loose_ma200_dip: bool = False
    # Minimum % price gap from last entry close before a new buy is accepted.
    # 0 disables. Reset to nan when position becomes flat.
    min_entry_gap_pct: float = 0.0
    # 'both' = |px - last| >= gap; 'lower' = last - px >= gap (only add lower).
    gap_direction: str = "both"
    # If True: daily rainbow fan up halves daily_sell_pct, fan down doubles it
    # (capped at 100% of equity). Weekly sells unaffected.
    sell_mult_rainbow: bool = False
    # If True: lev_down signal on days with rainbow_down_d triggers a daily-tier
    # sell (sellMult also applied). Python daily-only proxy — no 1h/4h tiers.
    lev_sells_on_daily_rainbow_down: bool = False
    # Halve buy size when BB56 width % <= bb_narrow_width_pct.
    halve_buy_on_narrow_bb: bool = False
    bb_narrow_width_pct: float = 4.0
    # extra buys that fire on _any_ dip signal category (dip1_fresh/dip/bblunder)
    # Extra weekly triggers: also treat any daily fresh BB lower reclaim while
    # weekly basis is rising as a weekly-magnitude buy (used by candidate G').


def run(df: pd.DataFrame, cfg: Config, start: str, end: str, label: str) -> Result:
    mask = (df.index >= start) & (df.index <= end)
    d = df.loc[mask].copy()
    if d.empty:
        raise ValueError(f"No rows in window {start}..{end}")

    cash = CAPITAL
    shares = 0.0
    core_shares = 0.0
    last_entry_price = float("nan")
    w_touch = False
    core_armed = False

    pending_buys: list[tuple[float, str]] = []
    pending_core_buy = 0.0
    pending_sell_frac_equity = 0.0
    pending_sell_frac_shares = 0.0
    pending_flatten = False

    fills: list[Trade] = []
    peak = CAPITAL
    max_dd = 0.0

    avg_entry_px = np.nan
    wins = losses = 0
    gw = gl = 0.0

    def equity(px: float) -> float:
        return cash + shares * px

    def do_buy(date, px, pct, tag):
        nonlocal cash, shares, avg_entry_px, last_entry_price
        px = px + SLIPPAGE
        eq = equity(px)
        if eq <= 0 or px <= 0:
            return
        if cfg.min_entry_gap_pct > 0 and last_entry_price == last_entry_price and last_entry_price > 0:
            if cfg.gap_direction == "lower":
                gap_pct = (last_entry_price - px) / last_entry_price * 100.0
            else:
                gap_pct = abs(px - last_entry_price) / last_entry_price * 100.0
            if gap_pct < cfg.min_entry_gap_pct:
                return
        pos_pct = shares * px / eq
        room = max(0.0, 1.0 - pos_pct)
        use = min(pct, room)
        if use < 0.002:
            return
        notional = eq * use
        spend = min(notional, cash / (1 + COMMISSION))
        if spend <= 0:
            return
        qty = spend / px
        cash -= spend * (1 + COMMISSION)
        if shares <= 0:
            avg_entry_px = px
        else:
            avg_entry_px = (avg_entry_px * shares + px * qty) / (shares + qty)
        shares += qty
        last_entry_price = px
        fills.append(Trade("BUY", date, px, qty, f"{use*100:.1f}% {tag}"))

    def do_sell_qty(date, px, qty, tag):
        nonlocal cash, shares, avg_entry_px, wins, losses, gw, gl, last_entry_price
        px = px - SLIPPAGE
        qty = min(qty, shares)
        if qty <= 0 or px <= 0:
            return
        proceeds = qty * px * (1 - COMMISSION)
        cash += proceeds
        if avg_entry_px == avg_entry_px:
            pnl = (px - avg_entry_px) * qty
            if px > avg_entry_px:
                wins += 1
                gw += abs(pnl)
            else:
                losses += 1
                gl += abs(pnl)
        shares -= qty
        fills.append(Trade("SELL", date, px, qty, tag))
        if shares <= 1e-8:
            shares = 0.0
            avg_entry_px = np.nan
            last_entry_price = float("nan")

    idx = d.index
    for i in range(len(d)):
        row = d.iloc[i]
        date = idx[i]
        o = float(row["Open"])
        h = float(row["High"])
        l = float(row["Low"])
        c = float(row["Close"])

        if pending_flatten and shares > 0:
            do_sell_qty(date, o, shares, "W-flip-all")
            pending_flatten = False
            pending_sell_frac_equity = 0.0
            pending_sell_frac_shares = 0.0
            pending_buys = []

        if pending_sell_frac_shares > 0 and shares > 0:
            qty = shares * pending_sell_frac_shares
            do_sell_qty(date, o, qty, f"W-{pending_sell_frac_shares*100:.0f}%")
            pending_sell_frac_shares = 0.0

        if pending_sell_frac_equity > 0 and shares > 0:
            eq = equity(o)
            target_notional = pending_sell_frac_equity * eq
            qty = min(shares, target_notional / max(o + SLIPPAGE, 1e-9))
            do_sell_qty(date, o, qty, f"D-{pending_sell_frac_equity*100:.0f}%")
            pending_sell_frac_equity = 0.0

        for pct, tag in pending_buys:
            do_buy(date, o, pct, tag)
        pending_buys = []

        if pending_core_buy > 0:
            before = shares
            do_buy(date, o, pending_core_buy, "CORE")
            core_shares += shares - before
            pending_core_buy = 0.0

        w_lo = row["w_lower_now"]
        if w_lo == w_lo and l <= float(w_lo):
            w_touch = True
        u56 = row["upper56"]
        if u56 == u56 and h >= float(u56):
            w_touch = False

        buy_d = bool(row["buy"])
        buy_w = bool(row["buy_w"])
        sell_d = bool(row["sell"])
        sell_w = bool(row["sell_w"])
        w_rising_v = row["w_rising"]
        w_rising = bool(w_rising_v) if w_rising_v == w_rising_v else False
        d_rising = bool(row["d_basis_rising"])
        rainbow_w = bool(row["rainbow_down_w"])
        if cfg.loose_ma200_dip:
            dip1 = bool(row["dip1_fresh_L"]) or bool(row["dip_L"]) or bool(row["bblunder"])
        else:
            dip1 = bool(row["dip1_fresh"]) or bool(row["dip"]) or bool(row["bblunder"])

        if cfg.weekly_basis_flip_sell_pct > 0 and shares > 0 and not w_rising:
            pending_flatten = True
        elif shares > 0 and sell_w and not w_touch:
            if cfg.weekly_sell_pct_acct > 0:
                pending_sell_frac_equity = max(pending_sell_frac_equity, cfg.weekly_sell_pct_acct)
            elif cfg.weekly_sell_shares_frac > 0:
                pending_sell_frac_shares = max(pending_sell_frac_shares, cfg.weekly_sell_shares_frac)
        elif shares > 0 and sell_d and cfg.daily_sell_pct > 0:
            mult = 1.0
            if cfg.sell_mult_rainbow:
                if bool(row["rainbow_down_d"]):
                    mult = 2.0
                elif bool(row["rainbow_up_d"]):
                    mult = 0.5
            pending_sell_frac_equity = max(pending_sell_frac_equity, min(1.0, cfg.daily_sell_pct * mult))

        if cfg.lev_sells_on_daily_rainbow_down and shares > 0 and bool(row.get("lev_down", False)) and bool(row["rainbow_down_d"]) and cfg.daily_sell_pct > 0:
            mult = 1.0
            if cfg.sell_mult_rainbow:
                if bool(row["rainbow_down_d"]):
                    mult = 2.0
                elif bool(row["rainbow_up_d"]):
                    mult = 0.5
            pending_sell_frac_equity = max(pending_sell_frac_equity, min(1.0, cfg.daily_sell_pct * mult))

        block_daily = cfg.rainbow_block_daily and rainbow_w

        if cfg.require_weekly_up and not w_rising:
            allow_dip = False
        elif cfg.require_daily_up and not d_rising:
            allow_dip = False
        else:
            allow_dip = True

        buy_mult = 1.0
        if cfg.halve_buy_on_narrow_bb and float(row["bb_width_pct"]) <= cfg.bb_narrow_width_pct:
            buy_mult = 0.5

        if cfg.weekly_buy > 0 and buy_w:
            pending_buys.append((cfg.weekly_buy * buy_mult, "W"))
        if cfg.daily_buy > 0 and buy_d and not block_daily and allow_dip:
            pending_buys.append((cfg.daily_buy * buy_mult, "D"))
        if cfg.dip_buy > 0 and dip1 and (cfg.dip_bypass_rainbow or not block_daily) and allow_dip:
            pending_buys.append((cfg.dip_buy * buy_mult, "DIP"))

        if cfg.core_lot_frac > 0 and not core_armed and w_rising:
            pending_core_buy = cfg.core_lot_frac
            core_armed = True

        eq = equity(c)
        peak = max(peak, eq)
        if peak > 0:
            max_dd = max(max_dd, (peak - eq) / peak)

    if shares > 0:
        do_sell_qty(idx[-1], float(d.iloc[-1]["Close"]), shares, "EOD")

    bh = float(d.iloc[-1]["Close"]) / float(d.iloc[0]["Open"]) - 1.0

    return Result(
        label=label,
        strategy=cfg.name,
        start=idx[0],
        end=idx[-1],
        equity=cash,
        max_dd=max_dd,
        trades=sum(1 for t in fills if t.kind == "BUY"),
        wins=wins,
        losses=losses,
        gross_win=gw,
        gross_loss=gl,
        bh_return=bh,
        fills=fills,
    )


CANDIDATES: list[Config] = [
    Config(
        name="A. Baseline v1 (D50/W100, sell D50/W half)",
        daily_buy=0.50,
        weekly_buy=1.00,
        daily_sell_pct=0.50,
        weekly_sell_shares_frac=0.50,
        rainbow_block_daily=True,
    ),
    Config(
        name="B. Weekly-primary compound (W100, W half sell)",
        daily_buy=0.0,
        weekly_buy=1.00,
        daily_sell_pct=0.0,
        weekly_sell_shares_frac=0.50,
        rainbow_block_daily=False,
    ),
    Config(
        name="C. Daily+weekly hybrid (D50, W100, half both)",
        daily_buy=0.50,
        weekly_buy=1.00,
        daily_sell_pct=0.50,
        weekly_sell_shares_frac=0.50,
        rainbow_block_daily=True,
    ),
    Config(
        name="D. Rainbow trend-follow (need W+D rising)",
        daily_buy=0.50,
        weekly_buy=1.00,
        dip_buy=0.50,
        weekly_basis_flip_sell_pct=1.00,
        require_weekly_up=True,
        require_daily_up=True,
        rainbow_block_daily=True,
    ),
    Config(
        name="E. Aggressive pyramid (25% any dip, W100)",
        daily_buy=0.25,
        dip_buy=0.25,
        weekly_buy=1.00,
        daily_sell_pct=0.25,
        weekly_sell_shares_frac=0.50,
        rainbow_block_daily=True,
    ),
    Config(
        name="F. Two-lot never-flat (core50 + tactical D50)",
        daily_buy=0.50,
        weekly_buy=0.0,
        core_lot_frac=0.50,
        daily_sell_pct=0.50,
        rainbow_block_daily=True,
    ),
    Config(
        name="G. Weekly-only NEVER sell (W100, no sells)",
        weekly_buy=1.00,
        rainbow_block_daily=False,
    ),
    Config(
        name="H. Daily+Weekly NEVER sell (D50, W100)",
        daily_buy=0.50,
        weekly_buy=1.00,
        rainbow_block_daily=True,
    ),
    Config(
        name="I. Aggressive dip pyramid NEVER sell (25% dip, W100)",
        daily_buy=0.25,
        dip_buy=0.25,
        weekly_buy=1.00,
        rainbow_block_daily=True,
    ),
    Config(
        name="J. D+W never sell, no rainbow filter",
        daily_buy=0.50,
        weekly_buy=1.00,
        rainbow_block_daily=False,
    ),
    Config(
        name="K. All dips 25% never sell + W100 (no rainbow)",
        daily_buy=0.25,
        dip_buy=0.25,
        weekly_buy=1.00,
        rainbow_block_daily=False,
    ),
    Config(
        name="L. Weekly-only never sell + sell on W-flip",
        weekly_buy=1.00,
        weekly_basis_flip_sell_pct=1.00,
        rainbow_block_daily=False,
    ),
    Config(
        name="M. D+W never sell + weekly-half on W-sell",
        daily_buy=0.50,
        weekly_buy=1.00,
        weekly_sell_shares_frac=0.50,
        rainbow_block_daily=True,
    ),
    Config(
        name="N. D50+W100 + dips 50, sell only on W-half",
        daily_buy=0.50,
        weekly_buy=1.00,
        dip_buy=0.50,
        weekly_sell_shares_frac=0.50,
        rainbow_block_daily=True,
    ),
    Config(
        name="O. D50+W100 + dips 50, no rainbow, W-half sell",
        daily_buy=0.50,
        weekly_buy=1.00,
        dip_buy=0.50,
        weekly_sell_shares_frac=0.50,
        rainbow_block_daily=False,
    ),
    Config(
        name="P. D50+dip50+W100, NEVER sell (per hard rules)",
        daily_buy=0.50,
        weekly_buy=1.00,
        dip_buy=0.50,
        rainbow_block_daily=True,
    ),
    Config(
        name="Q. P + no rainbow filter",
        daily_buy=0.50,
        weekly_buy=1.00,
        dip_buy=0.50,
        rainbow_block_daily=False,
    ),
    Config(
        name="R. v1 + daily dip50 (D-sell + W-half kept)",
        daily_buy=0.50,
        weekly_buy=1.00,
        dip_buy=0.50,
        daily_sell_pct=0.50,
        weekly_sell_shares_frac=0.50,
        rainbow_block_daily=True,
    ),
    Config(
        name="S. R + dip bypasses weekly-rainbow block",
        daily_buy=0.50,
        weekly_buy=1.00,
        dip_buy=0.50,
        daily_sell_pct=0.50,
        weekly_sell_shares_frac=0.50,
        rainbow_block_daily=True,
        dip_bypass_rainbow=True,
    ),
    Config(
        name="T. R + loose ma200 for dip",
        daily_buy=0.50,
        weekly_buy=1.00,
        dip_buy=0.50,
        daily_sell_pct=0.50,
        weekly_sell_shares_frac=0.50,
        rainbow_block_daily=True,
        loose_ma200_dip=True,
    ),
    Config(
        name="U. R + loose ma200 + dip bypass rainbow",
        daily_buy=0.50,
        weekly_buy=1.00,
        dip_buy=0.50,
        daily_sell_pct=0.50,
        weekly_sell_shares_frac=0.50,
        rainbow_block_daily=True,
        dip_bypass_rainbow=True,
        loose_ma200_dip=True,
    ),
    Config(
        name="V. R + min entry gap 3%",
        daily_buy=0.50,
        weekly_buy=1.00,
        dip_buy=0.50,
        daily_sell_pct=0.50,
        weekly_sell_shares_frac=0.50,
        rainbow_block_daily=True,
        min_entry_gap_pct=3.0,
    ),
    Config(
        name="W. R + min entry gap 5%",
        daily_buy=0.50,
        weekly_buy=1.00,
        dip_buy=0.50,
        daily_sell_pct=0.50,
        weekly_sell_shares_frac=0.50,
        rainbow_block_daily=True,
        min_entry_gap_pct=5.0,
    ),
    Config(
        name="X. U + min entry gap 3%",
        daily_buy=0.50,
        weekly_buy=1.00,
        dip_buy=0.50,
        daily_sell_pct=0.50,
        weekly_sell_shares_frac=0.50,
        rainbow_block_daily=True,
        dip_bypass_rainbow=True,
        loose_ma200_dip=True,
        min_entry_gap_pct=3.0,
    ),
    Config(
        name="Y. R + gap 3% only lower",
        daily_buy=0.50,
        weekly_buy=1.00,
        dip_buy=0.50,
        daily_sell_pct=0.50,
        weekly_sell_shares_frac=0.50,
        rainbow_block_daily=True,
        min_entry_gap_pct=3.0,
        gap_direction="lower",
    ),
    Config(
        name="Z. R + gap 5% only lower",
        daily_buy=0.50,
        weekly_buy=1.00,
        dip_buy=0.50,
        daily_sell_pct=0.50,
        weekly_sell_shares_frac=0.50,
        rainbow_block_daily=True,
        min_entry_gap_pct=5.0,
        gap_direction="lower",
    ),
    Config(
        name="Y2. U + gap 3% only lower",
        daily_buy=0.50,
        weekly_buy=1.00,
        dip_buy=0.50,
        daily_sell_pct=0.50,
        weekly_sell_shares_frac=0.50,
        rainbow_block_daily=True,
        dip_bypass_rainbow=True,
        loose_ma200_dip=True,
        min_entry_gap_pct=3.0,
        gap_direction="lower",
    ),
    Config(
        name="M1. R + sellMult on daily rainbow",
        daily_buy=0.50,
        weekly_buy=1.00,
        dip_buy=0.50,
        daily_sell_pct=0.50,
        weekly_sell_shares_frac=0.50,
        rainbow_block_daily=True,
        sell_mult_rainbow=True,
    ),
    Config(
        name="M2. U + sellMult on daily rainbow",
        daily_buy=0.50,
        weekly_buy=1.00,
        dip_buy=0.50,
        daily_sell_pct=0.50,
        weekly_sell_shares_frac=0.50,
        rainbow_block_daily=True,
        dip_bypass_rainbow=True,
        loose_ma200_dip=True,
        sell_mult_rainbow=True,
    ),
    Config(
        name="M3. M1 + lev-down sell on D-rainbow down",
        daily_buy=0.50,
        weekly_buy=1.00,
        dip_buy=0.50,
        daily_sell_pct=0.50,
        weekly_sell_shares_frac=0.50,
        rainbow_block_daily=True,
        sell_mult_rainbow=True,
        lev_sells_on_daily_rainbow_down=True,
    ),
    Config(
        name="M4. M1 + halve buy on narrow BB (<=4%)",
        daily_buy=0.50,
        weekly_buy=1.00,
        dip_buy=0.50,
        daily_sell_pct=0.50,
        weekly_sell_shares_frac=0.50,
        rainbow_block_daily=True,
        sell_mult_rainbow=True,
        halve_buy_on_narrow_bb=True,
        bb_narrow_width_pct=4.0,
    ),
    Config(
        name="M5. M1 + halve buy on narrow BB (<=6%)",
        daily_buy=0.50,
        weekly_buy=1.00,
        dip_buy=0.50,
        daily_sell_pct=0.50,
        weekly_sell_shares_frac=0.50,
        rainbow_block_daily=True,
        sell_mult_rainbow=True,
        halve_buy_on_narrow_bb=True,
        bb_narrow_width_pct=6.0,
    ),
]


def score(r: Result) -> float:
    if r.bh_return <= 0:
        return float("nan")
    wr = r.win_rate if r.win_rate == r.win_rate else 0.0
    return 0.6 * (r.ret / r.bh_return) + 0.4 * wr


def qualifies(r: Result) -> bool:
    if r.win_rate != r.win_rate:
        return False
    if r.win_rate < 0.65:
        return False
    if r.ret < 0.9 * r.bh_return:
        return False
    return True


def fmt_pct(x: float) -> str:
    if x != x:
        return "n/a"
    return f"{x * 100:.2f}%"


def print_table(rows: list[Result], header: str) -> None:
    print()
    print(header)
    print("-" * 118)
    print(f"{'Strategy':<48} {'WR%':>8} {'Ret%':>11} {'MaxDD%':>9} {'PF':>8} {'#Trd':>6} {'B&H%':>11} {'score':>8}")
    for r in rows:
        pf = r.pf
        pf_str = "inf" if pf == float("inf") else (f"{pf:.2f}" if pf == pf else "n/a")
        print(
            f"{r.strategy:<48} "
            f"{fmt_pct(r.win_rate):>8} "
            f"{fmt_pct(r.ret):>11} "
            f"{fmt_pct(r.max_dd):>9} "
            f"{pf_str:>8} "
            f"{r.trades:>6} "
            f"{fmt_pct(r.bh_return):>11} "
            f"{score(r):>8.3f}"
        )
    if rows:
        bh = rows[0].bh_return
        bh_res = Result(
            label=rows[0].label,
            strategy="bh",
            start=rows[0].start,
            end=rows[0].end,
            equity=CAPITAL * (1 + bh),
            max_dd=0.0,
            trades=1,
            wins=1,
            losses=0,
            gross_win=bh * CAPITAL,
            gross_loss=0.0,
            bh_return=bh,
        )
        print(
            f"{'B&H reference':<48} "
            f"{'100.00%':>8} "
            f"{fmt_pct(bh):>11} "
            f"{'n/a':>9} "
            f"{'n/a':>8} "
            f"{1:>6} "
            f"{fmt_pct(bh):>11} "
            f"{score(bh_res):>8.3f}"
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="comma-separated substrings; only run matching candidates")
    args = ap.parse_args()

    print("Downloading SPX (^GSPC) ...")
    raw = base.load_spx()
    print(f"Bars: {len(raw)}  {raw.index[0].date()} -> {raw.index[-1].date()}")
    df = base.add_indicators(raw.copy())
    df = add_extra(df)

    windows = [
        ("20y", START_20Y, END_STR),
        ("10y", START_10Y, END_STR),
    ]

    cands = CANDIDATES
    if args.only:
        keys = [s.strip().lower() for s in args.only.split(",") if s.strip()]
        cands = [c for c in cands if any(k in c.name.lower() for k in keys)]

    all_rows: dict[str, list[Result]] = {label: [] for label, _, _ in windows}
    for cfg in cands:
        for label, s, e in windows:
            r = run(df, cfg, s, e, label)
            all_rows[label].append(r)

    for label, _, _ in windows:
        print_table(all_rows[label], f"SPX ^GSPC {label} window")

    print()
    print("Winner selection (score = 0.6*ret/bh + 0.4*WR; gate: WR>=65% and ret>=0.9*bh)")
    for label, _, _ in windows:
        eligible = [r for r in all_rows[label] if qualifies(r)]
        eligible.sort(key=score, reverse=True)
        print(f"  [{label}] eligible: {[r.strategy for r in eligible]}")
        if eligible:
            best = eligible[0]
            print(f"  [{label}] winner: {best.strategy}  score={score(best):.3f}  ret={fmt_pct(best.ret)}  WR={fmt_pct(best.win_rate)}")


if __name__ == "__main__":
    main()
