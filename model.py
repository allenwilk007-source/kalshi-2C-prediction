"""Python port of the Carbon Trading course model (HW2-HW5).

Chain:  Kaya (3 regions) -> Mt C emitted -> 5-box carbon cycle -> ppm CO2
        -> radiative forcing -> two-box (atmosphere/ocean) temperature.

Every function is vectorised: any parameter can be a scalar or a numpy array of
shape (n,), in which case the model runs n scenarios at once (for Monte Carlo).
Time runs along the last axis.

Temperature is measured from 1850, matching the workbook (M104 = N104 = 0).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parent / "data" / "hw5_inputs.json"
REGIONS = ("rich", "middle", "poor")

YEAR0 = 1750
YEAR_T0 = 1850   # temperature anomaly is zero here
YEAR_END = 2100


@dataclass(frozen=True)
class Params:
    # --- Kaya: annual growth rates 2021-2100, (rich, middle, poor) ---
    gdp_per_capita_growth: tuple = (0.012, 0.04, 0.022)          # AL5:AN5
    energy_intensity_change: tuple = (-0.0148, -0.0203, -0.0156)  # AU4:AW4
    emissions_intensity_change: tuple = (0.0014, 0.0045, -0.0051) # BD3:BF3
    # Not in the workbook. The historical series (col B) has 11,432 Mt C in 2020 but the
    # Kaya block's own 2020 value is 10,442, so projected emissions drop ~990 Mt C/yr
    # overnight in 2021 (probably land-use emissions). Adds a constant to 2021-2100.
    # Default 0 = exact course model.
    land_use_fill_mtc: float = 0.0
    # Not in the workbook. If set, replaces the Kaya projection for 2021-2100 with an explicit
    # emissions path in Mt C, shape (..., 80). Used for the IPCC-style scenario paths.
    future_emissions_mtc: object = None

    # --- carbon cycle (C2:G3, H3, L3) ---
    box_fractions: tuple = (0.13, 0.20, 0.32, 0.25, 0.10)
    box_lifetimes: tuple = (np.inf, 363.0, 74.0, 17.0, 2.0)  # years; inf = permanent
    mtc_to_ppm: float = 0.00047
    preindustrial_ppm: float = 275.0

    # --- forcing and temperature (L2, O1:O4) ---
    forcing_coef: float = 5.35        # W/m^2 per ln(C/C0)
    p1_adjust_speed: float = 0.0256   # rate atmosphere moves toward equilibrium
    p2_sensitivity: float = 1.15      # degC per W/m^2 at equilibrium
    p3_ocean_drag: float = 0.00738    # atmosphere response to ocean gap
    p4_ocean_uptake: float = 0.00568  # ocean response to atmosphere gap

    def ecs(self):
        """Equilibrium climate sensitivity implied by p2 (degC per CO2 doubling)."""
        return np.asarray(self.p2_sensitivity) * self.forcing_coef * np.log(2.0)


# The four sheets in the HW5 sample-answer workbook.
# NB the sheet named "scenario 3 - hw5" uses rich-country growth of -3%/yr,
# i.e. it answers the assignment's Scenario 4.
HW5_SCENARIOS = {
    "Hw5 template": Params(),
    "scenario 1 hw5": Params(
        gdp_per_capita_growth=(0.012, 0.0372754636397627, 0.058475149556828816),
        emissions_intensity_change=(0.003112823386849952,) * 3,
    ),
    "scenario 2 - hw5": Params(
        gdp_per_capita_growth=(0.0, 0.024975739819129643, 0.04592406385554809),
    ),
    "scenario 3 - hw5": Params(
        gdp_per_capita_growth=(-0.03, -0.005773690701766386, 0.014546102699180587),
    ),
}


@dataclass
class Inputs:
    hist_emissions_mtc: np.ndarray        # (271,) 1750-2020
    population: np.ndarray                # (3, 80) 2021-2100, millions
    gdp_pc_2020: np.ndarray               # (3,)
    ei_2020: np.ndarray                   # (3,)
    ci_2020: np.ndarray                   # (3,)

    @classmethod
    def load(cls, path: Path = DATA) -> "Inputs":
        d = json.loads(Path(path).read_text())
        b = d["base_2020"]
        return cls(
            hist_emissions_mtc=np.array(d["hist_emissions_mtc"]),
            population=np.array([d["population_millions"][r] for r in REGIONS]),
            gdp_pc_2020=np.array([b["gdp_per_capita"][r] for r in REGIONS]),
            ei_2020=np.array([b["energy_intensity"][r] for r in REGIONS]),
            ci_2020=np.array([b["emissions_intensity"][r] for r in REGIONS]),
        )


def _col(x):
    """Turn a per-region tuple/array of shape (3,) or (n,3) into (..., 3, 1)."""
    return np.asarray(x, dtype=float)[..., :, None]


def kaya_emissions(p: Params, inp: Inputs) -> np.ndarray:
    """Global emissions 2021-2100 in Mt C, shape (..., 80).

    Each region: pop * GDP/cap * energy intensity * emissions intensity * 1e-9
    gives Gt CO2 (columns BJ:BL); summed and converted at 12/44 * 1000 (BN).
    The 2020 level is the base; growth compounds from 2021.
    """
    steps = np.arange(1, inp.population.shape[1] + 1)            # 1..80
    g = (1 + _col(p.gdp_per_capita_growth)) ** steps
    e = (1 + _col(p.energy_intensity_change)) ** steps
    c = (1 + _col(p.emissions_intensity_change)) ** steps
    gdp_pc = inp.gdp_pc_2020[:, None] * g
    ei = inp.ei_2020[:, None] * e
    ci = inp.ci_2020[:, None] * c
    gt_co2 = inp.population * gdp_pc * ei * ci * 1e-9             # (..., 3, 80)
    return gt_co2.sum(axis=-2) * (12 / 44) * 1000


def concentrations(emissions_mtc: np.ndarray, p: Params) -> np.ndarray:
    """5-box carbon cycle. emissions: (..., T) for T years from 1750 onward.

    box_i(t) = decay_i * box_i(t-1) + E(t) * fraction_i * mtc_to_ppm
    Box 1 starts at the pre-industrial 275 ppm and never decays.
    Returns ppm, shape (..., T).
    """
    frac = np.asarray(p.box_fractions)
    decay = np.exp(-1.0 / np.asarray(p.box_lifetimes))             # exp(-1/inf) = 1
    T = emissions_mtc.shape[-1]
    boxes = np.zeros(emissions_mtc.shape[:-1] + (5,))
    boxes[..., 0] = p.preindustrial_ppm
    ppm = np.empty(emissions_mtc.shape)
    ppm[..., 0] = boxes.sum(-1)                                    # 1750: E=0 in workbook
    for t in range(1, T):
        boxes = decay * boxes + emissions_mtc[..., t, None] * frac * p.mtc_to_ppm
        ppm[..., t] = boxes.sum(-1)
    return ppm


def forcing(ppm: np.ndarray, p: Params) -> np.ndarray:
    return p.forcing_coef * np.log(ppm / p.preindustrial_ppm)


def temperature(F: np.ndarray, p: Params, t0_index: int = YEAR_T0 - YEAR0):
    """Two-box energy-balance model; F is forcing from 1750 on, (..., T).

    O(t) = p1 * (p2 * F(t) - AT(t-1))         pull toward equilibrium
    P(t) = p3 * (OT(t-1) - AT(t-1))           drag from cooler ocean
    AT(t) = AT(t-1) + O(t) + P(t)
    OT(t) = OT(t-1) + p4 * (AT(t-1) - OT(t-1))
    AT = OT = 0 at 1850. Returns (atmosphere, ocean), NaN before 1850.
    """
    p1, p2, p3, p4 = (np.asarray(x, dtype=float) for x in
                      (p.p1_adjust_speed, p.p2_sensitivity, p.p3_ocean_drag, p.p4_ocean_uptake))
    batch = np.broadcast_shapes(F.shape[:-1], p1.shape, p2.shape, p3.shape, p4.shape)
    F = np.broadcast_to(F, batch + F.shape[-1:])
    AT = np.full(F.shape, np.nan)
    OT = np.full(F.shape, np.nan)
    at = np.zeros(F.shape[:-1])
    ot = np.zeros(F.shape[:-1])
    AT[..., t0_index] = at
    OT[..., t0_index] = ot
    for t in range(t0_index + 1, F.shape[-1]):
        at_new = at + p1 * (p2 * F[..., t] - at) + p3 * (ot - at)
        ot = ot + p4 * (at - ot)
        at = at_new
        AT[..., t] = at
        OT[..., t] = ot
    return AT, OT


@dataclass
class Run:
    years: np.ndarray
    emissions_mtc: np.ndarray
    ppm: np.ndarray
    forcing: np.ndarray
    temp_atmos: np.ndarray
    temp_ocean: np.ndarray

    def at(self, year: int, series: str = "temp_atmos"):
        return getattr(self, series)[..., year - YEAR0]

    def first_year_at_or_above(self, threshold: float, series=None) -> np.ndarray:
        """First calendar year the series >= threshold; NaN if never by 2100."""
        x = self.temp_atmos if series is None else series
        hit = np.nan_to_num(x, nan=-np.inf) >= threshold
        idx = hit.argmax(axis=-1)
        return np.where(hit.any(axis=-1), self.years[idx], np.nan)


def run(p: Params = Params(), inp: Inputs | None = None) -> Run:
    inp = inp or Inputs.load()
    if p.future_emissions_mtc is None:
        future = kaya_emissions(p, inp)                             # (..., 80)
    else:
        future = np.asarray(p.future_emissions_mtc, dtype=float)
        assert future.shape[-1] == inp.population.shape[1], "override must cover 2021-2100"
    future = future +np.asarray(p.land_use_fill_mtc, dtype=float)[..., None]
    hist = np.broadcast_to(inp.hist_emissions_mtc, future.shape[:-1] + inp.hist_emissions_mtc.shape)
    E = np.concatenate([hist, future], axis=-1)                     # 1750-2100
    C = concentrations(E, p)
    F = forcing(C, p)
    AT, OT = temperature(F, p)
    years = np.arange(YEAR0, YEAR_END + 1)
    return Run(years, E, C, F, AT, OT)


if __name__ == "__main__":
    inp = Inputs.load()
    for name, p in HW5_SCENARIOS.items():
        r = run(p, inp)
        print(f"{name:18s} 2050 {r.at(2050):.2f}C  2100 {r.at(2100):.2f}C  "
              f"{r.at(2100, 'ppm'):.0f} ppm  first >=2C: {r.first_year_at_or_above(2.0):.0f}")
    print(f"implied ECS: {Params().ecs():.2f} C per doubling")
