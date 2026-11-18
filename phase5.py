"""Phase 5: 2026 nowcast (+ check vs Kalshi KXGTEMP-26), P(Yes) from the nowcast state, and how well
KXWARMING-50 hedges a hypothetical climate-damage exposure.

    python phase5.py      # uses the latest market snapshot (python market.py fetches a new one)

Analysis only. The hedge is for a hypothetical exposure; nothing here is a recommendation to trade.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import hedge as hg
import pricing as pc
from calibrate import fit_version
from market import MKT, latest_snapshot, walk_book
from model import YEAR0, Inputs, Params
from nowcast import (MONTHLY_SETS, backtest, fit_momentum, load_monthly, monthly_signal, nowcast_year,
                     p_kxgtemp, shifts)
from observations import DATASETS
from phase3 import K_PATHS, M_DRAWS, SPECS, climate_posteriors, kaya_setup, run_cell, setup, wsummary

HERE = Path(__file__).resolve().parent
FIG = HERE / "figures"
OUT = HERE / "results"
HEAD = "Kaya randomised + 2019-24 weighting"
CELLS = [HEAD, "Falling (SSP1-2.6-like)", "Flat (SSP2-4.5-like)", "Rising (SSP3-7.0-like)", "Doubling (SSP5-8.5-like)"]
HEDGE_CELLS = [(HEAD, "ipcc"), (HEAD, "history"), ("Flat (SSP2-4.5-like)", "ipcc"), ("Falling (SSP1-2.6-like)", "ipcc")]
N_PATHS = M_DRAWS * K_PATHS


def kx_quote(snap):
    ev = json.loads((MKT / snap["dir"] / "kxgtemp_26.json").read_text())
    m = (ev.get("event", {}).get("markets") or ev.get("markets"))[0]
    return {"ticker": m["ticker"], "bid": float(m["yes_bid_dollars"]), "ask": float(m["yes_ask_dollars"]),
            "last": float(m["last_price_dollars"]), "volume": float(m["volume_fp"]),
            "open_interest": float(m["open_interest_fp"]), "rule": m.get("rules_primary")}


def nowcast_state(st, inp, n_paths=N_PATHS, seed=55):
    """The 2026 starting state used by Phases 5 and 10: nowcast draws of the 2026 common signal,
    late-year momentum, and the per-path start dict for phase3.run_draws."""
    mon, (days, era5_last) = load_monthly()
    bt_raw, rms = backtest(mon, days)
    bt_cal, rms_cal = backtest(mon, days, total_scale=rms)
    nc = nowcast_year(2026, mon, days, total_scale=rms)
    sh = shifts()
    delta = dict(zip(DATASETS, st["off"]["delta"]))
    ann_rb = {k: nc[k]["draws"] - sh[k] for k in MONTHLY_SETS}
    q4_rb = {k: nc[k]["q4_draws"] - sh[k] for k in MONTHLY_SETS}
    sig26 = np.mean([ann_rb[k] - delta[k] for k in MONTHLY_SETS], axis=0)
    m26 = np.mean([q4_rb[k] - delta[k] for k in MONTHLY_SETS], axis=0) - sig26
    p_kx = p_kxgtemp(nc["giss"]["draws"])

    # momentum: does a warm late year (Q4 above the annual mean) carry into next year?
    msig = monthly_signal(mon, sh, delta)
    full = sorted({y for (y, m) in msig if all((y, mm) in msig for mm in range(1, 13))})
    ann_m = {y: float(np.mean([msig[(y, mm)] for mm in range(1, 13)])) for y in full}
    m_hist = {y: float(np.mean([msig[(y, mm)] for mm in (10, 11, 12)])) - ann_m[y] for y in full}
    fitA = fit_version(Params(), st["years"], st["S"], (1880, 2025), inp)
    r_hist = {y: ann_m[y] - float(fitA.model_T[y - YEAR0]) for y in full}
    mom = fit_momentum(r_hist, m_hist, (1960, 2025))
    use_mom = abs(mom["t_phi2"]) > 2

    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(sig26), n_paths)
    start = {"year": 2026, "signal": sig26[pick],
             "momentum": {"phi1": mom["phi1"], "phi2": mom["phi2"], "m": m26[pick]} if use_mom else None}
    return {"mon": mon, "days": days, "era5_last": era5_last, "bt_raw": bt_raw, "rms": rms, "bt_cal": bt_cal,
            "rms_cal": rms_cal, "nc": nc, "sh": sh, "ann_rb": ann_rb, "sig26": sig26, "m26": m26, "p_kx": p_kx,
            "fitA": fitA, "mom": mom, "use_mom": use_mom, "start": start}


def main():
    FIG.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    snap = latest_snapshot()
    kx = kx_quote(snap)
    inp = Inputs.load()
    st = setup(inp)
    posts, _, _ = climate_posteriors(st["grid"])
    ks = kaya_setup(st, inp)

    # ================================================================ A. nowcast
    ns = nowcast_state(st, inp)
    mon, days, era5_last = ns["mon"], ns["days"], ns["era5_last"]
    bt_raw, rms, bt_cal, rms_cal = ns["bt_raw"], ns["rms"], ns["bt_cal"], ns["rms_cal"]
    nc, sh, ann_rb, sig26, m26 = ns["nc"], ns["sh"], ns["ann_rb"], ns["sig26"], ns["m26"]
    p_kx, fitA, mom, use_mom, start = ns["p_kx"], ns["fitA"], ns["mom"], ns["use_mom"], ns["start"]

    # ================================================================ A5. P(Yes) from the nowcast state
    p3 = json.loads((OUT / "phase3.json").read_text())["headline"]
    yc = walk_book(snap["yes_asks"], 10)["all_in_per_contract"]
    ncost = walk_book(snap["no_asks"], 10)["all_in_per_contract"]
    lo, hi = pc.no_trade_band(yc, ncost, 1.0, 1.0)
    table, store = {}, {}
    for cv in ("history", "ipcc"):
        for label in CELLS:
            kind, wsd = SPECS[label]
            out, idx = run_cell(st, posts[cv], kind, ks, wsd, inp=inp, start=start)
            s = wsummary(out["yes"], out["first"], out["w"])
            s["p_yes_2048"] = float((out["w"] * (np.nan_to_num(out["first"], nan=9999) <= 2048)).sum() / out["w"].sum())
            s["p_yes_2025_start"] = p3[label][cv]["p_yes"]
            P = s["p_yes"]
            s["position"] = "above band" if P > hi else ("below band" if P < lo else "inside band")
            table.setdefault(label, {})[cv] = s
            store[(label, cv)] = out
    # sensitivity: no momentum term; and the 2025 start for the fan chart
    o_nm, _ = run_cell(st, posts["ipcc"], "kaya", ks, 0.02, inp=inp, start={**start, "momentum": None})
    no_mom = wsummary(o_nm["yes"], o_nm["first"], o_nm["w"])
    o_25, _ = run_cell(st, posts["ipcc"], "kaya", ks, 0.02, inp=inp)

    # ================================================================ B. climate-damage hedge
    dmg = hg.load_impact()
    a_med = hg.median_damage_coef(dmg)
    rng_a = np.random.default_rng(77)
    c71, c76 = hg.capacity(snap["yes_asks"], 0.71), hg.capacity(snap["yes_asks"], 0.76)
    hedge_res = {}
    for key in HEDGE_CELLS:
        out = store[key]
        w, yes = out["w"], out["yes"].astype(float)
        T26, S = out["s_start"], out["S"].astype(float)
        T49 = S[:, -1]
        a = hg.sample_damage_coef(len(w), rng_a, dmg)
        L = hg.loss_2049(a, T49, T26)
        Lm = hg.loss_2049(a_med, T49, T26)
        rows = {
            "linear temperature swap, damage coef fixed": hg.min_var_hedge(Lm, T49, w),
            "linear temperature swap, damage coef random": hg.min_var_hedge(L, T49, w),
            "KXWARMING-50 Yes, damage coef fixed": hg.min_var_hedge(Lm, yes, w),
            "KXWARMING-50 Yes, damage coef random": hg.min_var_hedge(L, yes, w),
        }
        Lc = hg.loss_cumulative(a, S, T26)
        rows["KXWARMING-50 Yes vs cumulative 2027-49 damages"] = hg.min_var_hedge(Lc, yes, w)
        h = rows["KXWARMING-50 Yes, damage coef random"]["h"]
        P = table[key[0]][key[1]]["p_yes"]
        mean_L_yes = float((w * L * yes).sum() / (w * yes).sum())
        mean_L_no = float((w * L * (1 - yes)).sum() / (w * (1 - yes)).sum())
        hedge_res[f"{key[0]} | {key[1]}"] = {
            "p_yes": P, "rows": rows,
            "h_contracts_per_1M_income": h,
            "expected_cost_per_1M": h * (yc - P),           # delta 0: all-in cost minus expected payout
            "mean_loss_if_yes": mean_L_yes, "mean_loss_if_no": mean_L_no,
            "capacity_contracts_le_0.71": c71, "capacity_contracts_le_0.76": c76,
            "max_income_hedgeable_le_0.71_$M": c71 / h if h > 0 else float("inf"),
            "max_income_hedgeable_le_0.76_$M": c76 / h if h > 0 else float("inf"),
            "_L": L, "_T49": T49, "_yes": yes, "_w": w,
        }

    # ================================================================ print
    print(f"\nSnapshot {snap['dir']}: KXWARMING-50 Yes {snap['yes_bid']:.2f}/{snap['yes_ask']:.2f}; "
          f"{kx['ticker']} {kx['bid']:.3f}/{kx['ask']:.3f} (vol {kx['volume']:.0f}, OI {kx['open_interest']:.0f})")
    print(f"ERA5 data through {era5_last}; monthly: " + ", ".join(f"{k} to {max(mon[k])}" for k in MONTHLY_SETS))

    print("\nA. 2026 nowcast (annual; native baseline -> 1850-1900):")
    for k in MONTHLY_SETS:
        d, b = nc[k], nc[k]["bridge"]
        print(f"  {k:8s} observed months {d['months_obs'][0]}-{d['months_obs'][-1]}, filled {d['months_filled']}  "
              f"bridge a={b['alpha']:.3f} b={b['beta']:.3f} s={b['s']:.3f} rho={b['rho']:.2f}  "
              f"2026 {d['draws'].mean():.3f}±{d['draws'].std():.3f} -> {ann_rb[k].mean():.3f}")
    print(f"  common signal 2026: {sig26.mean():.3f} ± {sig26.std():.3f} (2025 was {st['s_2025']:.3f}); "
          f"Q4 minus annual {m26.mean():+.3f}")
    print(f"  shared bridge-error correlation {nc['_shared_corr']:.2f}; spread scaled x{rms:.2f} from back-test")
    print("  back-test (as of ~8 Nov each year): " + "; ".join(
        f"{r['year']} {r['dataset']} z {r['z']:+.1f}" for r in bt_raw))
    print(f"  RMS z raw {rms:.2f} -> after scaling {rms_cal:.2f}; outside ±2sd: "
          f"{sum(abs(r['z']) > 2 for r in bt_cal)}/{len(bt_cal)}")
    print(f"\n  KXGTEMP-26 ({kx['rule'][:90]}...)")
    print(f"  model P = {p_kx:.3f}   market {kx['bid']:.3f}/{kx['ask']:.3f}   gap {p_kx - (kx['bid'] + kx['ask']) / 2:+.3f}")
    print(f"\n  momentum fit 1960-2025: r(Y+1) = {mom['c']:+.3f} + {mom['phi1']:.2f} r(Y) + {mom['phi2']:.2f} (Q4-annual)(Y); "
          f"t(phi2) = {mom['t_phi2']:.1f} -> {'USED' if use_mom else 'not used'} for 2027 "
          f"(mean shift {mom['phi2'] * m26.mean():+.3f} C)" if use_mom else
          f"\n  momentum fit: phi2 {mom['phi2']:.2f}, t {mom['t_phi2']:.1f} -> not used")

    print(f"\nA5. P(KXWARMING-50 = Yes) from the 2026 nowcast vs the 2025 start (band after costs [{lo:.3f}, {hi:.3f}]):")
    print(f"  {'emissions':38s} {'history 2025->2026':>20s} {'IPCC 2025->2026':>18s}  IPCC <=2048  IPCC position")
    for label in CELLS:
        h_, i_ = table[label]["history"], table[label]["ipcc"]
        print(f"  {label:38s} {h_['p_yes_2025_start']:7.3f} -> {h_['p_yes']:.3f}    {i_['p_yes_2025_start']:7.3f} -> {i_['p_yes']:.3f}"
              f"    {i_['p_yes_2048']:.3f}    {i_['position']}")
    print(f"  IPCC headline without the momentum term: {no_mom['p_yes']:.3f}")

    print("\nB. Hedging a hypothetical climate-damage exposure with KXWARMING-50 (per $1M of annual income):")
    print(f"  damage coef a: median {a_med:.3f} %/C^2 (Impact {-a_med * 6.25:.2f}% at 2.5 C); loss = a(T49^2 - T26^2)")
    for name, r in hedge_res.items():
        print(f"  [{name}]  P(Yes) {r['p_yes']:.3f}; mean 2049 loss if Yes ${r['mean_loss_if_yes']:,.0f} vs if No ${r['mean_loss_if_no']:,.0f}")
        for rn, v in r["rows"].items():
            print(f"     {rn:48s} R2 {v['r2']:.3f}  sd ${v['sd_unhedged']:,.0f} -> ${v['sd_hedged']:,.0f}  h {v['h']:,.1f}")
        print(f"     min-var hedge {r['h_contracts_per_1M_income']:,.0f} contracts; expected cost ${r['expected_cost_per_1M']:+,.0f}; "
              f"book capacity {r['capacity_contracts_le_0.71']:.0f} (<=0.71) / {r['capacity_contracts_le_0.76']:.0f} (<=0.76) contracts "
              f"= ${r['max_income_hedgeable_le_0.71_$M']:.1f}M / ${r['max_income_hedgeable_le_0.76_$M']:.1f}M of income")

    figures(nc, sh, ann_rb, p_kx, kx, store, o_25, hedge_res, sig26)

    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items() if not str(k).startswith("_") and k not in ("draws", "q4_draws")}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, np.generic):
            return o.item()
        return o
    results = {
        "snapshot": snap["dir"], "kxgtemp_26": kx, "era5_last_day": era5_last,
        "nowcast": {k: {"months_obs": nc[k]["months_obs"], "months_filled": nc[k]["months_filled"],
                        "bridge": nc[k]["bridge"], "native_mean": float(nc[k]["draws"].mean()),
                        "native_sd": float(nc[k]["draws"].std()), "rebased_mean": float(ann_rb[k].mean())}
                    for k in MONTHLY_SETS},
        "signal_2026": {"mean": float(sig26.mean()), "sd": float(sig26.std()), "q4_minus_annual": float(m26.mean())},
        "shared_corr": nc["_shared_corr"], "sd_scale": rms,
        "backtest": {"raw": bt_raw, "calibrated": bt_cal, "rms_raw": rms, "rms_calibrated": rms_cal},
        "p_kxgtemp_model": p_kx, "momentum": mom, "momentum_used": use_mom,
        "p_yes": table, "band": [lo, hi], "ipcc_headline_no_momentum": no_mom,
        "hedge": clean(hedge_res), "damage_coef_median": a_med,
    }
    (OUT / "phase5.json").write_text(json.dumps(clean(results), indent=1, default=float))
    write_slider_context(st, inp, sig26, m26, mom, use_mom, fitA)
    print(f"\nwrote {OUT / 'phase5.json'}, results/slider_context.json and figures/p5_*.png")


def write_slider_context(st, inp, sig26, m26, mom, use_mom, fitA):
    """Everything the in-browser what-if model needs, plus Python reference values to check it against."""
    from model import run
    import scenarios as sc
    from phase3 import run_draws
    yrs = st["years"]
    sel = (yrs >= 2006) & (yrs <= 2025)
    off = st["off"]
    ar = {"c": 0.0, "phi": fitA.ar1["phi"], "sigma": fitA.ar1["sigma"]}
    # Python reference: class-model parameters, HW5 template economy, same simplified noise as the page
    n = 40_000
    rng = np.random.default_rng(88)
    pick = rng.integers(0, len(sig26), n)
    start = {"year": 2026, "signal": sig26[pick],
             "momentum": {"phi1": mom["phi1"], "phi2": mom["phi2"], "m": m26[pick]} if use_mom else None}
    out = run_draws(Params(), ar, np.ones(1), st["s_2025"], off, K=n, seed=9, inp=inp,
                    anchor=(yrs, st["S"]), start=start)
    p_ref = float(out["yes"].mean())
    r = run(Params(), inp)
    T = r.temp_atmos - r.temp_atmos[1850 - YEAR0: 1901 - YEAR0].mean()
    actual = st["actual"]
    ctx = {
        "anchor_years": [int(y) for y in yrs[sel]], "anchor_signal": [float(v) for v in st["S"][sel]],
        "signal_2026": {"mean": float(sig26.mean()), "sd": float(sig26.std())},
        "q4_minus_annual_2026": float(m26.mean()),
        "momentum": {"used": bool(use_mom), "phi1": mom["phi1"], "phi2": mom["phi2"]},
        "ar1": {"phi": fitA.ar1["phi"], "sigma": fitA.ar1["sigma"]},
        "datasets": list(DATASETS),
        "offsets": {"delta": off["delta"].tolist(), "tau": off["tau"].tolist(), "rho": off["rho"].tolist(),
                    "last_dev": off["last_dev"].tolist()},
        "scenario_paths_mtc": {s: sc.path(s, actual).tolist() for s in sc.NAMES},
        "reference": {"template_temp_1750_2100": [None if t != t else float(t) for t in T],
                      "template_p_yes": p_ref, "n_paths": n},
    }
    (OUT / "slider_context.json").write_text(json.dumps(ctx))


def figures(nc, sh, ann_rb, p_kx, kx, store, o_25, hedge_res, sig26):
    cols = {"giss": "C0", "noaa": "C2", "hadcrut": "C4"}
    # 1 monthly 2026
    fig, ax = plt.subplots(figsize=(10, 4.5))
    m = np.arange(1, 13)
    for k in MONTHLY_SETS:
        d = nc[k]
        mm, sd = d["month_mean"] - sh[k], d["month_sd"]
        obs = np.isin(m, d["months_obs"])
        ax.plot(m[obs], mm[obs], "o-", color=cols[k], label=f"{k} observed (2026 annual {ann_rb[k].mean():.2f})")
        f = ~obs
        if f.any():
            first = np.where(f)[0][0]
            idx = np.r_[first - 1, np.where(f)[0]] if first > 0 else np.where(f)[0]
            ax.plot(m[idx], mm[idx], "--", color=cols[k])
            ax.errorbar(m[f], mm[f], yerr=2 * sd[f], fmt="s", color=cols[k], mfc="none", capsize=3)
    ax.set(xticks=m, xlabel="month of 2026", ylabel="°C above 1850-1900",
           title="2026 so far (solid) and ERA5-bridged months (hollow, ±2 sd)")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "p5_1_nowcast_2026.png", dpi=130); plt.close(fig)

    # 2 KXGTEMP-26
    fig, ax = plt.subplots(figsize=(8, 4))
    g = np.floor(nc["giss"]["draws"] * 100 + 0.5) / 100
    vals, cnt = np.unique(g, return_counts=True)
    ax.bar(vals, cnt / cnt.sum(), width=0.008, color=["C3" if v > 1.285 else "grey" for v in vals])
    ax.axvline(1.285, color="k", ls="--", lw=1, label="needs ≥ 1.29 (record 1.28)")
    ax.set(xlabel="GISS 2026 annual (native, rounded as published)", ylabel="share of draws",
           title=f"KXGTEMP-26: model {p_kx:.2f} vs market {kx['bid']:.2f}/{kx['ask']:.2f}")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "p5_2_kxgtemp26.png", dpi=130); plt.close(fig)

    # 3 fan: nowcast start vs 2025 start (IPCC headline)
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for out, col, lab in ((o_25, "grey", "2025 start"), (store[(HEAD, "ipcc")], "C3", "2026 nowcast start")):
        q, ys = out["fan"], out["sim_years"]
        ax.fill_between(ys, q[:, 0], q[:, 4], color=col, alpha=0.15)
        ax.plot(ys, q[:, 2], color=col, lw=2, label=f"{lab}: median, 5-95%")
    ax.axhline(2.0, color="orange")
    ax.set(xlabel="year", ylabel="second-highest dataset, °C", title="IPCC-calibrated headline: effect of starting from 2026")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "p5_3_fan_nowcast.png", dpi=130); plt.close(fig)

    # 4 loss vs temperature, coloured by contract outcome
    r = hedge_res[f"{HEAD} | ipcc"]
    sel = np.random.default_rng(0).choice(len(r["_L"]), 6000, replace=False)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for yv, col, lab in ((1.0, "C3", "contract Yes"), (0.0, "C0", "contract No")):
        s = sel[r["_yes"][sel] == yv]
        ax.scatter(r["_T49"][s], r["_L"][s] / 1e3, s=4, alpha=0.4, color=col, label=lab)
    ax.set(xlabel="common-signal temperature 2049 (°C above 1850-1900)", ylabel="2049 loss per \\$1M income (\\$K)",
           title=f"Hypothetical damage exposure vs contract outcome (R² of Yes hedge "
                 f"{r['rows']['KXWARMING-50 Yes, damage coef random']['r2']:.2f})")
    ax.legend(fontsize=8, markerscale=3)
    fig.tight_layout(); fig.savefig(FIG / "p5_4_loss_vs_outcome.png", dpi=130); plt.close(fig)

    # 5 basis-risk breakdown
    fig, ax = plt.subplots(figsize=(10, 4.5))
    names = list(r["rows"])
    x = np.arange(len(names))
    for off, key, col in ((-0.2, f"{HEAD} | ipcc", "C3"), (0.2, f"{HEAD} | history", "C0")):
        ax.bar(x + off, [hedge_res[key]["rows"][n]["r2"] for n in names], 0.4, color=col, label=key.split(" | ")[1])
    ax.set_xticks(x, [n.replace(", ", ",\n").replace(" vs ", "\nvs ") for n in names], fontsize=7)
    ax.set(ylabel="hedge effectiveness R²", ylim=(0, 1), title="How much of the damage risk each instrument removes")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "p5_5_basis_risk.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    main()
