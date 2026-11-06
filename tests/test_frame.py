import numpy as np

from thermalview.frame import (
    RAW_DTYPE,
    ThermalFrame,
    decode_payload,
    encode_payload,
    frames_from_bytes,
)
from thermalview.protocol import FRAME_MAGIC


def gradient() -> np.ndarray:
    return np.arange(1024, dtype=np.uint16).reshape(32, 32)


def test_temperature_is_raw_divided_by_ten():
    raw = np.full((32, 32), 250, dtype=np.uint16)
    frame = decode_payload(encode_payload(raw))

    assert np.allclose(frame.celsius, 25.0)
    stats = frame.stats()
    assert stats.min_celsius == 25.0
    assert stats.max_celsius == 25.0
    assert stats.center_celsius == 25.0


def test_stats_positions_and_values():
    raw = np.full((32, 32), 200, dtype=np.uint16)
    raw[3, 7] = 400
    raw[20, 2] = 50
    stats = decode_payload(encode_payload(raw)).stats()

    assert stats.max_position == (3, 7)
    assert stats.min_position == (20, 2)
    assert stats.max_celsius == 40.0
    assert stats.min_celsius == 5.0


def test_axis_flips_match_native_index_math():
    raw = gradient()
    plain = decode_payload(encode_payload(raw))
    x = plain.rotated(x_flip=True)
    y = plain.rotated(y_flip=True)
    both = plain.rotated(x_flip=True, y_flip=True)

    assert np.array_equal(x.raw, raw[:, ::-1])
    assert np.array_equal(y.raw, raw[::-1, :])
    assert np.array_equal(both.raw, raw[::-1, ::-1])


def test_decode_payload_applies_flips():
    raw = gradient()
    payload = encode_payload(raw)
    assert np.array_equal(decode_payload(payload, x_flip=True).raw, raw[:, ::-1])
    assert np.array_equal(decode_payload(payload, y_flip=True).raw, raw[::-1, :])


def test_encode_payload_dtype_and_roundtrip():
    raw = gradient()
    payload = encode_payload(raw)
    decoded = np.frombuffer(payload, dtype=RAW_DTYPE).reshape(32, 32)
    assert np.array_equal(decoded, raw)


def test_frames_from_bytes_accepts_stream_and_bare_payload():
    raw = gradient()
    payload = encode_payload(raw)
    stream = FRAME_MAGIC + b"\x00\x00" + payload

    streamed = list(frames_from_bytes(stream))
    bare = list(frames_from_bytes(payload))

    assert len(streamed) == 1
    assert len(bare) == 1
    assert np.array_equal(streamed[0].raw, raw)
    assert np.array_equal(bare[0].raw, raw)


def test_frame_is_immutable():
    frame = decode_payload(encode_payload(np.zeros((32, 32), dtype=np.uint16)))
    try:
        frame.raw[0, 0] = 1
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("raw array should be read-only")
