"""Colour palettes used by the ThermalView native renderer.

Each function mirrors the decompiled ``iron_red`` / ``rainbow`` / ``white_hot``
/ ``blue_orange`` / ``blue_yellow`` routines from ``libhongwai.so`` and maps a
normalised value ``t`` in ``0..1`` to an RGB triple.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

RGBArray = np.ndarray


def _as_t(celsius: np.ndarray, vmin: float, vmax: float) -> np.ndarray:
    celsius = np.asarray(celsius, dtype=np.float64)
    if vmax <= vmin:
        return np.zeros_like(celsius, dtype=np.float64)
    return np.clip((celsius - vmin) / (vmax - vmin), 0.0, 1.0)


def iron_red(t: np.ndarray) -> RGBArray:
    """``color_type == 0`` (Iron Red)."""

    t = np.asarray(t, dtype=np.float64)
    r = np.where(t <= 0.5, t * 180.0, np.where(t <= 0.8, 255.0, 255.0))
    g = np.where(t <= 0.5, 0.0, np.where(t <= 0.8, t * 255.0, 253.0))
    b = np.where(t <= 0.5, t * 120.0, np.where(t <= 0.8, 0.0, 238.0))
    return _stack(r, g, b)


def rainbow(t: np.ndarray) -> RGBArray:
    """``color_type == 1`` (stepped rainbow)."""

    t = np.asarray(t, dtype=np.float64)
    conditions = [t <= 0.2, t <= 0.4, t <= 0.5, t <= 0.6, t <= 0.75, t <= 0.8]
    r = np.select(conditions, [0.0, 0x1A, 0x3F, 0x4C, 0x76, 0xFF], default=0xF4)
    g = np.select(conditions, [0.0, 0x23, 0x51, 0xAF, 0xFF, 0xEB], default=0x43)
    b = np.select(conditions, [0.0, 0x7E, 0xB5, 0x50, 0x03, 0x3B], default=0x36)
    return _stack(r, g, b)


def white_hot(t: np.ndarray) -> RGBArray:
    """``color_type == 2`` (white hot)."""

    v = np.asarray(t, dtype=np.float64) * 255.0
    return _stack(v, v, v)


def blue_orange(t: np.ndarray) -> RGBArray:
    """``color_type == 3`` (blue -> orange)."""

    t = np.asarray(t, dtype=np.float64)
    r = t * 255.0
    g = np.where(t <= 0.5, 0.0, t * 120.0)
    b = -255.0 * t + 255.0
    return _stack(r, g, b)


def blue_yellow(t: np.ndarray) -> RGBArray:
    """``color_type == 4`` (blue -> yellow)."""

    t = np.asarray(t, dtype=np.float64)
    r = np.where(t <= 0.5, t * 70.0, np.where(t <= 0.82, 255.0, 255.0))
    g = np.where(t <= 0.5, t * 70.0, np.where(t <= 0.82, 255.0, 253.0))
    b = np.where(t <= 0.5, t * 200.0, np.where(t <= 0.82, 0.0, 238.0))
    return _stack(r, g, b)


def _stack(r: np.ndarray, g: np.ndarray, b: np.ndarray) -> RGBArray:
    # The native code casts to int (truncation) and then to uchar.
    rgb = np.stack([r, g, b], axis=-1)
    rgb = np.clip(rgb, 0.0, 255.0)
    return rgb.astype(np.uint8)


#: Canonical palette names in the app's ``color_type`` order.
PALETTES: dict[str, tuple[int, Callable[[np.ndarray], RGBArray]]] = {
    "iron_red": (0, iron_red),
    "rainbow": (1, rainbow),
    "white_hot": (2, white_hot),
    "blue_orange": (3, blue_orange),
    "blue_yellow": (4, blue_yellow),
}

_ALIASES = {
    "iron": "iron_red",
    "ironred": "iron_red",
    "white": "white_hot",
    "whitehot": "white_hot",
    "grey": "white_hot",
    "gray": "white_hot",
    "blue-orange": "blue_orange",
    "blue-yellow": "blue_yellow",
}


def palette_names() -> tuple[str, ...]:
    """Return canonical palette names in ``color_type`` order."""

    return tuple(PALETTES)


def resolve_palette(name: str | int) -> Callable[[np.ndarray], RGBArray]:
    """Resolve a palette name, alias or app ``color_type`` index."""

    if isinstance(name, int):
        for canonical, (index, function) in PALETTES.items():
            if index == name:
                return function
        raise ValueError(f"unknown palette index {name}; expected 0..4")

    key = name.strip().lower().replace(" ", "_")
    key = _ALIASES.get(key, key)
    try:
        return PALETTES[key][1]
    except KeyError as exc:
        raise ValueError(
            f"unknown palette {name!r}; choose from {', '.join(PALETTES)}"
        ) from exc


def apply_palette(
    celsius: np.ndarray,
    vmin: float | None = None,
    vmax: float | None = None,
    palette: str | int = "iron_red",
) -> RGBArray:
    """Map a temperature array to an ``(H, W, 3)`` uint8 RGB array."""

    values = np.asarray(celsius, dtype=np.float64)
    if vmin is None:
        vmin = float(values.min())
    if vmax is None:
        vmax = float(values.max())
    return resolve_palette(palette)(_as_t(values, float(vmin), float(vmax)))
