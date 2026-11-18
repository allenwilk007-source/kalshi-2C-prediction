"""Check the Python port against every year of all four HW5 sample-answer sheets.

    python validate.py ["../Future Sample Answer (corrected 9.24.25) HW5 copy.xlsx"]

Compares emissions (col B), ppm (H), forcing (L) and atmospheric temperature (M)
for 1750-2100 and exits non-zero if any relative error exceeds 1e-9.
"""
import sys
from pathlib import Path

import numpy as np
import openpyxl

from model import HW5_SCENARIOS, Inputs, run

HERE = Path(__file__).resolve().parent
DEFAULT_XLSX = HERE.parent / "Future Sample Answer (corrected 9.24.25) HW5 copy.xlsx"
COLS = {"emissions_mtc": "B", "ppm": "H", "forcing": "L", "temp_atmos": "M"}
TOL = 1e-9


def main(xlsx: Path) -> int:
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    inp = Inputs.load()
    worst_overall = 0.0
    for name, p in HW5_SCENARIOS.items():
        ws = wb[name]
        r = run(p, inp)
        line = [f"{name:18s}"]
        for attr, col in COLS.items():
            ours = getattr(r, attr)
            errs = []
            for i, year in enumerate(r.years):
                v = ws[f"{col}{i + 4}"].value
                if not isinstance(v, (int, float)) or (attr == "temp_atmos" and year < 1850):
                    continue
                if (col, year) in (("L", 1750), ("H", 1750)):  # L4 = "=L354" display cell; H4 is a label
                    continue
                errs.append(abs(ours[i] - v) / max(abs(v), 1e-6))
            worst = max(errs)
            worst_overall = max(worst_overall, worst)
            line.append(f"{col}:{len(errs)}yrs max rel err {worst:.1e}")
        print("  ".join(line))
    ok = worst_overall < TOL
    print("PASS" if ok else "FAIL", f"(worst {worst_overall:.1e}, tol {TOL:.0e})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_XLSX))
