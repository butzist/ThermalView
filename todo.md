# TODO

Living progress log for the ThermalView RE effort.

## Environment

- [x] Create `flake.nix` with RE toolchain (Ghidra, JDK, Android tools, Frida, ...)
- [x] `nix flake lock` (nixpkgs-unstable, `1d060086d60c`)
- [x] Verify `nix develop` builds and tools run
- [x] Add `.gitignore` + `git init` + initial commit
- [x] Pin Ghidra to 12.1.4 (`nixpkgs-ghidra` input, `ghidra-bin`) so the REA
      MCP Ghidra provider binds; JDK 21 is enough (12.1.4 declares
      `application.java.min=21`, 12.2 declares `min=25`)
- [x] `rea doctor`: all `ghidra*` checks healthy on 12.1.4 + JDK 21
- [ ] Restart the MCP client after the Ghidra pin so REA re-reads `GHIDRA_HOME`
- [ ] Optional: `wireshark` GUI, `objection` (via venv) if needed
- [ ] Optional: `REA_JADX_MCP_JAR` (jadx-headless-mcp 0.7.1) to decompile Java
      through REA instead of the `jadx` CLI
- [x] Add Python deps for the driver to the dev shell: `pyserial`, `pyusb`,
      `numpy`, `pillow`, `pytest`
- [x] Add USB tooling to the dev shell: `usbutils`, `picocom`, `screen`
- [x] `.envrc`: export `JAIL_EXTRA_ARGS_THERMALVIEW` with `--ro-bind-try /sys`,
      `--ro-bind-try /run/udev` and `--dev-bind-try` for **only the specific
      serial tty nodes** (`/dev/ttyUSB*`, `/dev/ttyACM*`, `/dev/serial` ro);
      the whole `/dev` is never shared. `--dev-bind-try` skips absent nodes,
      so the jail starts with the adapter unplugged.

Notes:

- `cutter` is not installed and not needed: it is a Qt GUI over rizin, and
  REA's `cutter_command` only attaches to a user-started Cutter. rizin/radare2
  CLI + Ghidra cover the same ground.

## Triage

- [x] Extract `AndroidManifest.xml` (decoded) and note permissions, services,
      exported components, SDK levels
      -> `com.ruiqi.hongwai` 1.1 (code 1), minSdk 21, targetSdk 34,
      USB host required, CAMERA + INTERNET, `MainActivity` exported,
      app class `com.ruiqi.hongwai.MyApplication`
- [x] Decompile `classes.dex` with jadx into `out/jadx/` (2904 `.java`)
- [x] Decode resources with apktool (via REA `decode_android_resources`):
      92 locales, 202 default strings, 1103 decoded files
- [x] Extract APK contents to `out/apk/` (REA `extract_artifact`, 22 MB)
- [x] List JNI entry points (`Java_*`) in `libhongwai.so`
      -> 7 exports, all on `com.ruiqi.hongwai.JniPicData`: `initJNI`,
      `setGlobalObject`, `setColorType`, `setTempType`, `setAxisSwitch`,
      `signalData`, `stringFromJNI`
- [x] Decompile all 7 JNI functions (Ghidra 12.1.4,
      `scripts/ghidra/DecompileFunctions.java`)
- [x] Identify the transport: usb-serial-for-android (`com.hoho.android.usbserial`),
      **not** raw bulk USB
- [x] Locate the thermal frame format / image decoding path
- [x] Map `JniResultCall` callbacks back into the Java layer
      (`TempData` -> `JniPicData.signalData` -> JNI `writeWork` -> Java callback)
- [x] Locate network endpoints, ports, and protocols: none used for the camera
      (only `INTERNET` permission / app boilerplate)
- [ ] Identify remaining third-party SDKs (AndroidX, usb-serial, OpenCV subset)

## USB protocol (reconstructed)

Source of truth: `out/jadx/sources/com/ruiqi/hongwai/TempData.java` and
`libhongwai.so` (`getTempPicData` @ `0x305320`, `writeWork`).

- [x] Serial parameters: **115200 8N1**, RTS=true, DTR=true
- [x] TX command frame: `00 80 <cmd> 00 <len_lo> <len_hi> [payload]`
      (LE16 sync `0x8000`, LE16 cmd, LE16 payload length)
- [x] Commands: `0x03` set emissivity (1 byte `round(e*100)`),
      `0x04` start stream, `0x05` stop stream
- [x] `sendStart()` / `sendStop()` are never called from Java: the device
      streams as soon as the port is opened (needs hardware confirmation)
- [x] RX framing: header `00 80 01 00 ?? ??` (LE16 `0x8000`, subtype `1`),
      pixel payload starts at byte 6 and is appended until 2048 bytes
- [x] Status packets start with LE16 `0x9000`; subtype `4`/`5` resets the
      frame buffer (start/stop ack)
- [x] Frame payload: exactly **2048 bytes** = 1024 x **uint16 little-endian**,
      row-major **32 x 32**
- [x] Temperature: `T_celsius = raw_u16 / 10.0`
      (`temp_val_xishu = 10.0` at vaddr `0x6c6d14`)
- [x] Axis options applied per pixel: X mirrors each 32-pixel row, Y flips the
      image vertically
- [x] Candidate USB IDs: `1a86:7523` CH340 (default prober + device filter),
      `1a86:5523` CH341, `1a86:55d4` CH9102, FTDI/CP210x/PL2303 alternatives;
      `CustomProber` maps `1a86:7522` -> FTDI (looks like dead code)
- [x] **Confirm actual VID:PID on real hardware**: `303a:4001` Espressif Systems USB Device (CDC ACM), exposed as `/dev/ttyACM0`. Not the CH340 (`1a86:7523`) the app's device_filter targets; added to `KNOWN_DEVICES`. No CH340/FTDI/CP210x device present.
- [x] **Confirm whether opening the port alone starts the stream**: yes. The device streams continuously as soon as the port is opened (115200 8N1, DTR/RTS asserted). No start command (`0x04`) is needed (and sending it does not change behaviour).
- [x] Capture real sessions (`out/bigcap.bin`, `out/capture1.bin`): the Espressif firmware streams **raw, headerless 2048-byte frames** (no `00 80`/`00 90` sync words, unlike the CH340 variant the Java `TempData` parser expects). Frames are 32x32 uint16 LE, /10.0 °C, contiguous. Driver now auto-detects raw mode and decodes correctly (see `thermalview/device.py`).

## Native renderer (reference, for optional fidelity)

- [x] `writeWork` pipeline recovered: 32x32 float -> `minMaxLoc` ->
      median hot-spot adjust -> palette -> blur/resize -> saturation ->
      brightness -> Laplacian unsharp -> `cv::imencode` JPEG
- [x] Palettes decompiled exactly (`iron_red`, `rainbow`, `white_hot`,
      `blue_orange`, `blue_yellow` = `color_type` 0..4)
- [x] Documented app quirks (all values are raw tenths of a degree, so
      `+10` raw = `+1 °C`):
      - pixels above a median-derived threshold get `+10.0` before max/min
      - narrow range (`max-min < 60` raw = `6 °C`): `max *= 1.5`
      - `max-min >= 200` raw (20 °C): CLAHE
      - `150..200` raw (15..20 °C): histogram equalisation
- [x] `MAPTemperatureToRGB` (`0x3046a8`), `increaseSaturation` (`0x304ab4`),
      `adjustBrightness` (`0x305204`), `CLAHEImage` (`0x305590`),
      `equalizeHistImage` (`0x305910`), `calculateMedianTemperature`
      (`0x306558`), `findClosestToTemperature` (`0x3069c8`),
      `calibrateTemperature` (`0x306b80`)

## Python library (`thermalview/`)

- [x] `thermalview/protocol.py`: command builders, incremental `FrameParser`
      (arbitrary chunking, status events, resync on truncated frames)
- [x] `thermalview/frame.py`: `ThermalFrame`, `decode_payload`,
      `encode_payload`, `frames_from_bytes`, honest min/max/mean/centre stats
- [x] `thermalview/palette.py`: exact ports of the five native palettes
- [x] `thermalview/render.py`: RGB / Pillow rendering, PNG/JPEG, CSV, NPY
- [x] `thermalview/device.py`: pyserial transport, port auto-detection,
      commands, frame iterator, raw capture hook
- [x] `thermalview/cli.py` + `__main__.py`: `ports`, `info`, `capture`,
      `stream`, `decode`, `emissivity`
- [x] `thermalview/viewer.py`: live web viewer (`view`) that tolerates clients
      aborting the polling image request (no more `BrokenPipeError` tracebacks)
- [x] `pyproject.toml` (+ console script `thermalview`), `README.md`
- [x] `tests/`: 34 passing tests covering commands, framing, chunking,
      temperature scaling, flips, palettes, rendering and CLI
- [ ] Optional: `pyusb` transport fallback when the kernel driver is absent
- [ ] Optional: live preview window / video writer
- [ ] Optional: emulate the app's full display pipeline (hot-spot bias, blur,
      unsharp mask, CLAHE/equalise)

## Dynamic analysis (optional, needs device)

- [ ] `adb devices`, install APK on test device
- [ ] `frida-ps -U`, hook native + Java entry points
- [ ] Capture serial traffic with `picocom` / the `capture --record` tool
- [ ] Validate protocol against the recorded session and adjust parser

## Deliverables

- [x] Reusable Python driver in-project (`thermalview/`)
- [x] `README.md` protocol summary + usage
- [x] Reusable scripts in `scripts/`
- [ ] `notes/` write-up of findings (gitignored; add a tracked summary once
      the hardware is validated)
