"""Tests for ctrl+o keybinding integration: chat -> FilePickerScreen -> callback.

Covers PICK-01: user in main TUI session opens picker via keybinding. The
24-01 plan owns picker-internal behavior (filter, path display, dismiss).
This file owns the chat -> picker -> back integration.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from claude_teletype.file_picker_screen import FilePickerScreen
from claude_teletype.printer import NullPrinterDriver
from claude_teletype.tui import TeletypeApp

# ------------------------------------------------------------------
# Structural tests (no Pilot needed)
# ------------------------------------------------------------------


def test_ctrl_o_binding_registered():
    """PICK-01: ctrl+o is in TeletypeApp.BINDINGS bound to action open_markdown."""
    entries = [(b.key, b.action) for b in TeletypeApp.BINDINGS]
    assert ("ctrl+o", "open_markdown") in entries


def test_ctrl_o_no_duplicate():
    """No duplicate ctrl+o entries (conflict check from must_haves)."""
    keys = [b.key for b in TeletypeApp.BINDINGS]
    assert keys.count("ctrl+o") == 1


def test_open_markdown_action_exists():
    """action_open_markdown method exists with the right name (Textual convention)."""
    assert callable(getattr(TeletypeApp, "action_open_markdown", None))


def test_picker_result_handler_exists():
    """_handle_picker_result callback method exists."""
    assert callable(getattr(TeletypeApp, "_handle_picker_result", None))


def test_existing_bindings_intact():
    """Regression check: existing bindings (ctrl+d, ctrl+t, ctrl+comma, escape) untouched."""
    keys = [b.key for b in TeletypeApp.BINDINGS]
    for required in ("ctrl+d", "ctrl+t", "ctrl+comma", "escape"):
        assert required in keys, f"Missing existing binding: {required}"


# ------------------------------------------------------------------
# Pilot integration tests
# ------------------------------------------------------------------


def _make_app(transcript_dir: Path | None = None) -> TeletypeApp:
    """Construct a TeletypeApp wired for headless testing.

    - NullPrinterDriver: no real printer I/O.
    - no_audio=True: no sounddevice calls.
    - No backend: stream_response would fail if invoked, but tests don't
      invoke it.
    - discovery=None: no setup screen on mount (skips _show_setup_screen).
    """
    return TeletypeApp(
        base_delay_ms=0.0,
        printer=NullPrinterDriver(),
        no_audio=True,
        transcript_dir=str(transcript_dir) if transcript_dir is not None else None,
        backend=None,
        backend_name="claude-cli",
        discovery=None,
    )


@pytest.mark.asyncio
async def test_action_open_markdown_pushes_picker():
    """PICK-01: action_open_markdown pushes a FilePickerScreen onto the stack."""
    app = _make_app()
    async with app.run_test(size=(80, 40)) as pilot:
        # Trigger the action directly (Pilot keypress timing for ctrl+o is
        # platform-flaky in headless tests; the action handler IS the unit
        # of behavior -- Textual's binding layer just routes key -> action).
        app.action_open_markdown()
        await pilot.pause()
        assert isinstance(app.screen, FilePickerScreen)


@pytest.mark.asyncio
async def test_ctrl_o_keypress_opens_picker():
    """PICK-01: pressing ctrl+o (the actual key) opens the picker.

    This is the end-to-end binding test. If the action handler test passes
    but this one fails, the binding registration is broken.
    """
    app = _make_app()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.press("ctrl+o")
        await pilot.pause()
        assert isinstance(app.screen, FilePickerScreen), (
            f"Expected FilePickerScreen, got {type(app.screen).__name__}"
        )


@pytest.mark.asyncio
async def test_picker_cancel_returns_to_chat_silently():
    """PICK-04: cancel (escape) returns to chat, no notify emitted, no transcript change."""
    app = _make_app()
    notifications: list[str] = []
    async with app.run_test(size=(80, 40)) as pilot:
        with patch.object(
            app, "notify", side_effect=lambda msg, **_: notifications.append(msg)
        ):
            app.action_open_markdown()
            await pilot.pause()
            assert isinstance(app.screen, FilePickerScreen)
            # Picker handles escape -> dismiss(None). Drive directly to
            # avoid Pilot timing dependencies.
            app.screen.dismiss(None)
            await pilot.pause()
            # Back on the main TeletypeApp chat screen
            assert not isinstance(app.screen, FilePickerScreen)
            # Silent: no notify
            assert notifications == [], (
                f"Cancel must not notify; got: {notifications}"
            )


@pytest.mark.asyncio
async def test_picker_selection_emits_notify_with_path(tmp_path: Path):
    """PICK-01 + PICK-05 smoke: selecting a Path emits 'Selected: <path>' notify."""
    target = (tmp_path / "doc.md").resolve()
    target.write_text("# Doc\n")
    app = _make_app()
    notifications: list[str] = []
    async with app.run_test(size=(80, 40)) as pilot:
        with patch.object(
            app, "notify", side_effect=lambda msg, **_: notifications.append(msg)
        ):
            app.action_open_markdown()
            await pilot.pause()
            # Drive the picker dismiss directly. Equivalent to the user
            # activating a file node -- same callback path runs.
            app.screen.dismiss(target)
            await pilot.pause()
            assert not isinstance(app.screen, FilePickerScreen)
            assert any(
                f"Selected: {target}" in msg for msg in notifications
            ), f"Expected 'Selected: {target}' in notify; got: {notifications}"


@pytest.mark.asyncio
async def test_picker_opens_during_disabled_input():
    """ctrl+o is App-level: works even when the input prompt is disabled
    (simulating mid-stream state)."""
    from textual.widgets import Input

    app = _make_app()
    async with app.run_test(size=(80, 40)) as pilot:
        # Disable input to simulate "Thinking..." mid-stream state
        input_widget = app.query_one("#prompt", Input)
        input_widget.disabled = True
        await pilot.pause()
        await pilot.press("ctrl+o")
        await pilot.pause()
        assert isinstance(app.screen, FilePickerScreen), (
            "ctrl+o must open the picker even when input is disabled"
        )
