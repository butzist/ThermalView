"""Live web viewer for the ThermalView adapter.

Serves a small single-page UI over HTTP that shows the latest 32x32 thermal
frame as a PNG and live min/max/mean/centre statistics.  Only the standard
library and Pillow (already a dependency of ``thermalview``) are required, so
no extra GUI toolkit has to be installed.
"""

from __future__ import annotations

import io
import json
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .device import ThermalCamera
from .frame import ThermalFrame
from .palette import palette_names
from .render import frame_to_image


class _LatestFrame:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: ThermalFrame | None = None
        self._error: str | None = None
        self._seq = 0

    def set(self, frame: ThermalFrame) -> None:
        with self._lock:
            self._frame = frame
            self._seq += 1

    def set_error(self, message: str) -> None:
        with self._lock:
            self._error = message

    def snapshot(self) -> tuple[ThermalFrame | None, int, str | None]:
        with self._lock:
            return self._frame, self._seq, self._error


class ThermalViewer:
    """Capture frames in a background thread and serve them over HTTP."""

    def __init__(
        self,
        camera: ThermalCamera,
        *,
        palette: str = "iron_red",
        size: int = 480,
        vmin: float | None = None,
        vmax: float | None = None,
        app_auto_range: bool = False,
    ) -> None:
        self.camera = camera
        self.palette = palette
        self.size = size
        self.vmin = vmin
        self.vmax = vmax
        self.app_auto_range = app_auto_range
        self.latest = _LatestFrame()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- capture loop ----------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self.camera.open()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        try:
            self.camera.close()
        except Exception:  # pragma: no cover - best effort
            pass

    def _capture_loop(self) -> None:
        while not self._stop.is_set():
            try:
                frame = self.camera.read_frame(timeout=self.camera.timeout)
                self.latest.set(frame)
            except Exception as exc:  # keep serving last frame
                self.latest.set_error(str(exc))
                time.sleep(0.2)

    # -- rendering -------------------------------------------------------

    def render_png(self) -> bytes:
        frame, _seq, err = self.latest.snapshot()
        if frame is None:
            # 1x1 placeholder
            img = None
        else:
            img = frame_to_image(
                frame,
                palette=self.palette,
                vmin=self.vmin,
                vmax=self.vmax,
                size=self.size,
                app_auto_range=self.app_auto_range,
            )
        if img is None:
            # tiny grey placeholder
            from PIL import Image

            img = Image.new("RGB", (self.size, self.size), (40, 40, 40))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def stats_json(self) -> str:
        frame, seq, err = self.latest.snapshot()
        if frame is None:
            return json.dumps({"ready": False, "seq": seq, "error": err})
        stats = frame.stats()
        return json.dumps(
            {
                "ready": True,
                "seq": seq,
                "error": err,
                "min_c": round(stats.min_celsius, 2),
                "max_c": round(stats.max_celsius, 2),
                "mean_c": round(stats.mean_celsius, 2),
                "center_c": round(stats.center_celsius, 2),
                "min_pos": list(stats.min_position),
                "max_pos": list(stats.max_position),
            }
        )


_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ThermalView live</title>
<style>
  body { font-family: system-ui, sans-serif; background:#111; color:#eee; margin:0; padding:16px; }
  .wrap { display:flex; gap:24px; align-items:flex-start; flex-wrap:wrap; }
  img { image-rendering: pixelated; border:1px solid #333; background:#000; }
  .panel { background:#1a1a1a; padding:16px; border-radius:8px; min-width:220px; }
  .stat { display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid #2a2a2a; }
  .stat:last-child { border-bottom:none; }
  .label { color:#aaa; }
  .value { font-variant-numeric: tabular-nums; }
  h1 { font-size:1.2rem; margin:0 0 12px; }
</style>
</head>
<body>
<h1>ThermalView live</h1>
<div class="wrap">
  <img id="frame" width="{size}" height="{size}" alt="thermal frame">
  <div class="panel">
    <div class="stat"><span class="label">min</span><span class="value" id="min">--</span></div>
    <div class="stat"><span class="label">max</span><span class="value" id="max">--</span></div>
    <div class="stat"><span class="label">mean</span><span class="value" id="mean">--</span></div>
    <div class="stat"><span class="label">centre</span><span class="value" id="center">--</span></div>
    <div class="stat"><span class="label">min@</span><span class="value" id="minpos">--</span></div>
    <div class="stat"><span class="label">max@</span><span class="value" id="maxpos">--</span></div>
    <div class="stat"><span class="label">frames</span><span class="value" id="seq">0</span></div>
  </div>
</div>
<script>
const img = document.getElementById('frame');
const fields = ['min','max','mean','center','minpos','maxpos','seq'];
function refresh() {
  img.src = '/frame.png?t=' + Date.now();
  fetch('/stats').then(r=>r.json()).then(d=>{
    if(!d.ready) return;
    document.getElementById('min').textContent = d.min_c.toFixed(1)+' C';
    document.getElementById('max').textContent = d.max_c.toFixed(1)+' C';
    document.getElementById('mean').textContent = d.mean_c.toFixed(1)+' C';
    document.getElementById('center').textContent = d.center_c.toFixed(1)+' C';
    document.getElementById('minpos').textContent = d.min_pos.join(',');
    document.getElementById('maxpos').textContent = d.max_pos.join(',');
    document.getElementById('seq').textContent = d.seq;
  }).catch(()=>{});
}
setInterval(refresh, 120);
refresh();
</script>
</body>
</html>
"""


def make_handler(viewer: ThermalViewer):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                body = _HTML.replace("{size}", str(viewer.size)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif parsed.path == "/frame.png":
                data = viewer.render_png()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
            elif parsed.path == "/stats":
                data = viewer.stats_json().encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):  # quiet
            return

    return Handler


def serve(
    viewer: ThermalViewer,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    viewer.start()
    httpd = ThreadingHTTPServer((host, port), make_handler(viewer))
    url = f"http://{host}:{port}/"
    print(f"ThermalView viewer: {url}", flush=True)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        viewer.stop()
