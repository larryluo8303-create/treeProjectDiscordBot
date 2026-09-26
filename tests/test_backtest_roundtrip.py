"""Regression tests for backtest round-trip accounting.

Semantics (locked here): ALL cash flows of a position — every buy (incl.
commission) and every partial sell (net of commission) — accumulate into one
round trip. A win/loss is counted exactly once, when the position is fully
flattened. Neither per-partial-sell counting nor last-chunk-only pnl is
acceptable.
"""

import sys
import types
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load_spx_module():
    if "yfinance" not in sys.modules:
        stub = types.ModuleType("yfinance")
        stub.download = lambda *a, **k: None
        sys.modules["yfinance"] = stub
    sys.path.insert(0, str(SCRIPTS))
    try:
        import backtest_spx_bigtree as base

        return base
    finally:
        sys.path.remove(str(SCRIPTS))


@pytest.fixture(scope="module")
def base():
    return _load_spx_module()


class TestRoundTrip:
    def test_single_buy_two_sells_counts_one_win(self, base):
        """1 buy, 2 partial sells → exactly 1 round trip; pnl covers all fills."""
        trip = base.RoundTrip()
        # Buy $10,000 incl. commission
        trip.record_buy(10_000.0)
        # Partial sell: +$6,000 proceeds; final sell: +$5,000 proceeds
        trip.record_sell(6_000.0)
        trip.record_sell(5_000.0)
        assert trip.flatten_pnl() == pytest.approx(1_000.0)

    def test_empty_trip_has_no_pnl(self, base):
        trip = base.RoundTrip()
        assert trip.flatten_pnl() is None

    def test_reset_starts_new_round_trip(self, base):
        trip = base.RoundTrip()
        trip.record_buy(5_000.0)
        trip.record_sell(4_000.0)
        assert trip.flatten_pnl() == pytest.approx(-1_000.0)
        trip.reset()
        assert trip.flatten_pnl() is None
        trip.record_buy(2_000.0)
        trip.record_sell(2_500.0)
        assert trip.flatten_pnl() == pytest.approx(500.0)

    def test_old_per_sell_counting_would_fail(self, base):
        """Guard against the old bug: counting each partial sell as its own
        trade would report 2 wins here instead of 1."""
        trip = base.RoundTrip()
        trip.record_buy(10_000.0)
        trip.record_sell(6_000.0)   # partial — must NOT close the round trip
        trip.record_sell(5_000.0)   # flatten
        pnl = trip.flatten_pnl()
        # Whole-trip pnl is +1000 (a win). Per-sell accounting would have
        # compared each sell against average cost and counted 2 trades.
        assert pnl == pytest.approx(1_000.0)
        assert pnl > 0  # exactly one win, not two

    def test_candidates_shares_roundtrip_class(self, base):
        """backtest_candidates.py must use the same RoundTrip class."""
        sys.path.insert(0, str(SCRIPTS))
        try:
            for mod in ("backtest_candidates",):
                sys.modules.pop(mod, None)
            import backtest_candidates as cand
        finally:
            sys.path.remove(str(SCRIPTS))
        assert cand.base.RoundTrip is base.RoundTrip
