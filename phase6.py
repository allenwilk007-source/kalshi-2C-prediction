"""Phase 6: the social cost of carbon from the class model, compared with Tol's 14,141 estimates.

    python phase6.py      # results/phase6.json, figures/p6_*.png
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import hedge as hg
import priors as pr
import scenarios as sc
from model import YEAR0, Inputs, Params
from phase3 import climate_posteriors, kaya_setup, setup
from scc import extended, load_tol, marginal_damages, scc_from_md, temps, tol_by_prtp

HERE = Path(__file__).resolve().parent
FIG = HERE / "figures"
OUT = HERE / "results"
N = 4000
ETA = 1.4
RHOS = (0.0, 1.0, 1.5, 3.0)
CONST = (2.0, 3.0, 5.0)
HADCRUT_OFFSET = 0.038          # second-highest dataset sits ~this far above the common signal


def draws(st, ks, post, rng, n=N):
    """Parameter draws: climate grid point from the posterior, Kaya draw by its 2019-24 weight."""
    g = st["grid"]
    ic = pr.sample_grid(post, n, rng)
    wk = ks["w_k"][0.02]
    ik = rng.choice(len(wk), size=n, p=wk / wk.sum())
    kaya = {k: v[ik] for k, v in ks["kaya"].items()}
    p = replace(Params(), p1_adjust_speed=g.p1[ic], p2_sensitivity=g.p2[ic], **kaya)
    return p, ic, ik


def anchor(st, p, inp, post="decline"):
    x = extended(p, inp, post=post)
    T = temps(x["E"], p)
    yrs, S = st["years"], st["S"]
    b = pr.recent_bias(yrs, S[None, :] - T[:, yrs - YEAR0])
    return b, T


def stats(v):
    v = np.asarray(v)
    return {"mean": float(v.mean()), "median": float(np.median(v)),
            "p5": float(np.percentile(v, 5)), "p95": float(np.percentile(v, 95)),
            "share_negative": float((v < 0).mean())}


def main():
    FIG.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    inp = Inputs.load()
    st = setup(inp)
    posts, _, _ = climate_posteriors(st["grid"])
    ks = kaya_setup(st, inp)
    dmg = hg.load_impact()
    tol = tol_by_prtp(RHOS)

    res = {"eta": ETA, "pulse": "1 GtC in 2027", "n_draws": N, "tol": {str(k): v for k, v in tol.items()},
           "views": {}, "sensitivities": {}, "scenarios": {}}
    keep = {}
    for view in ("ipcc", "history"):
        rng = np.random.default_rng(606 if view == "ipcc" else 607)
        p, ic, ik = draws(st, ks, posts[view], rng)
        a = hg.sample_damage_coef(N, rng, dmg)
        b, Tbase = anchor(st, p, inp)
        md = marginal_damages(p, a, b, inp)
        out = {}
        for r in RHOS:
            out[f"Ramsey rho={r}%"] = stats(scc_from_md(md, r / 100, ETA))
        for r in CONST:
            out[f"constant {r}%"] = stats(scc_from_md(md, const_r=r / 100))
        res["views"][view] = out
        # sensitivities (rho = 1.5 %)
        s = {}
        for eta in (1.0, 2.0):
            s[f"eta={eta}"] = stats(scc_from_md(md, 0.015, eta))
        s["horizon 2100 only"] = stats(scc_from_md(md, 0.015, ETA, horizon=2100))
        md_flat = marginal_damages(p, a, b, inp, post="flat")
        s["emissions flat after 2100"] = stats(scc_from_md(md_flat, 0.015, ETA))
        res["sensitivities"][view] = s
        # what drives it: SCC is linear in a, so SCC = a * K (K = climate x economy x discounting)
        scc15 = scc_from_md(md, 0.015, ETA)
        K = scc15 / a
        pos = a > 0
        la, lK = np.log(a[pos]), np.log(K[pos])
        tot = np.var(la + lK)
        res.setdefault("drivers", {})[view] = {
            "var_share_damage_coef": float(np.var(la) / tot), "var_share_climate_economy": float(np.var(lK) / tot),
            "K_p5_50_95": [float(x) for x in np.percentile(K, [5, 50, 95])]}
        # link to the contract: does the anchored trend cross 2 C by 2049?
        Ta = Tbase + b[:, None]
        cross = (Ta[:, 2026 - YEAR0: 2050 - YEAR0].max(axis=1) + HADCRUT_OFFSET) >= 1.995
        res.setdefault("by_trend_crossing", {})[view] = {
            "share_crossing": float(cross.mean()),
            "median_scc_if_cross": float(np.median(scc15[cross])) if cross.any() else None,
            "median_scc_if_not": float(np.median(scc15[~cross])) if (~cross).any() else None}
        keep[view] = {"scc15": scc15, "md": md, "a": a}

    # SCC under each IPCC-style emissions path (IPCC posterior, template economy for GDP)
    p5 = json.loads((OUT / "phase5.json").read_text()) if (OUT / "phase5.json").exists() else None
    owid_actual = st["actual"]
    rng = np.random.default_rng(608)
    p_c, _, _ = draws(st, ks, posts["ipcc"], rng)
    a = hg.sample_damage_coef(N, rng, dmg)
    for name in sc.NAMES:
        p = replace(Params(), p1_adjust_speed=p_c.p1_adjust_speed, p2_sensitivity=p_c.p2_sensitivity,
                    future_emissions_mtc=sc.path(name, owid_actual))
        b, _ = anchor(st, p, inp)
        md = marginal_damages(p, a, b, inp)
        label = f"{name.capitalize()} ({sc.ANALOGUE[name]}-like)"
        res["scenarios"][label] = {"scc_rho1.5": stats(scc_from_md(md, 0.015, ETA)),
                                   "p_yes_ipcc": (p5["p_yes"][label]["ipcc"]["p_yes"] if p5 else None)}

    # ---------------------------------------------------------------- print
    c = 12 / 44
    print(f"\nSocial cost of carbon from the class model ($/tC; /tCO2 = x{c:.3f}); pulse {res['pulse']}, eta {ETA}")
    print(f"  {'discounting':20s} {'IPCC view: median [5-95%]':>32s} {'history view: median [5-95%]':>34s}   Tol weighted mean / median")
    for k in res["views"]["ipcc"]:
        i, h = res["views"]["ipcc"][k], res["views"]["history"][k]
        tk = None
        if k.startswith("Ramsey"):
            r = float(k.split("=")[1].rstrip("%"))
            tk = tol[r]
        print(f"  {k:20s} {i['median']:8.0f} [{i['p5']:6.0f} - {i['p95']:6.0f}] {h['median']:12.0f} [{h['p5']:6.0f} - {h['p95']:6.0f}]"
              + (f"   {tk['mean']:6.0f} / {tk['p5_50_95'][1]:5.0f}  (n={tk['n']})" if tk else ""))
    print(f"  share of draws with negative SCC (damage coef < 0): {res['views']['ipcc']['Ramsey rho=1.5%']['share_negative']:.1%}")
    print("\nSensitivities (rho 1.5%, medians):")
    for v, s in res["sensitivities"].items():
        print(f"  {v:8s} " + "; ".join(f"{k} {x['median']:.0f}" for k, x in s.items()))
    print("\nWhat drives the spread (variance of log SCC):")
    for v, d in res["drivers"].items():
        print(f"  {v:8s} damage coefficient {d['var_share_damage_coef']:.0%}, climate+economy+discounting {d['var_share_climate_economy']:.0%}")
    print("\nSCC vs whether the anchored trend crosses 2 C by 2049 (rho 1.5%):")
    for v, d in res["by_trend_crossing"].items():
        yes_, no_ = d["median_scc_if_cross"], d["median_scc_if_not"]
        print(f"  {v:8s} {d['share_crossing']:.0%} of draws cross; median SCC if they cross "
              f"{'n/a' if yes_ is None else f'{yes_:.0f}'}, if not {'n/a' if no_ is None else f'{no_:.0f}'} $/tC")
    print("\nSCC by emissions path (IPCC view, rho 1.5%) next to P(KXWARMING-50 = Yes):")
    for k, d in res["scenarios"].items():
        print(f"  {k:28s} SCC median {d['scc_rho1.5']['median']:6.0f} $/tC  ({d['scc_rho1.5']['median'] * c:5.0f} $/tCO2)   P(Yes) {d['p_yes_ipcc']}")

    figures(res, keep, tol)
    (OUT / "phase6.json").write_text(json.dumps(res, indent=1, default=float))
    print(f"\nwrote {OUT / 'phase6.json'} and figures/p6_*.png")


def figures(res, keep, tol):
    t = load_tol()
    # 1 distributions at rho = 1.5 %: ours vs Tol's PRTP=1.5 estimates
    fig, ax = plt.subplots(figsize=(10, 4.5))
    bins = np.logspace(0, 4, 60)
    m = (t["PRTP"] == 1.5) & (t["w"] > 0) & (t["SCC"] > 0)
    ax.hist(t["SCC"][m], bins=bins, weights=t["w"][m] / t["w"][m].sum(), alpha=0.45, color="grey",
            label=f"Tol database, PRTP 1.5% (n={m.sum()})")
    for v, col in (("ipcc", "C3"), ("history", "C0")):
        s = keep[v]["scc15"]
        s = s[s > 0]
        ax.hist(s, bins=bins, weights=np.full(len(s), 1 / len(keep[v]["scc15"])), alpha=0.45, color=col,
                label=f"class model, {v} view")
    ax.set(xscale="log", xlabel="SCC, $ per tonne of carbon (log scale)", ylabel="share",
           title="Social cost of carbon at a 1.5% pure rate of time preference")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "p6_1_scc_distribution.png", dpi=130); plt.close(fig)

    # 2 by PRTP: ours vs Tol
    fig, ax = plt.subplots(figsize=(10, 4.5))
    x = np.arange(len(RHOS))
    for off, v, col in ((-0.25, "ipcc", "C3"), (0.0, "history", "C0")):
        st = [res["views"][v][f"Ramsey rho={r}%"] for r in RHOS]
        med = np.array([s["median"] for s in st])
        ax.errorbar(x + off, med, yerr=[med - np.array([s["p5"] for s in st]), np.array([s["p95"] for s in st]) - med],
                    fmt="o", color=col, capsize=4, label=f"class model ({v}): median, 5-95%")
    tm = np.array([tol[r]["p5_50_95"][1] for r in RHOS])
    tmean = np.array([tol[r]["mean"] for r in RHOS])
    ax.plot(x + 0.25, tm, "s", color="k", label="Tol database: weighted median")
    ax.plot(x + 0.25, tmean, "^", color="grey", label="Tol database: weighted mean")
    ax.set_xticks(x, [f"PRTP {r}%" for r in RHOS])
    ax.set(yscale="log", ylabel="$ per tC (log)", title="SCC by pure rate of time preference: class model vs literature")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "p6_2_scc_by_prtp.png", dpi=130); plt.close(fig)

    # 3 pulse anatomy (median draw of the IPCC view)
    md = keep["ipcc"]["md"]
    i = int(np.argsort(keep["ipcc"]["scc15"])[len(keep["ipcc"]["scc15"]) // 2])
    yrs = md["years"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4))
    a1.plot(yrs, md["dT"][i] * 1000, color="C3")
    a1.set(title="Extra warming from 1 GtC emitted in 2027", ylabel="milli-°C", xlabel="year")
    a2.plot(yrs, md["MD"][i], color="C1")
    a2.set(title="Marginal damages ($ per tC per year), median draw", xlabel="year")
    a2.axvline(2100, color="grey", ls=":", lw=1)
    fig.tight_layout(); fig.savefig(FIG / "p6_3_pulse.png", dpi=130); plt.close(fig)

    # 4 SCC by emissions path vs P(Yes)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for k, d in res["scenarios"].items():
        if d["p_yes_ipcc"] is None:
            continue
        s = d["scc_rho1.5"]
        ax.errorbar(d["p_yes_ipcc"], s["median"], yerr=[[s["median"] - s["p5"]], [s["p95"] - s["median"]]], fmt="o", capsize=4)
        ax.annotate(k.split(" (")[0], (d["p_yes_ipcc"], s["median"]), textcoords="offset points", xytext=(6, 6), fontsize=8)
    ax.set(xlabel="P(KXWARMING-50 = Yes), IPCC view", ylabel="SCC $/tC (rho 1.5%)", yscale="log",
           title="Higher-emission worlds: more likely 2°C and costlier carbon")
    fig.tight_layout(); fig.savefig(FIG / "p6_4_scc_vs_pyes.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    main()
