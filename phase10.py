"""Phase 10: probability density of predicted temperatures across versions of the model, vs Kalshi.

    python phase10.py      # results/phase10.json, figures/p10_*.png

Every version starts from the same 2026 nowcast and is simulated 2027-2049 with Kalshi's exact rule.
Two quantities per simulated future:
  peak     the highest contract reading 2027-2049 (second-highest of the four datasets, rounded to
           0.01 as published). KXWARMING-50 resolves Yes exactly when peak >= 2.00.
  T2049    the 2049 global temperature (common signal across datasets), deg C above 1850-1900.
Model-vs-market comparison only, not a recommendation to trade.
"""
from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import pricing as pc
from market import latest_snapshot, walk_book
from model import Inputs, Params
from phase3 import K_PATHS, M_DRAWS, climate_posteriors, kaya_setup, run_cell, run_draws, setup
from phase5 import nowcast_state

HERE = Path(__file__).resolve().parent
FIG = HERE / "figures"
OUT = HERE / "results"
N_PATHS = M_DRAWS * K_PATHS
GRID = np.round(np.arange(0.80, 3.6001, 0.01), 2)
THRESH = 2.0

# key, label, group
VARIANTS = [
    ("class_hw5", "Class model as taught (HW5 economy)", "model version"),
    ("class_real", "Class settings, emissions matched to real data", "model version"),
    ("history", "Fitted to history", "model version"),
    ("ipcc", "IPCC-calibrated (headline)", "model version"),
    ("blend", "Blend: 50% history + 50% IPCC", "model version"),
    ("ipcc_full", "IPCC, full AR6 width", "sensitivity"),
    ("ipcc_fill", "IPCC + missing land-use emissions", "sensitivity"),
    ("ipcc_nomom", "IPCC, no El Niño carry-over into 2027", "sensitivity"),
    ("ipcc_falling", "IPCC, falling emissions (SSP1-2.6-like)", "emissions"),
    ("ipcc_flat", "IPCC, flat emissions (SSP2-4.5-like)", "emissions"),
    ("ipcc_rising", "IPCC, rising emissions (SSP3-7.0-like)", "emissions"),
    ("ipcc_doubling", "IPCC, doubling emissions (SSP5-8.5-like)", "emissions"),
]


# ---------------------------------------------------------------- statistics
def wquant(x, w, qs):
    o = np.argsort(x)
    c = np.cumsum(w[o])
    c /= c[-1]
    return [float(x[o][min(np.searchsorted(c, q), len(x) - 1)]) for q in qs]


def wkde(x, w, grid=GRID, bw=None):
    """Weighted Gaussian KDE on a grid (density in 1/degC). Silverman bandwidth on the effective n."""
    x, w = np.asarray(x, float), np.asarray(w, float)
    w = w / w.sum()
    mu = float((w * x).sum())
    sd = math.sqrt(float((w * (x - mu) ** 2).sum()))
    ess = 1.0 / float((w ** 2).sum())
    h = bw or max(1.06 * sd * ess ** (-0.2), 0.02)
    # bin to a fine histogram, then smooth: fast and accurate for 100k+ points
    edges = np.arange(grid[0] - 0.6, grid[-1] + 0.6 + 1e-9, 0.0025)
    hist, _ = np.histogram(x, bins=edges, weights=w)
    centres = 0.5 * (edges[1:] + edges[:-1])
    dens = np.zeros(len(grid))
    for i in range(0, len(grid), 64):
        g = grid[i:i + 64, None]
        dens[i:i + 64] = (hist[None, :] * np.exp(-0.5 * ((g - centres[None, :]) / h) ** 2)).sum(axis=1)
    return dens / (h * math.sqrt(2 * math.pi)), h


def summarize(o, mid, band):
    w, peak, t49, yes, first = o["w"], o["peak"], o["t49"], o["yes"], o["first"]
    W = w / w.sum()
    p_yes = float((W * yes).sum())
    p_peak = float((W * (peak >= THRESH - 1e-9)).sum())
    fy = np.isfinite(first)
    q_first = wquant(first[fy], w[fy], (0.1, 0.5, 0.9)) if fy.any() else [None] * 3
    pk = wquant(peak, w, (0.05, 0.25, 0.5, 0.75, 0.95))
    tq = wquant(t49, w, (0.05, 0.25, 0.5, 0.75, 0.95))
    # how far (deg C) the model's peak distribution would have to shift to agree with Kalshi's mid
    shift = THRESH - wquant(peak, w, (1 - mid,))[0]
    lo, hi = band
    return {
        "p_yes": p_yes, "p_peak_ge_2": p_peak, "gap_vs_kalshi_pts": 100 * (p_yes - mid),
        "position": "inside" if lo <= p_yes <= hi else ("above" if p_yes > hi else "below"),
        "shift_to_match_kalshi_C": float(shift),
        "peak": {"mean": float((W * peak).sum()), "sd": float(math.sqrt((W * (peak - (W * peak).sum()) ** 2).sum())),
                 "p5_25_50_75_95": pk, "p_ge_1_8": float((W * (peak >= 1.8)).sum()),
                 "p_ge_2_2": float((W * (peak >= 2.2 - 1e-9)).sum())},
        "t2049": {"mean": float((W * t49).sum()), "sd": float(math.sqrt((W * (t49 - (W * t49).sum()) ** 2).sum())),
                  "p5_25_50_75_95": tq, "p_ge_2": float((W * (t49 >= THRESH)).sum())},
        "first_year_p10_50_90": q_first,
        "ess": float(1 / (W ** 2).sum()), "n_paths": int(len(w)),
    }


# ---------------------------------------------------------------- runs
def collect(out):
    return {"w": out["w"].astype(float), "peak": out["peak"].astype(float), "t49": out["signal_end"].astype(float),
            "yes": out["yes"].astype(float), "first": out["first"].astype(float)}


def main():
    FIG.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    snap = latest_snapshot()
    mid = snap["mid"]
    yc = walk_book(snap["yes_asks"], 10)["all_in_per_contract"]
    ncost = walk_book(snap["no_asks"], 10)["all_in_per_contract"]
    band = list(pc.no_trade_band(yc, ncost, 1.0, 1.0))
    inp = Inputs.load()
    st = setup(inp)
    posts, _, _ = climate_posteriors(st["grid"])
    ks = kaya_setup(st, inp)
    ns = nowcast_state(st, inp)
    start = ns["start"]
    fitA = ns["fitA"]
    ar_class = {"c": 0.0, "phi": fitA.ar1["phi"], "sigma": fitA.ar1["sigma"]}
    anchor = (st["years"], st["S"])

    runs = {}
    runs["class_hw5"] = collect(run_draws(Params(), ar_class, np.ones(1), st["s_2025"], st["off"], K=N_PATHS,
                                          seed=11, inp=inp, anchor=anchor, start=start))
    runs["class_real"] = collect(run_draws(replace(Params(), **ks["kaya"]), ar_class, ks["w_k"][0.02], st["s_2025"],
                                           st["off"], seed=11, inp=inp, anchor=anchor, start=start))
    runs["history"] = collect(run_cell(st, posts["history"], "kaya", ks, 0.02, inp=inp, start=start)[0])
    runs["ipcc"] = collect(run_cell(st, posts["ipcc"], "kaya", ks, 0.02, inp=inp, start=start)[0])
    runs["ipcc_full"] = collect(run_cell(st, posts["ipcc_full"], "kaya", ks, 0.02, inp=inp, start=start)[0])
    runs["ipcc_fill"] = collect(run_cell(st, posts["ipcc"], "kaya", ks, 0.02, fill=990.0, inp=inp, start=start)[0])
    runs["ipcc_nomom"] = collect(run_cell(st, posts["ipcc"], "kaya", ks, 0.02, inp=inp,
                                          start={**start, "momentum": None})[0])
    for s in ("falling", "flat", "rising", "doubling"):
        runs[f"ipcc_{s}"] = collect(run_cell(st, posts["ipcc"], s, None, None, inp=inp, start=start)[0])
    # blend: each climate view gets half the total weight
    h, i = runs["history"], runs["ipcc"]
    runs["blend"] = {k: np.concatenate([h[k], i[k]]) for k in h}
    runs["blend"]["w"] = np.concatenate([h["w"] / h["w"].sum(), i["w"] / i["w"].sum()])

    res = {"snapshot": snap["dir"], "fetched_utc": snap["fetched_utc"],
           "kalshi": {"bid": snap["yes_bid"], "ask": snap["yes_ask"], "mid": mid, "last": snap["last"], "band": band},
           "grid": GRID.tolist(), "threshold": THRESH, "variants": {}}
    for key, label, group in VARIANTS:
        o = runs[key]
        s = summarize(o, mid, band)
        pdf_peak, h_peak = wkde(o["peak"], o["w"])
        pdf_t49, h_t49 = wkde(o["t49"], o["w"])
        s.update({"label": label, "group": group, "pdf_peak": pdf_peak.round(5).tolist(), "pdf_t2049": pdf_t49.round(5).tolist(),
                  "bandwidth_peak": h_peak, "bandwidth_t2049": h_t49,
                  "pdf_area_peak_ge_2": float(pdf_peak[GRID >= THRESH - 0.005].sum() * 0.01)})
        res["variants"][key] = s

    # ---------------------------------------------------------------- print
    print(f"\nKalshi KXWARMING-50 (snapshot {snap['dir']}): Yes {snap['yes_bid']:.2f}/{snap['yes_ask']:.2f}, mid {mid:.3f}; "
          f"range after fees [{band[0]:.3f}, {band[1]:.3f}]")
    print("\nHighest contract reading 2027-2049 (P(Yes) = P(peak >= 2.00)) and 2049 temperature, by model version:")
    print(f"  {'version':48s} {'P(Yes)':>7s} {'vs Kalshi':>9s} {'peak median [5-95%]':>22s} {'2049 temp median [5-95%]':>26s} "
          f"{'P(2049>=2)':>10s} {'median yr':>9s} {'shift':>7s}")
    for key, label, _ in VARIANTS:
        v = res["variants"][key]
        pk, tq = v["peak"]["p5_25_50_75_95"], v["t2049"]["p5_25_50_75_95"]
        fy = v["first_year_p10_50_90"][1]
        print(f"  {label:48s} {v['p_yes']:7.3f} {v['gap_vs_kalshi_pts']:+8.1f}p "
              f"{pk[2]:7.2f} [{pk[0]:.2f}-{pk[4]:.2f}]   {tq[2]:7.2f} [{tq[0]:.2f}-{tq[4]:.2f}]     "
              f"{v['t2049']['p_ge_2']:8.3f} {fy if fy is None else int(fy):>9} {v['shift_to_match_kalshi_C']:+7.2f}")
    print("  shift = how many degC the model's peak distribution would have to move to give Kalshi's mid "
          "(negative = the model runs hotter than the market)")
    figures(res)
    (OUT / "phase10.json").write_text(json.dumps(res, default=float))
    print(f"\nwrote {OUT / 'phase10.json'} and figures/p10_*.png")


# ---------------------------------------------------------------- figures
COL = {"class_hw5": "#7c3aed", "class_real": "#0891b2", "history": "#2563eb", "ipcc": "#dc2626", "blend": "#111827",
       "ipcc_full": "#f97316", "ipcc_fill": "#a16207", "ipcc_nomom": "#db2777",
       "ipcc_falling": "#16a34a", "ipcc_flat": "#65a30d", "ipcc_rising": "#ea580c", "ipcc_doubling": "#991b1b"}


def figures(res):
    g = np.array(res["grid"])
    V = res["variants"]
    mid, band = res["kalshi"]["mid"], res["kalshi"]["band"]

    def pdf_panel(ax, keys, field, title, shade=None):
        for k in keys:
            ax.plot(g, V[k][field], color=COL[k], lw=2.2 if k in ("ipcc", "blend") else 1.5,
                    label=f"{V[k]['label']}: P(Yes) {V[k]['p_yes']:.0%}" if field == "pdf_peak"
                    else f"{V[k]['label']}: median {V[k]['t2049']['p5_25_50_75_95'][2]:.2f}°C")
        if shade:
            y = np.array(V[shade][field])
            m = g >= THRESH
            ax.fill_between(g[m], y[m], color=COL[shade], alpha=0.15)
        ax.axvline(THRESH, color="#eab308", lw=2)
        ax.set(xlim=(1.2, 3.0), xlabel="°C above 1850-1900", ylabel="probability density", title=title)
        ax.legend(fontsize=7)

    fig, ax = plt.subplots(figsize=(11, 5))
    pdf_panel(ax, ["class_hw5", "class_real", "history", "ipcc", "blend"], "pdf_peak",
              f"Highest contract reading 2027-2049 (area right of 2.00 = P(Yes)); Kalshi mid {mid:.0%}", shade="ipcc")
    fig.tight_layout(); fig.savefig(FIG / "p10_1_pdf_peak_versions.png", dpi=130); plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 5))
    pdf_panel(ax, ["class_hw5", "class_real", "history", "ipcc", "blend"], "pdf_t2049", "2049 global temperature by model version")
    fig.tight_layout(); fig.savefig(FIG / "p10_2_pdf_2049_versions.png", dpi=130); plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    pdf_panel(axes[0], ["ipcc_falling", "ipcc_flat", "ipcc", "ipcc_rising", "ipcc_doubling"], "pdf_peak",
              "IPCC view: highest reading by emissions path")
    pdf_panel(axes[1], ["ipcc", "ipcc_full", "ipcc_fill", "ipcc_nomom"], "pdf_peak", "IPCC view: sensitivities")
    fig.tight_layout(); fig.savefig(FIG / "p10_3_pdf_peak_scenarios.png", dpi=130); plt.close(fig)

    # exceedance curves P(peak >= x)
    fig, ax = plt.subplots(figsize=(10, 4.8))
    for k in ("class_hw5", "class_real", "history", "ipcc", "blend", "ipcc_falling", "ipcc_doubling"):
        y = np.array(V[k]["pdf_peak"])
        exc = 1 - np.cumsum(y) * 0.01
        ax.plot(g, np.clip(exc, 0, 1), color=COL[k], lw=1.6, label=V[k]["label"])
    ax.errorbar([THRESH], [mid], yerr=[[mid - band[0]], [band[1] - mid]], fmt="D", color="k", ms=8, capsize=6,
                label=f"Kalshi: {mid:.0%} (range after fees {band[0]:.0%}-{band[1]:.0%})", zorder=5)
    ax.set(xlim=(1.4, 2.8), ylim=(0, 1.02), xlabel="threshold x (°C)", ylabel="P(highest reading 2027-49 ≥ x)",
           title="Chance of reaching each temperature before 2050: model versions vs Kalshi at 2.00°C")
    ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(FIG / "p10_4_exceedance.png", dpi=130); plt.close(fig)

    # P(Yes) by version vs Kalshi band
    keys = [k for k, _, _ in VARIANTS]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for i, k in enumerate(keys):
        ax.plot(V[k]["p_yes"], i, "o", color=COL[k], ms=8)
    ax.axvspan(band[0], band[1], color="#eab308", alpha=0.3, label="Kalshi range after fees")
    ax.axvline(mid, color="k", lw=1.2, label=f"Kalshi mid {mid:.0%}")
    ax.set_yticks(range(len(keys)), [V[k]["label"] for k in keys], fontsize=8)
    ax.invert_yaxis()
    ax.set(xlim=(0.3, 1.0), xlabel="P(any year ≥ 2.00°C before 2050)", title="Every model version vs Kalshi")
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout(); fig.savefig(FIG / "p10_5_pyes_versions.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    main()
