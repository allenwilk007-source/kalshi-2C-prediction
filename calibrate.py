"""Put the course model on the observations' footing and fit version B.

Version A = the HW5 class model, parameters untouched.
Version B = same equations; p2 (and p1 if a likelihood-ratio test says it helps) refit by
            maximum likelihood with AR(1) errors against the observed common signal.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from model import YEAR0, Inputs, Params, run
from noise import fit_ar1

BASE = (1850, 1900)


def model_rebaselined(p: Params, inp: Inputs | None = None):
    """(years 1750-2100, temperature minus its own 1850-1900 mean). Batched if p is."""
    r = run(p, inp)
    T = r.temp_atmos
    base = T[..., BASE[0] - YEAR0: BASE[1] - YEAR0 + 1].mean(axis=-1, keepdims=True)
    return r.years, T - base


def residuals(model_years, model_T, obs_years, obs_signal):
    """r[t] = observed common signal - model, on the observed years."""
    idx = obs_years - model_years[0]
    return obs_signal - model_T[..., idx]


@dataclass
class Fit:
    params: Params
    ar1: dict                 # c, phi, sigma, mu, loglik, n
    model_years: np.ndarray
    model_T: np.ndarray       # rebaselined, 1750-2100
    resid: np.ndarray         # on obs_years
    obs_years: np.ndarray


def fit_version(p: Params, obs_years, obs_signal, fit_window=(1880, 2025), inp=None, mask=None) -> Fit:
    my, mT = model_rebaselined(p, inp)
    r = residuals(my, mT, obs_years, obs_signal)
    sel = (obs_years >= fit_window[0]) & (obs_years <= fit_window[1])
    ar = fit_ar1(r[sel], mask=None if mask is None else mask[sel])
    return Fit(p, ar, my, mT, r, obs_years)


def fit_version_b(base: Params, obs_years, obs_signal, fit_window=(1880, 2025), inp=None):
    """Grid MLE over p2 (and jointly p1). Returns (Fit, report dict)."""
    inp = inp or Inputs.load()
    sel = (obs_years >= fit_window[0]) & (obs_years <= fit_window[1])

    def grid_ll(p1_grid, p2_grid):
        P1, P2 = np.meshgrid(p1_grid, p2_grid, indexing="ij")
        p = replace(base, p1_adjust_speed=P1.ravel(), p2_sensitivity=P2.ravel())
        my, mT = model_rebaselined(p, inp)
        R = residuals(my, mT, obs_years, obs_signal)[:, sel]
        ll = np.array([fit_ar1(row)["loglik"] for row in R])
        return P1.ravel(), P2.ravel(), ll

    p2_grid = np.round(np.arange(0.60, 1.6001, 0.005), 4)
    _, p2s, ll1 = grid_ll(np.array([base.p1_adjust_speed]), p2_grid)
    i1 = int(np.argmax(ll1))
    p1_grid = np.round(np.arange(0.010, 0.0601, 0.001), 4)
    p1s2, p2s2, ll2 = grid_ll(p1_grid, p2_grid)
    i2 = int(np.argmax(ll2))

    lr = 2 * (ll2[i2] - ll1[i1])            # likelihood-ratio statistic, 1 extra parameter
    use_p1 = lr > 3.84                       # chi2(1) 5% critical value
    if use_p1:
        best = replace(base, p1_adjust_speed=float(p1s2[i2]), p2_sensitivity=float(p2s2[i2]))
    else:
        best = replace(base, p2_sensitivity=float(p2s[i1]))
    fit = fit_version(best, obs_years, obs_signal, fit_window, inp)
    fitA = fit_version(base, obs_years, obs_signal, fit_window, inp)
    on_edge = best.p2_sensitivity in (p2_grid[0], p2_grid[-1]) or (
        use_p1 and best.p1_adjust_speed in (p1_grid[0], p1_grid[-1]))
    report = {
        "p2_only": {"p2": float(p2s[i1]), "loglik": float(ll1[i1])},
        "p1_p2": {"p1": float(p1s2[i2]), "p2": float(p2s2[i2]), "loglik": float(ll2[i2])},
        "lr_stat_p1": float(lr),
        "use_p1": bool(use_p1),
        "chosen": {"p1": float(best.p1_adjust_speed), "p2": float(best.p2_sensitivity)},
        "effective_ecs": float(best.ecs()),
        "loglik_A": float(fitA.ar1["loglik"]),
        "loglik_gain_vs_A": float(fit.ar1["loglik"] - fitA.ar1["loglik"]),
        "on_grid_edge": bool(on_edge),
    }
    return fit, report
