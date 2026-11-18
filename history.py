"""Kalshi price history (public daily candles) and a day-by-day 'what did the data say' nowcast.

Candles: GET /series/{series}/markets/{ticker}/candlesticks?period_interval=1440 (public, no login),
cached in data/market/candles/<ticker>.json.

Rolling nowcast for KXGTEMP-26: for each day D of 2026, re-run the Phase 5 nowcast using only data
that existed on D:
  ERA5 daily       up to D - 2 days (Copernicus Climate Pulse runs ~2 days behind)
  GISS, NOAA       month m treated as published on the 15th of month m+1
  HadCRUT 5.1      month m treated as published on the 15th of month m+3 (matches its lag in Nov 2026)
Those publication dates are approximations; they are stated wherever results are shown.
"""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from nowcast import nowcast_year, p_kxgtemp

HERE = Path(__file__).resolve().parent
CANDLES = HERE / "data" / "market" / "candles"
API = "https://api.elections.kalshi.com/trade-api/v2"
UA = {"User-Agent": "fecon-climate-research-script"}
LAG_MONTHS = {"giss": 1, "noaa": 1, "hadcrut": 3}
PUB_DAY = 15


def fetch_candles(series: str, ticker: str, start: date, refresh=True) -> list:
    CANDLES.mkdir(parents=True, exist_ok=True)
    path = CANDLES / f"{ticker}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text())
    t0 = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp())
    t1 = int(time.time())
    url = f"{API}/series/{series}/markets/{ticker}/candlesticks?start_ts={t0}&end_ts={t1}&period_interval=1440"
    d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read())
    c = d.get("candlesticks", [])
    path.write_text(json.dumps(c))
    return c


def candle_series(candles: list):
    """-> (dates, price, volume, open_interest). Price = traded close, else bid/ask mid at close."""
    out = []
    for c in candles:
        day = datetime.fromtimestamp(c["end_period_ts"], timezone.utc).date() - timedelta(days=1)
        p = c.get("price", {}).get("close_dollars")
        if p in (None, ""):
            b, a = c.get("yes_bid", {}).get("close_dollars"), c.get("yes_ask", {}).get("close_dollars")
            p = (float(b) + float(a)) / 2 if b not in (None, "") and a not in (None, "") else None
        if p is None:
            continue
        out.append((day, float(p), float(c.get("volume_fp") or 0), float(c.get("open_interest_fp") or 0)))
    out.sort()
    return ([o[0] for o in out], np.array([o[1] for o in out]), np.array([o[2] for o in out]),
            np.array([o[3] for o in out]))


def published_month(ds: str, d: date, year: int):
    """Last month of `year` that dataset `ds` had published by date d (0 = none)."""
    last = 0
    for m in range(1, 13):
        pm = m + LAG_MONTHS[ds]
        py, pmm = year + (pm - 1) // 12, (pm - 1) % 12 + 1
        if d >= date(py, pmm, PUB_DAY):
            last = m
    return last


def rolling_kxgtemp(monthly, era5_days, days: list, total_scale: float, n_draws=3000, seed=0):
    """Model P(KXGTEMP-26 = Yes) as it would have been computed on each day."""
    out = []
    for d in days:
        cut = d - timedelta(days=2)
        obs = {ds: published_month(ds, d, 2026) for ds in LAG_MONTHS}
        nc = nowcast_year(2026, monthly, era5_days, cutoff=(cut.year, cut.month, cut.day), n_draws=n_draws,
                          seed=seed, observed_months=obs, total_scale=total_scale)
        g = nc["giss"]["draws"]
        out.append({"date": d.isoformat(), "p": p_kxgtemp(g), "giss_mean": float(g.mean()),
                    "giss_sd": float(g.std()), "giss_months_published": obs["giss"]})
    return out


def lead_lag(a: np.ndarray, b: np.ndarray, max_lag=5) -> dict:
    """corr(a_t, b_{t-k}) for k = -max_lag..max_lag. Positive k: b leads a by k days."""
    out = {}
    for k in range(-max_lag, max_lag + 1):
        if k >= 0:
            x, y = a[k:], b[:len(b) - k]
        else:
            x, y = a[:k], b[-k:]
        out[k] = float(np.corrcoef(x, y)[0, 1]) if len(x) > 3 and x.std() > 0 and y.std() > 0 else float("nan")
    return out
