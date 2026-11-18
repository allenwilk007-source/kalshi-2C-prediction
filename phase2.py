"""Phase 2 end to end: P(KXWARMING-50 resolves Yes) from the course model + calibrated noise.

    python phase2.py            # results table, sensitivities, back-test, figures, results/phase2.json

Kaya path is fixed at the HW5 template here; Phase 3 adds parameter uncertainty.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from calibrate import fit_version, fit_version_b
from model import YEAR0, Inputs, Params
from noise import (DATASETS, common_signal, contract_outcome, dataset_offsets, fit_student_t_df,
                   simulate, summarize)
from observations import load

HERE = Path(__file__).resolve().parent
FIG = HERE / "figures"
OUT = HERE / "results"
SIM_YEARS = np.arange(2026, 2050)          # contract: any year before 1 Jan 2050
LAST_OBS = 2025
N = 100_000
FILL = 990.0                               # Mt C/yr, 2020 gap: 11,432 historical - 10,442 Kaya
VOLCANO_YEARS = (1883, 1884, 1963, 1964, 1982, 1983, 1991, 1992)
KALSHI = {"bid": 0.65, "ask": 0.69, "last": 0.69, "checked": "2026-11-08"}


def build(version="A", fill=0.0, giss_method="align", berkeley_column="air",
          offset_window=(1996, 2025), volcano_mask=False, dist="auto", fit_window=(1880, 2025),
          inp=None):
    """Everything up to (but not including) simulation for one configuration."""
    inp = inp or Inputs.load()
    years, X = load(giss_method, berkeley_column)
    off = dataset_offsets(years, X, offset_window)
    S = common_signal(X, off["delta"])
    mask = np.isin(years, VOLCANO_YEARS) if volcano_mask else None
    base = Params(land_use_fill_mtc=fill)
    if version == "A":
        fit = fit_version(base, years, S, fit_window, inp, mask=mask)
        report = None
    else:
        fit, report = fit_version_b(base, years, S, fit_window, inp)
        if volcano_mask:
            fit = fit_version(fit.params, years, S, fit_window, inp, mask=mask)
    sel = (years >= fit_window[0]) & (years <= fit_window[1])
    ar = fit.ar1
    use_t = (dist == "t") or (dist == "auto" and ar["excess_kurtosis"] > 1.0)
    t_df = fit_student_t_df(ar["eps"], ar["sigma"])[0] if use_t else None
    return {"years": years, "X": X, "S": S, "off": off, "fit": fit, "report": report,
            "dist": "t" if use_t else "normal", "t_df": t_df, "fit_sel": sel}


def simulate_cfg(b, start_year=LAST_OBS, sim_years=SIM_YEARS, n=N, seed=0):
    fit, years = b["fit"], b["years"]
    r0 = float(fit.resid[years == start_year][0])
    model_future = fit.model_T[sim_years - YEAR0]
    X, S = simulate(model_future, fit.ar1, r0, b["off"], n=n, seed=seed, dist=b["dist"], t_df=b["t_df"])
    return X, S, r0


def outcomes(b, X):
    years, S = b["years"], b["S"]
    hist = S[(years > LAST_OBS - 19) & (years <= LAST_OBS)]
    out = {}
    for rule in ("2of4", "any1", "mean4", "20yr"):
        yes, first = contract_outcome(X, SIM_YEARS, rule=rule, history=hist)
        out[rule] = summarize(yes, first)
        if rule == "2of4":
            out["_first"] = first
    return out


def backtest(version, inp):
    """Fit on data to 1999, simulate 2000-2025 from the 1999 state, compare with what happened."""
    b = build(version, fit_window=(1880, 1999), inp=inp)
    yrs_bt = np.arange(2000, 2026)
    _, Ssim, _ = simulate_cfg(b, start_year=1999, sim_years=yrs_bt, n=20_000, seed=11)
    obs = b["S"][np.isin(b["years"], yrs_bt)]
    lo, hi = np.percentile(Ssim, [5, 95], axis=0)
    coverage = float(np.mean((obs >= lo) & (obs <= hi)))
    prior_max = b["S"][(b["years"] <= 1999)].max()

    def records(series):
        m, count = prior_max, 0
        for v in series:
            if v > m:
                count, m = count + 1, v
        return count
    sim_records = np.array([records(row) for row in Ssim[:5000]])
    return {
        "version": version,
        "p2_used": float(b["fit"].params.p2_sensitivity),
        "coverage_5_95": coverage,
        "obs_records": records(obs),
        "sim_records_median": float(np.median(sim_records)),
        "sim_records_p10_p90": [float(np.percentile(sim_records, 10)), float(np.percentile(sim_records, 90))],
        "obs_sd_annual_change": float(np.std(np.diff(obs), ddof=1)),
        "sim_sd_annual_change": float(np.mean(np.std(np.diff(Ssim, axis=1), axis=1, ddof=1))),
        "obs_mean_2016_2025": float(obs[-10:].mean()),
        "sim_median_mean_2016_2025": float(np.median(Ssim[:, -10:].mean(axis=1))),
        "band": (lo, hi, obs, yrs_bt),
    }


def main():
    FIG.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    inp = Inputs.load()
    results = {"kalshi_reference": KALSHI, "n_paths": N, "variants": {}, "sensitivities": {}}

    # ---------------------------------------------------------- headline variants
    variants = {"A course model": ("A", 0.0), "A + emissions gap filled": ("A", FILL),
                "B fitted": ("B", 0.0), "B + emissions gap filled": ("B", FILL)}
    built, sims = {}, {}
    for label, (v, fill) in variants.items():
        b = build(v, fill, inp=inp)
        X, Ssim, r0 = simulate_cfg(b)
        o = outcomes(b, X)
        built[label], sims[label] = b, (X, Ssim, o["_first"])
        fit = b["fit"]
        results["variants"][label] = {
            "p1": float(fit.params.p1_adjust_speed), "p2": float(fit.params.p2_sensitivity),
            "implied_ecs": float(fit.params.ecs()), "land_use_fill_mtc": fill,
            "ar1": {k: fit.ar1[k] for k in ("c", "phi", "sigma", "mu", "excess_kurtosis", "loglik", "n")},
            "noise_dist": b["dist"], "t_df": b["t_df"], "r0_2025": r0,
            "model_2025": float(fit.model_T[2025 - YEAR0]), "model_2049": float(fit.model_T[2049 - YEAR0]),
            "fitB_report": b["report"],
            "rules": {k: v for k, v in o.items() if not k.startswith("_")},
        }

    off = built["A course model"]["off"]
    results["dataset_offsets"] = {k: {"delta": float(off["delta"][i]), "tau": float(off["tau"][i]),
                                      "rho": float(off["rho"][i])} for i, k in enumerate(DATASETS)}

    # ---------------------------------------------------------- sensitivities (2-of-4 rule)
    sens = {
        "GISS baseline = own 1880-1900": dict(giss_method="own1880"),
        "Berkeley water-temperature column": dict(berkeley_column="water"),
        "Offsets from 2006-2025": dict(offset_window=(2006, 2025)),
        "Volcano years masked in AR(1)": dict(volcano_mask=True),
        "Student-t shocks (forced)": dict(dist="t"),
    }
    for label, kw in sens.items():
        results["sensitivities"][label] = {}
        for v in ("A", "B"):
            b = build(v, inp=inp, **kw)
            X, _, _ = simulate_cfg(b)
            yes, first = contract_outcome(X, SIM_YEARS)
            results["sensitivities"][label][v] = summarize(yes, first)

    # ---------------------------------------------------------- back-test
    bts = {v: backtest(v, inp) for v in ("A", "B")}
    results["backtest"] = {v: {k: val for k, val in bt.items() if k != "band"} for v, bt in bts.items()}

    # ---------------------------------------------------------- 2024 spot check
    yrs, X = built["A course model"]["years"], built["A course model"]["X"]
    i24 = int(np.where(yrs == 2024)[0][0])
    results["spot_check_2024"] = {k: float(X[i, i24]) for i, k in enumerate(DATASETS)}
    results["spot_check_2024"]["mean"] = float(np.mean(X[:, i24]))

    # ---------------------------------------------------------- print
    print("\nKXWARMING-50: P(second-highest of 4 datasets >= 2.00 C in any year 2026-2049)")
    print(f"{'variant':28s} {'p2':>5s} {'ECS':>5s} {'P(Yes)':>8s} {'MC se':>7s} {'median yr':>9s} {'10-90%':>11s}")
    for label, r in results["variants"].items():
        s = r["rules"]["2of4"]
        print(f"{label:28s} {r['p2']:5.3f} {r['implied_ecs']:5.2f} {s['p_yes']:8.3f} {s['mc_se']:7.4f} "
              f"{s['first_year_median']:9.0f} {s['first_year_p10']:5.0f}-{s['first_year_p90']:4.0f}")
    print(f"{'Kalshi (reference only)':28s} {'':5s} {'':5s} {KALSHI['bid']:.2f}-{KALSHI['ask']:.2f}")

    print("\nSame paths, other resolution rules (P(Yes) by 2049):")
    print(f"{'variant':28s} {'2of4':>6s} {'any1':>6s} {'mean4':>6s} {'20yr':>6s}")
    for label, r in results["variants"].items():
        print(f"{label:28s} " + " ".join(f"{r['rules'][k]['p_yes']:6.3f}" for k in ("2of4", "any1", "mean4", "20yr")))

    print("\nSensitivities (2-of-4 rule):")
    for label, d in results["sensitivities"].items():
        print(f"  {label:36s} A {d['A']['p_yes']:.3f}   B {d['B']['p_yes']:.3f}")

    print("\nNoise and offsets:")
    for label, r in results["variants"].items():
        a = r["ar1"]
        print(f"  {label:28s} phi {a['phi']:.3f} sigma {a['sigma']:.3f} mu {a['mu']:+.3f} "
              f"kurt {a['excess_kurtosis']:+.2f} r0(2025) {r['r0_2025']:+.3f} dist {r['noise_dist']}")
    for k, d in results["dataset_offsets"].items():
        print(f"  {k:9s} delta {d['delta']:+.3f} tau {d['tau']:.3f} rho {d['rho']:.2f}")
    rb = results["variants"]["B fitted"]["fitB_report"]
    print(f"  B fit: p2={rb['chosen']['p2']} (p1 LR stat {rb['lr_stat_p1']:.2f}, use_p1={rb['use_p1']}), "
          f"loglik gain vs A {rb['loglik_gain_vs_A']:.2f}, grid edge {rb['on_grid_edge']}")

    print("\nBack-test (fit to 1999, simulate 2000-2025):")
    for v, bt in results["backtest"].items():
        print(f"  {v}: coverage {bt['coverage_5_95']:.2f} (target ~0.90) | records obs {bt['obs_records']} "
              f"sim median {bt['sim_records_median']:.0f} | sd(annual change) obs {bt['obs_sd_annual_change']:.3f} "
              f"sim {bt['sim_sd_annual_change']:.3f} | mean 2016-25 obs {bt['obs_mean_2016_2025']:.2f} "
              f"sim {bt['sim_median_mean_2016_2025']:.2f}")
    sc = results["spot_check_2024"]
    print("\n2024 on 1850-1900 baseline: " + ", ".join(f"{k} {v:.2f}" for k, v in sc.items()))

    # ---------------------------------------------------------- figures
    figures(built, sims, bts)

    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items() if k != "eps"}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, np.generic):
            return o.item()
        return o
    (OUT / "phase2.json").write_text(json.dumps(clean(results), indent=1))
    print(f"\nwrote {OUT / 'phase2.json'} and figures in {FIG}")


def figures(built, sims, bts):
    colors = {"giss": "#1f77b4", "noaa": "#2ca02c", "berkeley": "#d62728", "hadcrut": "#9467bd"}
    A, B = built["A course model"], built["B fitted"]
    yrs, X = A["years"], A["X"]

    # 1. observations vs models
    fig, ax = plt.subplots(figsize=(10, 5))
    for i, k in enumerate(DATASETS):
        ax.plot(yrs, X[i], lw=0.9, color=colors[k], label=k)
    my = A["fit"].model_years
    m = (my >= 1850) & (my <= 2049)
    ax.plot(my[m], A["fit"].model_T[m], "k-", lw=2, label="model A (course, p2=1.15)")
    ax.plot(my[m], B["fit"].model_T[m], "k--", lw=2, label=f"model B (fitted, p2={B['fit'].params.p2_sensitivity:.3f})")
    ax.axhline(2.0, color="orange", lw=1)
    ax.set(title="Observed annual temperature vs course model (1850-1900 baseline)", ylabel="°C", xlim=(1850, 2050))
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "1_obs_vs_model.png", dpi=130); plt.close(fig)

    # 2. residuals + ACF
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4), gridspec_kw={"width_ratios": [3, 1]})
    for b, lab, st in ((A, "A", "-"), (B, "B", "--")):
        r = b["fit"].resid
        a1.plot(yrs, r, st, lw=1, label=f"{lab}: σ={b['fit'].ar1['sigma']:.3f}, φ={b['fit'].ar1['phi']:.2f}")
    s = A["fit"].ar1["sigma"]
    a1.axhspan(-2 * s, 2 * s, color="grey", alpha=0.15)
    a1.axhline(0, color="k", lw=0.5)
    a1.set(title="Residual = observed signal − model", ylabel="°C", xlim=(1850, 2025))
    a1.legend(fontsize=8)
    r = A["fit"].resid[A["fit_sel"]]
    r = r - r.mean()
    acf = [1.0] + [float(np.corrcoef(r[:-k], r[k:])[0, 1]) for k in range(1, 11)]
    a2.bar(range(11), acf, color="grey")
    a2.axhline(1.96 / np.sqrt(len(r)), ls=":", color="k"); a2.axhline(-1.96 / np.sqrt(len(r)), ls=":", color="k")
    a2.set(title=f"ACF of A residuals (lag-1 {acf[1]:.2f})", xlabel="lag (years)")
    fig.tight_layout(); fig.savefig(FIG / "2_residuals.png", dpi=130); plt.close(fig)

    # 3. dataset deviations
    sel = (yrs >= 1996) & np.all(np.isfinite(X), axis=0)
    D = X[:, sel] - X[:, sel].mean(axis=0)
    fig, ax = plt.subplots(figsize=(9, 4))
    for i, k in enumerate(DATASETS):
        ax.plot(yrs[sel], D[i], "o-", ms=3, color=colors[k], label=f"{k} (δ={D[i].mean():+.3f})")
    ax.axhline(0, color="k", lw=0.5)
    ax.set(title="Each dataset minus the 4-dataset mean, 1996-2024", ylabel="°C")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "3_dataset_offsets.png", dpi=130); plt.close(fig)

    # 4. fan charts of the contract statistic (second-highest dataset)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), sharey=True)
    for ax, (label, b) in zip(axes, (("A course model", A), ("B fitted", B))):
        Xs, _, _ = sims[label]
        stat = np.sort(Xs[:20000], axis=1)[:, -2, :]
        qs = np.percentile(stat, [5, 25, 50, 75, 95], axis=0)
        ax.fill_between(SIM_YEARS, qs[0], qs[4], color="C0", alpha=0.15, label="5-95%")
        ax.fill_between(SIM_YEARS, qs[1], qs[3], color="C0", alpha=0.3, label="25-75%")
        ax.plot(SIM_YEARS, qs[2], color="C0", lw=2, label="median")
        for row in stat[:30]:
            ax.plot(SIM_YEARS, row, color="grey", lw=0.4, alpha=0.6)
        obs2 = np.sort(np.nan_to_num(X, nan=-9), axis=0)[-2]
        h = yrs >= 1990
        ax.plot(yrs[h], obs2[h], "k.-", lw=1, label="observed 2nd-highest")
        ax.axhline(2.0, color="orange", lw=1.5)
        p = np.mean(np.isfinite(sims[label][2]))
        ax.set(title=f"{label}: P(Yes) = {p:.2f}", xlim=(1990, 2049), xlabel="year")
        ax.legend(fontsize=7, loc="upper left")
    axes[0].set_ylabel("second-highest dataset, °C above 1850-1900")
    fig.tight_layout(); fig.savefig(FIG / "4_fan_chart.png", dpi=130); plt.close(fig)

    # 5. first-crossing histogram
    fig, ax = plt.subplots(figsize=(9, 4))
    bins = np.arange(2025.5, 2050.5, 1)
    for label, st in (("A course model", "C0"), ("B fitted", "C3")):
        f = sims[label][2]
        ax.hist(f[np.isfinite(f)], bins=bins, weights=np.full(np.isfinite(f).sum(), 1 / len(f)),
                alpha=0.5, color=st, label=f"{label} (never by 2049: {np.mean(~np.isfinite(f)):.2f})")
    ax.set(title="Year the contract would resolve Yes", xlabel="first qualifying year", ylabel="share of paths")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "5_first_crossing.png", dpi=130); plt.close(fig)

    # 6. back-test bands
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)
    for ax, (v, bt) in zip(axes, bts.items()):
        lo, hi, obs, ys = bt["band"]
        ax.fill_between(ys, lo, hi, alpha=0.25, label="simulated 5-95%")
        ax.plot(ys, obs, "k.-", label="observed signal")
        ax.set(title=f"Back-test {v}: fit to 1999, coverage {bt['coverage_5_95']:.2f}", xlabel="year")
        ax.legend(fontsize=8)
    axes[0].set_ylabel("°C above 1850-1900")
    fig.tight_layout(); fig.savefig(FIG / "6_backtest.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    main()
