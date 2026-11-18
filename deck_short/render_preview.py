"""Render each slide of the short deck to a PNG for a visual check: python deck_short/render_preview.py <deck project dir>"""
import json, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJ = Path(sys.argv[1])
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BLOBS = {"480dce9cdda58e29396d75ecdca2ce4b": "charts/pdf.png", "112750421342a035393670d6ab92ba81": "charts/orderbook.png",
         "36196194989309f7c8f1533d7179e882": "charts/compare.png", "44502c9df1c71a89f5cd46c71a6f191a": "charts/decision.png",
         "b6b2b9fa179c49c423bb8bc84c55c8a2": "shots/dashboard_c.png", "de3df696365001977d60327ec94dbfe6": "shots/lab_start_c.png",
         "e7123260bc35e899874ec3c907dea0cd": "shots/lab_result_c.png", "33e4d9ee2347a32a762f31a7549c6a9b": "shots/lab_play_c.png",
         "3f50d9995725b02def8d89cde7103ce7": "shots/lab_tools_c.png", "2311154b787548ddbcc8f177155ab985": "shots/lab_play_c.png"}
css = (PROJ / "deck.css").read_text(encoding="utf-8")
order = json.loads((PROJ / "deck.json").read_text(encoding="utf-8"))["order"]
out = HERE / "preview"; out.mkdir(exist_ok=True)
for i, sid in enumerate(order, 1):
    s = (PROJ / "slides" / f"{sid}.html").read_text(encoding="utf-8")
    s = re.sub(r"<aside>.*?</aside>", "", s, flags=re.S)
    s = re.sub(r"/_blob/([0-9a-f]{32})", lambda m: (HERE / BLOBS[m.group(1)]).as_uri(), s)
    page = ("<!doctype html><html><head><meta charset='utf-8'><link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300..700&family=Inter:wght@400;600;700&display=swap'>"
            f"<style>{css} *{{margin:0;box-sizing:content-box}} body{{margin:0;counter-reset:page {i - 1}}} section{{width:1664px;height:792px;position:relative;overflow:hidden}} .card,.cstat,.fig,.shot,.eq{{animation:none}}</style></head><body>{s}</body></html>")
    src = out / f"{i:02d}_{sid}.html"; src.write_text(page, encoding="utf-8")
    png = out / f"{i:02d}_{sid}.png"
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1920,1080", "--virtual-time-budget=5000",
                    "--allow-file-access-from-files", f"--screenshot={png}", src.as_uri()], check=True, capture_output=True, timeout=90)
    src.unlink()
    print(png.name)
