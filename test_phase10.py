"""Plain-Python tests for Phase 10 (temperature PDFs):  python test_phase10.py"""
import json
import sys
import traceback
from pathlib import Path

import numpy as np

from phase10 import GRID, wkde, wquant

RES = Path(__file__).resolve().parent / "results" / "phase10.json"


def test_kde_integrates_to_one_and_centres_correctly():
    x = np.random.default_rng(0).normal(2.0, 0.2, 50_000)
    d, h = wkde(x, np.ones_like(x))
    assert abs(d.sum() * 0.01 - 1) < 0.01
    assert abs(GRID[np.argmax(d)] - 2.0) < 0.03


def test_equal_weights_match_unweighted():
    x = np.random.default_rng(1).normal(1.9, 0.15, 20_000)
    a, _ = wkde(x, np.ones_like(x), bw=0.03)
    b, _ = wkde(x, np.full_like(x, 7.0), bw=0.03)
    assert np.allclose(a, b)


def test_weighted_quantile():
    x = np.array([1.0, 2.0, 3.0, 4.0])
    assert wquant(x, np.array([1, 1, 1, 1.0]), (0.5,))[0] == 2.0
    assert wquant(x, np.array([0, 0, 0, 1.0]), (0.5,))[0] == 4.0


def test_p_yes_equals_p_peak_and_matches_pdf_area():
    r = json.loads(RES.read_text())
    for k, v in r["variants"].items():
        assert abs(v["p_yes"] - v["p_peak_ge_2"]) < 1e-12, k         # contract rule == peak >= 2.00
        assert abs(v["pdf_area_peak_ge_2"] - v["p_yes"]) < 0.06, (k, v["pdf_area_peak_ge_2"], v["p_yes"])


def test_shift_sign_consistent_with_gap():
    r = json.loads(RES.read_text())
    for k, v in r["variants"].items():
        if abs(v["gap_vs_kalshi_pts"]) > 3:
            assert np.sign(v["shift_to_match_kalshi_C"]) == -np.sign(v["gap_vs_kalshi_pts"]), k


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
