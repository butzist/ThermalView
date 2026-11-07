"""USB-serial transport for the ThermalView adapter (pyserial on Linux)."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

try:
    import serial
    from serial.tools import list_ports
except ImportError as exc:  # pragma: no cover - dependency is in the dev shell
    raise ImportError(
        "pyserial is required; enter the Nix dev shell or `pip install pyserial`"
    ) from exc

from .frame import DEFAULT_SCALE, ThermalFrame, decode_payload
from .protocol import (
    FRAME_MAGIC,
    PAYLOAD_SIZE,
    FrameParser,
    FramePayload,
    StatusEvent,
    emissivity_command,
    start_command,
    stop_command,
)

#: VID/PID pairs from the app's ``device_filter.xml``.
KNOWN_DEVICES: dict[tuple[int, int], str] = {
    (0x1A86, 0x7523): "WCH CH340",
    (0x1A86, 0x5523): "WCH CH341A",
    (0x1A86, 0x55D4): "WCH CH9102",
    (0x0403, 0x6001): "FTDI FT232R",
    (0x0403, 0x6010): "FTDI FT2232",
    (0x0403, 0x6011): "FTDI FT4232",
    (0x0403, 0x6014): "FTDI FT232H",
    (0x0403, 0x6015): "FTDI FT231X",
    (0x10C4, 0xEA60): "Silicon Labs CP2102",
    (0x10C4, 0xEA70): "Silicon Labs CP2105",
    (0x10C4, 0xEA71): "Silicon Labs CP2108",
    (0x067B, 0x2303): "Prolific PL2303",
    (0x0483, 0x5740): "STM32 virtual COM port",
    (0x2E8A, 0x0005): "Raspberry Pi Pico",
    (0x2E8A, 0x000A): "Raspberry Pi Pico",
    (0x303A, 0x4001): "Espressif CDC (ThermalView device)",
}


@dataclass(frozen=True)
class PortInfo:
    """One serial port reported by the OS."""

    device: str
    description: str
    vid: int | None
    pid: int | None
    serial_number: str | None
    manufacturer: str | None
    product: str | None

    @property
    def known_name(self) -> str | None:
        if self.vid is None or self.pid is None:
            return None
        return KNOWN_DEVICES.get((self.vid, self.pid))

    @property
    def is_known_adapter(self) -> bool:
        return self.known_name is not None

    @property
    def vid_pid(self) -> str:
        if self.vid is None or self.pid is None:
            return "----:----"
        return f"{self.vid:04x}:{self.pid:04x}"


def find_ports() -> list[PortInfo]:
    """List serial ports, known USB-serial bridges first."""

    ports = [
        PortInfo(
            device=port.device,
            description=port.description or "",
            vid=port.vid,
            pid=port.pid,
            serial_number=port.serial_number,
            manufacturer=port.manufacturer,
            product=port.product,
        )
        for port in list_ports.comports()
    ]
    ports.sort(key=lambda item: (not item.is_known_adapter, item.device))
    return ports


def resolve_port(port: str | None = None) -> str:
    """Return an explicit port, or guess the only plausible adapter."""

    if port:
        return port
    ports = find_ports()
    known = [item for item in ports if item.is_known_adapter]
    if len(known) == 1:
        return known[0].device
    if len(ports) == 1:
        return ports[0].device
    if not ports:
        raise RuntimeError(
            "no serial ports found; is the adapter plugged in and visible in the jail?"
        )
    listing = ", ".join(f"{item.device} ({item.vid_pid})" for item in ports)
    raise RuntimeError(f"cannot choose a port; pass --port (found: {listing})")


class ThermalCamera:
    """Open a ThermalView adapter and read 32x32 thermal frames.

    The adapter streams continuously after the port is opened; the app never
    sends the documented start command.  ``auto_start=True`` sends it anyway
    for firmware variants that need it.
    """

    def __init__(
        self,
        port: str | None = None,
        *,
        baudrate: int = 115200,
        timeout: float = 2.0,
        scale: float = DEFAULT_SCALE,
        x_flip: bool = False,
        y_flip: bool = False,
        auto_start: bool = False,
        raw: bool | None = None,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.scale = scale
        self.x_flip = x_flip
        self.y_flip = y_flip
        self.auto_start = auto_start
        #: ``True`` forces raw 2048-byte frames, ``False`` forces framed
        #: (``00 80`` headers), ``None`` auto-detects from the byte stream.
        self.raw = raw

        self._port: serial.Serial | None = None
        self._parser = FrameParser()
        self._pending: deque[FramePayload | StatusEvent] = deque()
        self.last_status: StatusEvent | None = None
        self.raw_bytes = 0
        self._rx_mode: str | None = None  # "framed" or "raw"
        self._raw_buf = bytearray()
        self._detect_buf = bytearray()
        #: Optional callback receiving every raw chunk (for capture files).
        self.chunk_hook: Callable[[bytes], object] | None = None

    # -- lifecycle ---------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._port is not None and self._port.is_open

    @property
    def port_path(self) -> str:
        if self._port is not None:
            return self._port.port or self.port or ""
        return self.port or ""

    def open(self) -> ThermalCamera:
        if self.is_open:
            return self
        path = resolve_port(self.port)
        self.port = path
        self._port = serial.Serial(
            port=path,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.1,
            write_timeout=1.0,
            rtscts=False,
            dsrdtr=False,
        )
        # The app opens with RTS and DTR asserted.
        try:
            self._port.dtr = True
            self._port.rts = True
        except (OSError, serial.SerialException):
            pass
        self._parser.reset()
        self._pending.clear()
        self.last_status = None
        self.raw_bytes = 0
        self._raw_buf.clear()
        self._detect_buf.clear()
        if self.raw is True:
            self._rx_mode = "raw"
        elif self.raw is False:
            self._rx_mode = "framed"
        else:
            self._rx_mode = None
        if self.auto_start:
            self.start()
        return self

    def close(self) -> None:
        port = self._port
        if port is None:
            return
        try:
            port.dtr = False
            port.rts = False
        except (OSError, serial.SerialException):
            pass
        try:
            port.close()
        finally:
            self._port = None

    def __enter__(self) -> ThermalCamera:
        return self.open()

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- commands ----------------------------------------------------------

    def _write(self, data: bytes) -> None:
        if not self.is_open:
            raise RuntimeError("camera is not open")
        assert self._port is not None
        self._port.write(data)
        self._port.flush()

    def start(self) -> None:
        """Send the start-stream command (normally unnecessary)."""

        self._write(start_command())

    def stop(self) -> None:
        """Send the stop-stream command."""

        self._write(stop_command())

    def set_emissivity(self, value: float) -> None:
        """Set the scene emissivity (0.10 .. 0.98 in the Android UI)."""

        self._write(emissivity_command(value))

    # -- reading -----------------------------------------------------------

    def _drain_raw(self) -> None:
        while len(self._raw_buf) >= PAYLOAD_SIZE:
            payload = bytes(self._raw_buf[:PAYLOAD_SIZE])
            del self._raw_buf[:PAYLOAD_SIZE]
            self._pending.append(FramePayload(payload))

    def _read_chunk(self) -> bytes:
        if not self.is_open:
            raise RuntimeError("camera is not open")
        assert self._port is not None
        chunk = self._port.read(4096)
        if not chunk:
            return chunk
        self.raw_bytes += len(chunk)
        if self.chunk_hook is not None:
            self.chunk_hook(chunk)

        if self._rx_mode is None:
            self._detect_buf.extend(chunk)
            if FRAME_MAGIC in self._detect_buf:
                self._rx_mode = "framed"
            elif len(self._detect_buf) >= PAYLOAD_SIZE:
                self._rx_mode = "raw"
            else:
                return chunk
            data = bytes(self._detect_buf)
            self._detect_buf.clear()
            if self._rx_mode == "framed":
                self._pending.extend(self._parser.feed(data))
            else:
                self._raw_buf.extend(data)
                self._drain_raw()
            return chunk

        if self._rx_mode == "framed":
            self._pending.extend(self._parser.feed(chunk))
        else:
            self._raw_buf.extend(chunk)
            self._drain_raw()
        return chunk

    def read_event(self, timeout: float | None = None) -> FramePayload | StatusEvent | None:
        """Return the next frame/status event, or ``None`` on timeout."""

        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while True:
            if self._pending:
                event = self._pending.popleft()
                if isinstance(event, StatusEvent):
                    self.last_status = event
                return event
            if time.monotonic() >= deadline:
                return None
            self._read_chunk()

    def read_frame(self, timeout: float | None = None) -> ThermalFrame:
        """Read one complete frame or raise :class:`TimeoutError`."""

        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("timed out waiting for a thermal frame")
            event = self.read_event(remaining)
            if event is None:
                raise TimeoutError("timed out waiting for a thermal frame")
            if isinstance(event, FramePayload):
                return decode_payload(
                    event.data,
                    x_flip=self.x_flip,
                    y_flip=self.y_flip,
                    scale=self.scale,
                )

    def frames(
        self, count: int | None = None, *, timeout: float | None = None
    ) -> Iterator[ThermalFrame]:
        """Yield frames forever, or ``count`` times."""

        seen = 0
        while count is None or seen < count:
            yield self.read_frame(timeout)
            seen += 1


def frames_from_capture(
    path: str | Path,
    *,
    x_flip: bool = False,
    y_flip: bool = False,
    scale: float = DEFAULT_SCALE,
) -> Iterator[ThermalFrame]:
    """Yield frames from a file recorded with ``--record``."""

    from .frame import frames_from_bytes

    yield from frames_from_bytes(
        Path(path).read_bytes(), x_flip=x_flip, y_flip=y_flip, scale=scale
    )
