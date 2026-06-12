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

## .app bundle ("Claude Teletype.app")

After the onedir build, assemble the double-clickable app (D009):

```sh
uv run python packaging/make_app.py
```

This wipes and rebuilds `dist/Claude Teletype.app`, copying the onedir
output into `Contents/Resources/claude-teletype/` and installing a shell
launcher at `Contents/MacOS/launcher`, then ad-hoc re-signs the whole
bundle. **Double-clicking the .app opens Terminal running the TUI** — the
launcher asks Terminal.app to `exec` the inner console binary in a login
shell, so the user's PATH applies and the `claude` CLI is found wherever
Homebrew/npm put it. The .app is relocatable; the launcher resolves the
inner binary from its own location at runtime.

The inner binary stays directly runnable with full CLI args:

```sh
'dist/Claude Teletype.app/Contents/Resources/claude-teletype/claude-teletype' diagnose
```

### Gatekeeper note (clean-machine transfer)

The bundle is only **ad-hoc signed**. Apps transferred **without** a
quarantine xattr — USB drive, `scp`, AirDrop — launch fine. Apps
downloaded through a **browser** get quarantined and Gatekeeper will
refuse the ad-hoc signature (real signing + notarization is deferred —
PKG-07). The clean-machine tester must transfer via USB/scp/AirDrop, or
clear the flag with `xattr -dr com.apple.quarantine 'Claude Teletype.app'`.
