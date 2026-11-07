# thermalview-usb

Python driver for the **ThermalView** USB thermal adapter
(`com.ruiqi.hongwai`, 32×32 sensor, CH340-class USB-serial bridge) on Linux.

The protocol was reconstructed from the Android app's `TempData.java` and the
native `libhongwai.so` JNI decoder.  See `TODO.md` for the evidence trail.

## Install

Everything is provided by the Nix dev shell:

```sh
nix develop
python -m thermalview info
```

For a normal environment:

```sh
pip install -e .
```

## Quick start

```sh
# list candidate adapters
python -m thermalview ports

# read one frame, print stats and save an 800x800 PNG
python -m thermalview capture --png frame.png

# live stats (Ctrl-C to stop)
python -m thermalview stream

# live web viewer (opens a browser, no GUI toolkit required)
python -m thermalview view

# record the raw serial stream for later analysis
python -m thermalview capture --count 30 --record out/session.bin

# decode a capture offline
python -m thermalview decode out/session.bin --index 5 --png frame5.png --npy frame5.npy

# set scene emissivity
python -m thermalview emissivity 0.95
```

Python API:

```python
from thermalview import ThermalCamera, save_frame

with ThermalCamera() as camera:      # auto-detects the single adapter
    frame = camera.read_frame()
    print(frame.stats())
    print(frame.celsius.shape)       # (32, 32) float32 degrees Celsius
    save_frame(frame, "frame.png", palette="iron_red")
```

## Protocol summary

USB-serial, **115200 8N1**, RTS + DTR asserted.

Commands (`00 80 <cmd> 00 <len_lo> <len_hi> [payload]`):

| cmd | meaning | payload |
|-----|---------|---------|
| `0x03` | set emissivity | one byte, `round(e * 100)` |
| `0x04` | start stream | — |
| `0x05` | stop stream | — |

The app never sends `0x04`; the adapter streams as soon as the port opens.

Incoming frames:

```
00 80 01 00 ?? ??           6-byte header
<2048 bytes little-endian>  1024 x uint16
```

Each sample is **tenths of a degree Celsius**: `T = raw / 10.0`.

Some firmware variants (e.g. the Espressif CDC build) stream raw 2048-byte
frames with no `00 80` header; the driver auto-detects this mode.
`TempData` also handles `00 90` status packets (subtype `4`/`5` = start/stop
ack); the parser reports them as `StatusEvent`.

Axis options are applied per pixel: X mirrors each 32-pixel row, Y flips the
image vertically.

## Palettes

The native app has five palettes, exposed by index (`color_type`):

| index | name |
|-------|------|
| 0 | `iron_red` |
| 1 | `rainbow` (stepped) |
| 2 | `white_hot` |
| 3 | `blue_orange` |
| 4 | `blue_yellow` |

`thermalview.palette` reproduces the native functions exactly (including
integer truncation) and maps a Celsius array to RGB.

## Notes and caveats

- Reconstructed statically; validate against your unit with
  `python -m thermalview capture --record out/first.bin`.
- The Android renderer adds a **+1 °C** hot-spot bias to pixels above a
  median-derived threshold before computing max/min, and auto-ranges with
  `max *= 1.5` when the range is below 6 °C.  `FrameStats` reports honest
  values; `frame_to_rgb(..., app_auto_range=True)` reproduces the range rule.
- The app's custom prober registers `1a86:7522` as FTDI, but its USB device
  filter and the default prober point at `1a86:7523` (CH340).  The driver
  accepts both plus FTDI/CP210x/PL2303 alternatives.
- `/dev/ttyUSB*` must be visible inside the sandbox; see `.envrc`
  (`JAIL_EXTRA_ARGS`). Only the serial tty nodes and `/dev/serial` are bound —
  never the whole `/dev`.

## Tests

```sh
nix develop -c pytest
```
