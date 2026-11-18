"""Phase 3: P(KXWARMING-50 = Yes) with uncertainty in emissions and climate response.

    python phase3.py      # tables, diagnostics, sensitivities, figures/p3_*.png, results/phase3.json

Climate variants:  "history" = course model fitted to 1880-2020 (prior x likelihood)
                   "ipcc"    = same, tempered so 2041-2060 spread matches IPCC AR6 (net of observed)
Emission specs:    HW5 template | Kaya randomised (unweighted / weighted to 2019-24 actuals) |
                   falling / flat / rising / doubling (IPCC-style paths)
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

import priors as pr
import scenarios as sc
from model import YEAR0, Inputs, Params, kaya_emissions, run
from noise import common_signal, contract_outcome, dataset_offsets, simulate
from observations import load, owid_world_co2

HERE = Path(__file__).resolve().parent
FIG = HERE / "figures"
OUT = HERE / "results"
SIM_YEARS = np.arange(2026, 2050)
LAST_OBS = 2025
M_DRAWS = 20_000
K_PATHS = 5
FILL = 990.0
KALSHI = {"bid": 0.65, "ask": 0.69, "last": 0.69, "checked": "2026-11-08"}


# ---------------------------------------------------------------- core
def run_draws(p: Params, ar: dict, w, s_2025: float, off: dict, K=K_PATHS, seed=0, inp=None,
              anchor=None, start=None):
    """Run the model for M parameter draws, then K noise paths each.

    p:  Params, scalars or arrays of shape (M,)        ar: dict c/phi/sigma, scalars or (M,)
    w:  importance weights, shape (M,)
    anchor: (obs_years, signal) -> noise mean-reverts to each draw's own recent bias b
            (c = b * (1 - phi)) instead of ar["c"]. None = use ar["c"] (Phase 2 behaviour).
    start:  None = start from the observed LAST_OBS signal s_2025 (Phases 3-4). Or a dict
            {"year": Y, "signal": (M*K,) per-path starting signal draws,
             "first_shift": (M*K,) or None (added to the first simulated year)}:
            simulate years Y+1..2049 from a nowcast state.
    Returns per-path arrays (length M*K) and per-draw model output.
    """
    inp = inp or Inputs.load()
    w = np.asarray(w, dtype=float)
    M = len(w)
    r = run(p, inp)
    T = r.temp_atmos
    T = T - T[..., 1850 - YEAR0: 1901 - YEAR0].mean(axis=-1, keepdims=True)
    T = np.broadcast_to(T, (M, T.shape[-1]))
    E = np.broadcast_to(r.emissions_mtc, (M, r.emissions_mtc.shape[-1]))
    y0 = LAST_OBS if start is None else start["year"]
    sim_years = np.arange(y0 + 1, SIM_YEARS[-1] + 1)
    r0 = s_2025 - T[:, LAST_OBS - YEAR0]
    mf = T[:, sim_years[0] - YEAR0: sim_years[-1] - YEAR0 + 1]
    ar = dict(ar)
    b = None
    if anchor is not None:
        oy, sig = anchor
        b = pr.recent_bias(oy, sig[None, :] - T[:, oy - YEAR0])
        ar["c"] = b * (1 - np.broadcast_to(np.asarray(ar["phi"], dtype=float), (M,)))

    def rep(a):
        return np.repeat(np.broadcast_to(np.asarray(a, dtype=float), (M,)), K)

    if start is None:
        r0_paths, shift, s_start = rep(r0), None, None
    else:
        s_start = np.asarray(start["signal"], dtype=float)
        r0_paths = s_start - np.repeat(T[:, y0 - YEAR0], K)
        shift = start.get("first_shift")
        mom = start.get("momentum")
        if mom is not None:
            # Replace the first step's persistence by the momentum model, around the same anchor b:
            #   r1 = b + phi1 (r0 - b) + phi2 m + eps   vs the draw's   b + phi (r0 - b) + eps
            bp = rep(b if b is not None else 0.0)
            shift = (mom["phi1"] - rep(ar["phi"])) * (r0_paths - bp) + mom["phi2"] * np.asarray(mom["m"], dtype=float)
    X, S = simulate(np.repeat(mf, K, axis=0), {k: rep(ar[k]) for k in ("c", "phi", "sigma")},
                    r0_paths, off, n=M * K, seed=seed, first_shift=shift)
    yes, first = contract_outcome(X, sim_years)
    wp = np.repeat(w, K)
    stat = np.sort(X, axis=1)[:, -2, :]                       # second-highest dataset, per year
    # per-path readings, rounded to 0.01 as published: the highest reading 2027-2049 decides the contract
    stat_r = np.floor(stat * 100 + 0.5 + 1e-9) / 100
    peak, end = stat_r.max(axis=1).astype(np.float32), stat_r[:, -1].astype(np.float32)
    fan = np.array([pr.weighted_quantile(stat[:, t], wp, (.05, .25, .5, .75, .95))
                    for t in range(stat.shape[1])])           # (T, 5)
    out = {"yes": yes, "first": first, "w": wp, "K": K,
           "r0": r0, "b": b, "T": T, "E": E, "fan": fan, "sim_years": sim_years,
           "peak": peak, "reading_end": end, "signal_end": S[:, -1].astype(np.float32)}
    if start is not None:
        out["S"] = S.astype(np.float32)
        out["s_start"] = s_start
    return out


def wsummary(yes, first, w):
    sw = w.sum()
    p = float((w * yes).sum() / sw)
    se = float(math.sqrt(((w * (yes - p)) ** 2).sum()) / sw)
    f = np.isfinite(first)
    q = pr.weighted_quantile(first[f], w[f], (0.1, 0.5, 0.9)) if f.any() else [np.nan] * 3
    return {"p_yes": p, "mc_se": se, "first_p10": float(q[0]), "first_median": float(q[1]),
            "first_p90": float(q[2]), "ess_paths": pr.ess(w)}


# ---------------------------------------------------------------- setup
def setup(inp):
    years, X = load()
    off = dataset_offsets(years, X)
    S = common_signal(X, off["delta"])
    s_2025 = float(S[years == LAST_OBS][0])
    owid = owid_world_co2()
    actual = sc.actual_2021_2024(owid)
    flat = sc.path("flat", actual)
    grid = pr.build_climate_grid(years, S, flat, inp)
    return {"years": years, "X": X, "off": off, "S": S, "s_2025": s_2025, "owid": owid,
            "actual": actual, "grid": grid}


def climate_draws(grid, post, M, rng):
    idx = pr.sample_grid(post, M, rng)
    return idx, {"p1_adjust_speed": grid.p1[idx], "p2_sensitivity": grid.p2[idx]}, \
        {"c": grid.c[idx], "phi": grid.phi[idx], "sigma": grid.sigma[idx]}


def climate_posteriors(grid):
    """history (T=1), ipcc (target width), ipcc_full (full AR6 width) -> (posts, T values, flags)."""
    T_ipcc, flag = pr.calibrate_T(grid, pr.AR6_TARGET_WIDTH)
    T_full, flag_full = pr.calibrate_T(grid, pr.AR6_FULL_WIDTH)
    posts = {"history": pr.posterior(grid, 1.0), "ipcc": pr.posterior(grid, T_ipcc),
             "ipcc_full": pr.posterior(grid, T_full)}
    return posts, {"ipcc": T_ipcc, "ipcc_full": T_full}, {"ipcc": flag, "ipcc_full": flag_full}


def kaya_setup(st, inp, M=M_DRAWS):
    """Shared Kaya draws (common random numbers) and their 2019-24 weights."""
    rng = np.random.default_rng(2026)
    centres, sds = pr.kaya_prior()
    kaya = pr.sample_kaya(M, rng, centres, sds)
    k2019 = sc.course_kaya_2019()
    g_obs = math.log(st["owid"][2024] / st["owid"][2019])
    kaya_E = kaya_emissions(replace(Params(), **kaya), inp)          # (M, 80), 2021-2100
    w_k = {sd: pr.emission_weights(kaya_E[:, 2024 - 2021], k2019, g_obs, sd) for sd in (0.01, 0.02, 0.04)}
    tmpl_g = math.log(kaya_emissions(Params(), inp)[2024 - 2021] / k2019)
    return {"kaya": kaya, "kaya_E": kaya_E, "w_k": w_k, "g_obs": g_obs, "tmpl_g": tmpl_g,
            "centres": centres, "sds": sds}


def run_cell(st, post, kind, ks=None, wsd=0.02, fill=0.0, inp=None, start=None):
    """One (climate posterior x emissions spec) cell: M climate draws x K noise paths.

    kind: "template" | "kaya" (weighted by ks["w_k"][wsd]; wsd=None -> unweighted) | a scenario name.
    Returns (run_draws output, climate grid indices).
    """
    grid = st["grid"]
    idx, pclim, ar = climate_draws(grid, post, M_DRAWS, np.random.default_rng(7))
    ones = np.ones(M_DRAWS)
    if kind == "template":
        p, w = replace(Params(), **pclim, land_use_fill_mtc=fill), ones
    elif kind == "kaya":
        p = replace(Params(), **pclim, **ks["kaya"], land_use_fill_mtc=fill)
        w = ks["w_k"][wsd] if wsd else ones
    else:
        p = replace(Params(), **pclim, future_emissions_mtc=sc.path(kind, st["actual"]),
                    land_use_fill_mtc=fill)
        w = ones
    out = run_draws(p, ar, w, st["s_2025"], st["off"], seed=11, inp=inp,
                    anchor=(st["years"], st["S"]), start=start)
    return out, idx


SPECS = {"HW5 template": ("template", None), "Kaya randomised, unweighted": ("kaya", None),
         "Kaya randomised + 2019-24 weighting": ("kaya", 0.02)}
for _s in sc.NAMES:
    SPECS[f"{_s.capitalize()} ({sc.ANALOGUE[_s]}-like)"] = (_s, None)


def main():
    FIG.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    inp = Inputs.load()
    st = setup(inp)
    grid, off = st["grid"], st["off"]
    anch = (st["years"], st["S"])

    # ---------- climate posteriors
    allposts, Ts, flags = climate_posteriors(grid)
    posts = {k: allposts[k] for k in ("history", "ipcc")}
    clim = {k: pr.summarize_climate(grid, v) for k, v in posts.items()}
    clim["ipcc"]["T"] = Ts["ipcc"]
    clim["ipcc"]["T_hit_ceiling"] = flags["ipcc"]
    clim["ipcc_full_width"] = pr.summarize_climate(grid, allposts["ipcc_full"])
    clim["ipcc_full_width"]["T"] = Ts["ipcc_full"]

    # ---------- emissions draws (shared across climate variants: common random numbers)
    ks = kaya_setup(st, inp)
    kaya, kaya_E, w_k = ks["kaya"], ks["kaya_E"], ks["w_k"]
    g_obs, tmpl_g, centres, sds = ks["g_obs"], ks["tmpl_g"], ks["centres"], ks["sds"]

    results = {"kalshi_reference": KALSHI, "M_draws": M_DRAWS, "K_paths": K_PATHS,
               "climate": clim, "headline": {}, "sensitivities": {}}
    store = {}
    for cv, post in posts.items():
        for label, (kind, wsd) in SPECS.items():
            out, idx = run_cell(st, post, kind, ks, wsd, inp=inp)
            results["headline"].setdefault(label, {})[cv] = wsummary(out["yes"], out["first"], out["w"])
            store[(label, cv)] = (out, idx)

    # ---------- sensitivities
    sens = results["sensitivities"]
    for cv in posts:
        out, _ = store[("Kaya randomised, unweighted", cv)]
        for sd in (0.01, 0.04):
            wp = np.repeat(w_k[sd], out["K"])
            sens.setdefault(f"emissions weight sd {sd}", {})[cv] = wsummary(out["yes"], out["first"], wp)
        o, _ = run_cell(st, posts[cv], "kaya", ks, 0.02, fill=FILL, inp=inp)
        sens.setdefault("land-use gap filled (+990 Mt C/yr)", {})[cv] = wsummary(o["yes"], o["first"], o["w"])
    o, _ = run_cell(st, allposts["ipcc_full"], "kaya", ks, 0.02, inp=inp)
    sens["IPCC full-width target (0.90)"] = {"ipcc": wsummary(o["yes"], o["first"], o["w"])}

    # ---------- emissions diagnostics
    wk = w_k[0.02]
    ones = np.ones(M_DRAWS)
    e2049 =kaya_E[:, 2049 - 2021] * 44 / 12 / 1000
    results["emissions"] = {
        "g_obs_2019_2024": g_obs, "g_template": tmpl_g,
        "ess_weights": {str(k): pr.ess(v) for k, v in w_k.items()},
        "gtco2_2049_unweighted_5_50_95": pr.weighted_quantile(e2049, ones, (.05, .5, .95)).tolist(),
        "gtco2_2049_weighted_5_50_95": pr.weighted_quantile(e2049, wk, (.05, .5, .95)).tolist(),
        "paths_gtco2_2049": {s: float(sc.path(s, st["actual"])[2049 - 2021] * 44 / 12 / 1000) for s in sc.NAMES},
        "template_gtco2_2049": float(kaya_emissions(Params(), inp)[2049 - 2021] * 44 / 12 / 1000),
        "kaya_prior_centres": centres.tolist(), "kaya_prior_sds": sds.tolist(),
    }

    # ---------- what drives the answer (headline emissions spec)
    results["drivers"] = {}
    for cv in posts:
        out, idx = store[("Kaya randomised + 2019-24 weighting", cv)]
        K = out["K"]
        inputs = {}
        for f, arr in kaya.items():
            for j, r in enumerate(pr.REGIONS):
                inputs[f"{f.split('_')[0]} {r}"] = arr[:, j]
        inputs["p1 (adjust speed)"] = grid.p1[idx]
        inputs["p2 (sensitivity)"] = grid.p2[idx]
        inputs["emissions 2049"] = out["E"][:, 2049 - YEAR0]
        inputs["model warming 2025-49"] = out["T"][:, 2049 - YEAR0] - out["T"][:, 2025 - YEAR0]
        inputs["r0 (2025 anomaly vs model)"] = out["r0"]
        inputs["b (2006-25 bias vs model)"] = out["b"]
        d = {}
        for name, v in inputs.items():
            vp = np.repeat(v, K)
            lo, hi = pr.weighted_quantile(vp, out["w"], (0.2, 0.8))
            pl = (out["w"] * out["yes"])[vp <= lo].sum() / out["w"][vp <= lo].sum()
            ph = (out["w"] * out["yes"])[vp >= hi].sum() / out["w"][vp >= hi].sum()
            d[name] = {"bottom20": float(pl), "top20": float(ph)}
        results["drivers"][cv] = d

    # ---------- print
    print("\nClimate response (Flat path, 2041-2060 / 2021-2040 mean warming vs 1850-1900):")
    print(f"  AR6 SSP2-4.5: mid {pr.AR6_MID[0]} [{pr.AR6_MID[1]}-{pr.AR6_MID[2]}], near {pr.AR6_NEAR[0]} "
          f"[{pr.AR6_NEAR[1]}-{pr.AR6_NEAR[2]}]; target width {pr.AR6_TARGET_WIDTH:.3f} (full {pr.AR6_FULL_WIDTH:.2f})")
    for k, c in clim.items():
        m, n, e, p1 = c["w_mid_5_50_95"], c["w_near_5_50_95"], c["ecs_5_50_95"], c["p1_5_50_95"]
        print(f"  {k:16s} T={c.get('T', 1.0):6.2f}  mid {m[1]:.2f} [{m[0]:.2f}-{m[2]:.2f}] width {m[2]-m[0]:.3f}  "
              f"near {n[1]:.2f} [{n[0]:.2f}-{n[2]:.2f}]  ECS {e[1]:.2f} [{e[0]:.2f}-{e[2]:.2f}]  "
              f"p1 {p1[1]:.4f} [{p1[0]:.4f}-{p1[2]:.4f}]")
    em = results["emissions"]
    print(f"\nEmissions: observed growth 2019-24 {g_obs:.4f} (template {tmpl_g:.4f}); "
          f"ESS of weights " + ", ".join(f"sd {k}: {v:.0f}" for k, v in em["ess_weights"].items()))
    u, wq = em["gtco2_2049_unweighted_5_50_95"], em["gtco2_2049_weighted_5_50_95"]
    print(f"  2049 emissions GtCO2: template {em['template_gtco2_2049']:.1f}; Kaya unweighted {u[1]:.1f} "
          f"[{u[0]:.1f}-{u[2]:.1f}]; weighted {wq[1]:.1f} [{wq[0]:.1f}-{wq[2]:.1f}]; paths "
          + ", ".join(f"{k} {v:.1f}" for k, v in em["paths_gtco2_2049"].items()))

    print("\nP(KXWARMING-50 = Yes): second-highest of 4 datasets >= 2.00 C in any year 2026-2049")
    print(f"{'emissions':40s} {'history-fit':>24s} {'IPCC-calibrated':>24s}")
    for label, d in results["headline"].items():
        cells = [f"{d[c]['p_yes']:.3f}±{d[c]['mc_se']:.3f} ({d[c]['first_median']:.0f})" for c in ("history", "ipcc")]
        print(f"{label:40s} {cells[0]:>24s} {cells[1]:>24s}")
    print(f"{'Kalshi KXWARMING-50 bid/ask':40s} {KALSHI['bid']:.2f}-{KALSHI['ask']:.2f}")
    print("  (cells: P(Yes) ± MC se (median first year))")

    obs2 = np.sort(np.nan_to_num(st["X"], nan=-9), axis=0)[-2]
    o = {y: float(obs2[st["years"] == y][0]) for y in (2023, 2024, 2025)}
    print("\nDrift check, median second-highest dataset (observed 2023/24/25: "
          + "/".join(f"{v:.2f}" for v in o.values()) + "):")
    for cv in posts:
        fan = store[("Kaya randomised + 2019-24 weighting", cv)][0]["fan"]
        print(f"  {cv:8s} 2026 {fan[0, 2]:.2f}  2030 {fan[4, 2]:.2f}  2040 {fan[14, 2]:.2f}  2049 {fan[-1, 2]:.2f}")
    if clim["ipcc_full_width"]["T"] >= 1e4 - 1:
        print("  NOTE: full-width target (0.90) unreachable even with no history constraint; "
              f"max width {clim['ipcc_full_width']['w_mid_5_50_95'][2] - clim['ipcc_full_width']['w_mid_5_50_95'][0]:.3f}")

    print("\nSensitivities (headline emissions spec):")
    for label, d in sens.items():
        print(f"  {label:40s} " + "  ".join(f"{c} {v['p_yes']:.3f}" for c, v in d.items()))

    print("\nWhat drives it (P(Yes) bottom 20% -> top 20% of each input; weighted Kaya):")
    for cv, d in results["drivers"].items():
        print(f"  [{cv}]")
        for name, v in sorted(d.items(), key=lambda kv: -abs(kv[1]["top20"] - kv[1]["bottom20"])):
            print(f"    {name:28s} {v['bottom20']:.3f} -> {v['top20']:.3f}  (swing {v['top20']-v['bottom20']:+.3f})")

    figures(st, posts, clim, store, results, kaya_E, w_k[0.02])
    (OUT / "phase3.json").write_text(json.dumps(results, indent=1, default=float))
    print(f"\nwrote {OUT / 'phase3.json'} and figures/p3_*.png")


# ---------------------------------------------------------------- figures
def figures(st, posts, clim, store, results, kaya_E, wk):
    grid = st["grid"]
    yrs_f = np.arange(2021, 2101)

    # 1 emissions fan
    fig, ax = plt.subplots(figsize=(10, 5))
    gt = kaya_E * 44 / 12 / 1000
    for w, col, lab in ((np.ones(len(wk)), "grey", "Kaya prior"), (wk, "C0", "Kaya weighted to 2019-24")):
        q = np.array([pr.weighted_quantile(gt[:, t], w, (.05, .5, .95)) for t in range(gt.shape[1])])
        ax.fill_between(yrs_f, q[:, 0], q[:, 2], color=col, alpha=0.2, label=f"{lab} 5-95%")
        ax.plot(yrs_f, q[:, 1], color=col, lw=2)
    for s, ls in zip(sc.NAMES, (":", "--", "-.", "-")):
        ax.plot(yrs_f, sc.path(s, st["actual"]) * 44 / 12 / 1000, "k", ls=ls, lw=1.2, label=f"{s} ({sc.ANALOGUE[s]}-like)")
    k2019 = sc.course_kaya_2019() * 44 / 12 / 1000
    oy = np.arange(2000, 2025)
    ax.plot(oy, [k2019 * st["owid"][y] / st["owid"][2019] for y in oy], "r.-", label="actual (OWID, course units)")
    ax.set(xlim=(2000, 2060), ylim=(0, 110), ylabel="Gt CO2/yr", title="Emission paths")
    ax.axvline(2049.5, color="orange", lw=1)
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout(); fig.savefig(FIG / "p3_1_emissions.png", dpi=130); plt.close(fig)

    # 2 posterior heatmaps
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
    shape = (len(pr.P1_GRID), len(pr.P2_GRID))
    for ax, (k, post) in zip(axes, posts.items()):
        im = ax.imshow(post.reshape(shape).T, origin="lower", aspect="auto", cmap="viridis",
                       extent=(pr.P1_GRID[0], pr.P1_GRID[-1], pr.P2_GRID[0], pr.P2_GRID[-1]))
        ax.plot(0.0256, 1.15, "r*", ms=12, label="HW5 class values")
        ax.set(title=f"{k} posterior (T={clim[k].get('T', 1.0):.2f})", xlabel="p1 (adjust speed)")
        ax.legend(fontsize=8)
    axes[0].set_ylabel("p2 (sensitivity)")
    fig.tight_layout(); fig.savefig(FIG / "p3_2_climate_posterior.png", dpi=130); plt.close(fig)

    # 3 2041-2060 warming vs AR6
    fig, ax = plt.subplots(figsize=(9, 4))
    bins = np.arange(1.0, 3.0, 0.02)
    for (k, post), col in zip(posts.items(), ("C0", "C3")):
        ax.hist(grid.w_mid, bins=bins, weights=post, alpha=0.5, color=col, label=f"{k}")
    ax.axvspan(pr.AR6_MID[1], pr.AR6_MID[2], color="grey", alpha=0.15, label="AR6 SSP2-4.5 5-95%")
    ax.axvline(pr.AR6_MID[0], color="k", lw=1.5, label="AR6 best estimate")
    ax.set(title="2041-2060 mean warming under the Flat path", xlabel="°C above 1850-1900")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "p3_3_midterm_vs_ar6.png", dpi=130); plt.close(fig)

    # 4 tornado (ipcc)
    d = results["drivers"]["ipcc"]
    items = sorted(d.items(), key=lambda kv: abs(kv[1]["top20"] - kv[1]["bottom20"]))
    fig, ax = plt.subplots(figsize=(9, 5.5))
    base = results["headline"]["Kaya randomised + 2019-24 weighting"]["ipcc"]["p_yes"]
    for i, (name, v) in enumerate(items):
        ax.plot([v["bottom20"], v["top20"]], [i, i], color="grey", lw=6, alpha=0.5)
        ax.plot(v["bottom20"], i, "o", color="C0")
        ax.plot(v["top20"], i, "o", color="C3")
    ax.axvline(base, color="k", lw=1, label=f"headline {base:.2f}")
    ax.axvspan(KALSHI["bid"], KALSHI["ask"], color="orange", alpha=0.3, label="Kalshi bid-ask")
    ax.set_yticks(range(len(items)), [n for n, _ in items], fontsize=8)
    ax.set(title="P(Yes) in bottom (blue) vs top (red) 20% of each input — IPCC-calibrated", xlabel="P(Yes)")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "p3_4_drivers.png", dpi=130); plt.close(fig)

    # 5 P(Yes) by emission spec
    fig, ax = plt.subplots(figsize=(10, 4.5))
    labels = list(results["headline"])
    x = np.arange(len(labels))
    for off_, cv, col in ((-0.2, "history", "C0"), (0.2, "ipcc", "C3")):
        ax.bar(x + off_, [results["headline"][l][cv]["p_yes"] for l in labels], 0.4, color=col, label=cv)
    ax.axhspan(KALSHI["bid"], KALSHI["ask"], color="orange", alpha=0.4, label="Kalshi bid-ask")
    ax.set_xticks(x, [l.replace(" (", "\n(").replace(", ", ",\n").replace(" + ", "\n+ ") for l in labels], fontsize=7)
    ax.set(ylim=(0, 1.05), ylabel="P(Yes by 2049)", title="Model P(Yes) by emissions assumption")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "p3_5_pyes_by_scenario.png", dpi=130); plt.close(fig)

    # 7 fan chart of the contract statistic (headline spec)
    X, yrs = st["X"], st["years"]
    obs2 = np.sort(np.nan_to_num(X, nan=-9), axis=0)[-2]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), sharey=True)
    for ax, cv in zip(axes, ("history", "ipcc")):
        out, _ = store[("Kaya randomised + 2019-24 weighting", cv)]
        q = out["fan"]
        ax.fill_between(SIM_YEARS, q[:, 0], q[:, 4], color="C0", alpha=0.15, label="5-95%")
        ax.fill_between(SIM_YEARS, q[:, 1], q[:, 3], color="C0", alpha=0.3, label="25-75%")
        ax.plot(SIM_YEARS, q[:, 2], color="C0", lw=2, label="median")
        h = yrs >= 1990
        ax.plot(yrs[h], obs2[h], "k.-", lw=1, label="observed 2nd-highest")
        ax.axhline(2.0, color="orange", lw=1.5)
        p = results["headline"]["Kaya randomised + 2019-24 weighting"][cv]["p_yes"]
        ax.set(title=f"{cv}: P(Yes) = {p:.2f}", xlim=(1990, 2049), xlabel="year")
        ax.legend(fontsize=7, loc="upper left")
    axes[0].set_ylabel("second-highest dataset, °C above 1850-1900")
    fig.tight_layout(); fig.savefig(FIG / "p3_7_fan.png", dpi=130); plt.close(fig)

    # 6 first-crossing histograms (headline spec)
    fig, ax = plt.subplots(figsize=(9, 4))
    bins = np.arange(2025.5, 2050.5, 1)
    for cv, col in (("history", "C0"), ("ipcc", "C3")):
        out, _ = store[("Kaya randomised + 2019-24 weighting", cv)]
        f, w = out["first"], out["w"]
        m = np.isfinite(f)
        ax.hist(f[m], bins=bins, weights=w[m] / w.sum(), alpha=0.5, color=col,
                label=f"{cv} (never by 2049: {1 - (w * out['yes']).sum() / w.sum():.2f})")
    ax.set(title="Year the contract resolves Yes (weighted Kaya)", xlabel="first qualifying year", ylabel="share of paths")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "p3_6_first_crossing.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    main()
