"""Plain-Python tests for Phase 5:  python test_phase5.py"""
import sys
import traceback

import numpy as np

from hedge import capacity, load_impact, median_damage_coef, min_var_hedge, sample_damage_coef
from market import walk_book
from noise import simulate
from nowcast import fit_bridge, fit_momentum, load_monthly, nowcast_year, p_kxgtemp


def test_bridge_recovers_known_relation():
    rng = np.random.default_rng(0)
    keys = [(y, m) for y in range(1991, 2026) for m in range(1, 13)]
    e5 = {k: rng.normal(0.3, 0.3) for k in keys}
    x = {k: 0.6 + 0.9 * e5[k] + rng.normal(0, 0.01) for k in keys}
    b = fit_bridge(x, e5)
    assert abs(b["alpha"] - 0.6) < 0.005 and abs(b["beta"] - 0.9) < 0.01, b


def test_fully_observed_year_has_no_uncertainty():
    mon, (days, _) = load_monthly()
    nc = nowcast_year(2024, mon, days, n_draws=500)
    for k in ("giss", "noaa", "hadcrut"):
        d = nc[k]["draws"]
        assert np.allclose(d, np.mean([mon[k][(2024, m)] for m in range(1, 13)])) and d.std() < 1e-12
        assert nc[k]["months_filled"] == []


def test_first_shift_matches_recursion():
    T = 5
    off = {"delta": np.zeros(4), "tau": np.zeros(4), "rho": np.zeros(4), "last_dev": np.zeros(4)}
    ar = {"c": 0.01, "phi": 0.5, "sigma": 0.0}
    _, S = simulate(np.zeros(T), ar, 0.2, off, n=3, seed=0, first_shift=np.array([0.0, 0.1, -0.1]))
    for i, sh in enumerate((0.0, 0.1, -0.1)):
        r, path = 0.2, []
        for t in range(T):
            r = 0.01 + 0.5 * r + (sh if t == 0 else 0.0)
            path.append(r)
        assert np.allclose(S[i], path)
    _, S0 = simulate(np.zeros(T), ar, 0.2, off, n=3, seed=0)
    _, S1 = simulate(np.zeros(T), ar, 0.2, off, n=3, seed=0, first_shift=None)
    assert np.array_equal(S0, S1)


def test_damage_sampler_median():
    d = load_impact()
    a = sample_damage_coef(400_000, np.random.default_rng(1), d)
    assert abs(np.median(a) - median_damage_coef(d)) < 0.005
    assert abs(median_damage_coef(d) * 2.5 ** 2 - 1.51) < 0.02


def test_min_var_hedge():
    rng = np.random.default_rng(2)
    H = rng.normal(size=10_000)
    r = min_var_hedge(3 * H + 1, H)
    assert abs(r["h"] - 3) < 1e-9 and abs(r["r2"] - 1) < 1e-9
    r0 = min_var_hedge(rng.normal(size=10_000), H)
    assert r0["r2"] < 0.002


def test_capacity_matches_walk_book():
    asks = [(0.69, 10.63), (0.70, 21.81), (0.71, 500.0), (0.75, 130.1)]
    c = capacity(asks, 0.71)
    assert abs(c - 532.44) < 1e-9
    assert abs(walk_book(asks, c)["filled"] - c) < 1e-9


def test_kxgtemp_rounding():
    assert abs(p_kxgtemp(np.array([1.284, 1.285, 1.29, 1.17])) - 0.5) < 1e-12


def test_momentum_fit_recovers_coefficients():
    rng = np.random.default_rng(3)
    years = range(1900, 2026)
    r, m = {}, {y: rng.normal(0, 0.05) for y in years}
    prev = 0.0
    for y in years:
        r[y] = prev
        prev = 0.01 + 0.5 * prev + 0.8 * m[y] + rng.normal(0, 0.01)
    f = fit_momentum(r, m, years=(1900, 2025))
    assert abs(f["phi1"] - 0.5) < 0.05 and abs(f["phi2"] - 0.8) < 0.05 and f["t_phi2"] > 10, f


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
