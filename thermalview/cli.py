"""Command-line interface: ``python -m thermalview``."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import __version__
from .device import ThermalCamera, find_ports, resolve_port
from .frame import ThermalFrame, frames_from_bytes
from .palette import palette_names
from .render import save_frame, save_npy, temperature_csv


def _add_port_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--port",
        help="serial device (default: auto-detect the single USB-serial adapter)",
    )
    parser.add_argument("--timeout", type=float, default=2.0, help="per-frame timeout")
    parser.add_argument("--x-flip", action="store_true", help="mirror each row")
    parser.add_argument("--y-flip", action="store_true", help="flip vertically")


def _add_render_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--palette",
        default="iron_red",
        choices=list(palette_names()),
        help="colour palette (default: iron_red)",
    )
    parser.add_argument("--min", dest="vmin", type=float, help="colour scale minimum degC")
    parser.add_argument("--max", dest="vmax", type=float, help="colour scale maximum degC")
    parser.add_argument("--size", type=int, default=800, help="output image size")
    parser.add_argument(
        "--app-auto-range",
        action="store_true",
        help="apply the app's max*1.5 rule when the range is under 60 degC",
    )


def _stats_dict(frame: ThermalFrame) -> dict[str, object]:
    stats = frame.stats()
    return {
        "timestamp": frame.timestamp,
        "min_c": round(stats.min_celsius, 1),
        "max_c": round(stats.max_celsius, 1),
        "mean_c": round(stats.mean_celsius, 1),
        "center_c": round(stats.center_celsius, 1),
        "max_pos": list(stats.max_position),
        "min_pos": list(stats.min_position),
    }


def _print_stats(frame: ThermalFrame, as_json: bool) -> None:
    data = _stats_dict(frame)
    if as_json:
        print(json.dumps(data), flush=True)
    else:
        print(
            "min={min_c:6.1f}C max={max_c:6.1f}C mean={mean_c:6.1f}C "
            "center={center_c:6.1f}C max@{max_pos}".format(**data),
            flush=True,
        )


def cmd_ports(args: argparse.Namespace) -> int:
    ports = find_ports()
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "device": item.device,
                        "vid_pid": item.vid_pid,
                        "known_name": item.known_name,
                        "description": item.description,
                        "serial_number": item.serial_number,
                        "manufacturer": item.manufacturer,
                        "product": item.product,
                    }
                    for item in ports
                ],
                indent=2,
            )
        )
        return 0
    if not ports:
        print("no serial ports found", file=sys.stderr)
        return 1
    for item in ports:
        suffix = f"  [{item.known_name}]" if item.known_name else ""
        print(f"{item.device:20} {item.vid_pid}  {item.description}{suffix}")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    print(f"thermalview {__version__}")
    try:
        default_port = resolve_port(None)
    except RuntimeError:
        default_port = None
    print(f"default port: {default_port or '(none)'}")
    print("palettes: " + ", ".join(palette_names()))
    return cmd_ports(args)


def _open_camera(args: argparse.Namespace) -> ThermalCamera:
    camera = ThermalCamera(
        args.port,
        timeout=args.timeout,
        x_flip=args.x_flip,
        y_flip=args.y_flip,
        auto_start=getattr(args, "auto_start", False),
    )
    camera.open()
    return camera


def cmd_capture(args: argparse.Namespace) -> int:
    saved = 0
    record_file = None
    try:
        camera = _open_camera(args)
    except (RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        if args.record:
            record_path = Path(args.record)
            record_path.parent.mkdir(parents=True, exist_ok=True)
            record_file = record_path.open("wb")
            camera.chunk_hook = record_file.write
        if args.emissivity is not None:
            camera.set_emissivity(args.emissivity)

        frames = camera.frames(args.count, timeout=args.timeout)
        for index, frame in enumerate(frames):
            if not args.quiet:
                _print_stats(frame, args.json)

            if args.png and index == 0:
                path = save_frame(
                    frame,
                    args.png,
                    palette=args.palette,
                    vmin=args.vmin,
                    vmax=args.vmax,
                    size=args.size,
                    app_auto_range=args.app_auto_range,
                )
                saved += 1
                print(f"saved {path}", file=sys.stderr)
            if args.npy and index == 0:
                saved += 1
                print(f"saved {save_npy(frame, args.npy)}", file=sys.stderr)
            if args.csv and index == 0:
                csv_path = Path(args.csv)
                csv_path.parent.mkdir(parents=True, exist_ok=True)
                csv_path.write_text(temperature_csv(frame))
                saved += 1
                print(f"saved {csv_path}", file=sys.stderr)
            if args.png_dir:
                out = Path(args.png_dir) / f"frame_{index:06d}.png"
                save_frame(
                    frame,
                    out,
                    palette=args.palette,
                    vmin=args.vmin,
                    vmax=args.vmax,
                    size=args.size,
                    app_auto_range=args.app_auto_range,
                )
                saved += 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
    except TimeoutError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        camera.close()
        if record_file is not None:
            record_file.close()

    if args.record:
        print(f"recorded {camera.raw_bytes} bytes to {args.record}", file=sys.stderr)
    return 0


def cmd_stream(args: argparse.Namespace) -> int:
    deadline = None if args.duration is None else time.monotonic() + args.duration
    try:
        camera = _open_camera(args)
    except (RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    count = 0
    try:
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                break
            if args.count is not None and count >= args.count:
                break
            frame = camera.read_frame(args.timeout)
            count += 1
            _print_stats(frame, args.json)
    except KeyboardInterrupt:
        pass
    except TimeoutError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        camera.close()
    print(f"{count} frames", file=sys.stderr)
    return 0


def cmd_decode(args: argparse.Namespace) -> int:
    source = Path(args.input)
    frames = list(
        frames_from_bytes(
            source.read_bytes(), x_flip=args.x_flip, y_flip=args.y_flip
        )
    )
    if not frames:
        print("no frames found in input", file=sys.stderr)
        return 1
    if args.index >= len(frames):
        print(
            f"index {args.index} out of range (found {len(frames)} frames)",
            file=sys.stderr,
        )
        return 1
    frame = frames[args.index]
    _print_stats(frame, args.json)
    if args.png:
        print(
            f"saved {save_frame(frame, args.png, palette=args.palette, vmin=args.vmin, vmax=args.vmax, size=args.size, app_auto_range=args.app_auto_range)}"
        )
    if args.npy:
        print(f"saved {save_npy(frame, args.npy)}")
    if args.csv:
        Path(args.csv).write_text(temperature_csv(frame))
        print(f"saved {args.csv}")
    return 0


def cmd_emissivity(args: argparse.Namespace) -> int:
    try:
        with _open_camera(args) as camera:
            camera.set_emissivity(args.value)
    except (RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"emissivity set to {args.value:g}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="thermalview",
        description="Read frames from the ThermalView USB thermal adapter.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    ports = sub.add_parser("ports", help="list serial ports")
    ports.add_argument("--json", action="store_true")
    ports.set_defaults(func=cmd_ports)

    info = sub.add_parser("info", help="show version, ports and palettes")
    info.add_argument("--json", action="store_true")
    info.set_defaults(func=cmd_info)

    capture = sub.add_parser("capture", help="read frames and optionally save them")
    _add_port_options(capture)
    _add_render_options(capture)
    capture.add_argument("--count", type=int, default=1, help="frames to read")
    capture.add_argument("--record", help="write the raw serial stream to this file")
    capture.add_argument("--png", help="save the first frame as PNG/JPEG")
    capture.add_argument("--png-dir", help="save every frame into this directory")
    capture.add_argument("--npy", help="save the first frame's Celsius grid")
    capture.add_argument("--csv", help="save the first frame's Celsius grid as CSV")
    capture.add_argument("--emissivity", type=float, help="set emissivity before capture")
    capture.add_argument("--auto-start", action="store_true", help="send the start command")
    capture.add_argument("--json", action="store_true", help="stats as JSON lines")
    capture.add_argument("--quiet", action="store_true", help="suppress per-frame stats")
    capture.set_defaults(func=cmd_capture)

    stream = sub.add_parser("stream", help="print live frame statistics")
    _add_port_options(stream)
    stream.add_argument("--count", type=int, help="stop after N frames")
    stream.add_argument("--duration", type=float, help="stop after N seconds")
    stream.add_argument("--json", action="store_true", help="stats as JSON lines")
    stream.set_defaults(func=cmd_stream)

    decode = sub.add_parser("decode", help="decode a recorded stream or one payload")
    decode.add_argument("input", help="capture file or a single 2048-byte payload")
    decode.add_argument("--index", type=int, default=0, help="frame index")
    decode.add_argument("--png", help="write an image")
    decode.add_argument("--npy", help="write the Celsius grid")
    decode.add_argument("--csv", help="write the Celsius grid as CSV")
    decode.add_argument("--x-flip", action="store_true")
    decode.add_argument("--y-flip", action="store_true")
    decode.add_argument("--json", action="store_true")
    _add_render_options(decode)
    decode.set_defaults(func=cmd_decode)

    emissivity = sub.add_parser("emissivity", help="set the scene emissivity")
    _add_port_options(emissivity)
    emissivity.add_argument("value", type=float, help="0.10 .. 0.98")
    emissivity.set_defaults(func=cmd_emissivity)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
