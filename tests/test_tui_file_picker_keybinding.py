"""Tests for ctrl+o keybinding integration: chat -> FilePickerScreen -> callback.

Covers PICK-01: user in main TUI session opens picker via keybinding. The
24-01 plan owns picker-internal behavior (filter, path display, dismiss).
This file owns the chat -> picker -> back integration.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from claude_teletype.printing.drivers import NullPrinterDriver
from claude_teletype.printing.registry import ProfileRegistry
from claude_teletype.screens.file_picker import FilePickerScreen
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
async def test_picker_dismiss_path_pushes_speed_dialog(tmp_path: Path):
    """Plan 26-03: Phase 24's notify('Selected: ...') stub is REPLACED.

    Picker dismiss with a Path now pushes SpeedModeScreen for the user
    to choose typewriter vs instant before the render runs.
    """
    from claude_teletype.screens.speed_mode import SpeedModeScreen

    target = (tmp_path / "doc.md").resolve()
    target.write_text("# Doc\n")
    app = _make_app()
    async with app.run_test(size=(80, 40)) as pilot:
        app.action_open_markdown()
        await pilot.pause()
        # Drive the picker dismiss directly with a Path -- equivalent to
        # the user activating a file node.
        app.screen.dismiss(target)
        await pilot.pause()
        # SpeedModeScreen is now on top of the stack
        assert isinstance(app.screen, SpeedModeScreen), (
            f"Expected SpeedModeScreen, got {type(app.screen).__name__}"
        )


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


# ------------------------------------------------------------------
# Plan 26-03: Speed dialog + render pipeline + transcript fan-out
# ------------------------------------------------------------------


class _CapturingDriver:
    """Mock printer driver that captures text + byte writes.

    is_connected=True so _run_print_pipeline does NOT short-circuit.
    """

    is_connected = True

    def __init__(self) -> None:
        self.text_writes: list[str] = []
        self.byte_writes: list[bytes] = []

    def write(self, char: str) -> None:
        self.text_writes.append(char)

    def write_bytes(self, data: bytes) -> None:
        self.byte_writes.append(data)

    def close(self) -> None:
        pass


def _make_app_with_capturing_driver(
    driver: _CapturingDriver | None = None,
    transcript_dir: Path | None = None,
    profile_name: str = "generic",
    registry: ProfileRegistry | None = None,
) -> TeletypeApp:
    """Construct a TeletypeApp wired to a capturing driver for render tests."""
    if driver is None:
        driver = _CapturingDriver()
    return TeletypeApp(
        base_delay_ms=0.0,
        printer=driver,
        no_audio=True,
        transcript_dir=str(transcript_dir) if transcript_dir is not None else None,
        backend=None,
        backend_name="claude-cli",
        profile_name=profile_name,
        registry=registry,
        discovery=None,
    )


@pytest.mark.asyncio
async def test_speed_mode_default_follows_profile_instant_output(tmp_path: Path):
    """FLOW-02: SpeedModeScreen.default_mode follows active profile.instant_output."""
    from claude_teletype.printing.profiles import BUILTIN_PROFILES
    from claude_teletype.screens.speed_mode import SpeedModeScreen

    target = (tmp_path / "doc.md").resolve()
    target.write_text("# Doc\n")

    # citizen-cts2000 has instant_output=True (receipt printer)
    citizen = BUILTIN_PROFILES.get("citizen-cts2000")
    assert citizen is not None and citizen.instant_output is True, (
        "Test setup: expected citizen-cts2000 to have instant_output=True"
    )

    app = _make_app_with_capturing_driver(
        profile_name="citizen-cts2000",
        registry=ProfileRegistry({"citizen-cts2000": citizen}),
    )
    async with app.run_test(size=(80, 40)) as pilot:
        app.action_open_markdown()
        await pilot.pause()
        app.screen.dismiss(target)
        await pilot.pause()
        assert isinstance(app.screen, SpeedModeScreen)
        assert app.screen._default_mode == "instant", (
            f"Expected default 'instant' for citizen-cts2000; "
            f"got {app.screen._default_mode!r}"
        )


@pytest.mark.asyncio
async def test_speed_mode_default_typewriter_for_juki(tmp_path: Path):
    """FLOW-02: juki profile (instant_output=False) defaults to 'typewriter'."""
    from claude_teletype.printing.profiles import BUILTIN_PROFILES
    from claude_teletype.screens.speed_mode import SpeedModeScreen

    target = (tmp_path / "doc.md").resolve()
    target.write_text("# Doc\n")

    juki = BUILTIN_PROFILES.get("juki")
    assert juki is not None, "Test setup: expected juki profile to exist"

    app = _make_app_with_capturing_driver(
        profile_name="juki",
        registry=ProfileRegistry({"juki": juki}),
    )
    async with app.run_test(size=(80, 40)) as pilot:
        app.action_open_markdown()
        await pilot.pause()
        app.screen.dismiss(target)
        await pilot.pause()
        assert isinstance(app.screen, SpeedModeScreen)
        assert app.screen._default_mode == "typewriter"


@pytest.mark.asyncio
async def test_speed_mode_dismiss_none_aborts_print(tmp_path: Path):
    """FLOW-01 cancel arm: speed-mode None dismiss -> no print starts.

    Driver receives no writes; _pending_print_path is cleared.
    """
    target = (tmp_path / "doc.md").resolve()
    target.write_text("# Doc\nbody\n")

    driver = _CapturingDriver()
    app = _make_app_with_capturing_driver(driver)
    async with app.run_test(size=(80, 40)) as pilot:
        app.action_open_markdown()
        await pilot.pause()
        app.screen.dismiss(target)
        await pilot.pause()
        # SpeedModeScreen is shown -- now cancel it
        app.screen.dismiss(None)
        await pilot.pause()
        # No writes reached the printer
        assert driver.text_writes == []
        assert driver.byte_writes == []
        # Pending path cleared
        assert getattr(app, "_pending_print_path", None) is None


@pytest.mark.asyncio
async def test_speed_mode_instant_runs_render_pipeline(tmp_path: Path):
    """FLOW-01 success arm: speed-mode 'instant' triggers a render."""
    target = (tmp_path / "doc.md").resolve()
    target.write_text("Hello\n")

    driver = _CapturingDriver()
    app = _make_app_with_capturing_driver(driver)
    async with app.run_test(size=(80, 40)) as pilot:
        app.action_open_markdown()
        await pilot.pause()
        app.screen.dismiss(target)
        await pilot.pause()
        # Now resolve the speed dialog with "instant"
        app.screen.dismiss("instant")
        await pilot.pause()
        # Driver received the body text
        body_text = "".join(driver.text_writes)
        assert "Hello" in body_text


@pytest.mark.asyncio
async def test_end_to_end_picker_speed_dialog_render_transcript(tmp_path: Path):
    """E2E (TXN-01..TXN-03 + FLOW-01..FLOW-04): full picker -> speed dialog
    -> renderer -> printer + transcript pipeline."""
    md = tmp_path / "doc.md"
    md.write_text("# Heading\n\nParagraph with **bold**.\n")
    md_resolved = md.resolve()

    transcript_dir = tmp_path / "transcripts"

    driver = _CapturingDriver()
    app = _make_app_with_capturing_driver(driver, transcript_dir=transcript_dir)
    async with app.run_test(size=(80, 30)) as pilot:
        # Drive the full pipeline: picker -> SpeedModeScreen -> render
        app.action_open_markdown()
        await pilot.pause()
        app.screen.dismiss(md_resolved)
        await pilot.pause()
        app.screen.dismiss("instant")
        await pilot.pause()

    # Plain-text body reached the printer
    body_text = "".join(driver.text_writes)
    assert "Heading" in body_text
    assert "Paragraph with bold" in body_text
    # No emphasis markers in printed text
    assert "**" not in body_text

    # Transcript file exists (created by on_mount via make_transcript_output)
    transcript_files = list(transcript_dir.glob("transcript-*.txt"))
    assert len(transcript_files) == 1, (
        f"Expected one transcript file; got: {transcript_files}"
    )
    transcript_content = transcript_files[0].read_text(encoding="utf-8")
    # TXN-01: "Printed file:" header
    assert "Printed file:" in transcript_content
    assert str(md_resolved) in transcript_content
    # TXN-02: no ESC bytes
    assert "\x1b" not in transcript_content
    # Body contained
    assert "Heading" in transcript_content
    assert "bold" in transcript_content


@pytest.mark.asyncio
async def test_renderer_close_called_on_print_exception(tmp_path: Path):
    """FLOW-05: if rendering raises mid-print, renderer.close() still runs."""
    md = tmp_path / "doc.md"
    md.write_text("**bold ")  # unclosed bold to leave _bold_open=True
    md_resolved = md.resolve()

    # Driver that raises after a few text chars to simulate cancel
    class FlakyDriver:
        is_connected = True

        def __init__(self) -> None:
            self.calls = 0

        def write(self, char: str) -> None:
            self.calls += 1
            if self.calls > 3:
                raise RuntimeError("simulated cancel")

        def write_bytes(self, data: bytes) -> None:
            pass

        def close(self) -> None:
            pass

    driver = FlakyDriver()
    app = _make_app_with_capturing_driver(driver)
    async with app.run_test(size=(80, 30)) as pilot:
        # Patch MarkdownRenderer.close to observe the FLOW-05 finally call
        with patch(
            "claude_teletype.rendering.markdown.MarkdownRenderer.close",
        ) as close_mock:
            # Drive the pipeline straight to render via internal helper
            # (avoids screen-stack timing dependencies for cancel-safety
            # assertion)
            app._run_print_pipeline(md_resolved, "instant")
            await pilot.pause()
            assert close_mock.called, (
                "FLOW-05: renderer.close() must be called in finally even "
                "when render raises"
            )
