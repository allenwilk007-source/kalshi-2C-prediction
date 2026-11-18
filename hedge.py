"""How well KXWARMING-50 hedges a (hypothetical) climate-damage exposure.

Damage function from the course's SCC spreadsheet (Tol's database, 9.26.26.socialcostcarbon.xlsx):
  `Impact` = welfare-equivalent income change at 2.5 C warming, % (negative = loss), one per estimate.
  Weights = censor x quality x author x paper (Tol's scheme, as in Phase 1 of the notes).
  Quadratic through the origin, as in Tol and DICE:  D(T) = a * T^2  (% of income), a = -Impact / 2.5^2.

Exposure: an entity whose income moves with global damages. Loss per $1M of annual income at 2049,
from warming beyond today's level:  L = a/100 * (T_2049^2 - T_2026^2) * 1e6.

Analysis of a hypothetical exposure only; not a recommendation to trade.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SCC_XLSX = HERE.parent / "9.26.26.socialcostcarbon.xlsx"
CACHE = HERE / "data" / "scc_impact.json"
COLS = {"censor": 1, "quality": 2, "author": 3, "paper": 4, "impact": 11, "id": 22}


def load_impact(refresh: bool = False) -> dict:
    if CACHE.exists() and not refresh:
        d = json.loads(CACHE.read_text())
        return {k: np.array(v) for k, v in d.items() if k != "source"}
    import openpyxl
    ws = openpyxl.load_workbook(SCC_XLSX, read_only=True).worksheets[0]
    header = [c.value for c in next(ws.iter_rows(max_row=1))]
    assert header[11] == "Impact" and header[22] == "ID", header
    rows = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        v = {k: r[i] for k, i in COLS.items()}
        if v["impact"] in (None, "NA"):
            continue
        w = float(v["censor"]) * float(v["quality"]) * float(v["author"]) * float(v["paper"])
        if w > 0:
            rows.append((float(v["impact"]), w, int(v["id"])))
    imp, w, ids = (np.array(x) for x in zip(*rows))
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps({"source": SCC_XLSX.name, "impact": imp.tolist(), "w": w.tolist(),
                                 "id": ids.tolist()}))
    return {"impact": imp, "w": w, "id": ids}


def weighted_quantile(x, w, qs):
    o = np.argsort(x)
    c = np.cumsum(w[o]) / w.sum()
    return np.array([x[o][min(np.searchsorted(c, q), len(x) - 1)] for q in np.atleast_1d(qs)])


def sample_damage_coef(n, rng, data=None):
    """a (% of income per C^2), drawn from the weighted Impact distribution."""
    data = data or load_impact()
    idx = rng.choice(len(data["impact"]), size=n, p=data["w"] / data["w"].sum())
    return -data["impact"][idx] / 2.5 ** 2


def median_damage_coef(data=None):
    data = data or load_impact()
    return float(-weighted_quantile(data["impact"], data["w"], 0.5)[0] / 2.5 ** 2)


def loss_2049(a, T2049, T2026, income=1e6):
    return np.asarray(a) / 100 * (np.asarray(T2049) ** 2 - np.asarray(T2026) ** 2) * income


def loss_cumulative(a, S, T2026, income=1e6):
    """Incremental damages summed over the simulated years (S: (n, T) common signal)."""
    return np.asarray(a) / 100 * ((np.asarray(S) ** 2) - np.asarray(T2026)[:, None] ** 2).sum(axis=1) * income


def min_var_hedge(L, H, w=None) -> dict:
    """Minimum-variance hedge of loss L with instrument payoff H (weighted).

    Hedged position: L - h*H.  h* = Cov(L,H)/Var(H);  effectiveness R^2 = corr(L,H)^2.
    """
    L, H = np.asarray(L, float), np.asarray(H, float)
    w = np.ones_like(L) if w is None else np.asarray(w, float)
    w = w / w.sum()
    mL, mH = (w * L).sum(), (w * H).sum()
    cov = (w * (L - mL) * (H - mH)).sum()
    vH = (w * (H - mH) ** 2).sum()
    vL = (w * (L - mL) ** 2).sum()
    h = cov / vH if vH > 0 else 0.0
    r2 = cov ** 2 / (vH * vL) if vH > 0 and vL > 0 else 0.0
    return {"h": float(h), "r2": float(r2), "sd_unhedged": math.sqrt(vL),
            "sd_hedged": math.sqrt(max(vL * (1 - r2), 0.0)), "mean_loss": float(mL)}


def capacity(asks, max_price) -> float:
    """Contracts available at or below max_price on an ascending (price, size) book."""
    return float(sum(s for p, s in asks if p <= max_price + 1e-12))
