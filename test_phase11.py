"""Plain-Python tests for Phase 11 (hypothetical trade):  python test_phase11.py"""
import json
import sys
import traceback
from pathlib import Path

import numpy as np

RES = Path(__file__).resolve().parent / "results" / "phase11.json"


def load():
    return json.loads(RES.read_text())


def test_ensemble_mean_is_average_of_versions():
    r = load()["ensemble"]
    assert r["n_versions"] == 72 == len(r["versions"])
    avg = np.mean([v["p_yes"] for v in r["versions"]])         # equal paths per version -> mixture = average
    assert abs(r["p_yes"] - avg) < 1e-9


def test_pdf_area_matches_estimate():
    r = load()["ensemble"]
    g, pdf = np.array(r["grid"]), np.array(r["pdf"])
    assert abs(pdf.sum() * 0.01 - 1) < 0.02
    assert abs(pdf[g >= 1.995].sum() * 0.01 - r["p_yes"]) < 0.06


def test_value_bet_arithmetic():
    A = load()["strategy_A_value_bet"]
    p, c, n = A["our_p"], A["all_in_cost"], A["contracts_for_stake"]
    assert abs(A["edge_per_contract"] - (p - c)) < 1e-12
    assert abs(A["expected_profit"] - (n * p - n * c)) < 1e-9
    assert abs(A["kelly_fraction"] - max(0, (p - c) / (1 - c))) < 1e-12
    assert n * c <= 1000 < (n + 1) * c


def test_hedge_outcomes():
    B = load()["strategy_B_hedge"]
    nA, nB, s = B["leg_A_contracts"], B["leg_B_contracts"], B["spend"]
    want = [nA + nB - s, nB - s, nA - s, -s]
    assert np.allclose(list(B["outcomes"].values()), want)


def test_arbitrage_arithmetic():
    C = load()["strategy_C_arbitrage_check"]
    if C["available"]:
        for x in C["combos"]:
            assert abs(x["locked_profit_per_pair"] - (1 - x["total_cost"])) < 1e-12
        assert C["arbitrage_now"] == (C["best"]["locked_profit_per_pair"] > 0)


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
