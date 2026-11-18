"""Price live Kalshi climate markets with the project's models (public data only, no login).

Covered series and how each is modelled:
  KXWARMING  2-of-4 datasets >= 2.00 C before 2050           Phase 5 (IPCC-calibrated headline)
  KXGTEMP    GISS annual 2026 > 1.28 and > 2025               Phase 5 nowcast, GISS draws
  KXHMONTH   NCEI month is the hottest of that month ever     ERA5-bridged NOAA monthly draws vs NOAA record
  KXHMONTHRANGE  NOAA monthly anomaly in a bin                same NOAA monthly draws, market's own strikes
  KXCO2LEVEL Mauna Loa CO2 >= K before Jan 2030               class carbon cycle (weighted Kaya) trend
                                                              + MLO seasonal cycle + noise; monthly-mean and
                                                              daily-max readings (rule doesn't say which)
"""
from __future__ import annotations

import hashlib
import json
import math
import urllib.request
from datetime import datetime, timezone

import numpy as np

from observations import MANIFEST, RAW, UA

API = "https://api.elections.kalshi.com/trade-api/v2"
SERIES = ("KXWARMING", "KXGTEMP", "KXHMONTH", "KXHMONTHRANGE", "KXCO2LEVEL")
MLO = {"mlo_monthly": "https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_mm_mlo.txt",
       "mlo_daily": "https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_daily_mlo.txt"}


# ---------------------------------------------------------------- Kalshi
def fetch_climate_markets() -> list:
    out = []
    for s in SERIES:
        url = f"{API}/markets?series_ticker={s}&status=open&limit=200"
        d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read())
        out += d.get("markets", [])
    return out


def f(x):
    return float(x) if x not in (None, "") else float("nan")


def round2(x):
    return np.floor(np.asarray(x, dtype=float) * 100 + 0.5 + 1e-9) / 100


def p_strike(draws, strike_type, floor=None, cap=None) -> float:
    """P(published value, rounded to 0.01, satisfies the market's strike)."""
    v = round2(draws)
    e = 1e-9
    if strike_type == "greater":
        hit = v > floor + e
    elif strike_type == "greater_or_equal":
        hit = v >= floor - e
    elif strike_type == "less":
        hit = v < cap - e
    elif strike_type == "less_or_equal":
        hit = v <= cap + e
    elif strike_type == "between":
        hit = (v >= floor - e) & (v <= cap + e)
    else:
        raise ValueError(strike_type)
    return float(np.mean(hit))


def month_of(ticker: str):
    """'KXHMONTH-26NOV' -> (2026, 11)."""
    mons = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    code = ticker.split("-")[1]
    return 2000 + int(code[:2]), mons.index(code[2:5]) + 1


def p_monthly_record(draws, history: dict, year: int, month: int) -> tuple[float, float]:
    """P(month is the hottest of that calendar month in the record), and the record value."""
    rec = max(v for (y, m), v in history.items() if m == month and y < year)
    return float(np.mean(round2(draws) > round2(rec) + 1e-9)), float(rec)


# ---------------------------------------------------------------- Mauna Loa CO2
def download_mlo(refresh=False):
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    for name, url in MLO.items():
        path = RAW / f"{name}.txt"
        if path.exists() and not refresh and name in manifest:
            continue
        data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read()
        path.write_bytes(data)
        manifest[name] = {"url": url, "downloaded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                          "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    MANIFEST.write_text(json.dumps(manifest, indent=1))


def load_mlo():
    download_mlo()
    monthly, daily = {}, {}
    for line in (RAW / "mlo_monthly.txt").read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        p = line.split()
        avg, des = float(p[3]), float(p[4])
        if avg > 0:
            monthly[(int(p[0]), int(p[1]))] = (avg, des)
    for line in (RAW / "mlo_daily.txt").read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        p = line.split()
        v = float(p[4])
        if v > 0:
            daily[(int(p[0]), int(p[1]), int(p[2]))] = v
    return monthly, daily


def _ar1(x):
    x = np.asarray(x) - np.mean(x)
    phi = float(np.corrcoef(x[:-1], x[1:])[0, 1])
    return phi, float(np.std(x[1:] - phi * x[:-1], ddof=1))


def mlo_components(monthly, daily, years=(2010, 2025)):
    """MLO structure: monthly = trend + u (AR(1) wiggles in the deseasonalised series)
    + seasonal(month) + e (small AR(1) year-to-year variation of the seasonal cycle).
    Also the daily-max-minus-monthly-mean gap by month (for a daily reading of the rule)."""
    seas = {m: float(np.mean([a - d for (y, mm), (a, d) in monthly.items() if mm == m and years[0] <= y <= years[1]]))
            for m in range(1, 13)}
    keys = sorted(k for k in monthly if years[0] <= k[0] <= years[1])
    e = np.array([monthly[k][0] - monthly[k][1] - seas[k[1]] for k in keys])
    phi, sig = _ar1(e)
    # NOAA's "deseasonalised" column still carries month-to-month wiggles around the trend
    allk = sorted(monthly)
    des = np.array([monthly[k][1] for k in allk])
    ma = np.convolve(des, np.ones(13) / 13, mode="same")
    sel = np.array([years[0] <= k[0] <= years[1] for k in allk]) & (np.arange(len(allk)) >= 6) & (np.arange(len(allk)) < len(allk) - 6)
    u = des[sel] - ma[sel]
    phi_u, sig_u = _ar1(u)
    gaps = {m: [] for m in range(1, 13)}
    for (y, m), (a, _) in monthly.items():
        if years[0] <= y <= years[1]:
            vals = [v for (yy, mm, dd), v in daily.items() if yy == y and mm == m]
            if len(vals) >= 10:
                gaps[m].append(max(vals) - a)
    return {"seasonal": seas, "phi": phi, "sigma": sig, "phi_u": phi_u, "sigma_u": sig_u,
            "gaps": {m: np.array(g) for m, g in gaps.items()}}


def trend_state(monthly, start, months_back=24):
    """Trend level at `start` from a linear fit to the last 24 deseasonalised months; u0 = des - trend."""
    keys = sorted(k for k in monthly if k <= start)[-months_back:]
    t = np.arange(len(keys))
    d = np.array([monthly[k][1] for k in keys])
    b, a = np.polyfit(t, d, 1)
    trend0 = a + b * t[-1]
    return float(trend0), float(d[-1] - trend0)


def empirical_trend_errors(monthly, horizons=(12, 24, 36), origins=(1990, 2023)):
    """How far a 'trend + trailing 10-yr growth' forecast of the deseasonalised level has missed,
    by horizon (sd over all monthly origins). Used to size the model's trend uncertainty."""
    keys = sorted(monthly)
    idx = {k: i for i, k in enumerate(keys)}
    ann = {y: np.mean([monthly[(y, m)][0] for m in range(1, 13) if (y, m) in monthly])
           for y in range(keys[0][0], keys[-1][0] + 1)}
    err = {h: [] for h in horizons}
    for o in keys:
        if not (origins[0] <= o[0] <= origins[1]):
            continue
        t0, _ = trend_state(monthly, o)
        g = np.mean([ann[o[0] - k] - ann[o[0] - k - 1] for k in range(1, 11)])
        for h in horizons:
            if idx[o] + h < len(keys):
                k = keys[idx[o] + h]
                err[h].append(monthly[k][1] - (t0 + g * h / 12))
    return {h: float(np.std(e, ddof=1)) for h, e in err.items()}


def model_trend_sd(comp, growth_sd, rw_sd, horizons=(12, 24, 36), n=4000, seed=0):
    """sd of the simulated deseasonalised level (trend + u) at each horizon, growth mean set to 0."""
    rng = np.random.default_rng(seed)
    H = max(horizons)
    trend, u, out = np.zeros(n), np.zeros(n), {}
    shock = None
    for h in range(1, H + 1):
        if (h - 1) % 12 == 0:
            shock = rng.normal(0, growth_sd, n)
        trend = trend + shock / 12 + rng.normal(0, rw_sd, n)
        u = comp["phi_u"] * u + rng.normal(0, comp["sigma_u"], n)
        if h in horizons:
            out[h] = float(np.std(trend + u))
    return out


def calibrate_rw(comp, growth_sd, emp: dict, grid=np.linspace(0.0, 0.4, 81)):
    """Monthly random-walk sd for the trend so the model's spread matches historical forecast errors."""
    best = min(grid, key=lambda s: sum((model_trend_sd(comp, growth_sd, s)[h] - v) ** 2 for h, v in emp.items()))
    return float(best)


def simulate_mlo(start, end, trend0, u0, growth_by_year, comp, rng, n, growth_sd=0.0, rw_sd=0.0):
    """Monthly MLO paths from the month after `start` to `end` inclusive.

    trend0, u0: smooth trend level and wiggle at `start` (trend_state);
    growth_by_year: dict year -> (n,) ppm/yr for that calendar year;
    growth_sd: unexplained year-to-year growth noise.
    Returns (months list, monthly (n, M), daily_max (n, M)).
    """
    months = []
    y, m = start
    while (y, m) != end:
        m += 1
        if m == 13:
            y, m = y + 1, 1
        months.append((y, m))
    shocks = {yy: rng.normal(0, growth_sd, n) for yy in {mm[0] for mm in months}}
    trend = np.full(n, trend0, dtype=float)
    u = np.full(n, u0, dtype=float)
    e = np.zeros(n)
    mon, dmax = np.empty((n, len(months))), np.empty((n, len(months)))
    for j, (yy, mm) in enumerate(months):
        trend = trend + (np.asarray(growth_by_year[yy]) + shocks[yy]) / 12 + (rng.normal(0, rw_sd, n) if rw_sd else 0.0)
        u = comp["phi_u"] * u + rng.normal(0, comp["sigma_u"], n)
        e = comp["phi"] * e + rng.normal(0, comp["sigma"], n)
        mon[:, j] = trend + u + comp["seasonal"][mm] + e
        g = comp["gaps"][mm]
        dmax[:, j] = mon[:, j] + (rng.choice(g, n) if len(g) else 0.0)
    return months, mon, dmax
