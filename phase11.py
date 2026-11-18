"""Phase 11 (class project): a hypothetical trade on KXWARMING-50 built from the model's ensemble PDF.

    python phase11.py      # results/phase11.json, figures/p11_*.png

HYPOTHETICAL ONLY. This is a classroom exercise in how a model estimate turns into a trading idea.
It is not investment advice, and nothing here places orders.

1. Ensemble PDF: run the class model while changing its most important settings
     climate sensitivity (Parameter 2)   1.00 / 1.15 (class) / 1.30
     adjustment speed (Parameter 1)      0.020 / 0.0256 (class) / 0.032
     emissions after 2024                HW5 Kaya economy / falling / flat / rising
     missing land-use emissions          off / on (+990 Mt C/yr)
   = 72 versions x 4,000 simulated futures, each from the 2026 nowcast with Kalshi's exact rule.
   Our estimate = the mean of the ensemble: the share of all simulated futures that reach 2.00 C.
2. Strategy A (value bet): buy Yes if our estimate beats Kalshi's all-in cost.
3. Strategy B (hedge): add No on CO2 >= 445 ppm before 2030 (the model says that market is overpriced),
   which tends to pay in the slow-warming worlds where Strategy A loses.
4. Strategy C (arbitrage check): KXGTEMP-26 and KXGTEMP-27 carry the same rule but trade separately.
"""
from __future__ import annotations

import itertools
import json
import math
from dataclasses import replace
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import scenarios as sc
from market import MKT, fee, latest_snapshot, walk_book
from model import Inputs, Params
from phase3 import run_draws, setup
from phase5 import nowcast_state
from phase10 import GRID, wkde

HERE = Path(__file__).resolve().parent
FIG = HERE / "figures"
OUT = HERE / "results"
K = 4000
STAKE = 1000.0
ASPECTS = {
    "Climate sensitivity (Parameter 2)": [1.00, 1.15, 1.30],
    "Adjustment speed (Parameter 1)": [0.020, 0.0256, 0.032],
    "Emissions after 2024": ["HW5 economy", "falling", "flat", "rising"],
    "Missing land-use emissions": ["off", "on"],
}


def ensemble(st, inp, ns):
    ar = {"c": 0.0, "phi": ns["fitA"].ar1["phi"], "sigma": ns["fitA"].ar1["sigma"]}
    anchor = (st["years"], st["S"])
    rows, peaks, firsts = [], [], []
    for i, (p2, p1, em, lu) in enumerate(itertools.product(*ASPECTS.values())):
        future = None if em == "HW5 economy" else sc.path(em, st["actual"])
        p = replace(Params(), p1_adjust_speed=p1, p2_sensitivity=p2, future_emissions_mtc=future,
                    land_use_fill_mtc=990.0 if lu == "on" else 0.0)
        out = run_draws(p, ar, np.ones(1), st["s_2025"], st["off"], K=K, seed=100 + i, inp=inp,
                        anchor=anchor, start=ns["start"])
        rows.append({"p2": p2, "p1": p1, "emissions": em, "land_use": lu, "p_yes": float(out["yes"].mean()),
                     "peak_mean": float(out["peak"].mean())})
        peaks.append(out["peak"].astype(float))
        firsts.append(out["first"])
    return rows, np.concatenate(peaks), np.concatenate(firsts)


def kalshi_market(snap, ticker):
    ms = json.loads((MKT / snap["dir"] / "climate_markets.json").read_text())
    return next((m for m in ms if m["ticker"] == ticker), None)


def main():
    FIG.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    snap = latest_snapshot()
    inp = Inputs.load()
    st = setup(inp)
    ns = nowcast_state(st, inp, n_paths=K)

    # ---------------------------------------------------------------- 1. ensemble PDF
    rows, peak, first = ensemble(st, inp, ns)
    p_ens = float(np.mean(peak >= 2.0 - 1e-9))
    pdf, _ = wkde(peak, np.ones_like(peak))
    marg = {a: {str(lv): float(np.mean([r["p_yes"] for r in rows if r[key] == lv]))
                for lv in levels}
            for (a, levels), key in zip(ASPECTS.items(), ("p2", "p1", "emissions", "land_use"))}
    fy = first[np.isfinite(first)]
    years_to_pay = float(np.mean(fy + 1.04 - 2026.88))       # Yes pays ~mid-January after the qualifying year
    p10 = json.loads((OUT / "phase10.json").read_text()) if (OUT / "phase10.json").exists() else None
    p_ipcc = p10["variants"]["ipcc"]["p_yes"] if p10 else None

    # ---------------------------------------------------------------- 2. Strategy A: value bet
    buy100 = walk_book(snap["yes_asks"], 100)
    c = buy100["all_in_per_contract"]                         # ask + fee, 100-contract order
    edge = p_ens - c
    n = math.floor(STAKE / c)
    kelly = max(0.0, (p_ens - c) / (1 - c))
    exp_mult = p_ens / c
    A = {"price_ask": snap["yes_ask"], "all_in_cost": c, "our_p": p_ens, "break_even_p": c, "edge_per_contract": edge,
         "contracts_for_stake": n, "stake": n * c, "payout_if_yes": float(n), "profit_if_yes": n - n * c,
         "loss_if_no": -n * c, "expected_profit": n * p_ens - n * c, "prob_lose_stake": 1 - p_ens,
         "expected_return_total": exp_mult - 1, "years_to_payout_mean": years_to_pay,
         "expected_return_per_year_excl_interest": exp_mult ** (1 / years_to_pay) - 1,
         "kalshi_apy": snap["kalshi_apy"], "kelly_fraction": kelly, "half_kelly": kelly / 2,
         "capacity_contracts_at_or_below_ask_plus_2c": float(sum(s for p, s in snap["yes_asks"] if p <= snap["yes_ask"] + 0.02)),
         "ev_if_ipcc_view": (p_ipcc - c) if p_ipcc is not None else None, "p_ipcc": p_ipcc}

    # ---------------------------------------------------------------- 3. Strategy B: hedge with No on CO2 >= 445
    p7 = json.loads((OUT / "phase7.json").read_text())
    co2 = next(r for r in p7["rows"] if r["ticker"] == "KXCO2LEVEL-30-445")
    m445 = kalshi_market(snap, "KXCO2LEVEL-30-445")
    no_ask = float(m445["no_ask_dollars"]) if m445 else 1 - co2["bid"]
    no_cost = no_ask + fee(no_ask, 100) / 100
    p_co2 = max(co2["p_model"], co2["p_alt"] or 0)            # daily reading: the less favourable one for this leg
    wA, wB = 0.7, 0.3
    nA, nB = math.floor(STAKE * wA / c), math.floor(STAKE * wB / no_cost)
    spend = nA * c + nB * no_cost
    outcomes = {   # (warming >= 2 C by 2049, CO2 >= 445 before 2030)
        "2 C reached, CO2 stays below 445 (most likely)": nA + nB - spend,
        "2 C not reached, CO2 stays below 445": nB - spend,
        "2 C reached, CO2 reaches 445": nA - spend,
        "2 C not reached, CO2 reaches 445 (least likely: high CO2 but slow warming)": -spend,
    }
    B = {"leg_A_contracts": nA, "leg_B_contracts": nB, "no_price_ask": no_ask, "no_all_in_cost": no_cost,
         "p_co2_445_model": p_co2, "p_co2_445_market_mid": (co2["bid"] + co2["ask"]) / 2,
         "edge_leg_B_per_contract": (1 - p_co2) - no_cost, "spend": spend,
         "expected_profit": nA * p_ens + nB * (1 - p_co2) - spend,
         "outcomes": outcomes,
         "loss_if_2C_not_reached_A_only": -STAKE, "loss_if_2C_not_reached_hedged": nB - spend}

    # ---------------------------------------------------------------- 4. Strategy C: same-rule arbitrage check
    g26, g27 = kalshi_market(snap, "KXGTEMP-26-P0"), kalshi_market(snap, "KXGTEMP-27-P0")
    C = {"available": bool(g26 and g27)}
    if g26 and g27:
        combos = []
        for yes_m, no_m in ((g26, g27), (g27, g26)):
            ya, na = float(yes_m["yes_ask_dollars"]), float(no_m["no_ask_dollars"])
            cost = ya + fee(ya, 100) / 100 + na + fee(na, 100) / 100
            combos.append({"buy_yes": yes_m["ticker"], "yes_ask": ya, "buy_no": no_m["ticker"], "no_ask": na,
                           "total_cost": cost, "locked_profit_per_pair": 1 - cost})
        best = max(combos, key=lambda x: x["locked_profit_per_pair"])
        norm = lambda s: " ".join((s or "").replace(" the ", " ").split())   # rules differ only by the word "the"
        C.update({"same_rule": norm(g26.get("rules_primary")) == norm(g27.get("rules_primary")), "combos": combos, "best": best,
                  "arbitrage_now": best["locked_profit_per_pair"] > 0,
                  "gap_needed_cents": max(0.0, -best["locked_profit_per_pair"]) * 100})

    res = {"snapshot": snap["dir"], "fetched_utc": snap["fetched_utc"], "hypothetical": True,
           "ensemble": {"n_versions": len(rows), "paths_per_version": K, "p_yes": p_ens,
                        "pdf_mean_peak": float(peak.mean()), "pdf_median_peak": float(np.median(peak)),
                        "p5_95_peak": [float(np.percentile(peak, 5)), float(np.percentile(peak, 95))],
                        "p_yes_range_across_versions": [min(r["p_yes"] for r in rows), max(r["p_yes"] for r in rows)],
                        "by_aspect": marg, "versions": rows, "grid": GRID.tolist(), "pdf": pdf.round(5).tolist()},
           "kalshi": {"bid": snap["yes_bid"], "ask": snap["yes_ask"], "mid": snap["mid"]},
           "strategy_A_value_bet": A, "strategy_B_hedge": B, "strategy_C_arbitrage_check": C}

    # ---------------------------------------------------------------- print
    e = res["ensemble"]
    print("\nHYPOTHETICAL class-project analysis (not advice)\n")
    print(f"1. Ensemble PDF: {e['n_versions']} versions of the class model x {K} futures")
    print(f"   our estimate (ensemble mean) P(2 C before 2050) = {p_ens:.1%}   vs Kalshi mid {snap['mid']:.1%}  "
          f"(versions range {e['p_yes_range_across_versions'][0]:.0%}-{e['p_yes_range_across_versions'][1]:.0%})")
    print(f"   PDF of the highest reading 2027-49: mean {e['pdf_mean_peak']:.2f} C, 90% range {e['p5_95_peak'][0]:.2f}-{e['p5_95_peak'][1]:.2f} C")
    for a, d in marg.items():
        print(f"   {a:36s} " + "  ".join(f"{k}: {v:.0%}" for k, v in d.items()))
    print(f"\n2. Strategy A, value bet: buy Yes at {snap['yes_ask']:.2f} (all-in {c:.4f} per contract incl. fee)")
    print(f"   edge {edge * 100:+.1f} cents/contract; ${STAKE:,.0f} buys {n} contracts")
    print(f"   if 2 C is reached: +${A['profit_if_yes']:,.0f}   if not: ${A['loss_if_no']:,.0f}   expected: ${A['expected_profit']:+,.0f} "
          f"({A['expected_return_total']:+.1%} total, {A['expected_return_per_year_excl_interest']:+.2%}/yr over ~{years_to_pay:.0f} yrs, plus Kalshi's "
          f"{A['kalshi_apy']:.1%} APY on the position)")
    print(f"   Kelly fraction {kelly:.0%} of bankroll (half-Kelly {kelly / 2:.0%}); thin book: ~{A['capacity_contracts_at_or_below_ask_plus_2c']:.0f} contracts within 2 cents of the ask")
    if p_ipcc is not None:
        print(f"   caution: with our IPCC-calibrated estimate ({p_ipcc:.1%}) the same trade has edge {A['ev_if_ipcc_view'] * 100:+.1f} cents")
    print(f"\n3. Strategy B, hedge: 70% in A ({nA} Yes) + 30% in No on CO2 >= 445 before 2030 ({nB} contracts at {no_cost:.3f})")
    print(f"   model P(CO2 >= 445) {p_co2:.1%} vs market {B['p_co2_445_market_mid']:.0%}; expected ${B['expected_profit']:+,.0f}")
    for k, v in outcomes.items():
        print(f"     {k:72s} ${v:+,.0f}")
    print(f"   if 2 C is NOT reached: lose ${-B['loss_if_2C_not_reached_hedged']:,.0f} hedged vs ${STAKE:,.0f} unhedged")
    if C["available"]:
        b = C["best"]
        print(f"\n4. Arbitrage check: {b['buy_yes']} Yes {b['yes_ask']:.3f} + {b['buy_no']} No {b['no_ask']:.3f} + fees = {b['total_cost']:.3f} "
              f"for a $1 payout -> {'ARBITRAGE ' if C['arbitrage_now'] else 'no arbitrage now; '}"
              f"{'locks ' + format(b['locked_profit_per_pair'] * 100, '.1f') + ' cents' if C['arbitrage_now'] else 'prices would need to diverge ' + format(C['gap_needed_cents'], '.1f') + ' more cents'}"
              f" (same rule text: {C['same_rule']})")
    figures(res)
    (OUT / "phase11.json").write_text(json.dumps(res, indent=1, default=float))
    print(f"\nwrote {OUT / 'phase11.json'} and figures/p11_*.png")


def figures(res):
    e, A, B = res["ensemble"], res["strategy_A_value_bet"], res["strategy_B_hedge"]
    g, pdf = np.array(e["grid"]), np.array(e["pdf"])
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(g, pdf, color="C3", lw=2.4, label=f"ensemble of {e['n_versions']} model versions")
    m = g >= 2.0
    ax.fill_between(g[m], pdf[m], color="C3", alpha=0.18, label=f"area ≥ 2.00°C = our estimate {e['p_yes']:.0%}")
    ax.axvline(2.0, color="#eab308", lw=2)
    ax.axvline(e["pdf_mean_peak"], color="k", ls="--", lw=1.2, label=f"PDF mean {e['pdf_mean_peak']:.2f}°C")
    ax.set(xlim=(1.4, 2.8), xlabel="highest contract reading 2027-2049 (°C above 1850-1900)", ylabel="probability density",
           title=f"Our ensemble PDF: {e['p_yes']:.0%} vs Kalshi {res['kalshi']['mid']:.0%}")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "p11_1_ensemble_pdf.png", dpi=130); plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ps = np.linspace(0.4, 1.0, 61)
    ax.plot(ps * 100, (ps - A["all_in_cost"]) * 100, color="k")
    ax.axhline(0, color="grey", lw=0.8)
    ax.axvline(A["all_in_cost"] * 100, color="#eab308", ls="--", label=f"break-even = Kalshi cost {A['all_in_cost']:.0%}")
    ax.plot(A["our_p"] * 100, A["edge_per_contract"] * 100, "o", color="C3", ms=10, label=f"ensemble mean {A['our_p']:.0%}")
    if A["p_ipcc"] is not None:
        ax.plot(A["p_ipcc"] * 100, A["ev_if_ipcc_view"] * 100, "s", color="C0", ms=8, label=f"IPCC-calibrated {A['p_ipcc']:.0%}")
    ax.set(xlabel="your probability of 2°C before 2050 (%)", ylabel="expected profit per $1 contract (cents)",
           title="Buying Yes: profitable only if you believe more than the market")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "p11_2_edge.png", dpi=130); plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4.5))
    labels = ["2°C reached", "2°C not reached"]
    a_vals = [A["profit_if_yes"], A["loss_if_no"]]
    o = list(B["outcomes"].values())
    b_vals = [o[0], o[1]]
    x = np.arange(2)
    ax.bar(x - 0.2, a_vals, 0.4, color="C3", label="A: Yes only ($1,000)")
    ax.bar(x + 0.2, b_vals, 0.4, color="C0", label="B: 70% Yes + 30% No on CO₂ ≥ 445 (CO₂ stays below)")
    for xi, v in zip(list(x - 0.2) + list(x + 0.2), a_vals + b_vals):
        ax.annotate(f"${v:+,.0f}", (xi, v), ha="center", va="bottom" if v >= 0 else "top", fontsize=9)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x, labels)
    ax.set(ylabel="profit / loss ($)", title="Hypothetical $1,000: the hedge gives up some upside to soften the loss")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "p11_3_payoffs.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    main()
