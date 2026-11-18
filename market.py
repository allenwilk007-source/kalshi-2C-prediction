"""Public market data for KXWARMING-50 plus US Treasury yields. No login, no orders.

    python market.py            # fetch a new snapshot into data/market/<UTC timestamp>/
    python market.py --show     # print the latest cached snapshot

Kalshi public REST API (trade-api v2): market, order book, full trade history (cursor-paginated).
Treasury: daily nominal and real par yield curves for the current year (home.treasury.gov CSV).

Fee schedule (kalshi.com/fee-schedule, checked 2026-11-08): KXWARMING is on the standard schedule,
taker fee = ceil_to_cent(0.07 * contracts * P * (1 - P)) per order, no maker fee, no settlement fee.
Interest (help.kalshi.com "APY on Kalshi", checked 2026-11-08): 3.50 % APY, variable, on cash and
open positions marked at last trade, accrued daily, $250 minimum average monthly balance.
"""
from __future__ import annotations

import csv
import io
import json
import math
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
MKT = HERE / "data" / "market"
UA = {"User-Agent": "fecon-climate-research-script"}
API = "https://api.elections.kalshi.com/trade-api/v2"
TICKER = "KXWARMING-50"
TREASURY = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
            "daily-treasury-rates.csv/{y}/all?type={t}&field_tdr_date_value={y}&page&_format=csv")
CLIMATE_SERIES = ("KXWARMING", "KXGTEMP", "KXHMONTH", "KXHMONTHRANGE", "KXCO2LEVEL")
TAKER_RATE = 0.07
KALSHI_APY = 0.035          # variable; checked 2026-11-08
APY_CHECKED = "2026-11-08"


# ---------------------------------------------------------------- fetch
def _get(url: str) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()


def _trades() -> list:
    out, cursor = [], ""
    while True:
        url = f"{API}/markets/trades?ticker={TICKER}&limit=1000" + (f"&cursor={cursor}" if cursor else "")
        d = json.loads(_get(url))
        out += d.get("trades", [])
        cursor = d.get("cursor") or ""
        if not cursor or not d.get("trades"):
            return out


def fetch() -> Path:
    now = datetime.now(timezone.utc)
    d = MKT / now.strftime("%Y%m%dT%H%M%SZ")
    d.mkdir(parents=True)
    files = {
        "market.json": _get(f"{API}/markets/{TICKER}"),
        "orderbook.json": _get(f"{API}/markets/{TICKER}/orderbook"),
        "trades.json": json.dumps(_trades()).encode(),
        "treasury_nominal.csv": _get(TREASURY.format(y=now.year, t="daily_treasury_yield_curve")),
        "treasury_real.csv": _get(TREASURY.format(y=now.year, t="daily_treasury_real_yield_curve")),
        "kxgtemp_26.json": _get(f"{API}/events/KXGTEMP-26?with_nested_markets=true"),
        "climate_markets.json": json.dumps([m for s in CLIMATE_SERIES for m in json.loads(
            _get(f"{API}/markets?series_ticker={s}&status=open&limit=200")).get("markets", [])]).encode(),
    }
    for name, data in files.items():
        (d / name).write_bytes(data)
    (d / "manifest.json").write_text(json.dumps({
        "fetched_utc": now.isoformat(timespec="seconds"), "ticker": TICKER, "api": API,
        "kalshi_apy": KALSHI_APY, "apy_checked": APY_CHECKED, "taker_rate": TAKER_RATE,
        "files": {k: len(v) for k, v in files.items()}}, indent=1))
    print(f"fetched snapshot {d.name}: {len(json.loads(files['trades.json']))} trades")
    return d


def latest_dir(refresh: bool = False) -> Path:
    dirs = sorted(p for p in MKT.glob("*T*Z") if p.is_dir()) if MKT.exists() else []
    return fetch() if (refresh or not dirs) else dirs[-1]


# ---------------------------------------------------------------- parse
def _f(x):
    return float(x) if x not in (None, "") else float("nan")


def latest_snapshot(refresh: bool = False) -> dict:
    d = latest_dir(refresh)
    m = json.loads((d / "market.json").read_text())["market"]
    ob = json.loads((d / "orderbook.json").read_text())["orderbook_fp"]
    yes_bids = sorted(((_f(p), _f(s)) for p, s in ob.get("yes_dollars") or []), reverse=True)
    no_bids = sorted(((_f(p), _f(s)) for p, s in ob.get("no_dollars") or []), reverse=True)
    snap = {
        "dir": d.name,
        "fetched_utc": json.loads((d / "manifest.json").read_text())["fetched_utc"],
        "yes_bid": _f(m["yes_bid_dollars"]), "yes_ask": _f(m["yes_ask_dollars"]),
        "no_bid": _f(m["no_bid_dollars"]), "no_ask": _f(m["no_ask_dollars"]),
        "last": _f(m["last_price_dollars"]), "volume": _f(m.get("volume_fp")),
        "open_interest": _f(m.get("open_interest_fp")),
        "close_time": m["close_time"], "latest_expiration_time": m.get("latest_expiration_time"),
        "yes_bids": yes_bids, "no_bids": no_bids,
        # buying Yes lifts resting No bids at (1 - p); buying No lifts resting Yes bids at (1 - p)
        "yes_asks": sorted((round(1 - p, 4), s) for p, s in no_bids),
        "no_asks": sorted((round(1 - p, 4), s) for p, s in yes_bids),
        "trades": json.loads((d / "trades.json").read_text()),
        "treasury_nominal": _treasury(d / "treasury_nominal.csv"),
        "treasury_real": _treasury(d / "treasury_real.csv"),
        "kalshi_apy": KALSHI_APY,
    }
    snap["mid"] = 0.5 * (snap["yes_bid"] + snap["yes_ask"])
    return snap


def _treasury(path: Path) -> dict:
    rows = list(csv.reader(io.StringIO(path.read_text())))
    head, latest = rows[0], rows[1]                 # newest date first
    out = {"date": latest[0]}
    for k, v in zip(head[1:], latest[1:]):
        if v:
            out[k.strip('"')] = float(v) / 100
    return out


# ---------------------------------------------------------------- fees and book
def fee(price: float, contracts: float = 1) -> float:
    """Kalshi standard taker fee for one order, rounded UP to the cent."""
    raw = TAKER_RATE * contracts * price * (1 - price)
    return math.ceil(raw * 100 - 1e-9) / 100


def walk_book(asks: list, size: float) -> dict:
    """Fill `size` contracts against ascending (price, size) levels; one order, one fee."""
    left, cost, raw_fee, filled = size, 0.0, 0.0, 0.0
    for p, s in asks:
        take = min(left, s)
        cost += take * p
        raw_fee += TAKER_RATE * take * p * (1 - p)
        filled += take
        left -= take
        if left <= 1e-12:
            break
    fee_total = math.ceil(raw_fee * 100 - 1e-9) / 100
    return {"requested": size, "filled": filled, "vwap": cost / filled if filled else float("nan"),
            "fee": fee_total, "all_in_per_contract": (cost + fee_total) / filled if filled else float("nan"),
            "complete": left <= 1e-12}


def trade_series(trades: list):
    """Daily VWAP and volume (Yes price) from the trade list."""
    by_day: dict[str, list] = {}
    for t in trades:
        day = t["created_time"][:10]
        p = _f(t.get("yes_price_dollars"))
        c = _f(t.get("count_fp"))
        by_day.setdefault(day, []).append((p, c))
    days = sorted(by_day)
    vwap = np.array([sum(p * c for p, c in by_day[d]) / sum(c for _, c in by_day[d]) for d in days])
    vol = np.array([sum(c for _, c in by_day[d]) for d in days])
    return np.array(days, dtype="datetime64[D]"), vwap, vol


if __name__ == "__main__":
    s = latest_snapshot(refresh="--show" not in sys.argv)
    print(f"{s['dir']}: Yes {s['yes_bid']:.2f}/{s['yes_ask']:.2f} last {s['last']:.2f} "
          f"OI {s['open_interest']:.0f}  trades {len(s['trades'])}  T-bill 1m "
          f"{s['treasury_nominal'].get('1 Mo')} 20y {s['treasury_nominal'].get('20 Yr')}")
