"""Build excel/ensemble_72_versions.xlsx: how the 72-version estimate (80.8%) is computed, with live formulas.

    python excel/build_ensemble_xlsx.py

Inputs come from the Python pipeline: results/phase11.json (each version's simulated futures),
results/decision_context.json (Kalshi quote, dataset offsets, noise), and the class model for the example future.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from calibrate import model_rebaselined  # noqa: E402
from model import YEAR0, Inputs, Params  # noqa: E402
from phase3 import setup  # noqa: E402

P11 = json.loads((ROOT / "results" / "phase11.json").read_text())
CTX = json.loads((ROOT / "results" / "decision_context.json").read_text())
SNAP_TIME = str(CTX.get("fetched_utc", ""))[:16].replace("T", " ")

FONT = "Arial"
BLUE = Font(name=FONT, color="0000FF")
BLACK = Font(name=FONT)
GREEN = Font(name=FONT, color="008000")
BOLD = Font(name=FONT, bold=True)
TITLE = Font(name=FONT, bold=True, size=14)
HEAD = Font(name=FONT, bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="14213D")
KEY_FILL = PatternFill("solid", fgColor="FFFF00")
THIN = Side(style="thin", color="D9DBD6")
BOX = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
PCT = "0.0%"


def header(ws, row, labels, widths=None):
    for j, lab in enumerate(labels, 1):
        c = ws.cell(row=row, column=j, value=lab)
        c.font, c.fill, c.alignment, c.border = HEAD, HEAD_FILL, Alignment(wrap_text=True, vertical="center"), BOX
    if widths:
        for j, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(j)].width = w


def cell(ws, ref, value, font=BLACK, fmt=None, fill=None, comment=None):
    c = ws[ref]
    c.value, c.font = value, font
    if fmt:
        c.number_format = fmt
    if fill:
        c.fill = fill
    if comment:
        c.comment = Comment(comment, "class project")
    return c


wb = Workbook()

# ------------------------------------------------------------------ Read me
rm = wb.active
rm.title = "Read me"
rm.column_dimensions["A"].width = 140
lines = [
    ("How the 72-version estimate (80.8%) is computed", TITLE),
    ("", None),
    ("Question: what is the chance that any calendar year before 2050 is at least 2.00°C above 1850–1900, under Kalshi’s rule for contract", None),
    ("KXWARMING-50? A year counts when the second-highest of NASA GISS, NOAA, Berkeley Earth and HadCRUT, rounded to 0.01, is at least 2.00.", None),
    ("", None),
    ("1. We vary the four most important inputs of the HW5 class model around the class values:", BOLD),
    ("   climate sensitivity p2 in {1.00, 1.15, 1.30} × adjustment speed p1 in {0.020, 0.0256, 0.032} × emissions after 2024 in {HW5 economy, falling, flat, rising}", None),
    ("   × missing land-use emissions {off, on = +990 MtC per year} = 3 × 3 × 4 × 2 = 72 versions.", None),
    ("2. For each version, Python (phase11.py) simulates 4,000 futures: the class model path, anchored to observed 2006–2025 temperatures,", BOLD),
    ("   plus year-to-year AR(1) noise (phi = 0.53, sigma = 0.099°C, fitted 1880–2025), started from the 2026 nowcast, with each dataset’s offset.", None),
    ("   Each future is scored with Kalshi’s rule. Sheet ‘One future (example)’ shows the scoring of one real simulated future, step by step.", None),
    ("3. Sheet ‘72 versions’: P(version) = futures reaching 2°C ÷ 4,000. Our estimate = all futures reaching 2°C ÷ all 288,000 futures.", BOLD),
    ("   Because every version has the same number of futures, this equals the plain average of the 72 probabilities (equal weights).", None),
    ("4. Sheet ‘By setting’ averages the versions by each input, and shows the 3 × 3 table of sensitivity × speed.", BOLD),
    ("5. Sheet ‘Vs Kalshi’ turns the estimate into a hypothetical Yes / No / Pass decision using Kalshi’s order book and fee.", BOLD),
    ("", None),
    ("Colour code: blue = inputs taken from the Python simulation or Kalshi’s order book; black = formulas; green = links to another sheet;", None),
    ("yellow fill = the key results. Change any blue input and every result recalculates.", None),
    ("", None),
    ("Sources: results/phase11.json (counts per version, from phase11.py, 4,000 futures each, seeds 100–171);", None),
    (f"results/decision_context.json (Kalshi order book snapshot {SNAP_TIME} UTC, dataset offsets, noise model); model.py is the HW5 class model.", None),
    ("The Monte Carlo standard error of the estimate is about 0.07 percentage points. Hypothetical class analysis; not investment advice.", None),
    ("Choice to note: the 72 versions get equal weight and are not weighted by how well they fit history. The IPCC-calibrated view in the project gives 67%.", None),
]
for i, (txt, f) in enumerate(lines, 1):
    rm.cell(row=i, column=1, value=txt).font = f or BLACK

# ------------------------------------------------------------------ 72 versions
vs = wb.create_sheet("72 versions")
header(vs, 1, ["Version", "Climate sensitivity p2", "Implied warming per CO₂ doubling (°C)", "Adjustment speed p1",
               "Emissions after 2024", "Land-use emissions", "Futures simulated", "Futures reaching 2°C",
               "P(2°C year by 2049)", "Mean hottest reading 2027–2049 (°C)"],
       [9, 14, 18, 14, 18, 14, 13, 14, 14, 18])
vs.row_dimensions[1].height = 48
vers = P11["ensemble"]["versions"]
K = P11["ensemble"]["paths_per_version"]
for i, v in enumerate(vers):
    r = i + 2
    hits = round(v["p_yes"] * K)
    assert abs(hits / K - v["p_yes"]) < 1e-9
    cell(vs, f"A{r}", i + 1)
    cell(vs, f"B{r}", v["p2"], BLUE, "0.00")
    cell(vs, f"C{r}", f"=B{r}*5.35*LN(2)", BLACK, "0.00")
    cell(vs, f"D{r}", v["p1"], BLUE, "0.0000")
    cell(vs, f"E{r}", v["emissions"], BLUE)
    cell(vs, f"F{r}", v["land_use"], BLUE)
    cell(vs, f"G{r}", K, BLUE, "#,##0")
    cell(vs, f"H{r}", hits, BLUE, "#,##0")
    cell(vs, f"I{r}", f"=IF(G{r}>0,H{r}/G{r},0)", BLACK, PCT)
    cell(vs, f"J{r}", round(v["peak_mean"], 4), BLUE, "0.000")
last = len(vers) + 1
vs["C1"].comment = Comment("Class model: forcing for doubled CO2 = 5.35 × ln 2 = 3.71 W/m², times p2.", "class project")
vs["H1"].comment = Comment("Counted by phase11.py: futures whose second-highest dataset reading, rounded to 0.01, "
                           "is at least 2.00 in at least one year 2027–2049.", "class project")
t = last + 2
cell(vs, f"A{t}", "Totals", BOLD)
cell(vs, f"G{t}", f"=SUM(G2:G{last})", BOLD, "#,##0")
cell(vs, f"H{t}", f"=SUM(H2:H{last})", BOLD, "#,##0")
cell(vs, f"A{t + 1}", "Our estimate: all futures reaching 2°C ÷ all futures", BOLD)
cell(vs, f"I{t + 1}", f"=IF(G{t}>0,H{t}/G{t},0)", BOLD, PCT, KEY_FILL)
cell(vs, f"A{t + 2}", "Check: plain average of the 72 probabilities (equal weights)")
cell(vs, f"I{t + 2}", f"=AVERAGE(I2:I{last})", BLACK, PCT)
cell(vs, f"A{t + 3}", "Lowest and highest single version")
cell(vs, f"H{t + 3}", f"=MIN(I2:I{last})", BLACK, PCT)
cell(vs, f"I{t + 3}", f"=MAX(I2:I{last})", BLACK, PCT)
cell(vs, f"A{t + 4}", "Monte Carlo standard error of the estimate")
cell(vs, f"I{t + 4}", f"=SQRT(I{t + 1}*(1-I{t + 1})/G{t})", BLACK, "0.00%")
cell(vs, f"A{t + 5}", "Mean hottest reading across all versions (°C)")
cell(vs, f"I{t + 5}", f"=AVERAGE(J2:J{last})", BLACK, "0.000")
vs.freeze_panes = "A2"
EST = f"'72 versions'!$I${t + 1}"

# ------------------------------------------------------------------ By setting
bs = wb.create_sheet("By setting")
bs.column_dimensions["A"].width = 34
for col in "BCDE":
    bs.column_dimensions[col].width = 18
R = f"'72 versions'!$I$2:$I${last}"
cell(bs, "A1", "Average P(2°C year by 2049) by each input: each row averages the versions with that setting", BOLD)
row = 3
groups = [("Climate sensitivity p2", "B", [1.0, 1.15, 1.3], "0.00"), ("Adjustment speed p1", "D", [0.02, 0.0256, 0.032], "0.0000"),
          ("Emissions after 2024", "E", ["HW5 economy", "falling", "flat", "rising"], None), ("Land-use emissions", "F", ["off", "on"], None)]
for name, col, vals, fmt in groups:
    for j, lab in enumerate([name, "Versions", "Average P", "Futures reaching 2°C"], 1):
        c = bs.cell(row=row, column=j, value=lab)
        c.font, c.fill, c.border = HEAD, HEAD_FILL, BOX
    for v in vals:
        row += 1
        cell(bs, f"A{row}", v, BLUE, fmt)
        rng = f"'72 versions'!${col}$2:${col}${last}"
        cell(bs, f"B{row}", f"=COUNTIF({rng},A{row})", BLACK)
        cell(bs, f"C{row}", f"=AVERAGEIF({rng},A{row},{R})", BLACK, PCT)
        cell(bs, f"D{row}", f"=SUMIF({rng},A{row},'72 versions'!$H$2:$H${last})", BLACK, "#,##0")
    row += 2
cell(bs, f"A{row}", "Sensitivity p2 (rows) × speed p1 (columns): each cell averages 8 versions (4 emissions × 2 land use)", BOLD)
row += 1
hr = row
c = bs.cell(row=hr, column=1, value="p2 \\ p1")
c.font, c.fill = HEAD, HEAD_FILL
for j, p1 in enumerate([0.02, 0.0256, 0.032]):
    c = bs.cell(row=hr, column=2 + j, value=p1)
    c.font, c.fill, c.number_format = HEAD, HEAD_FILL, "0.0000"
for i, p2 in enumerate([1.0, 1.15, 1.3]):
    r = hr + 1 + i
    cell(bs, f"A{r}", p2, BLUE, "0.00")
    for j in range(3):
        cl = get_column_letter(2 + j)
        cell(bs, f"{cl}{r}", f"=AVERAGEIFS({R},'72 versions'!$B$2:$B${last},$A{r},'72 versions'!$D$2:$D${last},{cl}${hr})", BLACK, PCT)
r = hr + 5
cell(bs, f"A{r}", "Average of the nine cells", BOLD)
cell(bs, f"B{r}", f"=AVERAGE(B{hr + 1}:D{hr + 3})", BOLD, PCT, KEY_FILL)
cell(bs, f"A{r + 1}", "Our estimate (from ‘72 versions’)")
cell(bs, f"B{r + 1}", f"={EST}", GREEN, PCT)
cell(bs, f"A{r + 2}", "Class settings (p2 = 1.15, p1 = 0.0256)")
cell(bs, f"B{r + 2}", f"=C{hr + 2}", BLACK, PCT)

# ------------------------------------------------------------------ Vs Kalshi
kx = wb.create_sheet("Vs Kalshi")
kx.column_dimensions["A"].width = 70
for col in "BCD":
    kx.column_dimensions[col].width = 16
k = CTX["kalshi"]
cell(kx, "A1", "From a probability to a hypothetical decision (Kalshi KXWARMING-50)", BOLD)
cell(kx, "A2", f"Order book snapshot {SNAP_TIME} UTC. Hypothetical; no trades were placed.")
rows = [
    ("Our estimate P(Yes)", f"={EST}", GREEN, PCT),
    ("Contracts per order", 100, BLUE, "0"),
    ("Kalshi fee rate (taker fee = ROUNDUP(rate × contracts × price × (1 − price), to the cent))", 0.07, BLUE, "0.00"),
    ("Best bid for Yes ($)", k["bid"], BLUE, "0.00"),
    ("Best ask for Yes ($)", k["ask"], BLUE, "0.00"),
    ("Market midpoint = market’s probability", "=(B7+B8)/2", BLACK, PCT),
    ("Fee to buy 100 Yes at the ask ($)", "=ROUNDUP(B6*B5*B8*(1-B8),2)", BLACK, "$0.00"),
    ("All-in cost of one Yes contract", "=B8+B10/B5", BLACK, "0.0000"),
]
for i, (lab, val, f, fmt) in enumerate(rows, 4):
    cell(kx, f"A{i}", lab)
    cell(kx, f"B{i}", val, f, fmt)
cell(kx, "A13", "Buying 100 No walks the No order book:", BOLD)
for j, lab in enumerate(["No ask price ($)", "Contracts filled", "Cost ($)"]):
    c = kx.cell(row=14, column=2 + j, value=lab)
    c.font, c.fill = HEAD, HEAD_FILL
for i, (p, q) in enumerate([(0.32, 20.0), (0.33, 64.48), (0.34, 15.52)], 15):
    cell(kx, f"A{i}", f"Price level {i - 14}")
    cell(kx, f"B{i}", p, BLUE, "0.00")
    cell(kx, f"C{i}", q, BLUE, "0.00")
    cell(kx, f"D{i}", f"=B{i}*C{i}", BLACK, "$0.00")
kx["C15"].comment = Comment("Contracts available at each No price in the snapshot: 20 at 32¢, 64.48 at 33¢, "
                            "then 15.52 of the 112.88 at 34¢ to complete 100.", "class project")
cell(kx, "A18", "Fee for the No order ($)")
cell(kx, "B18", "=ROUNDUP(B6*SUMPRODUCT(C15:C17,B15:B17,1-B15:B17),2)", BLACK, "$0.00")
cell(kx, "A19", "All-in cost of one No contract")
cell(kx, "B19", "=(SUM(D15:D17)+B18)/SUM(C15:C17)", BLACK, "0.0000")
cell(kx, "A21", "Range of beliefs where neither side is worth buying (from, to)", BOLD)
cell(kx, "B21", "=1-B19", BLACK, PCT)
cell(kx, "C21", "=B11", BLACK, PCT)
cell(kx, "A22", "Decision for our estimate")
cell(kx, "B22", '=IF(B4>B11,"Buy YES",IF(1-B4>B19,"Buy NO","Pass"))', BOLD, None, KEY_FILL)
cell(kx, "A24", "Stake ($, hypothetical)")
cell(kx, "B24", 100, BLUE, "$#,##0")
cell(kx, "A25", "Contracts bought")
cell(kx, "B25", '=IF(B22="Buy YES",INT(B24/B11),IF(B22="Buy NO",INT(B24/B19),0))', BLACK, "#,##0")
cell(kx, "A26", "Cost per contract")
cell(kx, "B26", '=IF(B22="Buy YES",B11,IF(B22="Buy NO",B19,0))', BLACK, "0.0000")
cell(kx, "A27", "Chance this bet wins")
cell(kx, "B27", '=IF(B22="Buy YES",B4,IF(B22="Buy NO",1-B4,0))', BLACK, PCT)
cell(kx, "A28", "Profit if it wins ($)")
cell(kx, "B28", "=B25*(1-B26)", BLACK, "$#,##0.00")
cell(kx, "A29", "Profit if it loses ($)")
cell(kx, "B29", "=-B25*B26", BLACK, "$#,##0.00;($#,##0.00);-")
cell(kx, "A30", "Expected profit ($)")
cell(kx, "B30", "=B27*B28+(1-B27)*B29", BOLD, "$#,##0.00;($#,##0.00);-", KEY_FILL)
cell(kx, "A32", "Try it: replace the formula in B4 with another probability (e.g. 0.67 for the IPCC-calibrated view) to see the decision change.")

# ------------------------------------------------------------------ One future (example)
inp = Inputs.load()
st = setup(inp)
_, T = model_rebaselined(Params(), inp)
ys, S = st["years"], st["S"]
sel = (ys >= 2006) & (ys <= 2025)
b = float(np.mean(S[sel] - T[ys[sel] - YEAR0]))
phi, sig = CTX["class_ar1"]["phi"], CTX["class_ar1"]["sigma"]
off, mom = CTX["offsets"], CTX["momentum"]
rng = np.random.default_rng(11)
r0 = CTX["signal_2026"]["mean"] - T[2026 - YEAR0]
rr = b + phi * (r0 - b) + rng.normal() * sig + (mom["phi1"] - phi) * (r0 - b) + mom["phi2"] * CTX["q4_minus_annual_2026"]
u = np.array(off["last_dev"])
ex = []
for t_, y in enumerate(range(2027, 2050)):
    if t_ > 0:
        rr = b * (1 - phi) + phi * rr + sig * rng.normal()
    errs = []
    for kk in range(4):
        if off["rho"][kk] > 0.3:
            u[kk] = off["rho"][kk] * u[kk] + off["tau"][kk] * math.sqrt(1 - off["rho"][kk] ** 2) * rng.normal()
        else:
            u[kk] = off["tau"][kk] * rng.normal()
        errs.append(float(u[kk]))
    ex.append((y, float(T[y - YEAR0] + b), float(rr - b), errs))

ef = wb.create_sheet("One future (example)")
cell(ef, "A1", "Scoring one simulated future with Kalshi’s rule (class settings: p2 = 1.15, p1 = 0.0256, HW5 economy)", BOLD)
cell(ef, "A2", "Blue = from the simulation. Formulas add each dataset’s offset and its own small error, round to 0.01, take the second-highest, and test it against the threshold.")
cell(ef, "D4", "Dataset offset (°C)", BOLD)
for j, d in enumerate(off["delta"]):
    cell(ef, f"{get_column_letter(5 + j)}4", round(d, 4), BLUE, "+0.000;-0.000")
ef["E4"].comment = Comment("Average gap between each dataset and the four-dataset mean, 1996–2025.", "class project")
cell(ef, "A5", "Threshold (°C)")
cell(ef, "B5", 2.0, BLUE, "0.00")
header(ef, 7, ["Year", "Model + anchor (°C)", "Year-to-year noise (°C)", "Signal (°C)", "GISS", "NOAA", "Berkeley", "HadCRUT",
               "2nd-highest (°C)", "Counts (1 = yes)", "GISS own error", "NOAA own error", "Berkeley own error", "HadCRUT own error"],
       [8, 16, 14, 12, 10, 10, 10, 10, 14, 11, 12, 12, 12, 12])
ef.row_dimensions[7].height = 34
for i, (y, sm, nz, errs) in enumerate(ex):
    r = 8 + i
    cell(ef, f"A{r}", str(y), BLUE)
    cell(ef, f"B{r}", round(sm, 4), BLUE, "0.000")
    cell(ef, f"C{r}", round(nz, 4), BLUE, "+0.000;-0.000")
    cell(ef, f"D{r}", f"=B{r}+C{r}", BLACK, "0.000")
    for j in range(4):
        err_col = get_column_letter(11 + j)
        cell(ef, f"{err_col}{r}", round(errs[j], 4), BLUE, "+0.000;-0.000")
        cl = get_column_letter(5 + j)
        cell(ef, f"{cl}{r}", f"=ROUND($D{r}+{cl}$4+{err_col}{r},2)", BLACK, "0.00")
    cell(ef, f"I{r}", f"=LARGE(E{r}:H{r},2)", BLACK, "0.00")
    cell(ef, f"J{r}", f"=IF(I{r}>=$B$5,1,0)", BLACK, "0")
lr = 8 + len(ex) - 1
cell(ef, f"A{lr + 2}", "First year that counts", BOLD)
cell(ef, f"D{lr + 2}", f'=IFERROR(INDEX(A8:A{lr},MATCH(1,J8:J{lr},0)),"none")', BOLD, None, KEY_FILL)
cell(ef, f"A{lr + 3}", "This future pays", BOLD)
cell(ef, f"D{lr + 3}", f'=IF(SUM(J8:J{lr})>0,"Yes","No")', BOLD, None, KEY_FILL)
cell(ef, f"A{lr + 4}", "Hottest reading 2027–2049 (°C)")
cell(ef, f"D{lr + 4}", f"=MAX(I8:I{lr})", BLACK, "0.00")
cell(ef, f"A{lr + 6}", "phase11.py scores 4,000 futures like this one for every version; ‘Futures reaching 2°C’ on the ‘72 versions’ sheet counts those that pay Yes.")
ef.freeze_panes = "A8"

out = HERE / "ensemble_72_versions.xlsx"
wb.save(out)
print(out)
