"""Grid-search account% sizes for daily/weekly buy & sell. No hard stop."""

from __future__ import annotations

import sys
from itertools import product
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest_spx_bigtree import CAPITAL, COMMISSION, SLIPPAGE, add_indicators, load_spx

STEPS = (0.0, 0.25, 0.5, 0.75, 1.0)
FINE = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)


def pack(d):
    return dict(
        o=d["Open"].to_numpy(dtype=float),
        h=d["High"].to_numpy(dtype=float),
        l=d["Low"].to_numpy(dtype=float),
        c=d["Close"].to_numpy(dtype=float),
        buy_d=d["buy"].to_numpy(dtype=bool),
        sell_d=d["sell"].to_numpy(dtype=bool),
        buy_w=d["buy_w"].to_numpy(dtype=bool),
        sell_w=d["sell_w"].to_numpy(dtype=bool),
        w_lo=d["w_lower_now"].to_numpy(dtype=float),
        u56=d["upper56"].to_numpy(dtype=float),
        first_open=float(d.iloc[0]["Open"]),
        last_close=float(d.iloc[-1]["Close"]),
    )


def sim(p, db: float, wb: float, ds: float, ws: float) -> tuple[float, float]:
    o, h, l, c = p["o"], p["h"], p["l"], p["c"]
    buy_d, sell_d = p["buy_d"], p["sell_d"]
    buy_w, sell_w = p["buy_w"], p["sell_w"]
    w_lo, u56 = p["w_lo"], p["u56"]
    n = len(o)
    cash = CAPITAL
    shares = 0.0
    pending_buy = 0.0
    pending_sell = 0.0
    w_touch = False
    peak = CAPITAL
    max_dd = 0.0

    for i in range(n):
        if pending_sell > 0.0 and shares > 0.0:
            px = o[i] - SLIPPAGE
            eq = cash + shares * px
            qty = min(shares, pending_sell * eq / px) if px > 0 else 0.0
            if qty > 0.0:
                cash += qty * px * (1.0 - COMMISSION)
                shares -= qty
                if shares < 1e-8:
                    shares = 0.0
            pending_sell = 0.0
        if pending_buy > 0.0:
            px = o[i] + SLIPPAGE
            eq = cash + shares * px
            room = max(0.0, 1.0 - (shares * px) / eq) if eq > 0 else 0.0
            use = min(pending_buy, room)
            spend = min(eq * use, cash / (1.0 + COMMISSION)) if px > 0 else 0.0
            if spend > 0.0 and use >= 0.002:
                cash -= spend * (1.0 + COMMISSION)
                shares += spend / px
            pending_buy = 0.0

        eq = cash + shares * c[i]
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

        lo = w_lo[i]
        if lo == lo and l[i] <= lo:
            w_touch = True
        up = u56[i]
        if up == up and h[i] >= up:
            w_touch = False

        if shares > 0.0:
            red = 0.0
            if sell_w[i] and (not w_touch) and ws > 0.0:
                red = ws
                pending_buy = 0.0
            elif sell_d[i] and ds > 0.0:
                red = ds
            pending_sell = red

        bp = 0.0
        if buy_w[i] and wb > 0.0:
            bp = wb
        if buy_d[i] and db > 0.0:
            bp = max(bp, db)
        if bp > 0.0:
            pending_buy = bp

    if shares > 0.0:
        px = p["last_close"] - SLIPPAGE
        cash += shares * px * (1.0 - COMMISSION)
        shares = 0.0
    return cash, max_dd


def bh(p) -> float:
    return p["last_close"] / p["first_open"] - 1.0


def grid(p, steps):
    rows = []
    for db, wb, ds, ws in product(steps, repeat=4):
        if db <= 0.0 and wb <= 0.0:
            continue
        eq, dd = sim(p, db, wb, ds, ws)
        rows.append((eq, dd, db, wb, ds, ws))
    rows.sort(key=lambda r: -r[0])
    return rows


def fmt(r) -> str:
    eq, dd, db, wb, ds, ws = r
    return (
        f"Dbuy={db:.0%} Wbuy={wb:.0%} Dsell={ds:.0%} Wsell={ws:.0%}  "
        f"equity={eq:>10,.0f}  ret={(eq / CAPITAL - 1) * 100:7.1f}%  maxDD={dd * 100:5.1f}%"
    )


def main() -> None:
    print("Downloading SPX ...")
    raw = load_spx()
    df = add_indicators(raw.copy())
    windows = [
        ("10y", "2016-09-01", "2026-09-01"),
        ("20y", "2006-09-01", "2026-09-01"),
    ]
    packed = {}
    for name, a, b in windows:
        d = df.loc[(df.index >= a) & (df.index <= b)]
        packed[name] = pack(d)
        print(f"{name}: {len(d)} bars  B&H={bh(packed[name])*100:.1f}%")

    # sanity vs last known 50/100/50/100 no-stop 10y ~228030
    eq, dd = sim(packed["10y"], 0.5, 1.0, 0.5, 1.0)
    print(f"sanity 50/100/50/100 10y equity={eq:,.0f} maxDD={dd*100:.1f}%")

    print(f"\nCoarse grid {STEPS}  (no stop, filters ON, next-open fill)")
    tops = {}
    for name, p in packed.items():
        rows = grid(p, STEPS)
        tops[name] = rows
        print(f"\n=== {name} TOP 12 by profit ===")
        for r in rows[:12]:
            print(" ", fmt(r))
        used = [r for r in rows if r[2] > 0 and r[3] > 0 and r[4] > 0 and r[5] > 0]
        nosell = [r for r in rows if r[4] <= 0 and r[5] <= 0]
        print(" best with all 4 sizes > 0:", fmt(used[0]) if used else "n/a")
        print(" best never-sell:         ", fmt(nosell[0]) if nosell else "n/a")
        base = next(r for r in rows if r[2:] == (0.5, 1.0, 0.5, 1.0))
        print(" baseline 50/100/50/100:  ", fmt(base))

    # Fine grid around each window's best that uses sells
    print(f"\nFine grid {FINE}  (one pass per window, then rank)")
    fine_rows = {}
    for name, p in packed.items():
        rows = grid(p, FINE)
        fine_rows[name] = {(r[2], r[3], r[4], r[5]): r for r in rows}
        used = [r for r in rows if r[2] > 0 and r[3] > 0 and r[4] > 0 and r[5] > 0]
        print(f"\n=== {name} FINE top 8 overall ===")
        for r in rows[:8]:
            print(" ", fmt(r))
        print(f"=== {name} FINE top 8 with all 4 > 0 ===")
        for r in used[:8]:
            print(" ", fmt(r))

    print("\n=== Robust: same sizes, geometric mean of 10y & 20y terminal wealth ===")
    scored = []
    keys = set(fine_rows["10y"]) | set(fine_rows["20y"])
    for key in keys:
        r1 = fine_rows["10y"].get(key)
        r2 = fine_rows["20y"].get(key)
        if r1 is None or r2 is None:
            continue
        e1, d1, db, wb, ds, ws = r1
        e2, d2 = r2[0], r2[1]
        geo = (e1 * e2) ** 0.5
        scored.append((geo, e1, d1, e2, d2, db, wb, ds, ws))
    scored.sort(key=lambda r: -r[0])
    used = [r for r in scored if r[5] > 0 and r[6] > 0 and r[7] > 0 and r[8] > 0]
    print("top 8 overall:")
    for geo, e1, d1, e2, d2, db, wb, ds, ws in scored[:8]:
        print(
            f"  Dbuy={db:.0%} Wbuy={wb:.0%} Dsell={ds:.0%} Wsell={ws:.0%}  "
            f"geo={geo:,.0f}  10y={e1:,.0f} ({(e1/CAPITAL-1)*100:.1f}%, DD {d1*100:.1f}%)  "
            f"20y={e2:,.0f} ({(e2/CAPITAL-1)*100:.1f}%, DD {d2*100:.1f}%)"
        )
    print("top 8 with all 4 > 0:")
    for geo, e1, d1, e2, d2, db, wb, ds, ws in used[:8]:
        print(
            f"  Dbuy={db:.0%} Wbuy={wb:.0%} Dsell={ds:.0%} Wsell={ws:.0%}  "
            f"geo={geo:,.0f}  10y={e1:,.0f} ({(e1/CAPITAL-1)*100:.1f}%, DD {d1*100:.1f}%)  "
            f"20y={e2:,.0f} ({(e2/CAPITAL-1)*100:.1f}%, DD {d2*100:.1f}%)"
        )


if __name__ == "__main__":
    main()
