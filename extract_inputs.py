"""Pull the hard-coded inputs out of the HW5 sample-answer workbook into JSON.

Run once; the model itself then needs only numpy.

    python extract_inputs.py ["../Future Sample Answer (corrected 9.24.25) HW5 copy.xlsx"]

Workbook layout (sheet "Hw5 template"):
  A4:A354   years 1750-2100
  B4:B274   historical emissions, Mt C, 1750-2020 (2021+ come from the Kaya block)
  AC67:AE146 population 2021-2100, millions, Rich/Middle/Poor (UN projection)
  AL66:AN66 GDP per capita 2020, $/person
  AU66:AW66 energy intensity 2020, TOE per $ (x1000)
  BD66:BF66 emissions intensity 2020, tCO2 per TOE
"""
import json
import sys
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
DEFAULT_XLSX = HERE.parent / "Future Sample Answer (corrected 9.24.25) HW5 copy.xlsx"


def main(xlsx_path: Path) -> None:
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb["Hw5 template"]

    hist_years = [ws[f"A{r}"].value for r in range(4, 275)]
    assert hist_years[0] == 1750 and hist_years[-1] == 2020
    hist_emissions = [float(ws[f"B{r}"].value) for r in range(4, 275)]

    pop = {
        region: [float(ws[f"{col}{r}"].value) for r in range(67, 147)]
        for region, col in zip(("rich", "middle", "poor"), ("AC", "AD", "AE"))
    }

    def row3(cols, r):
        return dict(zip(("rich", "middle", "poor"), (float(ws[f"{c}{r}"].value) for c in cols)))

    # Regional history 1960-2020 (rows 6-66), used for Phase 3 priors.
    # NB middle/poor energy (and so EI, CI) before 1971 is back-filled in the workbook
    # (AS6 = BB6/BE6 with BE extrapolated), so only 1971+ is real data for those.
    hist_rows = range(6, 67)
    def series(cols):
        return {reg: [float(ws[f"{c}{r}"].value) for r in hist_rows]
                for reg, c in zip(("rich", "middle", "poor"), cols)}
    history = {
        "years": [int(ws[f"AB{r}"].value) for r in hist_rows],
        "gdp_per_capita": series(("AL", "AM", "AN")),
        "energy_intensity": series(("AU", "AV", "AW")),
        "emissions_intensity": series(("BD", "BE", "BF")),
        "kaya_global_mtc": [float(ws[f"BN{r}"].value) for r in hist_rows],
    }
    assert history["years"][0] == 1960 and history["years"][-1] == 2020

    out = {
        "source": xlsx_path.name,
        "history_1960_2020": history,
        "hist_years": [1750, 2020],
        "hist_emissions_mtc": hist_emissions,
        "proj_years": [2021, 2100],
        "population_millions": pop,
        "base_2020": {
            "gdp_per_capita": row3(("AL", "AM", "AN"), 66),
            "energy_intensity": row3(("AU", "AV", "AW"), 66),
            "emissions_intensity": row3(("BD", "BE", "BF"), 66),
        },
    }
    dest = HERE / "data" / "hw5_inputs.json"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(out, indent=1))
    print(f"wrote {dest}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_XLSX)
