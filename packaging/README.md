# Packaging claude-teletype (macOS onedir bundle)

Builds a self-contained PyInstaller **onedir** bundle from the checked-in
spec (`packaging/claude-teletype.spec`). End users need no Homebrew and no
dev Python — libusb ships inside the bundle (R026/R027).

## Build-machine prerequisites

- Apple Silicon Mac (the build is **arm64-only**; Intel/universal2 is
  deferred — PKG-06).
- Homebrew libusb on the **build** machine only: `brew install libusb`.
  The spec fails loudly at build time if `/opt/homebrew/lib/libusb-1.0.dylib`
  is missing. End users never need it — the dylib is bundled.
- `uv` with Python 3.13 (PyInstaller ≥ 6.11 supports 3.13).

## Build

```sh
uv sync --extra usb --group packaging
uv run --group packaging pyinstaller --noconfirm packaging/claude-teletype.spec
```

The `--extra usb` is **mandatory**: pyusb must be in the build venv or it is
silently absent from the bundle and the frozen app permanently reports pyusb
missing — a quiet R027 failure that `claude-teletype diagnose` would surface
only at runtime.

Output lands in `dist/claude-teletype/`:

- `dist/claude-teletype/claude-teletype` — the console executable
- `dist/claude-teletype/_internal/` — all bundled code, data, and dylibs
  (including `libusb-1.0.dylib` and the sounddevice wheel's
  `_sounddevice_data/portaudio-binaries/libportaudio.dylib`)

## Smoke check (dev machine)

```sh
dist/claude-teletype/claude-teletype --help
dist/claude-teletype/claude-teletype diagnose
test -f dist/claude-teletype/_internal/libusb-1.0.dylib
test -f dist/claude-teletype/_internal/_sounddevice_data/portaudio-binaries/libportaudio.dylib
```

## Signing

Ad-hoc signing only for now (PKG-07 defers real Developer ID signing and
notarization). PyInstaller ad-hoc signs all collected binaries automatically
on Apple Silicon; no manual `codesign` step is needed for local use.
