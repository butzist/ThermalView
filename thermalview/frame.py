"""Thermal frame decoding and statistics."""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Iterable

import numpy as np

from .protocol import FRAME_HEIGHT, FRAME_WIDTH, PAYLOAD_SIZE

#: Pixel samples are little-endian uint16 in tenths of a degree Celsius.
RAW_DTYPE = np.dtype("<u2")
#: ``temp_val_xishu`` in ``libhongwai.so``.
DEFAULT_SCALE = 10.0


@dataclasses.dataclass(frozen=True)
class FrameStats:
    """Summary values for one frame, in degrees Celsius."""

    min_celsius: float
    max_celsius: float
    mean_celsius: float
    center_celsius: float
    min_position: tuple[int, int]
    max_position: tuple[int, int]


@dataclasses.dataclass(frozen=True)
class ThermalFrame:
    """A 32x32 thermal frame.

    ``raw`` holds the uint16 sensor samples *after* optional axis flips.
    Divide by :attr:`scale` (10.0) to obtain degrees Celsius.
    """

    raw: np.ndarray
    scale: float = DEFAULT_SCALE
    timestamp: float = dataclasses.field(default_factory=time.time)

    def __post_init__(self) -> None:
        raw = np.asarray(self.raw)
        if raw.shape != (FRAME_HEIGHT, FRAME_WIDTH):
            raise ValueError(
                f"expected a {(FRAME_HEIGHT, FRAME_WIDTH)} array, got {raw.shape}"
            )
        if raw.dtype != np.uint16:
            raw = raw.astype(np.uint16)
        raw = raw.copy()
        raw.flags.writeable = False
        object.__setattr__(self, "raw", raw)
        if not self.scale:
            raise ValueError("scale must be non-zero")

    @property
    def celsius(self) -> np.ndarray:
        """Temperature array as float32 degrees Celsius."""

        return self.raw.astype(np.float32) / np.float32(self.scale)

    def stats(self) -> FrameStats:
        """Return honest min/max/mean/centre values.

        Unlike the Android app, this does not apply the native decoder's
        +1 degC hot-spot adjustment before computing the maximum.
        """

        values = self.celsius
        max_flat = int(np.argmax(values))
        min_flat = int(np.argmin(values))
        rows, cols = values.shape
        return FrameStats(
            min_celsius=float(values.min()),
            max_celsius=float(values.max()),
            mean_celsius=float(values.mean()),
            center_celsius=float(values[rows // 2, cols // 2]),
            min_position=(min_flat // cols, min_flat % cols),
            max_position=(max_flat // cols, max_flat % cols),
        )

    def rotated(self, *, x_flip: bool = False, y_flip: bool = False) -> ThermalFrame:
        """Return a copy with the same axis options the app exposes."""

        raw = self.raw
        if x_flip:
            raw = raw[:, ::-1]
        if y_flip:
            raw = raw[::-1, :]
        return ThermalFrame(np.ascontiguousarray(raw), self.scale, self.timestamp)


def decode_payload(
    payload: bytes,
    *,
    x_flip: bool = False,
    y_flip: bool = False,
    scale: float = DEFAULT_SCALE,
    timestamp: float | None = None,
) -> ThermalFrame:
    """Decode a :data:`~thermalview.protocol.PAYLOAD_SIZE` byte payload.

    The native ``getTempPicData`` reads little-endian uint16 pairs, stores
    them unchanged as float, and finally reports ``raw / 10.0``.
    """

    if len(payload) != PAYLOAD_SIZE:
        raise ValueError(f"expected {PAYLOAD_SIZE} bytes, got {len(payload)}")
    raw = np.frombuffer(payload, dtype=RAW_DTYPE).reshape(FRAME_HEIGHT, FRAME_WIDTH)
    if x_flip:
        raw = raw[:, ::-1]
    if y_flip:
        raw = raw[::-1, :]
    return ThermalFrame(
        np.ascontiguousarray(raw),
        scale=scale,
        timestamp=time.time() if timestamp is None else timestamp,
    )


def encode_payload(raw: np.ndarray) -> bytes:
    """Encode a 32x32 uint16 array as a wire payload (test/synthetic helper)."""

    array = np.asarray(raw)
    if array.shape != (FRAME_HEIGHT, FRAME_WIDTH):
        raise ValueError(f"expected {(FRAME_HEIGHT, FRAME_WIDTH)}, got {array.shape}")
    return array.astype(RAW_DTYPE, copy=False).tobytes(order="C")


def frames_from_bytes(
    data: bytes,
    *,
    x_flip: bool = False,
    y_flip: bool = False,
    scale: float = DEFAULT_SCALE,
) -> Iterable[ThermalFrame]:
    """Decode frames from a recorded serial stream or a bare payload."""

    from .protocol import FrameParser, FramePayload

    if len(data) == PAYLOAD_SIZE:
        yield decode_payload(data, x_flip=x_flip, y_flip=y_flip, scale=scale)
        return
    parser = FrameParser()
    events = parser.feed(data)
    frames = [e for e in events if isinstance(e, FramePayload)]
    if frames:
        for event in frames:
            yield decode_payload(
                event.data, x_flip=x_flip, y_flip=y_flip, scale=scale
            )
        return
    # Raw (headerless) stream: split into consecutive 2048-byte frames.
    if len(data) >= PAYLOAD_SIZE and len(data) % PAYLOAD_SIZE == 0:
        for offset in range(0, len(data), PAYLOAD_SIZE):
            yield decode_payload(
                data[offset : offset + PAYLOAD_SIZE],
                x_flip=x_flip,
                y_flip=y_flip,
                scale=scale,
            )
