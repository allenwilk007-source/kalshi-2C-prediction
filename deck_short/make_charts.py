"""Charts for the short deck, from the project's results: python deck_short/make_charts.py -> deck_short/charts/*.png"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
THEME = sys.argv[1] if len(sys.argv) > 1 else "light"     # "light" (original deck) or "kalshi" (dark, Kalshi-style)
OUT = HERE / ("charts_kalshi" if THEME == "kalshi" else "charts")
OUT.mkdir(exist_ok=True)
C = json.loads((HERE.parent / "results" / "decision_context.json").read_text())
INK, BODY, MUTED, LINE, BG = "#14213D", "#3D4656", "#5B6475", "#D9DBD6", "#FCFBF8"
ORANGE, ORANGE_D, BLUE, GOLD = "#EA580C", "#C2410C", "#1D4ED8", "#CA8A04"
GOLD_T, BAND_BG = "#A16207", "#ECEEF2"
if THEME == "kalshi":   # Kalshi-style dark palette: green = Yes / our model, red = No, white text on near-black
    INK, BODY, MUTED, LINE, BG = "#F2F3F3", "#C9CBCD", "#8F9193", "#2A2E34", "#13161A"
    ORANGE, ORANGE_D, BLUE, GOLD = "#00DD94", "#00B67A", "#6EA8FE", "#F2C94C"
    GOLD_T, BAND_BG = "#F2C94C", "#22262C"
plt.rcParams.update({"font.family": "Segoe UI", "font.size": 15, "text.color": INK, "axes.labelcolor": BODY,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.edgecolor": LINE, "figure.facecolor": BG,
                     "axes.facecolor": BG, "axes.spines.top": False, "axes.spines.right": False})
K = C["kalshi"]


def save(fig, name):
    fig.savefig(OUT / f"{name}.png", dpi=200, bbox_inches="tight", pad_inches=0.25, facecolor=BG)
    plt.close(fig)
    print(name)


# 1 · the probability density functions behind 81% and 67%
fig, ax = plt.subplots(figsize=(10, 6))
for key, col, lab, p in (("ensemble_pdf", ORANGE, "Our model, 72 versions", C["reference"]["ensemble_72"]),
                         ("ipcc_pdf", BLUE, "Our model, IPCC-calibrated", C["reference"]["ipcc"])):
    g, f = np.array(C[key]["grid"]), np.array(C[key]["pdf"])
    m = (g >= 1.4) & (g <= 2.8)
    ax.plot(g[m], f[m], color=col, lw=3, label=f"{lab}: {p:.0%} of futures reach 2°C")
    s = m & (g >= 2.0)
    ax.fill_between(g[s], f[s], color=col, alpha=0.13)
ax.axvline(2.0, color=GOLD, lw=3)
ym = ax.get_ylim()[1]
ax.text(1.985, ym * 0.97, "2.00°C", color=GOLD_T, va="top", ha="right", fontsize=15, fontweight="bold")
ax.text(2.40, ym * 0.62, "Shaded area right of 2.00°C\n= chance the contract pays Yes", color=INK, fontsize=14, fontweight="bold")
ax.set_xlabel("Hottest contract reading in 2027–2049 (°C above 1850–1900)")
ax.set_ylabel("Probability density")
ax.set_yticks([])
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), frameon=False, fontsize=15, ncol=1)
ax.set_xlim(1.4, 2.8)
save(fig, "pdf")

# 2 · Kalshi's order book
asks = [(0.84, 212), (0.76, 400), (0.75, 40), (0.72, 500)]
bids = [(0.68, 20), (0.67, 64), (0.66, 113), (0.65, 546), (0.64, 166)]
fig, ax = plt.subplots(figsize=(8.5, 6.4))
ASK_C, BID_C = ("#FF454D", "#00DD94") if THEME == "kalshi" else (ORANGE, BLUE)
rows = [(f"{p * 100:.0f}¢", n, ASK_C) for p, n in asks] + [("", 0, BG)] + [(f"{p * 100:.0f}¢", n, BID_C) for p, n in bids]
y = np.arange(len(rows))[::-1]
ax.barh(y, [r[1] for r in rows], color=[r[2] for r in rows], height=0.72)
for yi, (lab, n, col) in zip(y, rows):
    if n:
        ax.text(n + 8, yi, f"{n:.0f}", va="center", color=MUTED, fontsize=13)
ax.set_yticks(y, [r[0] for r in rows], fontsize=15, color=INK)
ax.text(300, y[4], "Spread 68¢–72¢ · midpoint 70¢ = 70%", ha="center", va="center", fontsize=16, fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.5", fc=BAND_BG, ec="none"))
ax.text(560, y[0] + 0.1, "Offers to SELL Yes (asks)", ha="right", color=ASK_C, fontweight="bold")
ax.text(560, y[-1] - 0.1, "Offers to BUY Yes (bids)", ha="right", color=BID_C, fontweight="bold")
ax.set_xlabel("Contracts offered (18 Nov 2026)")
ax.set_xlim(0, 620)
ax.tick_params(axis="y", length=0)
ax.spines["left"].set_visible(False)
save(fig, "orderbook")

# 3 · every number side by side
ref = C["reference"]
items = [("Class model as taught (HW5)", ref["class_hw5"], ORANGE_D), ("Fitted to history", ref["history"], ORANGE_D),
         ("Our model, 72 versions", ref["ensemble_72"], ORANGE), ("Kalshi market", K["mid"], INK),
         ("Our model, IPCC-calibrated", ref["ipcc"], BLUE), ("Wide (full IPCC range)", ref["ipcc_full"], BLUE)]
fig, ax = plt.subplots(figsize=(10, 5.6))
y = np.arange(len(items))[::-1]
ax.axvspan(K["band"][0] * 100, K["band"][1] * 100, color=GOLD, alpha=0.18, lw=0)
ax.barh(y, [v * 100 for _, v, _ in items], color=[c for *_, c in items], height=0.62)
for yi, (lab, v, c) in zip(y, items):
    ax.text(v * 100 + 1, yi, f"{v:.0%}", va="center", fontweight="bold", color=c, fontsize=16)
ax.set_yticks(y, [i[0] for i in items], fontsize=15, color=INK)
ax.text((K["band"][0] + K["band"][1]) * 50, len(items) - 0.35, "Kalshi’s fair range\nafter fees: 65–73%", ha="center",
        va="bottom", color=GOLD_T, fontsize=13, fontweight="bold")
ax.set_xlim(0, 108)
ax.set_ylim(-0.6, len(items) + 0.5)
ax.set_xlabel("Chance of a 2°C year before 2050 (%)")
ax.tick_params(axis="y", length=0)
ax.spines["left"].set_visible(False)
save(fig, "compare")

# 4 · the decision zones
lo, hi = 1 - K["no_cost"], K["yes_cost"]
NO_C, YES_C = ("#FF454D", "#00DD94") if THEME == "kalshi" else (BLUE, ORANGE_D)
fig, ax = plt.subplots(figsize=(13, 3.0))
ax.axvspan(0, lo * 100, color=NO_C, alpha=0.16, lw=0)
ax.axvspan(lo * 100, hi * 100, color=MUTED, alpha=0.16, lw=0)
ax.axvspan(hi * 100, 100, color=YES_C, alpha=0.16, lw=0)
ax.text(lo * 50, 0.5, f"Buy NO\nif you believe under {lo:.1%}", ha="center", va="center", color=NO_C, fontweight="bold", fontsize=15)
ax.text((lo + hi) * 50, 0.5, "Pass", ha="center", va="center", color=MUTED, fontweight="bold", fontsize=15)
ax.text((hi + 1) * 50, 0.5, f"Buy YES\nif you believe over {hi:.1%}", ha="center", va="center", color=YES_C, fontweight="bold", fontsize=15)
for v, lab, col, yy in ((ref["ipcc"], "IPCC-cal.\n67%", BLUE, 1.02), (K["mid"], "Kalshi 70%", INK, -0.02),
                        (ref["ensemble_72"], "Our model\n81%", ORANGE_D, 1.02)):
    ax.plot([v * 100], [yy if yy > 0.5 else 0.0], marker="v" if yy > 0.5 else "^", color=col, ms=13, clip_on=False)
    ax.text(v * 100, yy + (0.08 if yy > 0.5 else -0.1), lab, ha="center", va="bottom" if yy > 0.5 else "top", color=col, fontsize=13, fontweight="bold")
ax.set_xlim(0, 100)
ax.set_ylim(0, 1)
ax.set_yticks([])
ax.set_xticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
ax.spines["left"].set_visible(False)
ax.set_xlabel("Your chance of a 2°C year", labelpad=26)
save(fig, "decision")
