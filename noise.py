"""Year-to-year noise, dataset offsets, path simulation and the KXWARMING-50 rule.

Structure of a simulated year t (2026-2049):
    common signal   s[t]    = model[t] + r[t]
    common noise    r[t]    = c + phi * r[t-1] + eps[t]          eps ~ Normal or scaled Student-t
    dataset k       x_k[t]  = s[t] + delta_k + u_k[t]           u_k iid or AR(1), sd tau_k
Contract: a year counts if the SECOND-HIGHEST of the four, rounded to 0.01, is >= 2.00.
"""
from __future__ import annotations

import math

import numpy as np

DATASETS = ("giss", "noaa", "berkeley", "hadcrut")


# ---------------------------------------------------------------- AR(1)
def fit_ar1(r: np.ndarray, mask: np.ndarray | None = None, intercept: bool = True) -> dict:
    """OLS fit of r[t] = c + phi*r[t-1] + eps.  Conditional Gaussian log-likelihood.

    mask: boolean array same length as r; True = exclude year t (pairs touching it are dropped).
    """
    r = np.asarray(r, dtype=float)
    y, x = r[1:], r[:-1]
    keep = np.isfinite(y) & np.isfinite(x)
    if mask is not None:
        keep &= ~mask[1:] & ~mask[:-1]
    y, x = y[keep], x[keep]
    A = np.column_stack([np.ones_like(x), x]) if intercept else x[:, None]
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    c, phi = (coef[0], coef[1]) if intercept else (0.0, coef[0])
    eps = y - (c + phi * x)
    n = len(y)
    s2 = float(eps @ eps) / n
    ll = -0.5 * n * (math.log(2 * math.pi * s2) + 1)
    m2 = float(np.mean(eps ** 2))
    kurt = float(np.mean(eps ** 4) / m2 ** 2 - 3) if m2 > 0 else 0.0
    mu = c / (1 - phi) if abs(1 - phi) > 1e-9 else float("nan")
    return {"c": float(c), "phi": float(phi), "sigma": math.sqrt(s2), "mu": float(mu),
            "loglik": ll, "n": n, "excess_kurtosis": kurt, "eps": eps}


def fit_student_t_df(eps: np.ndarray, sigma: float, grid=range(3, 31)) -> tuple[int, float]:
    """Pick Student-t degrees of freedom by likelihood, scale fixed so sd = sigma."""
    best = (None, -np.inf)
    for df in grid:
        scale = sigma * math.sqrt((df - 2) / df)
        z = eps / scale
        ll = np.sum(math.lgamma((df + 1) / 2) - math.lgamma(df / 2)
                    - 0.5 * math.log(df * math.pi) - math.log(scale)
                    - (df + 1) / 2 * np.log1p(z ** 2 / df))
        if ll > best[1]:
            best = (df, float(ll))
    return best


# ---------------------------------------------------------------- datasets
def dataset_offsets(years, X, window=(1996, 2025)) -> dict:
    """delta_k, tau_k, rho_k from deviations of each dataset from the 4-dataset mean.

    Uses only years in the window where all four datasets have a value.
    """
    sel = (years >= window[0]) & (years <= window[1]) & np.all(np.isfinite(X), axis=0)
    D = X[:, sel] - X[:, sel].mean(axis=0)
    delta = D.mean(axis=1)
    tau = D.std(axis=1, ddof=1)
    dc = D - delta[:, None]
    rho = np.array([np.corrcoef(d[:-1], d[1:])[0, 1] for d in dc])
    return {"delta": delta, "tau": tau, "rho": rho, "years_used": years[sel],
            "last_dev": dc[:, -1]}


def common_signal(X, delta):
    """Offset-adjusted mean across available datasets (so a missing dataset doesn't bias it)."""
    adj = X - delta[:, None]
    with np.errstate(invalid="ignore"):
        return np.nanmean(adj, axis=0)


# ---------------------------------------------------------------- simulation
def simulate(model_future, ar1, r0, offsets, n=100_000, seed=0, dist="normal", t_df=None,
             ar_rho_threshold=0.3, first_shift=None):
    """Simulate dataset readings.

    model_future: (T,) or (n, T) rebaselined model for the simulated years.
    ar1["c"], ar1["phi"], ar1["sigma"] and r0: scalars, or arrays of shape (n,) (one per path).
    first_shift: optional scalar or (n,) added to the FIRST simulated step only
                 (e.g. El Nino momentum from the previous year's late-year state). None = 0.
    Returns X with shape (n, 4, T) and the common signal S with shape (n, T).
    """
    rng = np.random.default_rng(seed)
    model_future = np.asarray(model_future, dtype=float)
    T = model_future.shape[-1]
    mf = np.broadcast_to(model_future, (n, T))
    c, phi, sigma, r0 = (np.broadcast_to(np.asarray(v, dtype=float), (n,))
                         for v in (ar1["c"], ar1["phi"], ar1["sigma"], r0))
    if dist == "t":
        eps = rng.standard_t(t_df, size=(n, T)) * (sigma * math.sqrt((t_df - 2) / t_df))[:, None]
    else:
        eps = rng.standard_normal(size=(n, T)) * sigma[:, None]
    r = np.empty((n, T))
    prev = r0.copy()
    for t in range(T):
        prev = c + phi * prev + eps[:, t]
        if t == 0 and first_shift is not None:
            prev = prev + np.broadcast_to(np.asarray(first_shift, dtype=float), (n,))
        r[:, t] = prev
    S = mf + r

    delta, tau, rho = offsets["delta"], offsets["tau"], offsets["rho"]
    U = np.empty((n, 4, T))
    for k in range(4):
        if rho[k] > ar_rho_threshold:
            innov_sd = tau[k] * math.sqrt(1 - rho[k] ** 2)
            u = np.full(n, offsets["last_dev"][k])
            for t in range(T):
                u = rho[k] * u + rng.normal(0, innov_sd, n)
                U[:, k, t] = u
        else:
            U[:, k, :] = rng.normal(0, tau[k], size=(n, T))
    X = S[:, None, :] + delta[None, :, None] + U
    return X, S


def _round2(x):
    """Round half up to 0.01, as published tables do (numpy's round is half-to-even)."""
    return np.floor(np.asarray(x) * 100 + 0.5 + 1e-9) / 100


def contract_outcome(X, years, threshold=2.0, rule="2of4", last_year=2049, history=None):
    """Return (yes: bool[n], first_year: float[n] (NaN if never)).

    rule: "2of4"  second-highest dataset (each rounded to 0.01) >= threshold  <- KXWARMING-50
          "any1"  any single dataset
          "mean4" mean of the four
          "20yr"  20-year trailing mean of the 4-dataset mean (needs `history`: observed
                  4-mean for the 19 years before the first simulated year)
    """
    sel = years <= last_year
    X = X[..., sel]
    yrs = years[sel]
    if rule == "2of4":
        stat = np.sort(_round2(X), axis=1)[:, -2, :]
    elif rule == "any1":
        stat = _round2(X).max(axis=1)
    elif rule == "mean4":
        stat = _round2(X.mean(axis=1))
    elif rule == "20yr":
        m = X.mean(axis=1)
        full = np.concatenate([np.broadcast_to(history, (m.shape[0], len(history))), m], axis=1)
        cs = np.cumsum(full, axis=1)
        roll = (cs[:, 19:] - np.concatenate([np.zeros((m.shape[0], 1)), cs[:, :-20]], axis=1)) / 20
        stat = _round2(roll[:, -m.shape[1]:])
    else:
        raise ValueError(rule)
    hit = stat >= threshold - 1e-9
    yes = hit.any(axis=1)
    first = np.where(yes, yrs[hit.argmax(axis=1)], np.nan)
    return yes, first


def summarize(yes, first):
    n = len(yes)
    p = float(yes.mean())
    f = first[np.isfinite(first)]
    q = (lambda a: float(np.percentile(f, a))) if len(f) else (lambda a: float("nan"))
    return {"p_yes": p, "mc_se": math.sqrt(p * (1 - p) / n), "n": n,
            "first_year_median": q(50), "first_year_p10": q(10), "first_year_p90": q(90)}
