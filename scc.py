"""Social cost of carbon from the class model.

  1. Run the HW5 model to 2300 (it stops at 2100, but damages continue long after):
       population held at its 2100 level, GDP per capita +1 %/yr, emissions falling linearly from
       their 2100 level to zero in 2200 ("decline"; alternatives "flat" and a 2100 cut-off).
  2. Add a 1 GtC pulse in 2027 and take the extra warming dT(t) = T_pulse(t) - T_base(t).
  3. Marginal damage MD(t) = a/100 * [(T + dT)^2 - T^2] * GDP(t), with a from the course SCC
     spreadsheet (hedge.py) and T anchored to observations (model + recent bias b).
     $bn per GtC = $ per tC.
  4. Discount to the pulse year (HW1 NPV): Ramsey r(t) = rho + eta * g(t) (g = per-capita growth),
     or a constant rate.

Reuses model.concentrations / forcing / temperature unchanged.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from model import YEAR0, Inputs, Params, concentrations, forcing, kaya_emissions, temperature

HERE = Path(__file__).resolve().parent
TOL_CACHE = HERE / "data" / "scc_dataset.json"
SCC_XLSX = HERE.parent / "9.26.26.socialcostcarbon.xlsx"
END = 2300
PULSE_YEAR = 2027
PULSE_MTC = 1000.0           # 1 GtC
POST_GDPPC_GROWTH = 0.01
BASE = (1850, 1900)


# ---------------------------------------------------------------- economy and emissions to END
def kaya_gdp(p: Params, inp: Inputs):
    """GDP (billion $) and population (millions) for 2021-2100, shape (..., 80)."""
    steps = np.arange(1, inp.population.shape[1] + 1)
    g = np.asarray(p.gdp_per_capita_growth, dtype=float)[..., :, None]
    gdp_pc = inp.gdp_pc_2020[:, None] * (1 + g) ** steps                 # (..., 3, 80) $/person
    gdp = (inp.population * gdp_pc / 1000).sum(axis=-2)                  # billion $
    pop = np.broadcast_to(inp.population.sum(axis=0), gdp.shape)
    return gdp, pop


def extended(p: Params, inp: Inputs | None = None, end=END, post="decline"):
    """Emissions 1750..end (Mt C), GDP 2021..end (bn $), per-capita growth g 2021..end."""
    inp = inp or Inputs.load()
    if p.future_emissions_mtc is None:
        fut = kaya_emissions(p, inp)
    else:
        fut = np.asarray(p.future_emissions_mtc, dtype=float)
    fut = fut + np.asarray(p.land_use_fill_mtc, dtype=float)[..., None]
    gdp, pop = kaya_gdp(p, inp)
    batch = np.broadcast_shapes(fut.shape[:-1], gdp.shape[:-1])
    fut, gdp, pop = (np.broadcast_to(x, batch + x.shape[-1:]) for x in (fut, gdp, pop))
    n_post = end - 2100
    k = np.arange(1, n_post + 1)
    if post == "decline":
        shape = np.clip(1 - k / (2200 - 2100), 0, None)
    elif post == "flat":
        shape = np.ones(n_post)
    else:
        raise ValueError(post)
    e_post = fut[..., -1:] * shape
    gdp_post = gdp[..., -1:] * (1 + POST_GDPPC_GROWTH) ** k
    pop_post = np.broadcast_to(pop[..., -1:], batch + (n_post,))
    hist = np.broadcast_to(inp.hist_emissions_mtc, batch + inp.hist_emissions_mtc.shape)
    E = np.concatenate([hist, fut, e_post], axis=-1)
    GDP = np.concatenate([gdp, gdp_post], axis=-1)
    POP = np.concatenate([pop, pop_post], axis=-1)
    gpc = GDP / POP
    # per-capita growth; 2021 uses the 2020 base per-capita income (population-weighted)
    # GDP/POP is bn$/million people = thousand $ per person; gdp_pc_2020 is $ per person
    gpc20 = (inp.gdp_pc_2020 * inp.population[:, 0]).sum() / inp.population[:, 0].sum() / 1000
    g = np.diff(np.log(np.concatenate([np.broadcast_to(gpc20, batch + (1,)), gpc], axis=-1)), axis=-1)
    return {"years": np.arange(YEAR0, end + 1), "E": E, "GDP": GDP, "g": g,
            "econ_years": np.arange(2021, end + 1)}


def temps(E, p: Params):
    C = concentrations(E, p)
    T, _ = temperature(forcing(C, p), p)
    return T - T[..., BASE[0] - YEAR0: BASE[1] - YEAR0 + 1].mean(axis=-1, keepdims=True)


# ---------------------------------------------------------------- discounting and SCC
def discount_factors(g, start_index, rho=None, eta=None, const_r=None):
    """DF for each econ year relative to econ index start_index (DF=1 there).

    Ramsey r_t = rho + eta * g_t, compounding from start; or a constant rate."""
    g = np.asarray(g, dtype=float)
    n = g.shape[-1] - start_index
    if const_r is not None:
        r = np.full(g.shape[:-1] + (n,), const_r)
    else:
        r = rho + eta * g[..., start_index:]
    # DF_0 = 1, DF_k = prod_{j=1..k} 1/(1+r_j)
    logdf = -np.cumsum(np.log1p(r[..., 1:]), axis=-1)
    return np.exp(np.concatenate([np.zeros(r.shape[:-1] + (1,)), logdf], axis=-1))


def marginal_damages(p: Params, a, anchor_b=0.0, inp=None, end=END, post="decline",
                     pulse_year=PULSE_YEAR, pulse=PULSE_MTC):
    """MD ($bn per GtC = $/tC) for each year from the pulse year to `end`, plus dT and the base T."""
    x = extended(p, inp, end, post)
    E = x["E"]
    Ep = E.copy()
    Ep[..., pulse_year - YEAR0] += pulse
    T = temps(E, p) + np.asarray(anchor_b, dtype=float)[..., None]
    Tp = temps(Ep, p) + np.asarray(anchor_b, dtype=float)[..., None]
    i0 = pulse_year - YEAR0
    T, Tp = T[..., i0:], Tp[..., i0:]
    j0 = pulse_year - 2021
    GDP = x["GDP"][..., j0:]
    a = np.asarray(a, dtype=float)[..., None]
    MD = a / 100 * (Tp ** 2 - T ** 2) * GDP * (1000.0 / pulse)    # per GtC
    return {"MD": MD, "dT": Tp - T, "T": T, "g": x["g"], "j0": j0,
            "years": np.arange(pulse_year, end + 1)}


def scc_from_md(md: dict, rho=None, eta=None, const_r=None, horizon=None):
    """Present value at the pulse year of marginal damages, $/tC."""
    DF = discount_factors(md["g"], md["j0"], rho, eta, const_r)
    MD = md["MD"]
    if horizon is not None:
        keep = md["years"] <= horizon
        MD, DF = MD[..., keep], DF[..., keep]
    return (MD * DF).sum(axis=-1)


# ---------------------------------------------------------------- Tol's database
def load_tol(refresh=False) -> dict:
    """Year, SCC ($/tC, 2010 USD), PRTP, EIS and Tol's weights from the course spreadsheet."""
    if TOL_CACHE.exists() and not refresh:
        return {k: np.array(v, dtype=float) for k, v in json.loads(TOL_CACHE.read_text()).items()}
    import openpyxl
    ws = openpyxl.load_workbook(SCC_XLSX, read_only=True).worksheets[0]
    head = [c.value for c in next(ws.iter_rows(max_row=1))]
    idx = {k: head.index(k) for k in ("year", "censor", "quality", "author", "paper", "SCC", "PRTP", "EIS")}
    f = lambda v: np.nan if v in (None, "NA") else float(v)
    rows = [[f(r[i]) for i in idx.values()] for r in ws.iter_rows(min_row=2, values_only=True)]
    arr = np.array(rows)
    out = {k: arr[:, j] for j, k in enumerate(idx)}
    out["w"] = out["censor"] * out["quality"] * out["author"] * out["paper"]
    TOL_CACHE.parent.mkdir(exist_ok=True)
    TOL_CACHE.write_text(json.dumps({k: [None if np.isnan(x) else x for x in v.tolist()] for k, v in out.items()}))
    return {k: np.array([np.nan if x is None else x for x in v.tolist()], dtype=float) for k, v in out.items()}


def wq(x, w, qs):
    m = np.isfinite(x) & np.isfinite(w) & (w > 0)
    x, w = x[m], w[m]
    o = np.argsort(x)
    c = np.cumsum(w[o]) / w.sum()
    return [float(x[o][min(np.searchsorted(c, q), len(x) - 1)]) for q in qs]


def tol_by_prtp(prtps=(0.0, 1.0, 1.5, 3.0)) -> dict:
    t = load_tol()
    out = {}
    for r in prtps:
        m = (t["PRTP"] == r) & (t["w"] > 0) & np.isfinite(t["SCC"])
        w, s = t["w"][m], t["SCC"][m]
        out[r] = {"n": int(m.sum()), "mean": float((w * s).sum() / w.sum()),
                  "p5_50_95": wq(s, w, (0.05, 0.5, 0.95))}
    m = (t["w"] > 0) & np.isfinite(t["SCC"])
    out["all"] = {"n": int(m.sum()), "mean": float((t["w"][m] * t["SCC"][m]).sum() / t["w"][m].sum()),
                  "p5_50_95": wq(t["SCC"][m], t["w"][m], (0.05, 0.5, 0.95))}
    return out
