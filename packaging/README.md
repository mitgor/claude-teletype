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

After every build, run the checked-in frozen smoke gate from the repo root:

```sh
bash packaging/smoke_frozen.sh
```

It asserts, against `dist/claude-teletype/`:

1. `--help` exits 0.
2. `diagnose` exits 0 and renders the full no-USB degradation surface:
   the `Profile Capabilities` table, the `star-line` row, and the
   "Built-in profiles only" footnote (R029 without hardware).
3. The pyusb dependency row reads **Installed** and no row reads
   "Not installed" — the R027 quiet-failure guard. A bundle built without
   `uv sync --extra usb` still exits 0 everywhere; only this check
   catches it.
4. `otool -L` over every bundled `.dylib`/`.so` shows **zero** load-command
   references to `/opt/homebrew` or `/usr/local`. A leaked Homebrew path
   works on the dev machine and breaks only on a clean machine.
5. Clean-machine approximation: `diagnose` re-run under
   `env -i HOME=$(mktemp -d) PATH=/usr/bin:/bin` still exits 0 and renders
   the capability table (no Homebrew PATH, no dev shell, fresh HOME).

Each check prints `PASS`/`FAIL`; the script exits non-zero on any failure
and ends with `FROZEN SMOKE: ALL PASS`.

### What the smoke script does NOT prove (R028 — human needed)

The script is a headless approximation. A physical clean-machine pass
(no Homebrew, no dev Python) must still verify, by hand:

- Launch on a real clean machine: detection, simulator, and print paths
  all work.
- Double-clicking `Claude Teletype.app` opens Terminal running the TUI.
- USB hardware behavior: a real printer is detected, and unplugging USB
  degrades to the CUPS/simulator fallback.

Two surfaces are **environment-dependent by design** and intentionally
outside the smoke gate: the openai voice backend needs `OPENAI_API_KEY`
in the environment, and the claude backend needs the `claude` CLI on the
user's PATH. On a clean machine without them, both degrade with their
existing `BackendError` messages — that is correct behavior, not a
packaging defect.

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
