"""Plain-Python tests for Phase 3:  python test_phase3.py"""
import math
import sys
import traceback

import numpy as np

import priors as pr
import scenarios as sc
from calibrate import fit_version
from model import Inputs, Params
from noise import common_signal, contract_outcome, dataset_offsets, simulate
from observations import load
from phase3 import run_draws, setup, wsummary

_ST = {}


def st():
    if not _ST:
        _ST.update(setup(Inputs.load()))
    return _ST


def test_point_mass_reproduces_phase2():
    s = st()
    fit = fit_version(Params(), s["years"], s["S"], (1880, 2025))
    out = run_draws(Params(), fit.ar1, np.ones(1), s["s_2025"], s["off"], K=100_000, seed=0)
    r = wsummary(out["yes"], out["first"], out["w"])
    assert abs(r["p_yes"] - 0.978) < 3 * max(r["mc_se"], 0.0005), r


def test_vectorised_simulate_matches_scalar():
    years = np.arange(2026, 2050)
    off = {"delta": np.array([-0.06, -0.09, 0.11, 0.04]), "tau": np.full(4, 0.01),
           "rho": np.array([0.4, 0.5, 0.2, 0.3]), "last_dev": np.zeros(4)}
    mf = np.linspace(1.4, 2.0, len(years))
    ar = {"c": -0.01, "phi": 0.5, "sigma": 0.1}
    a, _ = simulate(mf, ar, 0.05, off, n=2000, seed=3)
    arv = {k: np.full(2000, v) for k, v in ar.items()}
    b, _ = simulate(np.tile(mf, (2000, 1)), arv, np.full(2000, 0.05), off, n=2000, seed=3)
    assert np.allclose(a, b)


def test_scenario_paths():
    actual = np.array([10_000.0, 10_100.0, 10_200.0, 10_300.0])
    flat = sc.path("flat", actual)
    assert np.allclose(flat[:4], actual) and np.allclose(flat[4:], 10_300.0)
    dbl = sc.path("doubling", actual)
    assert abs(dbl[2050 - 2021] / dbl[2024 - 2021] - 2.0) < 1e-12
    fall = sc.path("falling", actual)
    assert fall[2070 - 2021] == 0 and (fall >= 0).all() and fall[2069 - 2021] > 0


def test_ecs_prior_percentiles():
    ecs = np.linspace(0.5, 12, 200_001)
    w = np.exp(pr.ecs_logprior(ecs))
    q5, q95 = pr.weighted_quantile(ecs, w, (0.05, 0.95))
    assert abs(q5 - 2.0) < 0.01 and abs(q95 - 5.0) < 0.02, (q5, q95)


def test_tempering():
    g = st()["grid"]
    lw = g.logprior + g.loglik
    manual = np.exp(lw - lw.max()); manual /= manual.sum()
    assert np.allclose(pr.posterior(g, 1.0), manual)
    widths = [pr.mid_width(g, T) for T in (1, 2, 4, 8, 16, 64)]
    assert all(b >= a - 1e-9 for a, b in zip(widths, widths[1:])), widths


def test_emission_weights_and_ess():
    g = 0.04
    k19 = 100.0
    vals = k19 * np.exp(np.array([0.0, 0.02, 0.04, 0.06, 0.08]))
    w = pr.emission_weights(vals, k19, g, sd=0.02)
    assert int(np.argmax(w)) == 2
    assert pr.ess([1, 1, 0, 0]) == 2.0


def test_determinism():
    s = st()
    fit = fit_version(Params(), s["years"], s["S"], (1880, 2025))
    a = run_draws(Params(), fit.ar1, np.ones(1), s["s_2025"], s["off"], K=3000, seed=5)
    b = run_draws(Params(), fit.ar1, np.ones(1), s["s_2025"], s["off"], K=3000, seed=5)
    assert np.array_equal(a["yes"], b["yes"])


def test_override_matches_kaya():
    from model import kaya_emissions, run
    inp = Inputs.load()
    E = kaya_emissions(Params(), inp)
    a = run(Params(), inp).temp_atmos
    b = run(Params(future_emissions_mtc=E), inp).temp_atmos
    assert np.allclose(a, b, equal_nan=True)


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
