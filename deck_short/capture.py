"""Screenshots of the Decision Lab for the short deck (headless Chrome, no server needed).

    python deck_short/capture.py      # -> deck_short/shots/*.png
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parent / "Tool Dashboard.html"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
TMP = HERE / "_tmp"

# each state: JS run after load; it drives the page, then hides everything but the part to show
STATES = {
    "lab_start": "document.querySelector('footer').style.display='none';",
    "lab_result": """
      document.querySelector('#goBuild').click(); document.querySelector('#useRec').click();
      setTimeout(() => { document.querySelector('#pitch').style.display='none';
        document.querySelectorAll('#result > .panel').forEach((p,i)=>{ if(i>0) p.style.display='none'; });
        document.querySelectorAll('#result .note').forEach(n => n.innerHTML = n.innerHTML.replace(/ in \d+ ms/, ''));
        document.querySelector('footer').style.display='none'; window.scrollTo(0,0); }, 4000);""",
    "lab_play": """
      document.querySelector('#goRec').click();
      setTimeout(() => { document.querySelector('[data-a=hundred]').click(); }, 2500);
      setTimeout(() => { document.querySelector('#recPlay [data-a=one]').click(); }, 3000);
      setTimeout(() => { document.querySelector('#pitch').style.display='none';
        [...document.querySelectorAll('#rec > *')].forEach(e => { if (e.id !== 'recPlay') e.style.display='none'; });
        document.querySelector('footer').style.display='none'; window.scrollTo(0,0); }, 6500);""",
    "lab_tools": """
      document.querySelector('#goBuild').click(); document.querySelector('#useRec').click();
      setTimeout(() => { document.querySelector('#pitch').style.display='none';
        const ps = [...document.querySelectorAll('#result > .panel')];
        ps.forEach((p,i)=>{ if(i!==2) p.style.display='none'; }); document.querySelector('#result > .eyebrow').style.display='none';
        document.querySelector('#result > h2').style.display='none'; document.querySelector('#result > p.note').style.display='none';
        window.scrollTo(0,0); }, 9000);""",
}


SIZES = {"lab_start": (1440, 760), "lab_result": (1440, 700), "lab_play": (1440, 900), "lab_tools": (1440, 830)}


THEME = sys.argv[1] if len(sys.argv) > 1 else "light"     # "light" -> shots/, "dark" -> shots_dark/
SHOTS = HERE / ("shots_dark" if THEME == "dark" else "shots")


def shoot(name, js, size=(1440, 1000)):
    TMP.mkdir(exist_ok=True)
    SHOTS.mkdir(exist_ok=True)
    page = LAB.read_text(encoding="utf-8")
    if js:
        # chosen theme, and a fixed random seed so "play the future" shows the same future every capture
        js = (f"document.documentElement.dataset.theme='{THEME}';"
              "let __s=20260; Math.random=()=>{__s=(__s*16807)%2147483647; return (__s-1)/2147483646;};" + js)
        page = page.replace("</body>", f"<script>window.addEventListener('load',()=>setTimeout(()=>{{{js}}},800));</script></body>")
    src = TMP / f"{name}.html"
    src.write_text(page, encoding="utf-8")
    out = SHOTS / f"{name}.png"
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={size[0]},{size[1]}",
                    "--virtual-time-budget=30000", "--force-device-scale-factor=1", f"--screenshot={out}", src.as_uri()],
                   check=True, capture_output=True, timeout=120)
    print(name, out.stat().st_size)


if __name__ == "__main__":
    for n, js in STATES.items():
        shoot(n, js, SIZES[n])
