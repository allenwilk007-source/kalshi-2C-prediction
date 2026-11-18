"""IPCC-style emission paths for 2021-2100 (Mt C), in the course model's Kaya units.

2021-2024 are actual: the course's own Kaya 2019 value (10,580 Mt C, workbook BN65) scaled by
OWID/Global Carbon Budget World fossil CO2 relative to 2019. Using ratios keeps the level on the
course model's definition and avoids its missing COVID dip.

From 2025 the shapes follow the wording of IPCC AR6 WGI SPM Box SPM.1:
  falling   SSP1-2.6-like  "declining to net zero around or after 2050"  linear to 0 in 2070
  flat      SSP2-4.5-like  "around current levels until the middle of the century"
  rising    SSP3-7.0-like  "roughly double from current levels by 2100"   +0.9 %/yr
  doubling  SSP5-8.5-like  "roughly double ... by 2050"                   x2 by 2050
"""
from __future__ import annotations

import json

import numpy as np

from model import DATA
from observations import owid_world_co2

YEARS = np.arange(2021, 2101)
NAMES = ("falling", "flat", "rising", "doubling")
ANALOGUE = {"falling": "SSP1-2.6", "flat": "SSP2-4.5", "rising": "SSP3-7.0", "doubling": "SSP5-8.5"}


def course_kaya_2019() -> float:
    h = json.loads(DATA.read_text())["history_1960_2020"]
    return h["kaya_global_mtc"][h["years"].index(2019)]


def actual_2021_2024(owid=None, base_2019=None) -> np.ndarray:
    owid = owid or owid_world_co2()
    base = base_2019 or course_kaya_2019()
    return np.array([base * owid[y] / owid[2019] for y in range(2021, 2025)])


def path(name: str, actual=None) -> np.ndarray:
    """Emissions 2021-2100 in Mt C, shape (80,)."""
    a = actual if actual is not None else actual_2021_2024()
    base = a[-1]
    k = YEARS - 2024
    if name == "falling":
        shape = np.clip(1 - k / (2070 - 2024), 0, None)
    elif name == "flat":
        shape = np.ones_like(k, dtype=float)
    elif name == "rising":
        shape = 1.009 ** k
    elif name == "doubling":
        shape = 2.0 ** (k / (2050 - 2024))
    else:
        raise ValueError(name)
    out = base * shape.astype(float)
    out[:4] = a
    return out
