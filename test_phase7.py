"""Plain-Python tests for Phase 7 (scanner):  python test_phase7.py"""
import json
import sys
import traceback

import numpy as np

from market import MKT, latest_snapshot
from scanner import (load_mlo, mlo_components, month_of, p_monthly_record, p_strike, simulate_mlo,
                     trend_state)


def test_bins_partition_rounded_values():
    snap = latest_snapshot()
    ms = [m for m in json.loads((MKT / snap["dir"] / "climate_markets.json").read_text())
          if m["event_ticker"].startswith("KXHMONTHRANGE")]
    assert ms, "no range markets in snapshot"
    by_event = {}
    for m in ms:
        by_event.setdefault(m["event_ticker"], []).append(m)
    grid = np.round(np.arange(0.80, 1.80, 0.01), 2)
    for ev, mk in by_event.items():
        hits = np.zeros(len(grid))
        for m in mk:
            assert m["strike_type"] in ("greater", "less", "between"), m["strike_type"]
            hits += np.array([p_strike(np.array([g]), m["strike_type"], m.get("floor_strike"), m.get("cap_strike"))
                              for g in grid])
        assert np.allclose(hits, 1), (ev, grid[hits != 1])
        draws = np.random.default_rng(0).normal(1.25, 0.1, 5000)
        tot = sum(p_strike(draws, m["strike_type"], m.get("floor_strike"), m.get("cap_strike")) for m in mk)
        assert abs(tot - 1) < 1e-12


def test_record_probability_matches_direct_count():
    hist = {(y, 10): 1.0 + 0.01 * (y - 2000) for y in range(2000, 2026)}     # record = 1.25 (2025)
    draws = np.random.default_rng(1).normal(1.26, 0.05, 20000)
    p, rec = p_monthly_record(draws, hist, 2026, 10)
    direct = np.mean(np.floor(draws * 100 + 0.5) / 100 > 1.25 + 1e-9)
    assert rec == 1.25 and abs(p - direct) < 1e-12


def test_strike_rounding_edges():
    assert p_strike(np.array([1.304]), "greater", 1.3) == 0.0      # publishes 1.30, not above 1.30
    assert p_strike(np.array([1.305]), "greater", 1.3) == 1.0      # publishes 1.31
    assert p_strike(np.array([439.995]), "greater_or_equal", 440) == 1.0


def test_month_of():
    assert month_of("KXHMONTH-26NOV") == (2026, 11)
    assert month_of("KXHMONTHRANGE-26OCT-T1.30") == (2026, 10)


def test_co2_six_month_path_tracks_observations():
    mon, day = load_mlo()
    comp = mlo_components(mon, day)
    last = max(mon)
    start = (last[0], last[1] - 6) if last[1] > 6 else (last[0] - 1, last[1] + 6)
    t0, u0 = trend_state(mon, start)
    ann = [np.mean([mon[(y, m)][0] for m in range(1, 13) if (y, m) in mon]) for y in range(start[0] - 10, start[0] + 1)]
    g = float(np.mean(np.diff(ann)))
    months, mm, _ = simulate_mlo(start, last, t0, u0, {y: np.full(4000, g) for y in range(start[0], last[0] + 1)},
                                 comp, np.random.default_rng(2), 4000, 0.42, 0.15)
    act = np.array([mon[k][0] for k in months])
    lo, hi = np.percentile(mm, [1, 99], axis=0)
    assert np.sqrt(np.mean((np.median(mm, axis=0) - act) ** 2)) < 1.2
    assert np.mean((act >= lo) & (act <= hi)) >= 0.5


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
