"""Plain-Python tests for Phase 9 (history):  python test_phase9.py"""
import sys
import traceback
from datetime import date, timedelta

import numpy as np

from history import lead_lag, published_month, rolling_kxgtemp
from nowcast import load_monthly, nowcast_year, p_kxgtemp


def test_published_months_match_today():
    # as of 8 Nov 2026: GISS/NOAA through Sep, HadCRUT through Jul (what the agencies had actually published)
    d = date(2026, 11, 8)
    assert (published_month("giss", d, 2026), published_month("noaa", d, 2026), published_month("hadcrut", d, 2026)) == (9, 9, 7)
    assert published_month("giss", date(2026, 1, 20), 2026) == 0


def test_rolling_equals_direct_nowcast():
    mon, (era5, _) = load_monthly()
    d = date(2026, 11, 8)
    r = rolling_kxgtemp(mon, era5, [d], total_scale=1.3, n_draws=2000, seed=4)[0]
    cut = d - timedelta(days=2)
    nc = nowcast_year(2026, mon, era5, cutoff=(cut.year, cut.month, cut.day), n_draws=2000, seed=4,
                      observed_months={"giss": 9, "noaa": 9, "hadcrut": 7}, total_scale=1.3)
    assert r["p"] == p_kxgtemp(nc["giss"]["draws"])


def test_lead_lag_finds_known_lag():
    rng = np.random.default_rng(0)
    b = rng.normal(size=400)
    a = np.r_[np.zeros(3), b[:-3]] + 0.1 * rng.normal(size=400)    # a follows b by 3 days
    ll = lead_lag(a, b, 6)
    assert max(ll, key=ll.get) == 3 and ll[3] > 0.9


def test_trend_ar1_forecast_reverts_to_trend_not_period_mean():
    from nowcast import ar1_forecast
    ar = {"a": -52.0, "b": 0.026, "phi": 0.0, "sigma": 0.0}
    v = ar1_forecast(ar, np.array([5.0]), (2026, 5), np.random.default_rng(0), 1)
    assert abs(v[0] - (ar["a"] + ar["b"] * (2026 + 5.5 / 12))) < 1e-9     # phi=0 -> exactly the trend


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
