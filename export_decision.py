"""Data for the Decision Lab page (site/play.html): model draws, the 2026 starting state and the live
Kalshi quote, so the browser can re-run the class model for any choice of factors.

    python export_decision.py      # results/decision_context.json

Contents
  climate_draws   400 (p1, p2, AR(1) phi, sigma) draws for each climate view: history-fit, IPCC-calibrated,
                  wide (full AR6 width), sampled from the Phase 3 posteriors
  kaya_draws      400 Kaya growth-rate sets, resampled by their 2019-24 emissions weights (Phase 3)
  scenario paths, the HW5 template rates, the 2026 nowcast, momentum, dataset offsets, anchor data
  kalshi          bid/ask/mid and the all-in cost of buying Yes or No (100-contract fee rate)
  reference       Python's results for the same settings, to check the browser against
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import pricing as pc
import priors as pr
import scenarios as sc
from market import fee, latest_snapshot, walk_book
from model import Inputs, Params
from phase3 import climate_posteriors, kaya_setup, setup
from phase5 import nowcast_state

HERE = Path(__file__).resolve().parent
OUT = HERE / "results"
N = 400


def main():
    inp = Inputs.load()
    st = setup(inp)
    posts, _, _ = climate_posteriors(st["grid"])
    ks = kaya_setup(st, inp)
    ns = nowcast_state(st, inp, n_paths=1000)
    g = st["grid"]
    rng = np.random.default_rng(2027)

    climate = {}
    for view in ("history", "ipcc", "ipcc_full"):
        i = pr.sample_grid(posts[view], N, rng)
        climate[view] = {"p1": g.p1[i].round(5).tolist(), "p2": g.p2[i].round(4).tolist(),
                         "phi": g.phi[i].round(4).tolist(), "sigma": g.sigma[i].round(5).tolist()}
    w = ks["w_k"][0.02]
    ik = rng.choice(len(w), size=N, p=w / w.sum())
    kaya = {k: v[ik].round(6).tolist() for k, v in ks["kaya"].items()}

    snap = latest_snapshot()
    yes_cost = walk_book(snap["yes_asks"], 100)["all_in_per_contract"]
    no_cost = walk_book(snap["no_asks"], 100)["all_in_per_contract"]
    lo, hi = pc.no_trade_band(yes_cost, no_cost, 1.0, 1.0)

    yrs = st["years"]
    sel = (yrs >= 2006) & (yrs <= 2025)
    off = st["off"]
    p10 = json.loads((OUT / "phase10.json").read_text())
    p11 = json.loads((OUT / "phase11.json").read_text())
    ref = {k: v["p_yes"] for k, v in p10["variants"].items()}
    ref["ensemble_72"] = p11["ensemble"]["p_yes"]
    base = Params()
    ctx = {
        "snapshot": snap["dir"], "fetched_utc": snap["fetched_utc"],
        "kalshi": {"bid": snap["yes_bid"], "ask": snap["yes_ask"], "mid": snap["mid"], "last": snap["last"],
                   "yes_cost": yes_cost, "no_cost": no_cost, "band": [lo, hi], "apy": snap["kalshi_apy"]},
        "climate_draws": climate, "kaya_draws": kaya,
        "hw5": {"g": list(base.gdp_per_capita_growth), "ei": list(base.energy_intensity_change),
                "ci": list(base.emissions_intensity_change), "p1": base.p1_adjust_speed, "p2": base.p2_sensitivity},
        "class_ar1": {"phi": ns["fitA"].ar1["phi"], "sigma": ns["fitA"].ar1["sigma"]},
        "scenario_paths_mtc": {s: sc.path(s, st["actual"]).tolist() for s in sc.NAMES},
        "signal_2026": {"mean": float(ns["sig26"].mean()), "sd": float(ns["sig26"].std())},
        "q4_minus_annual_2026": float(ns["m26"].mean()),
        "momentum": {"used": bool(ns["use_mom"]), "phi1": ns["mom"]["phi1"], "phi2": ns["mom"]["phi2"]},
        "anchor_years": [int(y) for y in yrs[sel]], "anchor_signal": [float(v) for v in st["S"][sel]],
        "offsets": {"delta": off["delta"].tolist(), "tau": off["tau"].tolist(), "rho": off["rho"].tolist(),
                    "last_dev": off["last_dev"].tolist()},
        "land_use_fill_mtc": 990.0,
        "reference": ref,
        "ensemble_pdf": {"grid": p11["ensemble"]["grid"], "pdf": p11["ensemble"]["pdf"],
                         "mean_peak": p11["ensemble"]["pdf_mean_peak"]},
        "ipcc_pdf": {"grid": p10["grid"], "pdf": p10["variants"]["ipcc"]["pdf_peak"]},
    }
    (OUT / "decision_context.json").write_text(json.dumps(ctx))
    print(f"wrote {OUT / 'decision_context.json'}: {N} climate draws x 3 views, {N} Kaya draws; "
          f"Kalshi {snap['yes_bid']:.2f}/{snap['yes_ask']:.2f}, Yes costs {yes_cost:.3f}, No costs {no_cost:.3f}")


if __name__ == "__main__":
    main()
