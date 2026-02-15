"""Tests for the Textual split-screen TUI application."""

from textual.widgets import Footer, Header, Input, Log

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
    """Submitted prompt appears in the Log with '>' prefix."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:
        await pilot.press(*"test prompt")
        await pilot.press("enter")
        await pilot.pause()
        log = app.query_one("#output", Log)
        log_text = "\n".join(str(line) for line in log.lines)
        assert "> test prompt" in log_text


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
