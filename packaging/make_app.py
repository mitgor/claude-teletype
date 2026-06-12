#!/usr/bin/env python3
"""Assemble "dist/Claude Teletype.app" around the PyInstaller onedir output.

PyInstaller's BUNDLE step is documented for windowed apps only: a
double-clicked console binary gets no tty, so Textual cannot start. Per
D009 the .app is instead assembled here around a Terminal launcher — a
shell script that asks Terminal.app to run the inner console binary in a
login shell (so the user's PATH applies and ``shutil.which("claude")``
finds Homebrew/npm installs).

Layout produced::

    dist/Claude Teletype.app/
      Contents/
        Info.plist                      CFBundleExecutable=launcher
        MacOS/launcher                  osascript Terminal trampoline
        Resources/claude-teletype/      copy of dist/claude-teletype/

The inner binary at Contents/Resources/claude-teletype/claude-teletype
stays directly runnable with full CLI args; the .app double-click is the
launchability garnish, not the primary surface.

Run after the onedir build (see packaging/README.md)::

    uv run python packaging/make_app.py
"""

from __future__ import annotations

import plistlib
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ONEDIR_BUILD_CMD = (
    "uv sync --extra usb --group packaging && "
    "uv run --group packaging pyinstaller --noconfirm packaging/claude-teletype.spec"
)
BUNDLE_IDENTIFIER = "com.omdsystems.claude-teletype"
BUNDLE_NAME = "Claude Teletype"

# The launcher computes the inner-binary path from its own location at
# runtime so the .app is relocatable, and single-quotes it for the shell
# command embedded in the AppleScript string (the path contains spaces).
# Terminal's "do script" runs a login shell, so the user's PATH applies.
LAUNCHER_SCRIPT = """\
#!/bin/sh
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$HERE/../Resources/claude-teletype/claude-teletype"
BIN="$(cd "$(dirname "$BIN")" && pwd)/$(basename "$BIN")"
# Single-quote for the shell command inside the AppleScript string;
# escape any single quotes in the path itself ('\\'' dance).
QUOTED="'$(printf '%s' "$BIN" | sed "s/'/'\\\\\\\\''/g")'"
exec /usr/bin/osascript \\
  -e "tell application \\"Terminal\\" to do script \\"exec $QUOTED\\"" \\
  -e 'tell application "Terminal" to activate'
"""


def project_version(pyproject: Path) -> str:
    """Read the project version from pyproject.toml."""
    return tomllib.loads(pyproject.read_text())["project"]["version"]


def info_plist(version: str) -> dict:
    return {
        "CFBundleExecutable": "launcher",
        "CFBundleName": BUNDLE_NAME,
        "CFBundleDisplayName": BUNDLE_NAME,
        "CFBundleIdentifier": BUNDLE_IDENTIFIER,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "LSMinimumSystemVersion": "11.0",
    }


def assemble_app(onedir: Path, app: Path, version: str) -> None:
    """Wipe and rebuild ``app`` from the onedir bundle at ``onedir``."""
    inner_binary = onedir / "claude-teletype"
    if not inner_binary.is_file():
        raise SystemExit(
            f"error: onedir bundle not found at {onedir}/claude-teletype.\n"
            f"Build it first:\n  {ONEDIR_BUILD_CMD}"
        )

    if app.exists():
        shutil.rmtree(app)

    contents = app / "Contents"
    # symlinks=True: PyInstaller onedir output contains framework symlinks
    # that must survive the copy or codesign --deep rejects the bundle.
    shutil.copytree(onedir, contents / "Resources" / "claude-teletype", symlinks=True)

    macos_dir = contents / "MacOS"
    macos_dir.mkdir(parents=True)
    launcher = macos_dir / "launcher"
    launcher.write_text(LAUNCHER_SCRIPT)
    launcher.chmod(0o755)

    with open(contents / "Info.plist", "wb") as f:
        plistlib.dump(info_plist(version), f)


def resign(app: Path) -> None:
    """Ad-hoc re-sign the assembled bundle (launcher changed the seal)."""
    subprocess.run(
        ["codesign", "--force", "--deep", "-s", "-", str(app)],
        check=True,
    )


def main() -> None:
    onedir = REPO_ROOT / "dist" / "claude-teletype"
    app = REPO_ROOT / "dist" / f"{BUNDLE_NAME}.app"
    version = project_version(REPO_ROOT / "pyproject.toml")

    assemble_app(onedir, app, version)
    resign(app)
    print(f"Assembled {app} (version {version}, ad-hoc signed)")


if __name__ == "__main__":
    main()
