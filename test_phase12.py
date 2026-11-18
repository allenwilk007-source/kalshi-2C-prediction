"""Plain-Python tests for Phase 12 (small regular trades):  python test_phase12.py"""
import json
import sys
import traceback
from pathlib import Path

RES = Path(__file__).resolve().parent / "results" / "phase12.json"


def load():
    return json.loads(RES.read_text())


def test_valuation_arithmetic():
    r = load()
    e = r["estimates"]
    for k in ("dca_at_ask", "limit_orders"):
        v = r[k]
        assert abs(v["expected_profit_ensemble"] - (v["contracts"] * e["ensemble"] - v["spent"])) < 1e-6
        assert abs(v["expected_profit_ipcc"] - (v["contracts"] * e["ipcc"] - v["spent"])) < 1e-6
        assert abs(v["avg_cost"] - v["spent"] / v["contracts"]) < 1e-12


def test_limit_orders_pay_no_fee_and_cost_less():
    r = load()
    assert r["limit_orders"]["fees"] == 0.0
    assert r["limit_orders"]["avg_cost"] < r["dca_at_ask"]["avg_cost"]


def test_spread_capture_bookkeeping():
    s = load()["spread_capture"]
    assert s["inventory"] == s["bought"] - s["sold"]
    assert abs(s["profit_marked_at_bid"] - (s["cash"] + s["inventory_value_at_bid"])) < 1e-9


def test_small_orders_pay_more_fee_per_contract():
    ft = load()["fee_by_order_size"]
    assert ft[0]["contracts"] == 1 and ft[0]["fee_per_contract"] >= max(x["fee_per_contract"] for x in ft[1:])


def test_forward_break_even():
    for v in load()["forward_one_year"].values():
        assert abs(v["break_even_probability"] - v["all_in"]) < 1e-12
        assert (v["expected_ipcc"] > 0) == (load()["estimates"]["ipcc"] > v["all_in"])


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
