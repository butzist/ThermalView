"""Python driver for the ThermalView USB thermal adapter.

Reconstructed from ``com.ruiqi.hongwai`` (ThermalView) and ``libhongwai.so``.
"""

from .device import KNOWN_DEVICES, PortInfo, ThermalCamera, find_ports, resolve_port
from .frame import (
    DEFAULT_SCALE,
    FrameStats,
    ThermalFrame,
    decode_payload,
    encode_payload,
    frames_from_bytes,
)
from .palette import PALETTES, apply_palette, palette_names
from .protocol import (
    CMD_SET_EMISSIVITY,
    CMD_START,
    CMD_STOP,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    PAYLOAD_SIZE,
    FrameParser,
    FramePayload,
    StatusEvent,
    command,
    emissivity_command,
    start_command,
    stop_command,
)
from .render import frame_to_image, frame_to_rgb, save_frame

__version__ = "0.1.0"

__all__ = [
    "CMD_SET_EMISSIVITY",
    "CMD_START",
    "CMD_STOP",
    "DEFAULT_SCALE",
    "FRAME_HEIGHT",
    "FRAME_WIDTH",
    "KNOWN_DEVICES",
    "PALETTES",
    "PAYLOAD_SIZE",
    "FrameParser",
    "FramePayload",
    "FrameStats",
    "PortInfo",
    "StatusEvent",
    "ThermalCamera",
    "ThermalFrame",
    "apply_palette",
    "command",
    "decode_payload",
    "emissivity_command",
    "encode_payload",
    "find_ports",
    "frame_to_image",
    "frame_to_rgb",
    "frames_from_bytes",
    "palette_names",
    "resolve_port",
    "save_frame",
    "start_command",
    "stop_command",
]
