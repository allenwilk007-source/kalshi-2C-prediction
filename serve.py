"""Local dashboard: run the whole pipeline and see every result in the browser.

    python serve.py              # opens http://127.0.0.1:8000 ; runs the pipeline first if results are missing
    python serve.py --run        # always refresh Kalshi data and re-run everything on start
    python serve.py --no-browser --port 8050

Uses only Python's standard library web server (no installs). Listens on 127.0.0.1 only, so it is
reachable from this computer and nowhere else. The "Re-run" button on the page does the same as --run.

Pipeline (each step is a separate `python <script>` run, in order):
  market.py (fresh public Kalshi + Treasury snapshot) -> validate.py -> phase2.py -> phase3.py
  -> phase4.py -> phase5.py -> phase6.py -> phase7.py -> phase9.py
  (Phase 8, the what-if model, runs in the browser from results/slider_context.json.)
"""
from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

HERE = Path(__file__).resolve().parent
SITE = HERE / "site"
FIG = HERE / "figures"
RES = HERE / "results"
PIPELINE_FILE = RES / "pipeline.json"

STEPS = [
    ("market.py", "Fetch live Kalshi order book, trades and Treasury yields"),
    ("validate.py", "Check the Python model against the HW5 spreadsheet"),
    ("phase2.py", "Phase 2: observations, calibration, noise, 2-of-4 rule"),
    ("phase3.py", "Phase 3: Monte Carlo over emissions and climate response"),
    ("phase4.py", "Phase 4: what probability the price implies"),
    ("phase5.py", "Phase 5: 2026 nowcast and climate-damage hedge"),
    ("phase6.py", "Phase 6: social cost of carbon from the class model"),
    ("phase7.py", "Phase 7: price every live Kalshi climate market"),
    ("phase9.py", "Phase 9: market history and news test"),
    ("phase10.py", "Phase 10: temperature distributions across model versions"),
    ("phase11.py", "Phase 11: hypothetical trade idea (class project)"),
]
RESULT_FILES = ("phase2", "phase3", "phase4", "phase5", "phase6", "phase7", "phase9", "phase10", "phase11")


class Pipeline:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = json.loads(PIPELINE_FILE.read_text()) if PIPELINE_FILE.exists() else {
            "running": False, "steps": [], "started": None, "finished": None, "ok": None}
        self.state["running"] = False

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.state))

    def start(self) -> bool:
        with self.lock:
            if self.state["running"]:
                return False
            self.state = {"running": True, "ok": None, "finished": None,
                          "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                          "steps": [{"script": s, "label": l, "status": "pending", "seconds": None,
                                     "log": ""} for s, l in STEPS]}
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def _run(self):
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "MPLBACKEND": "Agg"}
        ok = True
        for i, (script, _) in enumerate(STEPS):
            with self.lock:
                self.state["steps"][i]["status"] = "running"
            t0 = time.time()
            proc = subprocess.Popen([sys.executable, script], cwd=HERE, env=env, text=True,
                                    encoding="utf-8", errors="replace",
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            for line in proc.stdout:
                with self.lock:
                    log = self.state["steps"][i]["log"] + line
                    self.state["steps"][i]["log"] = log[-20000:]
            proc.wait()
            with self.lock:
                st = self.state["steps"][i]
                st["seconds"] = round(time.time() - t0, 1)
                st["status"] = "done" if proc.returncode == 0 else "failed"
                if proc.returncode != 0:
                    ok = False
            if not ok:
                break
        with self.lock:
            self.state.update(running=False, ok=ok,
                              finished=datetime.now(timezone.utc).isoformat(timespec="seconds"))
            for st in self.state["steps"]:
                if st["status"] == "pending":
                    st["status"] = "skipped"
            PIPELINE_FILE.write_text(json.dumps(self.state, indent=1))


PIPE = Pipeline()


def model_summary():
    """Deterministic HW5 scenarios from the Python port (fast, no randomness)."""
    try:
        from model import HW5_SCENARIOS, Inputs, Params, run
        inp = Inputs.load()
        rows = []
        for name, p in HW5_SCENARIOS.items():
            r = run(p, inp)
            fy = r.first_year_at_or_above(2.0)
            rows.append({"sheet": name, "t2050": float(r.at(2050)), "t2100": float(r.at(2100)),
                         "ppm2100": float(r.at(2100, "ppm")),
                         "first_2c": None if fy != fy else int(fy)})
        return {"scenarios": rows, "ecs": float(Params().ecs())}
    except Exception as e:                      # model inputs not extracted yet
        return {"error": str(e)}


def results_payload():
    out = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "pipeline": PIPE.snapshot(), "model": model_summary(),
           "figures": sorted(p.name for p in FIG.glob("*.png")) if FIG.exists() else []}
    for name in RESULT_FILES:
        f = RES / f"{name}.json"
        out[name] = json.loads(f.read_text()) if f.exists() else None
        out[f"{name}_mtime"] = datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).isoformat(
            timespec="seconds") if f.exists() else None
    return out


def _finite(o):
    if isinstance(o, float):
        return o if o == o and o not in (float("inf"), float("-inf")) else None
    if isinstance(o, dict):
        return {k: _finite(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_finite(v) for v in o]
    return o


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):         # keep the console quiet
        pass

    def _send(self, code, body: bytes, ctype: str, cache=False):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=60" if cache else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        # Python writes NaN/Infinity into JSON; browsers reject them, so send null instead.
        self._send(code, json.dumps(_finite(obj), default=float, allow_nan=False).encode(), "application/json")

    def _file(self, base: Path, rel: str):
        path = (base / unquote(rel)).resolve()
        if base.resolve() not in path.parents or not path.is_file():
            return self._send(404, b"not found", "text/plain")
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._send(200, path.read_bytes(), ctype)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._file(SITE, "index.html")
        if path == "/api/results":
            return self._json(results_payload())
        if path == "/api/status":
            return self._json(PIPE.snapshot())
        if path == "/api/model-inputs":                 # class-model inputs for the in-browser model
            return self._file(HERE / "data", "hw5_inputs.json")
        if path == "/api/slider-context":               # nowcast, noise, offsets, Python reference values
            return self._file(RES, "slider_context.json")
        if path.startswith("/figures/"):
            return self._file(FIG, path[len("/figures/"):])
        if path.startswith("/site/"):
            return self._file(SITE, path[len("/site/"):])
        return self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if urlparse(self.path).path == "/api/run":
            started = PIPE.start()
            return self._json({"started": started, "running": True})
        return self._send(404, b"not found", "text/plain")


def main():
    args = sys.argv[1:]
    port = int(args[args.index("--port") + 1]) if "--port" in args else 8000
    server = None
    for p in range(port, port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), Handler)
            port = p
            break
        except OSError:
            continue
    if server is None:
        sys.exit("no free port found")
    missing = [n for n in RESULT_FILES if not (RES / f"{n}.json").exists()]
    if "--run" in args or missing:
        PIPE.start()
        print("running the pipeline in the background" + (f" (missing: {', '.join(missing)})" if missing else ""))
    url = f"http://127.0.0.1:{port}"
    print(f"dashboard at {url}  (Ctrl+C to stop)")
    if "--no-browser" not in args:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
