"""Nowcast the 2026 annual temperature for each settlement dataset from what is published so far.

Monthly sources (public, cached in data/obs/raw/, manifest entries added):
  GISS     tabledata_v4/GLB.Ts+dSST.csv               native 1951-80
  NOAA     Climate-at-a-Glance monthly land+ocean     native 1901-2000
  HadCRUT  5.1.0.0 monthly summary (already cached)   native 1961-90
  ERA5     Copernicus Climate Pulse daily global 2 m air temperature, anomaly vs 1991-2020
           (not a settlement dataset; used to fill months the four agencies haven't published)
Berkeley publishes nothing for 2026 yet, so its 2026 stays missing.

Method for each dataset k and each month it hasn't published:
  bridge   x_k,m = alpha_k + beta_k * ERA5_m + e,   e ~ AR(1)(rho_k, s_k), fitted 1991-2025
  partial  a month with only n ERA5 days: ERA5_m = mean(first n days) + N(0, sd_n), sd_n from history
  future   a month with no ERA5 yet: monthly ERA5 AR(1) forecast from the previous month
2026 annual = mean of 12 months (observed + filled), as Monte Carlo draws.
"""
from __future__ import annotations

import calendar
import csv
import hashlib
import io
import json
import math
import urllib.request
from datetime import datetime, timezone

import numpy as np

from observations import MANIFEST, RAW, UA, load_native, rebaseline, window_mean, DATASETS

SOURCES = {
    "giss_monthly": "https://data.giss.nasa.gov/gistemp/tabledata_v4/GLB.Ts+dSST.csv",
    "noaa_monthly": "https://www.ncei.noaa.gov/access/monitoring/climate-at-a-glance/global/"
                    "time-series/globe/tavg/land_ocean/1/0/1850-2026/data.csv",
    "era5_daily": "https://sites.ecmwf.int/data/climatepulse/data/series/era5_daily_series_2t_global.csv",
}
BRIDGE_YEARS = (1991, 2025)
MONTHLY_SETS = ("giss", "noaa", "hadcrut")


# ---------------------------------------------------------------- download / parse
def download(refresh: bool = False) -> None:
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    for name, url in SOURCES.items():
        path = RAW / f"{name}.txt"
        if path.exists() and not refresh and name in manifest:
            continue
        data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read()
        path.write_bytes(data)
        manifest[name] = {"url": url, "downloaded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                          "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        print(f"downloaded {name}: {len(data):,} bytes")
    MANIFEST.write_text(json.dumps(manifest, indent=1))


def _txt(name):
    return (RAW / f"{name}.txt").read_text(encoding="utf-8", errors="replace")


def parse_giss_monthly(txt) -> dict:
    out = {}
    rows = list(csv.reader(io.StringIO(txt)))
    for r in rows:
        if r and r[0].isdigit():
            y = int(r[0])
            for m in range(1, 13):
                v = r[m].strip()
                if v and "*" not in v:
                    out[(y, m)] = float(v)
    return out


def parse_noaa_monthly(txt) -> dict:
    out = {}
    for line in txt.splitlines():
        p = line.split(",")
        if p and len(p[0]) == 6 and p[0].isdigit():
            out[(int(p[0][:4]), int(p[0][4:]))] = float(p[1])
    return out


def parse_hadcrut_monthly(txt) -> dict:
    out = {}
    for r in csv.reader(io.StringIO(txt)):
        if r and len(r[0]) == 7 and r[0][:4].isdigit():
            out[(int(r[0][:4]), int(r[0][5:7]))] = float(r[1])
    return out


def parse_era5_daily(txt):
    """-> (days dict {(y,m): [anomalies in day order]}, last date)."""
    days, last = {}, None
    for line in txt.splitlines():
        if not line or line.startswith("#") or not line[:4].isdigit():
            continue
        p = line.split(",")
        y, m, d = int(p[0][:4]), int(p[0][5:7]), int(p[0][8:10])
        days.setdefault((y, m), []).append(float(p[3]))
        last = (y, m, d)
    return days, last


def load_monthly():
    download()
    return {
        "giss": parse_giss_monthly(_txt("giss_monthly")),
        "noaa": parse_noaa_monthly(_txt("noaa_monthly")),
        "hadcrut": parse_hadcrut_monthly(_txt("hadcrut_monthly")),
    }, parse_era5_daily(_txt("era5_daily"))


def era5_monthly(days: dict) -> dict:
    """Complete months only."""
    return {k: float(np.mean(v)) for k, v in days.items() if len(v) == calendar.monthrange(*k)[1]}


# ---------------------------------------------------------------- statistics
def ols(x, y):
    A = np.column_stack([np.ones_like(x), x])
    (a, b), *_ = np.linalg.lstsq(A, y, rcond=None)
    e = y - (a + b * x)
    return float(a), float(b), e


def lag1(e):
    e = np.asarray(e) - np.mean(e)
    return float(np.corrcoef(e[:-1], e[1:])[0, 1]) if len(e) > 2 else 0.0


def fit_bridge(monthly_k: dict, era5_m: dict, years=BRIDGE_YEARS) -> dict:
    keys = sorted(k for k in monthly_k if k in era5_m and years[0] <= k[0] <= years[1])
    x = np.array([era5_m[k] for k in keys])
    y = np.array([monthly_k[k] for k in keys])
    a, b, e = ols(x, y)
    return {"alpha": a, "beta": b, "s": float(np.std(e, ddof=2)), "rho": lag1(e), "n": len(keys)}


def partial_month_sd(days: dict, n_days: int, years=BRIDGE_YEARS) -> float:
    """sd of (full-month mean - mean of first n days), over complete historical months."""
    d = [np.mean(v) - np.mean(v[:n_days]) for k, v in days.items()
         if years[0] <= k[0] <= years[1] and len(v) == calendar.monthrange(*k)[1]]
    return float(np.std(d, ddof=1))


def fit_monthly_ar1(era5_m: dict, years=BRIDGE_YEARS) -> dict:
    """ERA5 monthly anomaly = linear warming trend + AR(1) deviation.

    Reverting to the trend (not to the 1991-2025 average) matters for forecasts many months ahead:
    the period average sits ~0.6 C below today's climate."""
    keys = sorted(k for k in era5_m if years[0] <= k[0] <= years[1])
    t = np.array([k[0] + (k[1] - 0.5) / 12 for k in keys])
    v = np.array([era5_m[k] for k in keys])
    b, a = np.polyfit(t, v, 1)
    y = v - (a + b * t)
    _, phi, e = ols(y[:-1], y[1:])
    return {"a": float(a), "b": float(b), "phi": phi, "sigma": float(np.std(e, ddof=2))}


def ar1_forecast(ar: dict, prev, prev_key, rng, n):
    """One-month-ahead ERA5 draw from the previous month's value(s)."""
    tp = prev_key[0] + (prev_key[1] - 0.5) / 12
    trend = lambda t: ar["a"] + ar["b"] * t
    return trend(tp + 1 / 12) + ar["phi"] * (prev - trend(tp)) + rng.normal(0, ar["sigma"], n)


# ---------------------------------------------------------------- nowcast
def bridge_residual_corr(monthly: dict, era5_m: dict, years) -> float:
    """Mean pairwise correlation of the three datasets' bridge residuals (shared surface error)."""
    keys = sorted(k for k in era5_m if years[0] <= k[0] <= years[1] and all(k in monthly[d] for d in MONTHLY_SETS))
    x = np.array([era5_m[k] for k in keys])
    E = [ols(x, np.array([monthly[d][k] for k in keys]))[2] for d in MONTHLY_SETS]
    C = np.corrcoef(E)
    return float(np.mean(C[np.triu_indices(3, 1)]))


def nowcast_year(year: int, monthly: dict, era5_days: dict, cutoff=None, n_draws=20_000, seed=0,
                 bridge_years=None, observed_months=None, sd_scale=1.0, shared=True, total_scale=1.0):
    """Predictive draws of each monthly dataset's annual mean for `year` (native baseline).

    cutoff: (y, m, d) last ERA5 day to use (default: all available).
    observed_months: {dataset: last published month} to truncate (for back-tests); default = all.
    bridge_years: fit window (default 1991..year-1, so no look-ahead).
    sd_scale: multiplies the bridge error sd (set from the back-test's RMS z-score).
    shared: bridge errors share a common component across datasets (correlation from history).
    total_scale: widen every draw's deviation from its dataset mean by this factor (calibration
                 from the back-test's RMS z-score; the same factor for all datasets keeps their
                 correlation).
    Returns dict dataset -> {"draws", "months_obs", "months_filled", "q4_draws"} and era5 info.
    """
    rng = np.random.default_rng(seed)
    by = bridge_years or (BRIDGE_YEARS[0], year - 1)
    # ERA5 days up to cutoff
    days = {}
    for k, v in era5_days.items():
        if cutoff and (k[0], k[1]) > (cutoff[0], cutoff[1]):
            continue
        vv = v[:cutoff[2]] if cutoff and k == (cutoff[0], cutoff[1]) else v
        if vv:
            days[k] = vv
    e5_full = era5_monthly(days)
    ar = fit_monthly_ar1(e5_full, by)

    # ERA5 draws for each month of `year`
    e5 = np.empty((n_draws, 12))
    prev = None
    for m in range(1, 13):
        k = (year, m)
        if k in e5_full:
            e5[:, m - 1] = e5_full[k]
        elif k in days:                                     # partial month
            n = len(days[k])
            e5[:, m - 1] = np.mean(days[k]) + rng.normal(0, partial_month_sd(days, n, by), n_draws)
        else:                                               # not started: AR(1)-around-trend forecast
            base = e5[:, m - 2] if m > 1 else np.full(n_draws, e5_full.get((year - 1, 12), 0.0))
            prev_key = (year, m - 1) if m > 1 else (year - 1, 12)
            e5[:, m - 1] = ar1_forecast(ar, base, prev_key, rng, n_draws)
    cc = bridge_residual_corr({d: {k: v for k, v in monthly[d].items() if k[0] < year} for d in MONTHLY_SETS},
                              e5_full, by) if shared else 0.0
    cc = min(max(cc, 0.0), 0.99)
    Z = rng.standard_normal((n_draws, 12))                  # shared monthly shock across datasets
    out = {"_era5_draws": e5, "_era5_ar1": ar, "_shared_corr": cc, "_sd_scale": sd_scale}
    for ds in MONTHLY_SETS:
        mk = monthly[ds]
        last = observed_months.get(ds) if observed_months else None
        obs = {m: mk[(year, m)] for m in range(1, 13) if (year, m) in mk and (last is None or m <= last)}
        bridge = fit_bridge({k: v for k, v in mk.items() if k[0] < year}, e5_full, by)
        s, rho = bridge["s"] * sd_scale, bridge["rho"]
        vals = np.empty((n_draws, 12))
        err = np.zeros(n_draws)
        filled = []
        for m in range(1, 13):
            if m in obs:
                vals[:, m - 1] = obs[m]
                err = np.zeros(n_draws)                     # observed month resets the error chain
            else:
                shock = math.sqrt(cc) * Z[:, m - 1] + math.sqrt(1 - cc) * rng.standard_normal(n_draws)
                if filled and filled[-1] == m - 1:
                    err = rho * err + s * math.sqrt(1 - rho ** 2) * shock
                else:
                    err = s * shock
                vals[:, m - 1] = bridge["alpha"] + bridge["beta"] * e5[:, m - 1] + err
                filled.append(m)
        ann, q4 = vals.mean(axis=1), vals[:, 9:12].mean(axis=1)
        if total_scale != 1.0:
            ann = ann.mean() + total_scale * (ann - ann.mean())
            q4 = q4.mean() + total_scale * (q4 - q4.mean())
        mdraws = vals.mean(axis=0) + total_scale * (vals - vals.mean(axis=0))
        out[ds] = {"draws": ann, "q4_draws": q4, "month_draws": mdraws,
                   "month_mean": vals.mean(axis=0), "month_sd": vals.std(axis=0) * total_scale,
                   "months_obs": sorted(obs), "months_filled": filled, "bridge": bridge}
    out["_total_scale"] = total_scale
    return out


BACKTEST_YEARS = (2023, 2024, 2025)
LAG_AS_OF_NOV8 = {"giss": 9, "noaa": 9, "hadcrut": 7}       # publication lag seen on 2026-11-08


def backtest(monthly, era5_days, years=BACKTEST_YEARS, total_scale=1.0):
    """Nowcast each past year with only the data available on ~8 November, vs the actual annual."""
    rows = []
    for Y in years:
        nc = nowcast_year(Y, monthly, era5_days, cutoff=(Y, 11, 6), observed_months=LAG_AS_OF_NOV8,
                          total_scale=total_scale)
        for k in MONTHLY_SETS:
            act = float(np.mean([monthly[k][(Y, m)] for m in range(1, 13)]))
            d = nc[k]["draws"]
            rows.append({"year": Y, "dataset": k, "pred": float(d.mean()), "sd": float(d.std()),
                         "actual": act, "z": float((act - d.mean()) / d.std())})
    z = np.array([r["z"] for r in rows])
    return rows, float(np.sqrt(np.mean(z ** 2)))


def shifts() -> dict:
    """Native -> 1850-1900 shift per dataset (same as observations.rebaseline)."""
    nat = load_native()
    rb = rebaseline(nat)
    return {k: nat[k][2000] - rb[k][2000] for k in DATASETS}


def round2(x):
    return np.floor(np.asarray(x) * 100 + 0.5 + 1e-9) / 100


def p_kxgtemp(giss_draws, record=1.28, prev_year=1.18):
    """KXGTEMP-26: GISS 2026 unsmoothed annual (published to 0.01) above 2025 AND above 1.28."""
    r = round2(giss_draws)
    return float(np.mean((r > record + 1e-9) & (r > prev_year + 1e-9)))


# ---------------------------------------------------------------- momentum
def monthly_signal(monthly: dict, sh: dict, delta: dict) -> dict:
    """Offset-adjusted monthly common signal on the 1850-1900 basis: mean_k(x_k - shift_k - delta_k)."""
    keys = set().union(*(monthly[k].keys() for k in MONTHLY_SETS))
    out = {}
    for key in keys:
        v = [monthly[k][key] - sh[k] - delta[k] for k in MONTHLY_SETS if key in monthly[k]]
        out[key] = float(np.mean(v))
    return out


def fit_momentum(resid_by_year: dict, q4_minus_annual: dict, years=(1960, 2025)) -> dict:
    """r(Y+1) = c + phi1 r(Y) + phi2 m(Y) + e, where m = Q4 signal - annual signal."""
    ys = [y for y in range(years[0], years[1]) if y in resid_by_year and y + 1 in resid_by_year and y in q4_minus_annual]
    y1 = np.array([resid_by_year[y + 1] for y in ys])
    X = np.column_stack([np.ones(len(ys)), [resid_by_year[y] for y in ys], [q4_minus_annual[y] for y in ys]])
    coef, *_ = np.linalg.lstsq(X, y1, rcond=None)
    e = y1 - X @ coef
    s2 = float(e @ e) / (len(ys) - 3)
    se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
    return {"c": float(coef[0]), "phi1": float(coef[1]), "phi2": float(coef[2]),
            "t_phi2": float(coef[2] / se[2]), "se_phi2": float(se[2]), "sigma": math.sqrt(s2), "n": len(ys)}
