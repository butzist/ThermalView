import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import numpy as np

from thermalview.frame import decode_payload, encode_payload
from thermalview.viewer import make_handler


def make_viewer() -> SimpleNamespace:
    raw = np.full((32, 32), 250, dtype=np.uint16)
    frame = decode_payload(encode_payload(raw))
    return SimpleNamespace(
        size=64,
        render_png=lambda: b"\x89PNG fake",
        stats_json=lambda: json.dumps({"ready": True, "min_c": 25.0}),
        frame=frame,
    )


def make_stub_handler(writer, viewer=None):
    handler_class = make_handler(viewer or make_viewer())

    class Stub(handler_class):
        def __init__(self):
            self.wfile = writer
            self.close_connection = False
            self.status = None
            self.headers = {}

        def send_response(self, code, message=None):
            self.status = code

        def send_header(self, key, value):
            self.headers[key] = value

        def end_headers(self):
            self.headers_sent = True

    return Stub()


class FailingWriter:
    def __init__(self, exc):
        self.exc = exc

    def write(self, data):
        raise self.exc


class RecordingWriter:
    def __init__(self):
        self.written = b""

    def write(self, data):
        self.written += data


def test_send_ignores_broken_pipe():
    handler = make_stub_handler(FailingWriter(BrokenPipeError(32, "Broken pipe")))

    assert handler._send(b"payload", "application/octet-stream") is False
    assert handler.close_connection is True


def test_send_ignores_connection_reset():
    handler = make_stub_handler(FailingWriter(ConnectionResetError(104, "reset")))

    assert handler._send(b"payload", "application/octet-stream") is False
    assert handler.close_connection is True


def test_send_writes_complete_response():
    writer = RecordingWriter()
    handler = make_stub_handler(writer)

    assert handler._send(b"hello", "text/plain", cache_control="no-store") is True
    assert writer.written == b"hello"
    assert handler.status == 200
    assert handler.headers["Content-Length"] == "5"
    assert handler.headers["Cache-Control"] == "no-store"
    assert handler.close_connection is False


def test_server_serves_frames_and_stats():
    viewer = make_viewer()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(viewer))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/") as response:
            assert response.status == 200
            assert b"ThermalView live" in response.read()

        with urllib.request.urlopen(base + "/frame.png") as response:
            assert response.headers["Content-Type"] == "image/png"
            assert response.read() == b"\x89PNG fake"

        with urllib.request.urlopen(base + "/stats") as response:
            assert json.loads(response.read())["min_c"] == 25.0

        try:
            urllib.request.urlopen(base + "/missing")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
        else:  # pragma: no cover
            raise AssertionError("missing path should return 404")
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)
