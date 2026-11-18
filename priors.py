"""Phase 3 priors and posteriors.

Emissions: the 9 Kaya growth rates, centred on the HW5 template, with sds from the
           decade-to-decade variation in the workbook's own 1960-2020 data; importance weights
           from actual 2019->2024 emissions growth.
Climate:   a (p1, p2) grid. Prior: IPCC AR6 ECS lognormal (very likely 2-5 C) mapped to p2,
           uniform in p1. Likelihood: AR(1) fit of the 1880-2020 residuals at each grid point.
           "history"  posterior = prior x L
           "ipcc"     posterior = prior x L^(1/T), T chosen so the spread of 2041-2060 warming under
                      the Flat path matches the AR6 range net of the part already observed.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace

import numpy as np

from calibrate import model_rebaselined, residuals
from model import DATA, YEAR0, Inputs, Params
from noise import fit_ar1

REGIONS = ("rich", "middle", "poor")
FACTORS = ("gdp_per_capita", "energy_intensity", "emissions_intensity")
PARAM_FIELD = {"gdp_per_capita": "gdp_per_capita_growth",
               "energy_intensity": "energy_intensity_change",
               "emissions_intensity": "emissions_intensity_change"}

F2X = 5.35 * math.log(2)                       # forcing for CO2 doubling, W/m^2
Z95 = 1.6448536269514722
ECS_LN_MU = (math.log(2) + math.log(5)) / 2    # AR6 very likely 2-5 C  ->  5 % / 95 %
ECS_LN_SD = (math.log(5) - math.log(2)) / (2 * Z95)

P1_GRID = np.round(np.arange(0.010, 0.06001, 0.0025), 4)
P2_GRID = np.round(np.arange(0.50, 1.80001, 0.01), 3)
HIST_FIT = (1880, 2020)

# AR6 WGI Table SPM.1, SSP2-4.5 (relative to 1850-1900): best estimate [5-95 %]
AR6_NEAR = (1.5, 1.2, 1.8)     # 2021-2040
AR6_MID = (2.0, 1.6, 2.5)      # 2041-2060
AR6_TARGET_WIDTH = 2 * math.sqrt(0.45 ** 2 - 0.30 ** 2)     # ~0.67: mid-term spread net of near-term
AR6_FULL_WIDTH = AR6_MID[2] - AR6_MID[1]                    # 0.90


# ---------------------------------------------------------------- helpers
def weighted_quantile(x, w, qs):
    x, w = np.asarray(x, float).ravel(), np.asarray(w, float).ravel()
    o = np.argsort(x)
    cw = np.cumsum(w[o])
    cw /= cw[-1]
    return np.array([x[o][min(np.searchsorted(cw, q), len(x) - 1)] for q in np.atleast_1d(qs)])


def ess(w):
    w = np.asarray(w, float)
    return float(w.sum() ** 2 / (w ** 2).sum())


# ---------------------------------------------------------------- Kaya prior
def _cagr(series, years, a, b):
    return (series[years.index(b)] / series[years.index(a)]) ** (1 / (b - a)) - 1


def kaya_prior():
    """centres[f, r] = HW5 template rate; sds[f, r] = sd of decade-average rates in 1960/1971-2020."""
    h = json.loads(DATA.read_text())["history_1960_2020"]
    years = h["years"]
    base = Params()
    centres = np.array([getattr(base, PARAM_FIELD[f]) for f in FACTORS], dtype=float)
    sds = np.zeros((3, 3))
    for i, f in enumerate(FACTORS):
        for j, r in enumerate(REGIONS):
            start = 1960 if (f == "gdp_per_capita" or r == "rich") else 1971
            decades = [_cagr(h[f][r], years, a, a + 10) for a in range(start, 2011, 10) if a + 10 <= 2020]
            sds[i, j] = np.std(decades, ddof=1)
    return centres, sds


def sample_kaya(n, rng, centres, sds):
    """Return dict field -> array (n, 3) of growth rates."""
    draws = centres[None] + sds[None] * rng.standard_normal((n, 3, 3))
    return {PARAM_FIELD[f]: draws[:, i, :] for i, f in enumerate(FACTORS)}


def emission_weights(kaya_2024, kaya_2019, g_obs, sd=0.02):
    """Gaussian weight on log growth 2019->2024 (model vs observed)."""
    g_model = np.log(np.asarray(kaya_2024) / kaya_2019)
    return np.exp(-0.5 * ((g_model - g_obs) / sd) ** 2)


# ---------------------------------------------------------------- climate grid
def ecs_logprior(ecs):
    z = (np.log(ecs) - ECS_LN_MU) / ECS_LN_SD
    return -0.5 * z ** 2 - np.log(ecs)


@dataclass
class ClimateGrid:
    p1: np.ndarray
    p2: np.ndarray
    loglik: np.ndarray
    logprior: np.ndarray
    c: np.ndarray
    phi: np.ndarray
    sigma: np.ndarray
    mu: np.ndarray
    b: np.ndarray          # recent bias: mean residual 2006-2025 (the anchor)
    w_near: np.ndarray     # 2021-2040 mean warming under the Flat path, anchored (model + b)
    w_mid: np.ndarray      # 2041-2060

    @property
    def ecs(self):
        return self.p2 * F2X


def build_climate_grid(obs_years, signal, flat_future_mtc, inp=None) -> ClimateGrid:
    inp = inp or Inputs.load()
    P1, P2 = np.meshgrid(P1_GRID, P2_GRID, indexing="ij")
    p1, p2 = P1.ravel(), P2.ravel()
    p = replace(Params(), p1_adjust_speed=p1, p2_sensitivity=p2, future_emissions_mtc=flat_future_mtc)
    my, mT = model_rebaselined(p, inp)
    sel = (obs_years >= HIST_FIT[0]) & (obs_years <= HIST_FIT[1])
    Rall = residuals(my, mT, obs_years, signal)
    fits = [fit_ar1(r) for r in Rall[:, sel]]
    g = {k: np.array([f[k] for f in fits]) for k in ("loglik", "c", "phi", "sigma", "mu")}
    b = recent_bias(obs_years, Rall)
    near = mT[:, 2021 - YEAR0: 2041 - YEAR0].mean(axis=1) + b
    mid = mT[:, 2041 - YEAR0: 2061 - YEAR0].mean(axis=1) + b
    return ClimateGrid(p1, p2, g["loglik"], ecs_logprior(p2 * F2X), g["c"], g["phi"], g["sigma"],
                       g["mu"], b, near, mid)


ANCHOR = (2006, 2025)


def recent_bias(obs_years, resid):
    """Mean residual over the last 20 years: where the world is now relative to this model.

    Projections continue from this level (model + b) rather than reverting to the 1880-2020
    mean residual, so a draw that runs cool or hot historically still starts from today's
    observed state and differs only in how fast it warms from here.
    """
    sel = (obs_years >= ANCHOR[0]) & (obs_years <= ANCHOR[1])
    return np.asarray(resid)[..., sel].mean(axis=-1)


def posterior(grid: ClimateGrid, T: float = 1.0) -> np.ndarray:
    lw = grid.logprior + grid.loglik / T
    w = np.exp(lw - lw.max())
    return w / w.sum()


def mid_width(grid, T):
    q = weighted_quantile(grid.w_mid, posterior(grid, T), (0.05, 0.95))
    return float(q[1] - q[0])


def calibrate_T(grid, target_width=AR6_TARGET_WIDTH, lo=1.0, hi=1e4, iters=60):
    """Bisection on log T so the 5-95 % width of 2041-2060 warming equals target_width."""
    if mid_width(grid, lo) >= target_width:
        return lo, False
    if mid_width(grid, hi) < target_width:
        return hi, True                       # can't reach target: flag it
    a, b = math.log(lo), math.log(hi)
    for _ in range(iters):
        m = 0.5 * (a + b)
        if mid_width(grid, math.exp(m)) < target_width:
            a = m
        else:
            b = m
    return math.exp(0.5 * (a + b)), False


def sample_grid(post, n, rng):
    return rng.choice(len(post), size=n, p=post)


def summarize_climate(grid, post):
    q = (0.05, 0.5, 0.95)
    return {
        "w_mid_5_50_95": weighted_quantile(grid.w_mid, post, q).tolist(),
        "w_near_5_50_95": weighted_quantile(grid.w_near, post, q).tolist(),
        "ecs_5_50_95": weighted_quantile(grid.ecs, post, q).tolist(),
        "p1_5_50_95": weighted_quantile(grid.p1, post, q).tolist(),
        "p2_5_50_95": weighted_quantile(grid.p2, post, q).tolist(),
        "ess_grid": ess(post),
    }
