"""Negative-path tests for the .app assembly script (packaging/make_app.py).

The packaging/ directory is not a package, so the module is loaded by path.
"""

import importlib.util
import plistlib
import shutil
import subprocess
from pathlib import Path

import pytest

_MAKE_APP_PATH = Path(__file__).resolve().parent.parent / "packaging" / "make_app.py"
_spec = importlib.util.spec_from_file_location("make_app", _MAKE_APP_PATH)
make_app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(make_app)


def test_missing_onedir_fails_loudly_naming_build_command(tmp_path):
    missing_onedir = tmp_path / "claude-teletype"
    with pytest.raises(SystemExit) as excinfo:
        make_app.assemble_app(missing_onedir, tmp_path / "Fake.app", "0.0.0")
    message = str(excinfo.value)
    assert "onedir bundle not found" in message
    assert "pyinstaller --noconfirm packaging/claude-teletype.spec" in message


def test_assemble_is_idempotent_and_wipes_stale_app(tmp_path):
    onedir = tmp_path / "claude-teletype"
    onedir.mkdir()
    (onedir / "claude-teletype").write_text("#!/bin/sh\n")
    app = tmp_path / "Test.app"

    make_app.assemble_app(onedir, app, "0.0.0")
    stale = app / "Contents" / "Resources" / "stale-marker"
    stale.write_text("left over from a previous assembly")

    make_app.assemble_app(onedir, app, "0.0.0")
    assert not stale.exists()
    launcher = app / "Contents" / "MacOS" / "launcher"
    assert launcher.is_file()
    assert launcher.stat().st_mode & 0o111, "launcher must be executable"
    with open(app / "Contents" / "Info.plist", "rb") as f:
        plist = plistlib.load(f)
    assert plist["CFBundleExecutable"] == "launcher"
    assert plist["CFBundleIdentifier"] == "com.omdsystems.claude-teletype"


@pytest.mark.skipif(shutil.which("sh") is None, reason="needs a POSIX shell")
def test_launcher_quotes_paths_with_spaces(tmp_path):
    """Drive the launcher with osascript stubbed out and assert the inner
    binary path (which contains spaces, like 'Claude Teletype.app') arrives
    fully quoted inside the AppleScript 'do script' command."""
    app = tmp_path / "Space Name.app"
    macos_dir = app / "Contents" / "MacOS"
    inner_dir = app / "Contents" / "Resources" / "claude-teletype"
    macos_dir.mkdir(parents=True)
    inner_dir.mkdir(parents=True)
    (inner_dir / "claude-teletype").write_text("#!/bin/sh\n")

    launcher = macos_dir / "launcher"
    # Redirect /usr/bin/osascript to a stub that echoes its arguments.
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    (stub_bin / "osascript").write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    (stub_bin / "osascript").chmod(0o755)
    launcher.write_text(
        make_app.LAUNCHER_SCRIPT.replace("/usr/bin/osascript", str(stub_bin / "osascript"))
    )
    launcher.chmod(0o755)

    result = subprocess.run(
        ["sh", str(launcher)], capture_output=True, text=True, check=True
    )
    expected_path = str(inner_dir / "claude-teletype")
    assert f"exec '{expected_path}'" in result.stdout
    assert 'tell application "Terminal" to activate' in result.stdout
