"""Compile the speaker script from the deck's slide notes: python deck/build_script.py -> deck/speaker_script.md"""
import html, json, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
WPM = 140
PARTS = [  # (first slide id, heading, one-line purpose)
    ("cover", "Introduction", "Set up the question, why it matters and the plan."),
    ("part1", "Part 1 · How Kalshi gets its number", "Explain the contract, the order book and what the 70% really means."),
    ("part2", "Part 2 · How we get our number", "Go from the class model to a probability density, and compare it with Kalshi and the IPCC."),
    ("part3", "Part 3 · What we could hypothetically do", "Turn the numbers into Yes / No / Pass, test strategies, and show what changes if you believe X."),
    ("takeaways", "Wrap-up", "What we learned, the limits, and the bonus SCC slide."),
]


def text(s):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def slide_info(sid):
    src = (HERE / "slides" / f"{sid}.html").read_text(encoding="utf-8")
    notes = src.split("<aside>", 1)[1].split("</aside>", 1)[0].strip() if "<aside>" in src else ""
    m = (re.search(r"<h[12][^>]*>(.*?)</h[12]>", src, re.S) or re.search(r'class="statement-line"[^>]*>(.*?)</p>', src, re.S))
    return text(m.group(1)) if m else sid, html.unescape(notes)


def mmss(sec):
    return f"{int(sec // 60)}:{int(sec % 60):02d}"


order = json.loads((HERE / "deck.json").read_text(encoding="utf-8"))["order"]
starts = {p[0]: p for p in PARTS}
blocks, cur, total = [], None, 0.0
for n, sid in enumerate(order, 1):
    if sid in starts:
        cur = {"head": starts[sid], "slides": [], "sec": 0.0}
        blocks.append(cur)
    title, notes = slide_info(sid)
    sec = len(notes.split()) / WPM * 60
    cur["slides"].append((n, sid, title, notes, sec))
    cur["sec"] += sec
    total += sec

out = ["# Speaker script: Will the world hit 2°C before 2050?", "",
       f"Carbon Trading class project. {len(order)} slides, about {round(total / 60)} minutes at {WPM} words a minute. "
       "The same text is in each slide's speaker notes. Hypothetical analysis; no trades were placed.", "",
       "| Part | Slides | Time |", "|---|---|---|"]
for b in blocks:
    ns = [s[0] for s in b["slides"]]
    out.append(f"| {b['head'][1]} | {ns[0]}–{ns[-1]} | {mmss(b['sec'])} |")
out += [f"| **Total** | 1–{len(order)} | **{mmss(total)}** |", ""]
for b in blocks:
    out += ["---", "", f"## {b['head'][1]}", "", f"*Goal: {b['head'][2]} About {mmss(b['sec'])}.*", ""]
    for n, sid, title, notes, sec in b["slides"]:
        out += [f"### Slide {n} · {title}", f"*~{mmss(sec)}*", ""]
        out += [p.strip() for p in notes.split("\n\n") for p in (p, "")]
(HERE / "speaker_script.md").write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
print(f"wrote speaker_script.md: {len(order)} slides, {mmss(total)}")
for b in blocks:
    print(f"  {b['head'][1]}: {len(b['slides'])} slides, {mmss(b['sec'])}")
