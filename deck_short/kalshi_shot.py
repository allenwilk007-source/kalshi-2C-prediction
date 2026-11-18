"""Screenshot Kalshi's public KXWARMING-50 market page for the deck (headless Chrome via the DevTools protocol).

    python deck_short/kalshi_shot.py   -> deck_short/kalshi/market.png

Opens the public page, closes the sign-up pop-up (same as clicking its X; nothing is signed or accepted),
and saves a 1440x1000 screenshot. Standard library only.
"""
import base64
import json
import os
import socket
import struct
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
URL = "https://kalshi.com/markets/kxwarming/global-warming/kxwarming-50"
PORT = 9333
OUT = Path(__file__).resolve().parent / "kalshi" / "market.png"


class WS:
    """Minimal websocket client (text frames, client masking) for the local DevTools endpoint."""

    def __init__(self, url):
        host_port, path = url.split("://", 1)[1].split("/", 1)
        host, port = host_port.split(":")
        self.s = socket.create_connection((host, int(port)), timeout=60)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET /{path} HTTP/1.1\r\nHost: {host_port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.s.recv(4096)
        self.rest = buf.split(b"\r\n\r\n", 1)[1]
        self.n = 0

    def _recv_exact(self, k):
        while len(self.rest) < k:
            self.rest += self.s.recv(1 << 20)
        out, self.rest = self.rest[:k], self.rest[k:]
        return out

    def send(self, obj):
        data = json.dumps(obj).encode()
        mask = os.urandom(4)
        hdr = bytes([0x81])
        n = len(data)
        hdr += bytes([0x80 | n]) if n < 126 else (bytes([0x80 | 126]) + struct.pack(">H", n) if n < 65536 else bytes([0x80 | 127]) + struct.pack(">Q", n))
        self.s.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def recv(self):
        msg = b""
        while True:
            b0, b1 = self._recv_exact(2)
            n = b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._recv_exact(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._recv_exact(8))[0]
            msg += self._recv_exact(n)
            if b0 & 0x80:
                return json.loads(msg)

    def call(self, method, **params):
        self.n += 1
        self.send({"id": self.n, "method": method, "params": params})
        while True:
            m = self.recv()
            if m.get("id") == self.n:
                return m.get("result", m)


def main():
    prof = tempfile.mkdtemp(prefix="kshot_")
    proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--remote-debugging-port={PORT}",
                             f"--user-data-dir={prof}", "--window-size=1440,1000", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=2).read())
                break
            except OSError:
                time.sleep(0.2)
        page = next(t for t in tabs if t["type"] == "page")
        ws = WS(page["webSocketDebuggerUrl"])
        ws.call("Emulation.setDeviceMetricsOverride", width=1440, height=1000, deviceScaleFactor=1, mobile=False)
        ws.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark"}])
        ws.call("Page.enable")
        ws.call("Page.navigate", url=URL)
        time.sleep(9)
        # close the sign-up pop-up the way its X button does
        r = ws.call("Runtime.evaluate", returnByValue=True, expression="""(() => {
            const d = [...document.querySelectorAll('[role=dialog], div')].find(e => /Create your account/.test(e.textContent || '') && e.querySelector('button'));
            if (!d) return 'no dialog';
            const close = [...d.querySelectorAll('button')].find(b => /close/i.test(b.getAttribute('aria-label') || '') || (!b.textContent.trim() && b.querySelector('svg')));
            if (close) { close.click(); return 'clicked close'; }
            return 'no close button';
        })()""")
        print("pop-up:", r.get("result", {}).get("value"))
        time.sleep(2.5)
        shot = ws.call("Page.captureScreenshot", format="png")
        OUT.parent.mkdir(exist_ok=True)
        OUT.write_bytes(base64.b64decode(shot["data"]))
        print(OUT, OUT.stat().st_size)
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
