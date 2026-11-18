"""Plain-Python tests for Phase 4:  python test_phase4.py"""
import math
import sys
import traceback

import numpy as np

import pricing as pc
from market import fee, walk_book


def test_fee_matches_schedule():
    assert fee(0.50, 100) == 1.75          # schedule: max $1.75 per 100 contracts
    assert fee(0.01, 100) == 0.07          # schedule: min $0.07 per 100 contracts
    assert fee(0.69, 1) == 0.02            # 0.01497 rounds UP to 2 cents
    assert fee(0.69, 100) == 1.50


def test_walk_book():
    asks = [(0.69, 10), (0.70, 20), (0.71, 500)]
    r = walk_book(asks, 50)
    vwap = (10 * 0.69 + 20 * 0.70 + 20 * 0.71) / 50
    assert abs(r["vwap"] - vwap) < 1e-12 and r["complete"]
    raw = 0.07 * (10 * 0.69 * 0.31 + 20 * 0.70 * 0.30 + 20 * 0.71 * 0.29)
    assert r["fee"] == math.ceil(raw * 100 - 1e-9) / 100
    short = walk_book([(0.5, 5)], 10)
    assert not short["complete"] and short["filled"] == 5


def test_implied_q_properties():
    assert pc.implied_q(0.67, 1.0, 1.0) == 0.67
    first = np.array([2040.0, 2044.0, 2048.0])
    w = np.ones(3)
    today = 2026.86
    qs = []
    for d in (0.0, 0.005, 0.02, 0.05):
        DY, DN = pc.discount_yes(first, w, d, today), pc.discount_no(d, today)
        qs.append(pc.implied_q(0.67, DY, DN))
        if d > 0:
            assert DY > DN and qs[-1] < 0.67
    assert all(b < a for a, b in zip(qs, qs[1:]))           # monotone in delta
    DY, DN = 0.9, 0.85
    assert abs(pc.implied_q(pc.price_for_q(0.6, DY, DN), DY, DN) - 0.6) < 1e-12


def test_band_collapses_without_costs():
    lo, hi = pc.no_trade_band(0.67, 0.33, 1.0, 1.0)
    assert abs(lo - 0.67) < 1e-12 and abs(hi - 0.67) < 1e-12


def test_band_hand_calc():
    yes_cost = 0.69 + 0.07 * 0.69 * 0.31
    no_cost = 0.35 + 0.07 * 0.35 * 0.65
    lo, hi = pc.no_trade_band(yes_cost, no_cost, 1.0, 1.0)
    # 0.69 + 0.07*0.69*0.31 = 0.704973 ; 1 - (0.35 + 0.07*0.35*0.65) = 0.634075
    assert abs(hi - 0.704973) < 1e-9 and abs(lo - 0.634075) < 1e-9, (lo, hi)


def test_expected_return_zero_at_breakeven():
    DY, DN, p = 0.91, 0.89, 0.67
    q = pc.implied_q(p, DY, DN)
    y = pc.side_expected_return(q, DY, p, 18.0)
    n = pc.side_expected_return(1 - q, DN, 1 - p, 23.0)
    # equal gross multiples at q*: both sides earn the same
    assert abs(y["gross_multiple"] - n["gross_multiple"]) < 1e-12
    y0 = pc.side_expected_return(p, 1.0, p, 18.0)
    assert abs(y0["total_excess"]) < 1e-12 and abs(y0["annualised_excess"]) < 1e-12


def test_haircut_zero_is_identity_and_cancels_in_q():
    a = pc.no_trade_band(0.705, 0.366, 0.9, 0.88, h=0.0)
    b = pc.no_trade_band(0.705, 0.366, 0.9, 0.88)
    assert a == b
    lo5, hi5 = pc.no_trade_band(0.705, 0.366, 0.9, 0.88, h=0.05)
    assert lo5 < a[0] and hi5 > a[1]                          # haircut widens the band


def test_year_fraction():
    from datetime import datetime, timezone
    assert abs(pc.year_fraction(datetime(2026, 7, 2, 12, tzinfo=timezone.utc)) - 2026.5) < 0.003


if __name__ == "__main__":
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    failed = 0
    for name, f in tests:
        try:
            f()
            print(f"ok    {name}")
        except Exception:
            failed += 1
            print(f"FAIL  {name}")
            traceback.print_exc()
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
