"""Daily-horizon backtest of bigTreeSignal2027 buyCoreD / sell cores on SPX.

Fill: confirmed daily buy -> next session open (not 1h/5m C/D; those histories
are not available on free data for 10-20 years).
Capital: 100_000. Commission 0.01% per fill. Slippage 1 tick (0.01).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import yfinance as yf

CAPITAL = 100_000.0
COMMISSION = 0.0001
SLIPPAGE = 0.01  # 1 tick
BB_LEN = 56
BB_MULT = 2.0
MA200 = 200
LEFT, RIGHT = 5, 3
END = dt.date(2026, 9, 1)


def stdev(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).std(ddof=0)


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rising_n(s: pd.Series, n: int) -> pd.Series:
    ok = pd.Series(True, index=s.index)
    for i in range(n):
        ok = ok & (s.shift(i) >= s.shift(i + 1))
    return ok


def pivot_series(src: pd.Series, left: int, right: int, mode: str) -> pd.Series:
    vals = src.to_numpy(dtype=float)
    n = len(vals)
    out = np.full(n, np.nan)
    for i in range(left + right, n):
        center = i - right
        window = vals[center - left : center + right + 1]
        if not np.isfinite(window).all():
            continue
        c = vals[center]
        if mode == "low" and c == np.nanmin(window):
            out[i] = c
        elif mode == "high" and c == np.nanmax(window):
            out[i] = c
    return pd.Series(out, index=src.index)


def load_spx() -> pd.DataFrame:
    raw = yf.download(
        "^GSPC",
        start="1998-01-01",
        end=str(END + dt.timedelta(days=1)),
        auto_adjust=True,
        progress=False,
    )
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw = raw.rename(columns=str.title)
    df = raw[["Open", "High", "Low", "Close", "Volume"]].dropna().copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df


def add_indicators(df: pd.DataFrame, *, require_bull: bool = True, require_rsi: bool = True, require_htf: bool = True) -> pd.DataFrame:
    c, h, l, o = df["Close"], df["High"], df["Low"], df["Open"]
    basis = sma(c, BB_LEN)
    lower = basis - BB_MULT * stdev(c, BB_LEN)
    upper = basis + BB_MULT * stdev(c, BB_LEN)
    lower14 = sma(c, 14) - 2 * stdev(c, 14)
    upper14 = sma(c, 14) + 2 * stdev(c, 14)

    df["basis56"] = basis
    df["lower56"] = lower
    df["upper56"] = upper
    df["upper14"] = upper14
    df["ma200"] = sma(c, MA200)
    df["ma120"] = sma(c, 120)
    df["ema55"] = ema(c, 55)
    df["ema34"] = ema(c, 34)
    df["rsi"] = rsi(c, 14)
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    df["ma200trend"] = rising_n(df["ma200"], 6)
    df["ema55trend"] = rising_n(df["ema55"], 5)
    df["ma120trend"] = rising_n(df["ma120"], 6)

    weekly = df.resample("W-FRI").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
    ).dropna()
    wc, wh, wl, wo = weekly["Close"], weekly["High"], weekly["Low"], weekly["Open"]
    w_basis = sma(wc, BB_LEN)
    w_dev = BB_MULT * stdev(wc, BB_LEN)
    w_lower = w_basis - w_dev
    w_upper = w_basis + w_dev
    # Completed weekly bar only (Pine security of basis[1] >= basis[2])
    w_rising = (w_basis.shift(1) >= w_basis.shift(2)).rename("w_rising")
    w_lower_closed = w_lower.shift(1).rename("w_lower")
    aligned = pd.concat([w_rising, w_lower_closed], axis=1).reindex(df.index, method="ffill")
    df["w_rising"] = aligned["w_rising"].astype("boolean")
    df["w_lower"] = aligned["w_lower"]
    df["w_lower_now"] = w_lower.reindex(df.index, method="ffill")

    w_bblc = (
        ((wc > w_lower) & (wc.shift(1) <= w_lower.shift(1)))
        | ((wc.shift(1) < w_lower.shift(1)) & (wc >= w_lower))
        | ((wo < w_lower) & (wc >= w_lower))
    ).fillna(False)
    w_bbuc = (
        ((wc < w_upper) & (wc.shift(1) >= w_upper.shift(1)))
        | ((wh > w_upper) & (wc < w_upper))
    ).fillna(False)
    w_no_recent = True
    for k in range(1, 9):
        w_no_recent = w_no_recent & ~w_bbuc.shift(k, fill_value=False)
    w_sell = w_bbuc & w_no_recent & (wc <= wo)
    df["buy_w"] = pd.Series(False, index=df.index)
    df["sell_w"] = pd.Series(False, index=df.index)

    def _stamp(flag: pd.Series, col: str) -> None:
        for ts, val in flag.items():
            if not bool(val):
                continue
            loc = df.index[df.index <= ts]
            if len(loc):
                df.loc[loc[-1], col] = True

    _stamp(w_bblc, "buy_w")
    _stamp(w_sell.fillna(False), "sell_w")

    bblc = (
        ((c > lower) & (c.shift(1) <= lower.shift(1)))
        | ((c.shift(1) < lower.shift(1)) & (c >= lower))
        | ((o < lower) & (c >= lower))
    )
    df["bblc"] = bblc.fillna(False)
    df["bblcFresh"] = df["bblc"] & ~df["bblc"].shift(1, fill_value=False) & ~df["bblc"].shift(2, fill_value=False)
    q_buy = pd.Series(True, index=df.index)
    if require_bull:
        q_buy = q_buy & (c >= o)
    if require_rsi:
        q_buy = q_buy & (df["rsi"] >= df["rsi"].shift(1))
    weekly_reclaim = (l <= df["w_lower"]) & (c >= df["w_lower"]) & (c >= o)
    htf_day = pd.Series(True, index=df.index) if not require_htf else (df["w_rising"].fillna(False) | weekly_reclaim.fillna(False))
    df["buy"] = (df["bblcFresh"] & q_buy & htf_day).fillna(False)

    bbuc = ((c < upper) & (c.shift(1) >= upper.shift(1))) | ((h > upper) & (c < upper))
    df["bbuc"] = bbuc.fillna(False)
    no_recent = True
    for k in range(1, 9):
        no_recent = no_recent & ~df["bbuc"].shift(k, fill_value=False)
    q_sell = (c <= o) if True else pd.Series(True, index=df.index)
    df["sell"] = (df["bbuc"] & no_recent & q_sell).fillna(False)

    bbuc14 = ((c < upper14) & (c.shift(1) >= upper14.shift(1))) | ((o > upper14) & (c - c.shift(1) >= 0))
    df["lev_down"] = (bbuc14.fillna(False) & ~df["bbuc"] & ~df["ema55trend"].fillna(False))

    pvtlo_raw = pivot_series(l, LEFT, RIGHT, "low")
    pvthi_raw = pivot_series(h, LEFT, RIGHT, "high")
    df["pvtlo"] = pvtlo_raw.shift(1)  # WaitForClose
    df["pvthi"] = pvthi_raw.shift(1)
    df["last_swing"] = df["pvtlo"].ffill()
    prev_lo = df["pvtlo"].ffill().shift(1)
    hl_hit = df["pvtlo"].notna() & (df["pvtlo"] > prev_lo)
    df["last_hl"] = df["pvtlo"].where(hl_hit).ffill()

    w_pvtlo = pivot_series(weekly["Low"], LEFT, RIGHT, "low").shift(1)
    df["w_swing"] = w_pvtlo.reindex(df.index, method="ffill")
    w_prev = w_pvtlo.shift(1)
    w_hl_hit = w_pvtlo.notna() & (w_pvtlo > w_prev)
    df["w_hl"] = w_pvtlo.where(w_hl_hit).reindex(df.index, method="ffill")

    osc = df["rsi"]
    ph = pivot_series(osc, 5, 0, "high")
    ph_found = ph.notna()
    bars_since_ph = ph_found[::-1].groupby(ph_found[::-1].cumsum()).cumcount()[::-1]
    # barssince(phFound): 0 on the bar, then 1,2,... until next
    since = []
    acc = np.nan
    for flag in ph_found.tolist():
        if flag:
            acc = 0
        elif acc == acc:
            acc += 1
        since.append(acc)
    df["ph_since"] = since
    ph_price = h.where(ph_found).ffill()
    ph_osc = osc.where(ph_found).ffill()
    # previous ph: shift the ffilled series at confirmation is current; use previous confirmation
    prev_ph_price = h.where(ph_found).replace(0, np.nan)
    prev_ph_price = pd.Series(np.where(ph_found, h, np.nan), index=df.index)
    # valuewhen(ph, high, 1) = previous pivot high's high
    prev_ph_h = pd.Series(np.nan, index=df.index)
    prev_ph_o = pd.Series(np.nan, index=df.index)
    last_h, last_o, prev_h, prev_o = np.nan, np.nan, np.nan, np.nan
    for i, flag in enumerate(ph_found.tolist()):
        if flag:
            prev_h, prev_o = last_h, last_o
            last_h, last_o = h.iloc[i], osc.iloc[i]
        prev_ph_h.iloc[i] = prev_h
        prev_ph_o.iloc[i] = prev_o
    in_range = df["ph_since"].shift(1).between(5, 60)
    price_hh = h > prev_ph_h
    osc_lh = (osc < prev_ph_o) & in_range
    df["raise_slp"] = (price_hh & osc_lh & ph_found & (osc > 30)).fillna(False)
    return df


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


def run(
    df: pd.DataFrame,
    start: str,
    end: str,
    label: str,
    *,
    stop_mode: str = "none",
    use_stop: bool | None = None,
) -> Result:
    if use_stop is True:
        stop_mode = "hl_ll"
    elif use_stop is False:
        stop_mode = "none"
    mask = (df.index >= start) & (df.index <= end)
    d = df.loc[mask].copy()
    cash = CAPITAL
    shares = 0.0
    stop = np.nan
    pos_hh = np.nan
    chand_k = {"chand3": 3.0, "chand5": 5.0}.get(stop_mode, 0.0)
    pending_buy = 0.0
    pending_buy_note = ""
    pending_exit = False
    pending_reduce = 0.0
    pending_flatten = False
    w_touch = False
    fills: list[Trade] = []
    equity_curve = []
    peak = CAPITAL
    max_dd = 0.0
    round_entry_px = np.nan
    round_entry_eq = np.nan
    wins = losses = 0
    gw = gl = 0.0

    def equity(px: float) -> float:
        return cash + shares * px

    def fill_buy(date, px, pct, note=""):
        nonlocal cash, shares, round_entry_px, round_entry_eq
        px = px + SLIPPAGE
        eq = equity(px)
        room = max(0.0, 1.0 - (shares * px) / eq if eq else 0.0)
        use = min(pct, room)
        notional = eq * use
        spend = min(notional, cash / (1 + COMMISSION))
        if spend <= 0 or px <= 0 or use < 0.002:
            return
        qty = spend / px
        cash -= spend * (1 + COMMISSION)
        if shares <= 0:
            round_entry_px = px
            round_entry_eq = eq
        shares += qty
        fills.append(Trade("BUY", date, px, qty, f"{use*100:.1f}% {note}"))

    def fill_sell(date, px, qty, note):
        nonlocal cash, shares, wins, losses, gw, gl, round_entry_px, round_entry_eq, stop, pos_hh
        px = px - SLIPPAGE
        qty = min(qty, shares)
        if qty <= 0:
            return
        proceeds = qty * px * (1 - COMMISSION)
        cash += proceeds
        shares -= qty
        fills.append(Trade("SELL", date, px, qty, note))
        if shares <= 1e-8:
            shares = 0.0
            stop = np.nan
            pos_hh = np.nan
            if round_entry_px == round_entry_px:
                pnl = (px - round_entry_px) * qty
                # approximate round-trip vs entry equity
                if px > round_entry_px:
                    wins += 1
                    gw += abs(pnl)
                else:
                    losses += 1
                    gl += abs(pnl)
            round_entry_px = np.nan

    rows = d.itertuples()
    # Need open of next bar: iterate by position
    idx = d.index
    for i in range(len(d)):
        row = d.iloc[i]
        date = idx[i]
        o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])

        if pending_exit:
            fill_sell(date, o, shares, "SL")
            pending_exit = False
            pending_flatten = False
            pending_reduce = 0.0
        elif pending_flatten and shares > 0:
            fill_sell(date, o, shares, "W-ALL")
            pending_flatten = False
            pending_reduce = 0.0
        elif pending_reduce > 0 and shares > 0:
            eq = equity(o)
            target_notional = pending_reduce * eq
            qty = min(shares, target_notional / max(o, 1e-9))
            fill_sell(date, o, qty, "D-50")
            pending_reduce = 0.0
        if pending_buy > 0:
            was_flat = shares <= 0
            fill_buy(date, o, pending_buy, pending_buy_note)
            pending_buy = 0.0
            pending_buy_note = ""
            fill_px = o + SLIPPAGE
            if shares > 0 and stop_mode == "pct10" and was_flat:
                stop = fill_px * 0.90
            if shares > 0 and chand_k:
                atr = row["atr"]
                pos_hh = fill_px if pos_hh != pos_hh else max(pos_hh, fill_px)
                if atr == atr:
                    cand = pos_hh - chand_k * float(atr)
                    if stop != stop or cand > stop:
                        stop = cand
            if shares > 0 and stop_mode == "trail10" and was_flat:
                stop = fill_px * 0.90

        eq = equity(c)
        peak = max(peak, eq)
        dd = (peak - eq) / peak if peak else 0.0
        max_dd = max(max_dd, dd)
        equity_curve.append(eq)

        def raise_stop(level) -> None:
            nonlocal stop
            if level != level:
                return
            level = float(level)
            if stop != stop or level > stop:
                stop = level

        hit_stop = False
        if shares > 0 and stop_mode != "none":
            if stop_mode == "hl_ll":
                if bool(row["raise_slp"]) or bool(row["lev_down"]):
                    raise_stop(row["last_hl"])
                hit_stop = stop == stop and c < stop
            elif stop_mode == "w_swing":
                raise_stop(row["w_hl"])
                if stop != stop and row["w_swing"] == row["w_swing"]:
                    stop = float(row["w_swing"])
                hit_stop = stop == stop and c < stop
            elif stop_mode == "bb56":
                band = row["lower56"]
                hit_stop = band == band and c < float(band)
            elif stop_mode == "w_bb":
                band = row["w_lower_now"]
                hit_stop = band == band and c < float(band)
            elif stop_mode in ("chand3", "chand5"):
                atr = row["atr"]
                pos_hh = h if pos_hh != pos_hh else max(pos_hh, h)
                if atr == atr:
                    raise_stop(pos_hh - chand_k * float(atr))
                hit_stop = stop == stop and c < stop
            elif stop_mode == "pct10":
                hit_stop = stop == stop and c < stop
            elif stop_mode == "trail10":
                raise_stop(c * 0.90)
                hit_stop = stop == stop and c < stop
            elif stop_mode == "ema34":
                ema34 = row["ema34"]
                hit_stop = ema34 == ema34 and c < float(ema34) and c <= o
            elif stop_mode == "ma200":
                ma = row["ma200"]
                hit_stop = ma == ma and c < float(ma)

        if hit_stop:
            pending_exit = True
            pending_buy = 0.0
            pending_reduce = 0.0
            pending_flatten = False
            continue

        w_lo = row["w_lower_now"]
        if w_lo == w_lo and l <= float(w_lo):
            w_touch = True
        u56 = row["upper56"]
        if u56 == u56 and h >= float(u56):
            w_touch = False

        if shares > 0 and bool(row["sell_w"]) and not w_touch:
            pending_flatten = True
            pending_reduce = 0.0
            pending_buy = 0.0
            pending_buy_note = ""
        elif shares > 0 and bool(row["sell"]):
            pending_reduce = 0.50

        if bool(row["buy_w"]):
            pending_buy = 1.0
            pending_buy_note = "W"
            if stop_mode == "hl_ll" and row["last_swing"] == row["last_swing"]:
                stop = float(row["last_swing"])
            elif stop_mode == "w_swing" and row["w_swing"] == row["w_swing"]:
                stop = float(row["w_swing"])
        elif bool(row["buy"]):
            pending_buy = max(pending_buy, 0.50)
            pending_buy_note = pending_buy_note or "D"
            if stop_mode == "hl_ll" and row["last_swing"] == row["last_swing"]:
                stop = float(row["last_swing"])
            elif stop_mode == "w_swing" and row["w_swing"] == row["w_swing"]:
                if stop != stop:
                    stop = float(row["w_swing"])

    # flatten last bar close
    if shares > 0:
        fill_sell(idx[-1], float(d.iloc[-1]["Close"]), shares, "EOD")

    bh = float(d.iloc[-1]["Close"]) / float(d.iloc[0]["Open"]) - 1.0
    return Result(
        label=label,
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


def fmt_pct(x: float) -> str:
    if x != x:
        return "n/a"
    return f"{x * 100:.1f}%"


def main() -> None:
    print("Downloading SPX (^GSPC) ...")
    raw = load_spx()
    print(f"Bars: {len(raw)}  {raw.index[0].date()} -> {raw.index[-1].date()}")
    df = add_indicators(raw.copy())

    windows = [
        ("10y", "2016-09-01", "2026-09-01"),
        ("20y", "2006-09-01", "2026-09-01"),
    ]
    def print_rows(title: str, items: list[Result]) -> None:
        print()
        print(title)
        print("-" * 100)
        print(f"{'window':<8} {'start':<12} {'end':<12} {'equity':>12} {'return':>9} {'maxDD':>8} {'buys':>6} {'WR':>7} {'PF':>7} {'B&H':>9}  mix")
        for r in items:
            sl = sum(1 for t in r.fills if t.note == "SL")
            d50 = sum(1 for t in r.fills if t.note == "D-50")
            wall = sum(1 for t in r.fills if t.note == "W-ALL")
            db = sum(1 for t in r.fills if t.kind == "BUY" and "W" not in t.note)
            wb = sum(1 for t in r.fills if t.kind == "BUY" and "W" in t.note)
            print(
                f"{r.label:<8} {str(r.start.date()):<12} {str(r.end.date()):<12} "
                f"{r.equity:12,.0f} {fmt_pct(r.ret):>9} {fmt_pct(r.max_dd):>8} "
                f"{r.trades:6d} {fmt_pct(r.win_rate):>7} {r.pf:7.2f} {fmt_pct(r.bh_return):>9}  "
                f"Dbuy={db} Wbuy={wb} D50={d50} Wall={wall} SL={sl}"
            )

    print()
    print("SPX  |  capital 100,000  |  daily buy 50%  weekly buy 100%  |  daily sell 50%  weekly sell all")
    print("Fill next open after signal close. Filters ON. Hard stop variants vs sell-only.")
    modes = [
        ("none", "no hard stop (sell signals only)"),
        ("hl_ll", "daily HL/LL + Raise SLP (current overlay)"),
        ("w_swing", "weekly pivot low, trail weekly HL"),
        ("w_bb", "close back under weekly BB56 lower"),
        ("bb56", "close under daily BB56 lower"),
        ("chand3", "Chandelier: HH - 3 ATR"),
        ("chand5", "Chandelier: HH - 5 ATR"),
        ("pct10", "hard -10% from entry, no trail"),
        ("trail10", "trail 10% off close, ratchet up only"),
        ("ema34", "close < EMA34 and bearish bar (overlay leftover)"),
        ("ma200", "close < MA200"),
    ]
    for mode, desc in modes:
        print_rows(
            f"{mode}  |  {desc}",
            [run(df, a, b, name, stop_mode=mode) for name, a, b in windows],
        )


if __name__ == "__main__":
    main()
