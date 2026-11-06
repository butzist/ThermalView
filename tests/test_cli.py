import numpy as np

from thermalview.cli import main
from thermalview.frame import encode_payload
from thermalview.protocol import FRAME_MAGIC, PAYLOAD_SIZE


def make_stream(count: int = 2) -> bytes:
    out = b""
    for index in range(count):
        raw = np.full((32, 32), 200 + index, dtype=np.uint16)
        out += FRAME_MAGIC + b"\x00\x00" + encode_payload(raw)
    return out


def test_decode_writes_image_and_json(tmp_path, capsys):
    capture = tmp_path / "capture.bin"
    capture.write_bytes(make_stream())
    png = tmp_path / "out.png"

    assert main(["decode", str(capture), "--png", str(png), "--json"]) == 0

    assert png.exists()
    output = capsys.readouterr().out
    assert '"max_c": 20.0' in output


def test_decode_index_selects_frame(tmp_path, capsys):
    capture = tmp_path / "capture.bin"
    capture.write_bytes(make_stream(3))

    assert main(["decode", str(capture), "--index", "2", "--json"]) == 0
    assert '"max_c": 20.2' in capsys.readouterr().out


def test_decode_accepts_bare_payload(tmp_path):
    payload = tmp_path / "frame.bin"
    raw = np.full((32, 32), 250, dtype=np.uint16)
    payload.write_bytes(encode_payload(raw))
    assert payload.stat().st_size == PAYLOAD_SIZE

    assert main(["decode", str(payload), "--json"]) == 0


def test_decode_error_when_no_frames(tmp_path, capsys):
    bogus = tmp_path / "bogus.bin"
    bogus.write_bytes(b"not a frame")
    assert main(["decode", str(bogus)]) == 1
    assert "no frames" in capsys.readouterr().err


def test_version_exits_cleanly(capsys):
    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0
    else:  # pragma: no cover
        raise AssertionError("--version should raise SystemExit")
