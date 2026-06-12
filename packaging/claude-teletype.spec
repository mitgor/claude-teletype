# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the claude-teletype onedir bundle (R026, R027).

Build (see packaging/README.md):
    uv sync --extra usb --group packaging
    uv run --group packaging pyinstaller --noconfirm packaging/claude-teletype.spec

Notes:
- libusb-1.0.dylib is bundled explicitly from Homebrew (R027). The pyusb
  contrib hook (hook-usb) may also bundle libusb via a build-time
  usb.core.find() — harmless duplication; if it misbehaves, set
  PYINSTALLER_USB_HOOK_SKIP_PYUSB_DISCOVERY=1 in the build environment.
- PortAudio is NOT hand-bundled: the contrib hook-sounddevice collects the
  wheel-vendored libportaudio.dylib. numpy/rich/platformdirs/certifi all
  have contrib hooks too — do not hand-collect them.
- Never hardcode bundle-relative paths except via sys._MEIPASS: PyInstaller
  6.x relocates all code and data into the _internal/ directory.
"""

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Build-machine prerequisite: the Homebrew libusb dylib must exist so it can
# be bundled. Fail loudly here rather than producing a silently-broken bundle
# whose frozen pyusb backend can never load (a quiet R027 failure).
LIBUSB_DYLIB = "/opt/homebrew/lib/libusb-1.0.dylib"
if not os.path.exists(LIBUSB_DYLIB):
    raise SystemExit(
        f"BUILD-MACHINE prerequisite missing: {LIBUSB_DYLIB} not found.\n"
        "Run 'brew install libusb' on the BUILD machine (end users never "
        "need Homebrew — the dylib ships inside the bundle)."
    )

# textual 7.x lazy-loads widgets via module-level __getattr__ and has NO
# PyInstaller contrib hook, so static analysis misses every widget module.
# collect_submodules is MANDATORY or the frozen app crashes on first widget
# import.
hiddenimports = collect_submodules("textual.widgets")

a = Analysis(
    ["entry.py"],
    pathex=[],
    binaries=[(LIBUSB_DYLIB, ".")],
    datas=collect_data_files("textual"),
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="claude-teletype",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="claude-teletype",
)
