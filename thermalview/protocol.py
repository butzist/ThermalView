"""Wire protocol for the ThermalView USB thermal adapter.

Reconstructed from ``com.ruiqi.hongwai.TempData`` (Java) and
``Java_com_ruiqi_hongwai_JniPicData_*`` / ``getTempPicData`` in
``lib/arm64-v8a/libhongwai.so``.

The adapter is a USB-serial bridge (CH340-class, 115200 8N1).  Command frames
are six bytes plus an optional payload::

    00 80 <cmd> <00> <len_lo> <len_hi> [payload ...]

Incoming data is a byte stream.  A frame is announced by a six-byte header
whose first two little-endian words are ``0x8000`` and ``1``::

    00 80 01 00 ?? ??

followed by exactly :data:`PAYLOAD_SIZE` bytes of pixel data.  Status packets
start with the little-endian word ``0x9000``; subtype ``4``/``5`` corresponds to
start/stop acknowledgement.

Because a real pixel value of ``0x8000`` would mean 3276.8 degC, the sync words
cannot collide with plausible pixel data, so the parser can safely scan for
them instead of depending on USB/tty read boundaries.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

#: Little-endian sync word introducing a pixel frame (``00 80``).
SYNC_FRAME = 0x8000
#: Little-endian sync word introducing a status packet (``00 90``).
SYNC_STATUS = 0x9000

#: Frame geometry reported by the native decoder.
FRAME_WIDTH = 32
FRAME_HEIGHT = 32
PIXEL_COUNT = FRAME_WIDTH * FRAME_HEIGHT
#: 1024 uint16 little-endian samples.
PAYLOAD_SIZE = PIXEL_COUNT * 2

#: Command to set the emissivity (one payload byte, ``round(e * 100)``).
CMD_SET_EMISSIVITY = 0x03
#: Command to start streaming.  The Android app never sends it; the device
#: appears to stream as soon as the port is opened.
CMD_START = 0x04
#: Command to stop streaming.
CMD_STOP = 0x05

#: Full four-byte prefix of a pixel frame header.
FRAME_MAGIC = b"\x00\x80\x01\x00"
#: Two-byte prefix of a status packet.
STATUS_MAGIC = b"\x00\x90"

_HEADER_SIZE = 6


def command(cmd: int, payload: bytes = b"") -> bytes:
    """Build a command frame.

    >>> command(CMD_START).hex()
    '008004000000'
    >>> command(CMD_SET_EMISSIVITY, b'\\x62').hex()
    '00800300010062'
    """

    if not 0 <= cmd <= 0xFFFF:
        raise ValueError(f"command out of range: {cmd!r}")
    payload = bytes(payload)
    if len(payload) > 0xFFFF:
        raise ValueError("payload too large")
    return struct.pack("<HHH", SYNC_FRAME, cmd, len(payload)) + payload


def start_command() -> bytes:
    """Return the start-stream command (not used by the Android app)."""

    return command(CMD_START)


def stop_command() -> bytes:
    """Return the stop-stream command."""

    return command(CMD_STOP)


def emissivity_command(value: float) -> bytes:
    """Return a set-emissivity command.

    The Android UI restricts the value to ``0.10 .. 0.98`` and stores it as
    ``(byte)(value * 100.0)``.
    """

    if not 0.0 <= value <= 1.0:
        raise ValueError(f"emissivity must be within 0..1, got {value!r}")
    return command(CMD_SET_EMISSIVITY, bytes([int(round(value * 100.0))]))


@dataclass(frozen=True)
class StatusEvent:
    """A ``0x9000`` status/ack packet."""

    subtype: int
    raw: bytes


@dataclass(frozen=True)
class FramePayload:
    """A complete :data:`PAYLOAD_SIZE` byte pixel payload."""

    data: bytes

    def __post_init__(self) -> None:
        if len(self.data) != PAYLOAD_SIZE:
            raise ValueError(f"expected {PAYLOAD_SIZE} bytes, got {len(self.data)}")


class FrameParser:
    """Incremental parser turning a serial byte stream into frames.

    Feed arbitrary chunks (any tty read size) and collect
    :class:`FramePayload` / :class:`StatusEvent` objects.  Partial frames are
    buffered until complete, and a new sync word aborts a truncated frame.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._payload = bytearray()
        self._in_frame = False

    @property
    def buffered_bytes(self) -> int:
        """Number of bytes currently buffered (diagnostics)."""

        return len(self._buffer)

    @property
    def in_frame(self) -> bool:
        """Whether a frame header was seen and its payload is incomplete."""

        return self._in_frame

    def reset(self) -> None:
        """Drop buffered data, e.g. after reopening the port."""

        self._buffer.clear()
        self._payload.clear()
        self._in_frame = False

    def feed(self, chunk: bytes) -> list[FramePayload | StatusEvent]:
        """Consume ``chunk`` and return every event completed by it.

        Payload bytes are consumed strictly by count and are never scanned for
        sync words: a two-byte value such as ``00 90`` occurs naturally inside
        a row of tenth-degree samples, so only frame/status boundaries are
        searched.
        """

        self._buffer.extend(chunk)
        events: list[FramePayload | StatusEvent] = []

        while True:
            if self._in_frame:
                need = PAYLOAD_SIZE - len(self._payload)
                window = bytes(self._buffer[:need])
                # Only a whole frame header can legitimately interrupt a
                # frame; a two-byte status word is not scanned for here because
                # ``00 90`` can occur across two adjacent pixel samples.
                restart_at = window.find(FRAME_MAGIC)
                take = need if restart_at < 0 else restart_at
                take = min(take, len(self._buffer))
                self._payload.extend(self._buffer[:take])
                del self._buffer[:take]
                if len(self._payload) == PAYLOAD_SIZE:
                    events.append(FramePayload(bytes(self._payload)))
                    self._payload.clear()
                    self._in_frame = False
                    continue
                if restart_at >= 0:
                    # The frame was truncated: drop it and resynchronise on
                    # the header we just found.
                    self._payload.clear()
                    self._in_frame = False
                    continue
                break

            # Between frames: look for a status packet or the next header.
            frame_at = self._buffer.find(FRAME_MAGIC)
            status_at = self._buffer.find(STATUS_MAGIC)

            if status_at >= 0 and (frame_at < 0 or status_at < frame_at):
                if len(self._buffer) < status_at + 4:
                    del self._buffer[:status_at]
                    break
                subtype = struct.unpack_from("<H", self._buffer, status_at + 2)[0]
                events.append(
                    StatusEvent(subtype, bytes(self._buffer[status_at : status_at + 4]))
                )
                # The status packet length is unknown; drop its marker and let
                # the next scan resynchronise on the following frame header.
                del self._buffer[: status_at + 4]
                continue

            if frame_at < 0:
                self._keep_partial_magic()
                break

            if len(self._buffer) < frame_at + _HEADER_SIZE:
                del self._buffer[:frame_at]
                break

            del self._buffer[: frame_at + _HEADER_SIZE]
            self._payload.clear()
            self._in_frame = True

        return events

    def _keep_partial_magic(self) -> None:
        """Drop bytes that cannot be the start of a future sync word."""

        buffer = self._buffer
        keep = 0
        for magic in (FRAME_MAGIC, STATUS_MAGIC):
            for length in range(min(len(buffer), len(magic) - 1), 0, -1):
                if buffer.endswith(magic[:length]):
                    keep = max(keep, length)
                    break
        if len(buffer) > keep:
            del buffer[: len(buffer) - keep]


def iter_payloads(data: bytes) -> list[bytes]:
    """Decode every pixel payload from a recorded byte stream."""

    parser = FrameParser()
    events = parser.feed(data)
    # ``feed`` already returns complete frames; no flush needed because a
    # truncated tail cannot become a valid frame.
    return [event.data for event in events if isinstance(event, FramePayload)]
