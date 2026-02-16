"""Tests for the Textual split-screen TUI application."""

from unittest.mock import patch

import typer
from textual.widgets import Footer, Header, Input, Log, Static

from claude_teletype.cli import check_claude_installed
from claude_teletype.tui import TeletypeApp


async def test_layout_has_log_and_input():
    """Verify the split-screen layout contains Log and Input widgets."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:  # noqa: F841
        assert app.query_one("#output", Log) is not None
        assert app.query_one("#prompt", Input) is not None


async def test_layout_has_header_and_footer():
    """Verify Header and Footer are present."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:  # noqa: F841
        assert app.query_one(Header) is not None
        assert app.query_one(Footer) is not None


async def test_app_title():
    """App title is 'Claude Teletype'."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:  # noqa: F841
        assert app.title == "Claude Teletype"


async def test_enter_clears_input():
    """Input field clears after pressing Enter with text."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:
        await pilot.press(*"hello")
        await pilot.press("enter")
        input_widget = app.query_one("#prompt", Input)
        assert input_widget.value == ""


async def test_prompt_echoed_to_log():
    """Submitted prompt appears in the Log with 'You: ' label."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:
        await pilot.press(*"test prompt")
        await pilot.press("enter")
        await pilot.pause()
        log = app.query_one("#output", Log)
        log_text = "\n".join(str(line) for line in log.lines)
        assert "You: test prompt" in log_text


async def test_empty_input_not_submitted():
    """Pressing Enter with empty input does not write to the log."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:
        initial_line_count = len(app.query_one("#output", Log).lines)
        await pilot.press("enter")
        await pilot.pause()
        assert len(app.query_one("#output", Log).lines) == initial_line_count


async def test_whitespace_only_not_submitted():
    """Pressing Enter with whitespace-only input does not write to the log."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:
        initial_line_count = len(app.query_one("#output", Log).lines)
        await pilot.press("space", "space", "space")
        await pilot.press("enter")
        await pilot.pause()
        # Whitespace-only input should not be submitted
        # The input should still contain the spaces (not cleared)
        assert len(app.query_one("#output", Log).lines) == initial_line_count


async def test_custom_delay_stored():
    """base_delay_ms is stored on the app instance."""
    app = TeletypeApp(base_delay_ms=42.0)
    assert app.base_delay_ms == 42.0


async def test_default_delay():
    """Default base_delay_ms is 75.0."""
    app = TeletypeApp()
    assert app.base_delay_ms == 75.0


async def test_typing_sends_chars_to_printer():
    """Each typed character is sent to the printer in real-time."""
    app = TeletypeApp(base_delay_ms=0)
    printed: list[str] = []
    async with app.run_test() as pilot:
        app._printer_write = lambda ch: printed.append(ch)
        await pilot.press(*"hi")
        await pilot.pause()
    # First char triggers prefix "\nYou: " then "h", then "i"
    assert printed == ["\n", "Y", "o", "u", ":", " ", "h", "i"]


async def test_submit_sends_newlines_and_label_to_printer():
    """On submit, printer gets two newlines then 'Claude: ' label."""
    app = TeletypeApp(base_delay_ms=0)
    printed: list[str] = []
    async with app.run_test() as pilot:
        app._printer_write = lambda ch: printed.append(ch)
        await pilot.press(*"ab")
        await pilot.pause()
        printed.clear()  # Reset to only capture submit output
        await pilot.press("enter")
        await pilot.pause()
    # Two newlines for end-of-prompt, then "Claude: " label
    assert printed == ["\n", "\n", "C", "l", "a", "u", "d", "e", ":", " "]


async def test_backspace_does_not_send_to_printer():
    """Backspace/deletion does not send anything to the printer."""
    app = TeletypeApp(base_delay_ms=0)
    printed: list[str] = []
    async with app.run_test() as pilot:
        app._printer_write = lambda ch: printed.append(ch)
        await pilot.press(*"abc")
        await pilot.pause()
        printed.clear()
        await pilot.press("backspace")
        await pilot.pause()
    assert printed == []


async def test_no_printer_write_does_not_crash():
    """on_input_changed exits early when no printer is attached."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:
        # _printer_write is None by default, should not crash
        await pilot.press(*"hello")
        await pilot.pause()


async def test_status_bar_exists():
    """Status bar Static widget with id 'status-bar' is present in layout."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:  # noqa: F841
        status = app.query_one("#status-bar", Static)
        assert status is not None


async def test_input_disabled_during_streaming():
    """Input widget is disabled after submitting a prompt (before worker completes)."""
    disabled_seen = False

    app = TeletypeApp(base_delay_ms=0)
    # Replace stream_response with a no-op to prevent the finally block from re-enabling
    original_stream = app.stream_response
    app.stream_response = lambda prompt: None  # type: ignore[assignment]

    async with app.run_test() as pilot:
        await pilot.press(*"hello")
        await pilot.press("enter")
        await pilot.pause()
        input_widget = app.query_one("#prompt", Input)
        disabled_seen = input_widget.disabled

    app.stream_response = original_stream  # type: ignore[assignment]
    assert disabled_seen is True


async def test_escape_binding_exists():
    """Escape key binding is registered for cancel_stream action."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:  # noqa: F841
        binding_keys = [b.key for b in app.BINDINGS]
        assert "escape" in binding_keys


async def test_claude_label_in_log():
    """'Claude:' label appears in the log after submitting a prompt.

    Note: The space after 'Claude:' is deferred by WordWrapper (pending_space)
    and will appear when the first response word arrives. At test time, only
    'Claude:' is visible in the log.
    """
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:
        await pilot.press(*"hello")
        await pilot.press("enter")
        await pilot.pause()
        log = app.query_one("#output", Log)
        log_text = "\n".join(str(line) for line in log.lines)
        assert "Claude:" in log_text


async def test_turn_count_increments():
    """Turn count increments on each prompt submission."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:
        assert app._turn_count == 0
        await pilot.press(*"hello")
        await pilot.press("enter")
        assert app._turn_count == 1


async def test_tui_wrapper_initialized_to_none():
    """_tui_wrapper is None before streaming starts."""
    app = TeletypeApp(base_delay_ms=0)
    assert app._tui_wrapper is None


async def test_on_resize_handler_exists():
    """TeletypeApp has on_resize method for dynamic wrap width."""
    app = TeletypeApp(base_delay_ms=0)
    assert hasattr(app, "on_resize")
    assert callable(app.on_resize)


def test_check_claude_installed_missing():
    """check_claude_installed raises typer.Exit when claude binary not found."""
    import pytest

    with patch("claude_teletype.cli.shutil.which", return_value=None):
        with pytest.raises(typer.Exit) as exc_info:
            check_claude_installed()
        assert exc_info.value.exit_code == 1


def test_check_claude_installed_found():
    """check_claude_installed succeeds when claude binary is on PATH."""
    with patch("claude_teletype.cli.shutil.which", return_value="/usr/local/bin/claude"):
        # Should not raise
        check_claude_installed()
