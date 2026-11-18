"""Plain-Python tests for Phase 6 (SCC):  python test_phase6.py"""
import sys
import traceback

import numpy as np

from model import Inputs, Params, run
from scc import discount_factors, extended, marginal_damages, scc_from_md, temps, tol_by_prtp


def test_extended_matches_run_to_2100():
    inp = Inputs.load()
    p = Params()
    x = extended(p, inp)
    r = run(p, inp)
    assert np.allclose(x["E"][:351], r.emissions_mtc)
    T = temps(x["E"], p)
    Tr = r.temp_atmos - r.temp_atmos[100:151].mean()
    assert np.allclose(T[:351], Tr, equal_nan=True)


def test_pulse_positive_and_slow_decay():
    md = marginal_damages(Params(), 0.242, 0.0)
    dT = md["dT"]
    assert (dT[1:] > 0).all()
    assert dT[-1] > 0.2 * dT.max()           # long-lived: still >20 % of peak 270 years later


def test_constant_rate_npv_by_hand():
    g = np.zeros(10)
    df = discount_factors(g, 0, const_r=0.05)
    assert np.allclose(df, 1 / 1.05 ** np.arange(10))
    md = {"MD": np.ones(10), "g": g, "j0": 0, "years": np.arange(2027, 2037)}
    assert abs(scc_from_md(md, const_r=0.05) - sum(1 / 1.05 ** k for k in range(10))) < 1e-12


def test_ramsey_equals_constant_when_growth_flat():
    g = np.full(20, 0.01)
    a = discount_factors(g, 0, rho=0.015, eta=1.4)
    b = discount_factors(g, 0, const_r=0.015 + 1.4 * 0.01)
    assert np.allclose(a, b)


def test_scc_linear_in_damage_coef():
    m1 = marginal_damages(Params(), 0.2, 0.0)
    m2 = marginal_damages(Params(), 0.4, 0.0)
    assert abs(scc_from_md(m2, 0.015, 1.4) / scc_from_md(m1, 0.015, 1.4) - 2) < 1e-9


def test_tol_prtp_means_match_phase1():
    t = tol_by_prtp()
    for r, want in ((0.0, 1438), (1.0, 311), (1.5, 213), (3.0, 53)):
        assert abs(t[r]["mean"] - want) < 1.0, (r, t[r]["mean"])


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
