"""Render thermal frames to RGB arrays and Pillow images."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .frame import ThermalFrame
from .palette import RGBArray, apply_palette


def frame_to_rgb(
    frame: ThermalFrame,
    *,
    palette: str | int = "iron_red",
    vmin: float | None = None,
    vmax: float | None = None,
    app_auto_range: bool = False,
) -> RGBArray:
    """Map a frame to RGB using honest or app-like auto-ranging.

    With ``app_auto_range=True`` the app's rule for a narrow range is applied:
    when ``max - min < 6 degC`` the upper colour bound becomes ``max * 1.5``.
    """

    values = frame.celsius
    if vmin is None:
        vmin = float(values.min())
    if vmax is None:
        vmax = float(values.max())
    if app_auto_range and vmax - vmin < 6.0:
        vmax = vmax * 1.5
    return apply_palette(values, vmin, vmax, palette)


def frame_to_image(
    frame: ThermalFrame,
    *,
    palette: str | int = "iron_red",
    vmin: float | None = None,
    vmax: float | None = None,
    size: int = 800,
    app_auto_range: bool = False,
):
    """Return a Pillow ``Image`` for a frame.

    The native renderer upscales the 32x32 grid to 800x800; bilinear scaling
    keeps the output close to the app's smoothed look.
    """

    from PIL import Image

    rgb = frame_to_rgb(
        frame, palette=palette, vmin=vmin, vmax=vmax, app_auto_range=app_auto_range
    )
    image = Image.fromarray(rgb, mode="RGB")
    if size and image.size != (size, size):
        image = image.resize((size, size), Image.Resampling.BILINEAR)
    return image


def save_frame(
    frame: ThermalFrame,
    path: str | Path,
    *,
    palette: str | int = "iron_red",
    vmin: float | None = None,
    vmax: float | None = None,
    size: int = 800,
    app_auto_range: bool = False,
) -> Path:
    """Render ``frame`` and write it to ``path`` (PNG/JPEG by extension)."""

    path = Path(path)
    image = frame_to_image(
        frame,
        palette=palette,
        vmin=vmin,
        vmax=vmax,
        size=size,
        app_auto_range=app_auto_range,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def temperature_csv(frame: ThermalFrame) -> str:
    """Return the temperature grid as CSV text."""

    values = frame.celsius
    lines = [",".join(f"{value:.1f}" for value in row) for row in values]
    return "\n".join(lines) + "\n"


def save_npy(frame: ThermalFrame, path: str | Path) -> Path:
    """Save the Celsius grid as ``.npy``."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, frame.celsius)
    return path
