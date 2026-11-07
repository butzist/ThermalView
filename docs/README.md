# ThermalView Web

Static web app that talks to the thermal adapter directly from the browser using
the **Web Serial API**. Works on Linux (Chrome/Edge) and Android (Chrome + USB
OTG) with no install and no backend.

## Run locally

Serve the directory over HTTP (Web Serial requires a secure context):

```sh
cd docs
python3 -m http.server 8000
# open http://localhost:8000
```

## Deploy to GitHub Pages

1. Push this repository to GitHub.
2. In the repo settings → Pages, set source to the `docs/` folder (or move these
   files to a `docs/` folder and select that).
3. Open the published HTTPS URL in Chrome/Edge and click **Connect**.

## Notes

- Web Serial is only available in Chromium-based browsers. Firefox/Safari do
  not support it.
- On Android you need a USB-OTG adapter and Chrome; the device must be a CDC
  ACM serial port (this adapter is).
- The adapter streams as soon as the port opens; no start command is sent.
- Palettes and rendering mirror `thermalview/palette.py`.

## Troubleshooting

- **"Failed to open serial port" / open failed**: on Linux the browser uses OS-level
  permissions. Make sure your user can read/write the node:
  ```sh
  sudo chmod 666 /dev/ttyACM0
  ```
  (or add a udev rule). Also close any other program holding the port
  (e.g. `thermalview view`, `picocom`), and check that `brltty`/`ModemManager`
  are not grabbing the device. On Android, grant the permission in the browser
  prompt and use a USB-OTG cable.
- **Black image**: the canvas stays black until the first frame arrives. If
  opening the port fails, no frames are produced — see above.
- **No data / device disconnected**: the adapter streams as soon as the port
  opens; if it was replugged, re-open the connection.

## Android / Brave notes

- Web Serial on Android is supported by **Chrome** (and Chromium forks that
  keep it enabled). **Brave** may disable or restrict it; if Connect shows
  "no compatible devices found" or "Web Serial not supported", try Chrome.
- The device must be a recognised CDC-ACM serial port. If the browser does
  not list it even in the unfiltered picker, the device's USB descriptor is
  not being exposed as a serial port by the OS — in that case a native app
  (using `usb-serial-for-android`) is required instead of the web app.
- Use a USB-OTG cable and grant the browser permission prompt.
