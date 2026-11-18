"""Editable PowerPoint version of the short deck (for Google Slides): python deck_short/build_pptx.py

Text, tables and cards are real, editable objects; charts and screenshots are images. Speaker notes come from each
slide's <aside> in deck_short/deck/slides/. Layout is in 1920x1080 "px" (the deck's canvas), converted to inches.
"""
import html
import re
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

HERE = Path(__file__).resolve().parent
SLIDES = HERE / "deck" / "slides"
IMG = HERE / "_pptx_img"
OUT = HERE / "kalshi_2C_pitch_deck.pptx"
REPO = "github.com/allenwilk007-source/kalshi-2C-prediction"

BG, BG2, CARD, LINE = "0A0C0F", "13161A", "15181C", "2A2E34"
TEXT, BODY, MUTED, GREEN, RED, CALL_BG, CALL_LINE = "F2F3F3", "C9CBCD", "8F9193", "00DD94", "FF454D", "0E2A22", "1F5A47"
HEAD, SANS = "Barlow Condensed", "Inter"


def px(v):
    return Emu(int(round(v * 6350)))          # 1920 px = 13.333 in


def rgb(h):
    return RGBColor.from_string(h)


def notes_for(sid):
    s = (SLIDES / f"{sid}.html").read_text(encoding="utf-8")
    m = re.search(r"<aside>(.*?)</aside>", s, re.S)
    return html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else ""


def image(name, w, h):
    """Copy an image at its display size x2 so the .pptx stays small."""
    IMG.mkdir(exist_ok=True)
    src = HERE / name
    out = IMG / (Path(name).stem + ".png")
    im = Image.open(src).convert("RGB")
    im.thumbnail((int(w * 1.6), int(h * 1.6)))
    im.save(out, optimize=True)
    return out


prs = Presentation()
prs.slide_width, prs.slide_height = px(1920), px(1080)
BLANK = prs.slide_layouts[6]


def new_slide(alt=False, sid=None):
    sl = prs.slides.add_slide(BLANK)
    sl.background.fill.solid()
    sl.background.fill.fore_color.rgb = rgb(BG2 if alt else BG)
    if sid:
        sl.notes_slide.notes_text_frame.text = notes_for(sid)
    return sl


def text(sl, x, y, w, h, paras, size=26, color=BODY, font=SANS, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, spacing=None):
    """paras: list of paragraphs; each paragraph a string or a list of (text, {size,color,font,bold}) runs."""
    tb = sl.shapes.add_textbox(px(x), px(y), px(w), px(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if spacing:
            p.space_after = Pt(spacing)
        runs = [(para, {})] if isinstance(para, str) else para
        for t, st in runs:
            r = p.add_run()
            r.text = t
            f = r.font
            f.size = Pt(st.get("size", size) / 2)
            f.color.rgb = rgb(st.get("color", color))
            f.name = st.get("font", font)
            f.bold = st.get("bold", bold)
    return tb


def box(sl, x, y, w, h, fill=CARD, line=LINE, radius=True):
    shp = sl.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE, px(x), px(y), px(w), px(h))
    shp.fill.solid()
    shp.fill.fore_color.rgb = rgb(fill)
    shp.line.color.rgb = rgb(line)
    shp.line.width = Pt(1.5)
    if radius:
        shp.adjustments[0] = 0.06
    shp.shadow.inherit = False
    return shp


def card(sl, x, y, w, h, title, label, title_color=TEXT, title_size=38, label_size=24):
    box(sl, x, y, w, h)
    text(sl, x + 30, y + 24, w - 60, h - 40, [[(title, {"size": title_size, "color": title_color, "font": HEAD, "bold": True})],
                                              [(label, {"size": label_size, "color": BODY})]], spacing=4)


def eq(sl, x, y, w, h, key, rest):
    box(sl, x, y, w, h)
    text(sl, x + 24, y + 14, w - 48, h - 20, [[(key, {"size": 30, "color": GREEN, "font": HEAD, "bold": True})], rest], size=26, color=BODY)


def head(sl, eyebrow, title):
    text(sl, 128, 120, 1664, 34, [[(eyebrow, {"size": 24, "color": GREEN, "bold": True})]])
    text(sl, 128, 160, 1664, 90, [[(title, {"size": 72, "color": TEXT, "font": HEAD, "bold": True})]])


def table(sl, x, y, w, rows, widths, row_h=58, size=24, highlight=None):
    t = sl.shapes.add_table(len(rows), len(rows[0]), px(x), px(y), px(w), px(row_h * len(rows))).table
    for j, fr in enumerate(widths):
        t.columns[j].width = px(w * fr)
    for i, row in enumerate(rows):
        t.rows[i].height = px(row_h)
        for j, val in enumerate(row):
            c = t.cell(i, j)
            c.fill.solid()
            c.fill.fore_color.rgb = rgb(CALL_BG if i == highlight else (BG2 if i == 0 else CARD))
            c.margin_left = c.margin_right = px(14)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = c.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            r = p.add_run()
            r.text = str(val)
            f = r.font
            f.size = Pt(size / 2)
            f.name = SANS
            f.bold = i == 0 or j == 0
            f.color.rgb = rgb(MUTED if i == 0 else (GREEN if i == highlight else (TEXT if j == 0 else BODY)))
    return t


def pic(sl, name, x, y, w, h):
    sl.shapes.add_picture(str(image(name, w, h)), px(x), px(y), px(w), px(h))


# 1 · cover -------------------------------------------------------------
s = new_slide(sid="cover")
text(s, 128, 190, 1664, 34, [[("FECON 390 · CLASS PROJECT BY ALLEN WILK · NOVEMBER 2026", {"size": 24, "color": GREEN, "bold": True})]])
text(s, 128, 235, 1664, 280, [[("Will the world hit 2°C", {"size": 136, "color": TEXT, "font": HEAD, "bold": True})],
                              [("before 2050?", {"size": 136, "color": TEXT, "font": HEAD, "bold": True})]])
text(s, 128, 545, 1664, 50, ["Our class climate model and a probability density function, against the Kalshi prediction market"], size=32)
for i, (n, lab, c) in enumerate([("81%", "Our model, 72 versions of the class model", GREEN), ("67%", "Our model with IPCC-sized uncertainty", GREEN),
                                 ("70%", "Kalshi’s market price", TEXT)]):
    x = 128 + i * 564
    box(s, x, 625, 536, 220)
    text(s, x + 32, 648, 480, 180, [[(n, {"size": 112, "color": c, "font": HEAD, "bold": True})], [(lab, {"size": 26, "color": BODY})]])
text(s, 128, 880, 1664, 40, [[("Code, data and the Excel workbook: ", {}), (REPO, {"color": GREEN}),
                              (" · Independent class project, not affiliated with Kalshi", {})]], size=24, color=BODY)

# 2 · Kalshi --------------------------------------------------------------
s = new_slide(alt=True, sid="kalshi")
head(s, "THE MARKET", "How Kalshi gets its number")
pic(s, "kalshi/market_c.png", 128, 290, 950, 635)
text(s, 128, 940, 950, 40, ["kalshi.com, 18 Nov 2026. Our comparison uses that morning’s order book: 68¢ to sell, 72¢ to buy."], size=22, color=MUTED)
for i, (t, l) in enumerate([("A $1 contract", "Yes pays $1 if any year before 2050 reaches 2°C on at least 2 of 4 datasets: NASA, NOAA, Berkeley Earth, HadCRUT"),
                            ("Price = probability", "Buyers and sellers meet around 70¢, so the market says about a 70% chance"),
                            ("Fees blur it", "After fees and the spread, 70% really means 65–73%. And it’s small: $21,756 traded since June 2025")]):
    card(s, 1134, 290 + i * 215, 658, 195, t, l)

# 3 · engine --------------------------------------------------------------
s = new_slide(sid="engine")
head(s, "1 · HOW THE MODEL WORKS", "The engine: the climate model from class")
for i, (k, r) in enumerate([("1 · Emissions (Kaya)", "Population × GDP per person × energy per $ × CO₂ per energy, for 3 regions"),
                            ("2 · Carbon cycle", "5 boxes that hold CO₂ for different lifetimes (forever, 363, 74, 17, 2 years) → CO₂ in ppm"),
                            ("3 · Forcing", "F = 5.35 × ln(CO₂ ÷ 275) W/m²"),
                            ("4 · Temperature", "A two-box model (air and ocean) turns forcing into warming above 1850–1900")]):
    eq(s, 128, 290 + i * 150, 900, 135, k, r)
table(s, 1084, 290, 708, [["Year", "Emissions", "CO₂ (ppm)", "Warming"], ["2026", "12.0 GtC (44 GtCO₂)", "429", "1.34°C"],
                          ["2040", "16.2 GtC (59 GtCO₂)", "482", "1.77°C"], ["2049", "19.5 GtC (72 GtCO₂)", "526", "2.09°C"]],
      [0.16, 0.44, 0.2, 0.2], highlight=3)
text(s, 1084, 560, 708, 150, ["The HW5 settings, run in Python. It matches the HW5 workbook in every year, 1750–2100. CO₂ only: GtC is carbon; × 3.67 gives GtCO₂."], size=24, color=MUTED)

# 4 · futures -------------------------------------------------------------
s = new_slide(alt=True, sid="futures")
head(s, "2 · FROM ONE LINE TO THOUSANDS OF FUTURES", "Real-world noise and Kalshi’s exact rule")
for i, (k, r) in enumerate([("Start from today", "Anchor to observed 2006–2025 temperatures; begin from 2026’s data (1.52°C)"),
                            ("Add El Niño-style noise", "Each year keeps 53% of last year’s swing plus a new shock of about ±0.1°C"),
                            ("Vary the settings", "Climate sensitivity, response speed, emissions path, land use"),
                            ("Score it like Kalshi", "4 datasets, rounded to 0.01: Yes if the 2nd-highest ≥ 2.00°C")]):
    eq(s, 128, 290 + i * 150, 820, 135, k, r)
text(s, 1004, 290, 788, 50, [[("One simulated future", {"size": 40, "color": TEXT, "font": HEAD, "bold": True})]])
table(s, 1004, 350, 788, [["Year", "Trend", "Noise", "2nd-highest"], ["2027", "1.39", "+0.21", "1.63"], ["2035", "1.63", "+0.03", "1.69"],
                          ["2041", "1.82", "+0.04", "1.92"], ["2042", "1.86", "+0.20", "2.09 = Yes"]], [0.2, 0.22, 0.22, 0.36], highlight=4)
text(s, 1004, 660, 788, 40, ["This future pays Yes in 2042. Repeat 288,000 times."], size=24, color=MUTED)

# 5 · PDF ---------------------------------------------------------------------
s = new_slide(sid="numbers")
head(s, "3 · HOW I GOT MY NUMBERS", "A probability density function of all the futures")
for i, (k, r) in enumerate([("Record", "For each future, its hottest reading between 2027 and 2049"),
                            ("Plot", "The probability density function: where all the futures land"),
                            ("Read off the answer", "A future pays Yes when its hottest reading ≥ 2.00°C, so P(Yes) = area right of 2.00°C"),
                            ("Two versions", "72 versions of the class model: 81%. With IPCC-sized uncertainty: 67%")]):
    eq(s, 128, 290 + i * 155, 740, 140, k, r)
pic(s, "charts_kalshi/pdf.png", 924, 290, 868, 632)

# 6 · 81% step by step --------------------------------------------------------
s = new_slide(alt=True, sid="calc")
head(s, "3 · HOW I GOT MY NUMBERS", "How the 81% is calculated, step by step")
for i, (k, r) in enumerate([("1 · Make 72 versions", "3 sensitivities × 3 speeds × 4 emissions paths × land use on/off"),
                            ("2 · Run each version", "The class model gives one smooth temperature path, 2027–2049"),
                            ("3 · Simulate 4,000 futures per version", "Add El Niño-style noise; each future reaches 2°C or not"),
                            ("4 · Count per version", "P(version) = futures reaching 2°C ÷ 4,000"),
                            ("5 · Pool all 72", "Add up every version’s count and divide by all 288,000 futures")]):
    eq(s, 128, 285 + i * 122, 860, 110, k, r)
table(s, 1044, 290, 748, [["Example version", "Reach 2°C", "P"], ["Lowest: sensitivity 1.00, slow, falling", "380 of 4,000", "9.5%"],
                          ["Sensitivity 1.00, class speed, flat", "2,040 of 4,000", "51%"], ["Class settings, HW5 economy", "3,975 of 4,000", "99.4%"],
                          ["All 72 versions", "232,668 of 288,000", "80.8%"]], [0.46, 0.36, 0.18], row_h=70, highlight=4)
box(s, 1044, 680, 748, 170, fill=CALL_BG, line=CALL_LINE)
text(s, 1072, 700, 692, 140, [[("232,668 ÷ 288,000 = ", {}), ("80.8%", {"bold": True, "color": GREEN}),
                               (". The same as the average of the 72 percentages, because every version has 4,000 futures.", {})]], size=28, color=TEXT)

# 7 · where 81% and 67% come from ---------------------------------------------
s = new_slide(sid="sources")
head(s, "3 · HOW I GOT MY NUMBERS", "Where 81% and 67% come from")
box(s, 128, 290, 812, 620)
text(s, 160, 314, 750, 60, [[("81%", {"color": GREEN}), (" · 72 versions, equal weight", {})]], size=40, color=TEXT, font=HEAD, bold=True)
text(s, 160, 374, 750, 70, ["Sensitivity × speed × 4 emissions paths × land use on/off, 4,000 futures each. Each cell averages 8 versions:"], size=24)
table(s, 160, 455, 750, [["Sensitivity ↓ · speed →", "0.020", "0.0256", "0.032"], ["1.00", "28%", "62%", "84%"],
                         ["1.15 (class)", "69%", "93%", "99%"], ["1.30", "94%", "100%", "100%"]], [0.4, 0.2, 0.2, 0.2], highlight=2)
text(s, 160, 715, 750, 80, ["232,668 of 288,000 futures reach 2°C = 80.8%. Excel workbook in the repo."], size=24)
box(s, 980, 290, 812, 620)
text(s, 1012, 314, 750, 60, [[("67%", {"color": GREEN}), (" · IPCC-sized uncertainty", {})]], size=40, color=TEXT, font=HEAD, bold=True)
text(s, 1012, 384, 750, 380, ["• 2,751 combinations of sensitivity and speed",
                              "• Weighted by the IPCC’s range for climate sensitivity (2–5°C) and by fit to 1880–2020",
                              "• Fit softened until 2041–60 warming spans 0.67°C, as in the IPCC AR6 report",
                              "• Paired with real-data emissions: 100,000 futures",
                              "67.1% reach 2°C. Same middle as the 81%, wider spread."], size=24, spacing=8)

# 8 · compare -----------------------------------------------------------------
s = new_slide(alt=True, sid="compare")
head(s, "4 · HOW WE COMPARE WITH KALSHI", "Our numbers next to Kalshi’s")
pic(s, "charts_kalshi/compare.png", 128, 290, 1100, 538)
card(s, 1284, 290, 508, 250, "Same middle", "Every version puts the first 2°C year around 2044, and the IPCC agrees on about 2°C for 2041–2060")
card(s, 1284, 565, 508, 250, "Different width", "A narrow PDF puts more futures past 2°C (81%); IPCC-sized uncertainty gives 67%, inside Kalshi’s range")

# 9 · customize ---------------------------------------------------------------
s = new_slide(sid="custom")
head(s, "5 · CUSTOMIZE THE MODEL", "Change any assumption and the odds move")
table(s, 128, 290, 760, [["Factor", "You can choose", "Chance"], ["Climate certainty", "IPCC, history fit, wide, or set it yourself", "54–93%"],
                         ["Emissions path", "Today’s trend, fast growth, falling, flat, rising, doubling", "44–75%"],
                         ["Land-use emissions", "Leave out or add back", "67–73%"], ["Does 2049 count?", "Yes, or only up to 2048", "62–67%"],
                         ["El Niño carry-over", "On or off", "67%"]], [0.3, 0.48, 0.22], row_h=80)
text(s, 128, 785, 760, 120, ["Ranges change one factor at a time from the IPCC-calibrated 67%. Your choices give your own chance next to Kalshi’s, with a Yes, No or Pass call, in about 0.1 seconds."], size=24)
pic(s, "shots_dark/lab_tools_g.png", 944, 290, 848, 584)

# 10 · what you can do (1) ----------------------------------------------------
s = new_slide(alt=True, sid="action")
head(s, "WHAT YOU CAN DO WITH THE MODEL · 1 · HYPOTHETICAL", "Turn a forecast into Yes, No or Pass")
pic(s, "charts_kalshi/decision.png", 460, 285, 1000, 391)
for i, (t, l, c) in enumerate([("Trust our 81%? Buy Yes", "$100 buys 136 contracts: +$36 if 2°C happens, −$100 if not. Expected +$10", GREEN),
                               ("Trust the IPCC’s 67%? Pass", "The price is fair once fees are paid, so there’s no trade", MUTED),
                               ("Net zero by 2070? Buy No", "The chance drops to 44%. $100 buys 289 No: +$189 or −$100. Expected +$63", RED)]):
    card(s, 128 + i * 564, 715, 536, 190, t, l, title_color=c)

# 11 · what you can do (2) ----------------------------------------------------
s = new_slide(alt=True, sid="uses")
head(s, "WHAT YOU CAN DO WITH THE MODEL · 2", "Where else the model could be used")
for i, (t, l) in enumerate([("Check other markets", "The same machinery already prices Kalshi’s hottest-year, monthly-record and CO₂ markets"),
                            ("Hedge climate risk", "Insurers, utilities or farms could judge whether a climate contract is fairly priced"),
                            ("Teach and explain", "See how each input, from emissions to climate sensitivity, changes a real-world probability"),
                            ("Track it live", "Refresh with new data and prices; add El Niño forecasts, methane and aerosols")]):
    card(s, 128 + (i % 2) * 502, 290 + (i // 2) * 250, 478, 226, t, l)
text(s, 128, 800, 980, 90, [[("Try it: ", {"bold": True, "color": TEXT}), ("Tool Dashboard.html at ", {}), (REPO, {"color": GREEN}),
                             (". Download it and double-click; no install.", {})]], size=24)
pic(s, "shots_dark/lab_play_g.png", 1164, 290, 628, 486)
text(s, 1164, 790, 628, 70, ["Play the future: watch a bet win or lose, one simulated year at a time"], size=24)

prs.save(OUT)
print(OUT, f"{OUT.stat().st_size / 1024:.0f} KB, {len(prs.slides)} slides")
