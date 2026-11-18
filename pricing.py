"""From a Kalshi quote to an implied probability, valued on the same footing as the model.

Timing: Yes pays when two agencies publish a qualifying year Y, about mid-January of Y+1
(tau_Y = Y + 1.04 - today). No pays at expiry (tau_N = 2050.02 - today).
Carry delta: the yearly cost of tying money up in the contract relative to the alternative
(0 if the alternative is cash on Kalshi, which earns the same APY as positions).

Implied probability q*: the belief at which buying Yes and buying No earn the same expected
return on their collateral:
    q*(p) = p * D_N / (p * D_N + (1 - p) * D_Y)
with D_Y = E[exp(-delta * tau_Y) | Yes] and D_N = exp(-delta * tau_N). delta = 0 gives q* = p.
A symmetric platform haircut h (both payouts x (1 - h)) cancels out of q* but not out of the band.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np

PUBLISH_LAG = 1.04          # mid-January of the following year
EXPIRY = 2050.02            # latest_expiration_time 2050-01-08


def year_fraction(dt: datetime | None = None) -> float:
    dt = dt or datetime.now(timezone.utc)
    start = datetime(dt.year, 1, 1, tzinfo=timezone.utc)
    end = datetime(dt.year + 1, 1, 1, tzinfo=timezone.utc)
    return dt.year + (dt - start).total_seconds() / (end - start).total_seconds()


def tau_yes(first_year, today: float):
    return np.asarray(first_year, dtype=float) + PUBLISH_LAG - today


def tau_no(today: float) -> float:
    return EXPIRY - today


def discount_yes(first_year, w, delta: float, today: float) -> float:
    """D_Y = weighted E[exp(-delta * tau_Y)] over Yes paths."""
    f = np.asarray(first_year, dtype=float)
    m = np.isfinite(f)
    if not m.any():
        return float("nan")
    w = np.asarray(w, dtype=float)[m]
    return float((w * np.exp(-delta * tau_yes(f[m], today))).sum() / w.sum())


def mean_tau_yes(first_year, w, today: float) -> float:
    f = np.asarray(first_year, dtype=float)
    m = np.isfinite(f)
    w = np.asarray(w, dtype=float)[m]
    return float((w * tau_yes(f[m], today)).sum() / w.sum())


def discount_no(delta: float, today: float) -> float:
    return math.exp(-delta * tau_no(today))


def implied_q(p: float, DY: float, DN: float) -> float:
    return p * DN / (p * DN + (1 - p) * DY)


def price_for_q(q: float, DY: float, DN: float) -> float:
    """Inverse of implied_q: the quote at which a belief q is the break-even belief."""
    return q * DY / (q * DY + (1 - q) * DN)


def no_trade_band(yes_cost: float, no_cost: float, DY: float, DN: float, h: float = 0.0):
    """Beliefs q in [lo, hi] for which neither buying Yes nor buying No beats the carry baseline.

    Buy Yes pays if q * DY * (1-h) > yes_cost  ->  q > hi
    Buy No  pays if (1-q) * DN * (1-h) > no_cost ->  q < lo
    """
    hi = yes_cost / (DY * (1 - h))
    lo = 1 - no_cost / (DN * (1 - h))
    return lo, hi


def side_expected_return(q_side: float, D: float, cost: float, tau: float, h: float = 0.0) -> dict:
    """Expected excess return of buying one side, over the carry baseline.

    q_side: probability that side wins; D: its discount factor; cost: all-in price paid;
    tau: (mean) years until it pays. Gross multiple = q_side * D * (1-h) / cost.
    """
    gross = q_side * D * (1 - h) / cost
    annual = gross ** (1 / tau) - 1 if gross > 0 else -1.0
    return {"gross_multiple": gross, "total_excess": gross - 1, "annualised_excess": annual}
