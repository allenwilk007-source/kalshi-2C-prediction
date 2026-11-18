"""Plain-Python tests for Phase 2 (no pytest needed):  python test_phase2.py"""
import math
import sys
import traceback

import numpy as np

from model import Params
from noise import contract_outcome, dataset_offsets, fit_ar1, simulate, summarize
from observations import rebaseline, window_mean


def _series(years, f):
    return {int(y): float(f(y)) for y in years}


def test_rebaseline_zero_mean():
    yrs = range(1850, 2026)
    native = {k: _series(yrs, lambda y, s=s: 0.01 * (y - 1850) + s)
              for k, s in (("noaa", -0.2), ("berkeley", 0.3), ("hadcrut", -0.5))}
    native["giss"] = _series(range(1880, 2026), lambda y: 0.01 * (y - 1850) + 0.7)
    rb = rebaseline(native)
    for k in ("noaa", "berkeley", "hadcrut"):
        assert abs(window_mean(rb[k], 1850, 1900)) < 1e-12, k


def test_giss_alignment_recovers_shift():
    yrs = range(1850, 2026)
    rng = np.random.default_rng(1)
    truth = {y: 0.008 * (y - 1850) + rng.normal(0, 0.1) for y in yrs}
    native = {k: dict(truth) for k in ("noaa", "berkeley", "hadcrut")}
    native["giss"] = {y: v + 0.3 for y, v in truth.items() if y >= 1880}   # same data, shifted
    rb = rebaseline(native)
    for y in range(1880, 2026):
        assert abs(rb["giss"][y] - rb["noaa"][y]) < 1e-12


def test_ar1_recovers_parameters():
    rng = np.random.default_rng(2)
    phi, sigma, n = 0.6, 0.1, 5000
    r = np.zeros(n)
    for t in range(1, n):
        r[t] = phi * r[t - 1] + rng.normal(0, sigma)
    fit = fit_ar1(r)
    assert abs(fit["phi"] - phi) < 0.03, fit["phi"]
    assert abs(fit["sigma"] - sigma) < 0.03, fit["sigma"]


def test_two_of_four_rule():
    years = np.array([2030])
    def X(vals):
        return np.array(vals, dtype=float).reshape(1, 4, 1)
    cases = [
        ([2.01, 1.90, 1.80, 1.70], False),   # one dataset alone is not enough
        ([2.00, 2.00, 1.50, 1.50], True),    # two at exactly 2.00
        ([1.995, 1.996, 1.0, 1.0], True),    # both round to 2.00
        ([1.994, 2.30, 1.0, 1.0], False),    # 1.994 rounds to 1.99
    ]
    for vals, want in cases:
        yes, first = contract_outcome(X(vals), years)
        assert bool(yes[0]) is want, (vals, yes)
        assert (first[0] == 2030) if want else math.isnan(first[0])


def test_last_year_is_2049():
    years = np.array([2049, 2050])
    X = np.array([[1.0, 2.5]] * 4).reshape(1, 4, 2)
    yes, _ = contract_outcome(X, years)
    assert not yes[0]                       # 2050 does not count ("before 2050")


def _zero_noise_offsets():
    return {"delta": np.zeros(4), "tau": np.zeros(4), "rho": np.zeros(4), "last_dev": np.zeros(4)}


def test_zero_noise_matches_deterministic():
    years = np.arange(2026, 2050)
    ar = {"c": 0.0, "phi": 0.5, "sigma": 0.0}
    for top, want in ((2.05, True), (1.95, False)):
        model_future = np.linspace(1.4, top, len(years))
        X, S = simulate(model_future, ar, r0=0.0, offsets=_zero_noise_offsets(), n=50, seed=0)
        assert np.allclose(S, model_future)
        yes, _ = contract_outcome(X, years)
        assert yes.all() == want and yes.any() == want


def test_seed_determinism():
    years = np.arange(2026, 2050)
    ar = {"c": 0.0, "phi": 0.5, "sigma": 0.1}
    off = {"delta": np.array([-0.06, -0.09, 0.11, 0.04]), "tau": np.full(4, 0.01),
           "rho": np.array([0.4, 0.5, 0.2, 0.3]), "last_dev": np.zeros(4)}
    mf = np.linspace(1.4, 2.0, len(years))
    a = summarize(*contract_outcome(simulate(mf, ar, 0.05, off, n=5000, seed=7)[0], years))
    b = summarize(*contract_outcome(simulate(mf, ar, 0.05, off, n=5000, seed=7)[0], years))
    assert a == b


def test_offsets_on_synthetic():
    years = np.arange(1990, 2026)
    base = np.linspace(0.5, 1.4, len(years))
    true_delta = np.array([-0.05, -0.08, 0.10, 0.03])
    X = base + true_delta[:, None]
    off = dataset_offsets(years, X)
    assert np.allclose(off["delta"], true_delta)


def test_default_params_unchanged():
    assert Params().land_use_fill_mtc == 0.0 and Params().p2_sensitivity == 1.15


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
