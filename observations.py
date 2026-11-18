"""Observed annual global temperature, the four Kalshi settlement datasets.

    python observations.py            # download if not cached, print summary
    python observations.py --refresh  # force re-download

Raw files are cached in data/obs/raw/ with a manifest (URL, download time, SHA-256).
Everything is re-baselined to the contract's 1850-1900 "pre-industrial" average.

Source notes (checked 2026-11-08):
  GISS      graph.txt is the exact file Kalshi links. Native baseline 1951-80, starts 1880.
  NOAA      Climate-at-a-Glance Jan-Dec series. Native baseline 1901-2000, starts 1850.
  Berkeley  The summary file Berkeley's data page links stops at 2024 (Jan-2025 run).
            Column 1 = air temperature over sea ice (Berkeley's preferred), column 5 = water.
  HadCRUT   Version 5.1.0.0 (5.0.2.0 stops at Feb 2025). The annual file includes a partial
            current year, so years are kept only if the monthly file has all 12 months.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RAW = HERE / "data" / "obs" / "raw"
MANIFEST = HERE / "data" / "obs" / "manifest.json"
UA = {"User-Agent": "fecon-climate-research-script"}

HADCRUT = ("https://www.metoffice.gov.uk/hadobs/hadcrut5/data/HadCRUT.5.1.0.0/analysis/"
           "diagnostics/HadCRUT.5.1.0.0.analysis.summary_series.global")
SOURCES = {
    "giss": "https://data.giss.nasa.gov/gistemp/graphs/graph_data/"
            "Global_Mean_Estimates_based_on_Land_and_Ocean_Data/graph.txt",
    "noaa": "https://www.ncei.noaa.gov/access/monitoring/climate-at-a-glance/global/"
            "time-series/globe/tavg/land_ocean/12/12/1850-2025/data.csv",
    "berkeley": "https://berkeley-earth-temperature.s3.us-west-1.amazonaws.com/"
                "Global/Land_and_Ocean_summary.txt",
    "hadcrut_annual": HADCRUT + ".annual.csv",
    "hadcrut_monthly": HADCRUT + ".monthly.csv",
}
DATASETS = ("giss", "noaa", "berkeley", "hadcrut")
BASE = (1850, 1900)
GISS_ALIGN = (1880, 1900)


# ---------------------------------------------------------------- download
def download(refresh: bool = False) -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    for name, url in SOURCES.items():
        path = RAW / f"{name}.txt"
        if path.exists() and not refresh and name in manifest:
            continue
        req = urllib.request.Request(url, headers=UA)
        data = urllib.request.urlopen(req, timeout=60).read()
        path.write_bytes(data)
        manifest[name] = {
            "url": url,
            "downloaded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        print(f"downloaded {name}: {len(data):,} bytes")
    MANIFEST.write_text(json.dumps(manifest, indent=1))
    return manifest


OWID_URL = "https://raw.githubusercontent.com/owid/co2-data/master/owid-co2-data.csv"
OWID_WORLD = RAW / "owid_world_co2.csv"


def download_owid_world(refresh: bool = False) -> Path:
    """Stream OWID's CO2 dataset (~14 MB) and keep only the World rows.

    Columns kept: year, co2 (fossil + cement, Mt CO2), co2_including_luc. OWID's source for
    these is the Global Carbon Budget.
    """
    if OWID_WORLD.exists() and not refresh:
        return OWID_WORLD
    RAW.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(OWID_URL, headers=UA)
    h = hashlib.sha256()
    total = 0
    rows = []
    with urllib.request.urlopen(req, timeout=120) as resp:
        header = None
        buf = b""
        for chunk in iter(lambda: resp.read(1 << 16), b""):
            h.update(chunk)
            total += len(chunk)
            buf += chunk
            *lines, buf = buf.split(b"\n")
            for raw in lines:
                rec = next(csv.reader([raw.decode("utf-8", "replace")]))
                if header is None:
                    header = {k: i for i, k in enumerate(rec)}
                    continue
                if rec and rec[header["country"]] == "World":
                    rows.append((rec[header["year"]], rec[header["co2"]], rec[header["co2_including_luc"]]))
    with OWID_WORLD.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "co2", "co2_including_luc"])
        w.writerows(rows)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    manifest["owid_world_co2"] = {
        "url": OWID_URL,
        "downloaded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bytes": total, "sha256": h.hexdigest(), "note": "only World rows kept",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1))
    print(f"downloaded OWID ({total:,} bytes), kept {len(rows)} World rows")
    return OWID_WORLD


def owid_world_co2(column: str = "co2") -> dict[int, float]:
    download_owid_world()
    out = {}
    with OWID_WORLD.open() as f:
        for rec in csv.DictReader(f):
            if rec[column]:
                out[int(rec["year"])] = float(rec[column])
    return out


def _text(name: str) -> str:
    return (RAW / f"{name}.txt").read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------- parsers (native baselines)
def parse_giss(txt: str) -> dict[int, float]:
    out = {}
    for line in txt.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit() and len(parts[0]) == 4:
            out[int(parts[0])] = float(parts[1])
    return out


def parse_noaa(txt: str) -> dict[int, float]:
    out = {}
    for row in csv.reader(l for l in txt.splitlines() if not l.startswith("#")):
        if row and row[0].strip().isdigit():
            out[int(row[0])] = float(row[1])
    return out


def parse_berkeley(txt: str, column: str = "air") -> dict[int, float]:
    idx = {"air": 1, "water": 5}[column]
    out = {}
    for line in txt.splitlines():
        if line.startswith("%") or not line.strip():
            continue
        parts = line.split()
        v = float(parts[idx])
        if np.isfinite(v):
            out[int(parts[0])] = v
    return out


def parse_hadcrut(annual_txt: str, monthly_txt: str) -> dict[int, float]:
    months: dict[int, int] = {}
    for row in csv.reader(monthly_txt.splitlines()[1:]):
        if row:
            y = int(row[0][:4])
            months[y] = months.get(y, 0) + 1
    out = {}
    for row in csv.reader(annual_txt.splitlines()[1:]):
        if row and months.get(int(row[0]), 0) == 12:     # complete calendar years only
            out[int(row[0])] = float(row[1])
    return out


def load_native(berkeley_column: str = "air") -> dict[str, dict[int, float]]:
    return {
        "giss": parse_giss(_text("giss")),
        "noaa": parse_noaa(_text("noaa")),
        "berkeley": parse_berkeley(_text("berkeley"), berkeley_column),
        "hadcrut": parse_hadcrut(_text("hadcrut_annual"), _text("hadcrut_monthly")),
    }


# ---------------------------------------------------------------- re-baselining
def window_mean(series: dict[int, float], lo: int, hi: int) -> float:
    vals = [series[y] for y in range(lo, hi + 1) if y in series]
    if len(vals) < (hi - lo + 1):
        raise ValueError(f"series is missing years in {lo}-{hi}")
    return float(np.mean(vals))


def rebaseline(native: dict[str, dict[int, float]], giss_method: str = "align") -> dict[str, dict[int, float]]:
    """Put every dataset on the 1850-1900 baseline.

    NOAA, Berkeley, HadCRUT: subtract their own 1850-1900 mean.
    GISS (starts 1880):
      "align"   -> shift so its 1880-1900 mean equals the other three's 1880-1900 mean (default)
      "own1880" -> subtract its own 1880-1900 mean (treats 1880-1900 as pre-industrial; sensitivity)
    """
    out = {}
    for k in ("noaa", "berkeley", "hadcrut"):
        b = window_mean(native[k], *BASE)
        out[k] = {y: v - b for y, v in native[k].items()}
    g = native["giss"]
    if giss_method == "align":
        target = np.mean([window_mean(out[k], *GISS_ALIGN) for k in ("noaa", "berkeley", "hadcrut")])
        shift = window_mean(g, *GISS_ALIGN) - target
    elif giss_method == "own1880":
        shift = window_mean(g, *GISS_ALIGN)
    else:
        raise ValueError(giss_method)
    out["giss"] = {y: v - shift for y, v in g.items()}
    return {k: out[k] for k in DATASETS}


def to_matrix(series: dict[str, dict[int, float]], y0: int = 1850, y1: int | None = None):
    """(years, X) with X shape (4, T) in DATASETS order, NaN where a dataset has no value."""
    y1 = y1 or max(max(s) for s in series.values())
    years = np.arange(y0, y1 + 1)
    X = np.array([[series[k].get(int(y), np.nan) for y in years] for k in DATASETS])
    return years, X


def load(giss_method: str = "align", berkeley_column: str = "air"):
    """Convenience: cached download -> re-baselined (years, X)."""
    download()
    return to_matrix(rebaseline(load_native(berkeley_column), giss_method))


if __name__ == "__main__":
    download(refresh="--refresh" in sys.argv)
    nat = load_native()
    rb = rebaseline(nat)
    print(f"{'dataset':9s} {'first':>5s} {'last':>5s}  " + "  ".join(str(y) for y in range(2019, 2026)))
    for k in DATASETS:
        s = rb[k]
        print(f"{k:9s} {min(s):5d} {max(s):5d}  " +
              "  ".join(f"{s[y]:4.2f}" if y in s else " -- " for y in range(2019, 2026)))
