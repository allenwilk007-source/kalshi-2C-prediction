"""Phase 7: scan every live Kalshi climate market the project's models can price.

    python phase7.py      # results/phase7.json, figures/p7_*.png (uses the latest market snapshot)

Model-vs-market comparisons only; nothing here is a recommendation to trade.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import pricing as pc
from market import MKT, fee, latest_snapshot
from model import YEAR0, Inputs, Params, run
from nowcast import backtest, load_monthly, nowcast_year, p_kxgtemp
from phase3 import kaya_setup, setup
from calibrate import fit_version
from scanner import (calibrate_rw, empirical_trend_errors, f, fetch_climate_markets, load_mlo,
                     mlo_components, model_trend_sd, month_of, p_monthly_record, p_strike, simulate_mlo,
                     trend_state)

HERE = Path(__file__).resolve().parent
FIG = HERE / "figures"
OUT = HERE / "results"
N = 20_000
CO2_OPEN = (2025, 7)          # KXCO2LEVEL-30 opened 2025-07-02: readings since then count


def band_for(m):
    """Beliefs where neither side beats holding cash on Kalshi, after fees (100-contract fee rate)."""
    ask, nask = f(m["yes_ask_dollars"]), f(m["no_ask_dollars"])
    yc = ask + fee(ask, 100) / 100 if 0 < ask < 1 else (1.0 if ask >= 1 else float("nan"))
    nc = nask + fee(nask, 100) / 100 if 0 < nask < 1 else (1.0 if nask >= 1 else float("nan"))
    lo, hi = pc.no_trade_band(yc, nc, 1.0, 1.0)
    return max(lo, 0.0), min(hi, 1.0)


def co2_model(st, ks, inp, rng):
    """Probabilities that Mauna Loa reaches each level before 2030 (monthly-mean and daily-max).

    Annual growth = beta x class-model growth (weighted Kaya draws) + kappa x temperature anomaly
    (El Nino years raise CO2 growth) + noise. Temperature anomalies 2026-29 start from the 2026
    nowcast, with the Phase 5 momentum step into 2027 and the course model's AR(1) after that.
    """
    mon, day = load_mlo()
    comp = mlo_components(mon, day)
    base = run(Params(), inp)
    yrs = np.arange(1959, 2021)
    ann = np.array([np.mean([mon[(y, m)][0] for m in range(1, 13) if (y, m) in mon]) for y in yrs])
    mod = base.ppm[yrs - YEAR0]
    beta, alpha = np.polyfit(mod, ann, 1)
    # temperature residuals vs the course model (Phase 2 version A fit)
    fitA = fit_version(Params(), st["years"], st["S"], (1880, 2025), inp)
    rA = {int(y): float(v) for y, v in zip(st["years"], fitA.resid)}
    Y = np.arange(1980, 2021)
    g_obs = np.array([ann[y - 1959] - ann[y - 1960] for y in Y])
    g_mod = beta * np.array([mod[y - 1959] - mod[y - 1960] for y in Y])
    t = np.array([rA[y] for y in Y])
    A = np.column_stack([np.ones_like(t), t])
    (c_g, kappa), *_ = np.linalg.lstsq(A, g_obs - g_mod, rcond=None)
    growth_sd = float(np.std(g_obs - g_mod - (c_g + kappa * t), ddof=2))
    # temperature anomaly paths 2026-2029
    p5 = json.loads((OUT / "phase5.json").read_text())
    s26, mom = p5["signal_2026"], p5["momentum"]
    r26 = s26["mean"] - float(fitA.model_T[2026 - YEAR0]) + rng.normal(0, s26["sd"], N)
    r = {2026: r26}
    r[2027] = mom["c"] + mom["phi1"] * r26 + mom["phi2"] * s26["q4_minus_annual"] + rng.normal(0, mom["sigma"], N)
    for y in (2028, 2029):
        r[y] = fitA.ar1["c"] + fitA.ar1["phi"] * r[y - 1] + rng.normal(0, fitA.ar1["sigma"], N)
    # weighted Kaya draws -> class-model growth
    wk = ks["w_k"][0.02]
    ik = rng.choice(len(wk), size=N, p=wk / wk.sum())
    kaya = {k: v[ik] for k, v in ks["kaya"].items()}
    ppm = run(replace(Params(), **kaya), inp).ppm
    growth = {y: beta * (ppm[:, y - YEAR0] - ppm[:, y - 1 - YEAR0]) + c_g + kappa * r[y] for y in range(2026, 2030)}
    emp = empirical_trend_errors(mon)
    rw_sd = calibrate_rw(comp, growth_sd, emp)
    mod_sd = model_trend_sd(comp, growth_sd, rw_sd)
    last = max(mon)
    trend0, u0 = trend_state(mon, last)
    months, mm, dm = simulate_mlo(last, (2029, 12), trend0, u0, growth, comp, rng, N, growth_sd, rw_sd)
    obs_m = max(v[0] for k, v in mon.items() if k >= CO2_OPEN)
    obs_d = max(v for k, v in day.items() if (k[0], k[1]) >= CO2_OPEN)
    max_m = np.maximum(mm.max(axis=1), obs_m)
    max_d = np.maximum(dm.max(axis=1), obs_d)
    # back-test: start 12 months earlier with the growth actually expected then (trailing 10-yr mean)
    bt_start = (last[0] - 1, last[1])
    tb, ub = trend_state(mon, bt_start)
    g10 = float(np.mean([ann[-1 - k] - ann[-2 - k] for k in range(10)]) if False else np.mean(np.diff(
        [np.mean([mon[(y, m)][0] for m in range(1, 13) if (y, m) in mon]) for y in range(bt_start[0] - 10, bt_start[0] + 1)])))
    bt_months, bt_m, _ = simulate_mlo(bt_start, last, tb, ub, {y: np.full(N, g10) for y in range(bt_start[0], last[0] + 1)},
                                      comp, np.random.default_rng(5), N, growth_sd, rw_sd)
    pred = np.median(bt_m, axis=0)
    act = np.array([mon[k][0] for k in bt_months])
    lo, hi = np.percentile(bt_m, [5, 95], axis=0)
    z12 = float((act[-1] - pred[-1]) / np.std(bt_m[:, -1]))
    info = {"beta": float(beta), "alpha": float(alpha), "growth_sd": growth_sd, "start_month": list(last),
            "rw_sd_monthly": rw_sd, "forecast_error_sd_historical": emp, "forecast_error_sd_model": mod_sd,
            "backtest_z_12m": z12,
            "kappa_ppm_per_C": float(kappa), "temp_anomaly_2026_27_median": [float(np.median(r[2026])), float(np.median(r[2027]))],
            "growth_2026_29_median": [float(np.median(growth[y])) for y in range(2026, 2030)],
            "trend_start": trend0, "observed_max_monthly_since_open": obs_m,
            "observed_max_daily_since_open": obs_d,
            "backtest_rmse": float(np.sqrt(np.mean((pred - act) ** 2))),
            "backtest_coverage_5_95": float(np.mean((act >= lo) & (act <= hi))),
            "max_monthly_p5_50_95": [float(x) for x in np.percentile(max_m, [5, 50, 95])],
            "max_daily_p5_50_95": [float(x) for x in np.percentile(max_d, [5, 50, 95])]}
    return max_m, max_d, info, (months, mm)


def main():
    FIG.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    snap = latest_snapshot()
    cm = MKT / snap["dir"] / "climate_markets.json"
    markets = json.loads(cm.read_text()) if cm.exists() else fetch_climate_markets()
    inp = Inputs.load()
    st = setup(inp)
    ks = kaya_setup(st, inp)
    rng = np.random.default_rng(707)

    mon, (days, _) = load_monthly()
    _, rms = backtest(mon, days)
    nc = nowcast_year(2026, mon, days, total_scale=rms)
    noaa_month = nc["noaa"]["month_draws"]                    # (draws, 12), NOAA native
    giss = nc["giss"]["draws"]
    p5 = json.loads((OUT / "phase5.json").read_text())
    max_m, max_d, co2_info, co2_paths = co2_model(st, ks, inp, rng)

    rows, notes = [], []
    gtemp_rules = {}
    for m in markets:
        s = m["event_ticker"].split("-")[0]
        bid, ask = f(m["yes_bid_dollars"]), f(m["yes_ask_dollars"])
        row = {"series": s, "ticker": m["ticker"], "event": m["event_ticker"], "label": m.get("yes_sub_title") or "",
               "bid": bid, "ask": ask, "mid": (bid + ask) / 2, "last": f(m.get("last_price_dollars")),
               "volume": f(m.get("volume_fp")), "close": m.get("close_time"), "rule": m.get("rules_primary"),
               "p_model": None, "p_alt": None, "method": ""}
        if s == "KXWARMING":
            row["p_model"] = p5["p_yes"]["Kaya randomised + 2019-24 weighting"]["ipcc"]["p_yes"]
            row["p_alt"] = p5["p_yes"]["Kaya randomised + 2019-24 weighting"]["history"]["p_yes"]
            row["method"] = "Phase 5, IPCC-calibrated (alt: history-fit)"
        elif s == "KXGTEMP":
            row["p_model"] = p_kxgtemp(giss)
            row["method"] = "2026 nowcast, GISS annual"
            gtemp_rules.setdefault(m.get("rules_primary"), []).append(row)
        elif s in ("KXHMONTH", "KXHMONTHRANGE"):
            y, mo = month_of(m["event_ticker"])
            if y != 2026:
                continue
            draws = noaa_month[:, mo - 1]
            if s == "KXHMONTH":
                row["p_model"], rec = p_monthly_record(draws, mon["noaa"], y, mo)
                row["method"] = f"ERA5-bridged NOAA {y}-{mo:02d} vs record {rec:.2f}"
            else:
                row["p_model"] = p_strike(draws, m["strike_type"], m.get("floor_strike"), m.get("cap_strike"))
                row["method"] = f"ERA5-bridged NOAA {y}-{mo:02d} ({m['strike_type']})"
        elif s == "KXCO2LEVEL":
            k = float(m["floor_strike"])
            row["p_model"] = p_strike(max_m, "greater_or_equal", k)
            row["p_alt"] = p_strike(max_d, "greater_or_equal", k)
            row["method"] = "Mauna Loa monthly mean (alt: daily max)"
        if row["p_model"] is None:
            continue
        lo, hi = band_for(m)
        row["band"] = [lo, hi]
        P = row["p_model"]
        row["position"] = "inside" if lo - 1e-9 <= P <= hi + 1e-9 else ("above" if P > hi else "below")
        row["gap"] = P - row["mid"]
        rows.append(row)
    for rule, rs in gtemp_rules.items():
        if len(rs) > 1:
            notes.append(f"{' and '.join(r['ticker'] for r in rs)} have the same rule (2026 GISS record) "
                         f"but trade at {', '.join(f'{r['bid']:.2f}/{r['ask']:.2f}' for r in rs)}")
    # each range event's bins should sum to ~1 under the model
    sums = {}
    for r in rows:
        if r["series"] == "KXHMONTHRANGE":
            sums[r["event"]] = sums.get(r["event"], 0) + r["p_model"]

    rows.sort(key=lambda r: -abs(r["gap"]))
    print(f"\nKalshi climate-market scanner, snapshot {snap['dir']} ({len(rows)} markets)")
    print(f"  {'ticker':28s} {'contract':22s} {'bid/ask':>11s} {'model':>7s} {'alt':>6s} {'band':>13s} {'gap':>7s}  position")
    for r in rows:
        alt = f"{r['p_alt']:.3f}" if r["p_alt"] is not None else ""
        print(f"  {r['ticker']:28s} {r['label'][:22]:22s} {r['bid']:.2f}/{r['ask']:.2f} {r['p_model']:7.3f} {alt:>6s} "
              f"[{r['band'][0]:.2f},{r['band'][1]:.2f}] {r['gap']:+7.3f}  {r['position']}")
    print("  range-event bin sums: " + ", ".join(f"{k} {v:.3f}" for k, v in sums.items()))
    for n in notes:
        print("  NOTE:", n)
    ci = co2_info
    print(f"\nCO2: MLO = {ci['alpha']:.1f} + {ci['beta']:.3f} x model ppm; +{ci['kappa_ppm_per_C']:.2f} ppm/yr growth per +1 C anomaly; "
          f"growth noise sd {ci['growth_sd']:.2f}; temp anomaly 2026/27 {[round(x, 2) for x in ci['temp_anomaly_2026_27_median']]}; "
          f"growth 2026-29 {[round(x, 2) for x in ci['growth_2026_29_median']]} ppm/yr")
    print(f"     observed max since market opened: monthly {ci['observed_max_monthly_since_open']:.2f}, daily {ci['observed_max_daily_since_open']:.2f}; "
          f"simulated max before 2030: monthly {ci['max_monthly_p5_50_95'][1]:.1f} [{ci['max_monthly_p5_50_95'][0]:.1f}-{ci['max_monthly_p5_50_95'][2]:.1f}], "
          f"daily {ci['max_daily_p5_50_95'][1]:.1f}")
    print("     trend uncertainty calibrated to history (sd of forecast misses, ppm): "
          + ", ".join(f"{h} mo: historical {ci['forecast_error_sd_historical'][h]:.2f} vs model {ci['forecast_error_sd_model'][h]:.2f}"
                      for h in ci["forecast_error_sd_historical"]))
    print(f"     2025-26 back-test: 12-month miss = {ci['backtest_z_12m']:+.1f} sd (slow post-La Nina growth); "
          f"RMSE {ci['backtest_rmse']:.2f} ppm")

    figures(rows, co2_paths)
    res = {"snapshot": snap["dir"], "rows": rows, "notes": notes, "range_bin_sums": sums, "co2": co2_info}
    (OUT / "phase7.json").write_text(json.dumps(res, indent=1, default=float))
    print(f"\nwrote {OUT / 'phase7.json'} and figures/p7_*.png")


def figures(rows, co2_paths):
    rs = sorted(rows, key=lambda r: (r["series"], r["ticker"]))
    fig, ax = plt.subplots(figsize=(10, 0.36 * len(rs) + 1.5))
    for i, r in enumerate(rs):
        ax.plot(r["band"], [i, i], color="orange", lw=7, alpha=0.5, solid_capstyle="butt")
        ax.plot(r["mid"], i, "|", color="k", ms=12)
        ax.plot(r["p_model"], i, "o", color="C3")
        if r["p_alt"] is not None:
            ax.plot(r["p_alt"], i, "o", mfc="none", color="C3")
    ax.set_yticks(range(len(rs)), [f"{r['ticker']}  {r['label'][:18]}" for r in rs], fontsize=7)
    ax.set(xlim=(-0.02, 1.02), xlabel="probability",
           title="Kalshi climate markets: model (red; hollow = alternative reading) vs market (bar = range after fees, | = mid)")
    fig.tight_layout(); fig.savefig(FIG / "p7_1_scanner.png", dpi=130); plt.close(fig)

    months, mm = co2_paths
    x = np.arange(len(months))
    q = np.percentile(mm, [5, 50, 95], axis=0)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.fill_between(x, q[0], q[2], alpha=0.2, color="C0", label="5-95%")
    ax.plot(x, q[1], color="C0", label="median monthly mean")
    for k in (440, 445, 450):
        ax.axhline(k, color="grey", ls=":", lw=1)
    step = max(1, len(months) // 12)
    ax.set_xticks(x[::step], [f"{y}-{m:02d}" for y, m in months[::step]], rotation=45, fontsize=7)
    ax.set(ylabel="ppm", title="Mauna Loa CO2: simulated monthly means to Dec 2029 (Kalshi strikes dotted)")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "p7_2_co2.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    main()
