# Rotorflight EdgeTX Suite Updater

A standalone desktop utility for Windows, macOS, and Linux to easily install, update, and manage the [Rotorflight Lua EdgeTX Suite](https://github.com/rotorflight/rotorflight-lua-edgetx-suite) on EdgeTX transmitters and SD cards.

## Features

- **SD Card / Radio Auto-Detection**: Automatically identifies connected EdgeTX radios and drives.
- **GitHub Release Integration**: Downloads and installs official releases and pre-releases from GitHub.
- **Multi-Language Support**: Installs language-specific packs (`en`, `de`, ...).
- **User Settings Preservation**: Preserves `preferences.ini` and custom user dashboards during updates.
- **Offline / Local Mode**: Supports manual installation from locally downloaded `.zip` files.

## Download

Updater binaries are published on GitHub Releases, **but only when**:
- a release is created, or
- the updater source is updated and a release is produced

This means the exact binary link can change or be missing on older releases. Use the Releases page to pick the matching version:

```
https://github.com/rotorflight/rotorflight-lua-edgetx-suite-updater/releases
```

Asset names (when present):
- Windows: `rotorflight-lua-edgetx-suite-updater-<version>-windows-<arch>.zip`
- macOS: `rotorflight-lua-edgetx-suite-updater-<version>-macos-<arch>.zip`
- Linux: `rotorflight-lua-edgetx-suite-updater-<version>-linux-<arch>.zip`

If a release does not include updater assets, the binaries were not rebuilt for that tag. In that case, use the most recent release **that includes** the updater artifacts, or build locally (see below).

## Running from Source

```bash
cd src
pip install -r requirements_updater.txt
python updater.py
```

Or use the launcher scripts:
- Windows: `src/run_updater.bat`
- Linux / macOS: `src/run_updater.sh`

## Building Standalone Executables

### Windows (.exe)
Run `make.cmd` from `src/`. The compiled binary will be placed at `rotorflight-lua-edgetx-suite-updater.exe` in the repo root.

### Linux / macOS
```bash
cd src
pip install -r requirements_updater.txt
pyinstaller --onefile --windowed --name rotorflight-lua-edgetx-suite-updater updater.py
```

## macOS / Linux Notes

- The updater uses `tkinter` for the GUI. Ensure your Python install includes Tk support.
  - macOS: the python.org installer typically includes Tk.
  - Linux: install your distro's `python3-tk` package.
- macOS icon: generate `icon.icns` from the Windows `.ico` with:
  - `python3 src/build_icon_icns.py`

## License

GPLv3 — see [LICENSE](LICENSE).
