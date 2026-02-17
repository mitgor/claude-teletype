"""Tests for the TypewriterScreen TUI component."""

import asyncio

import pytest
from textual.app import App

from claude_teletype.typewriter_screen import TypewriterScreen


class TypewriterTestApp(App):
    """Minimal test app that pushes a TypewriterScreen on mount."""

    def __init__(self, **tw_kwargs):
        super().__init__()
        self._tw_kwargs = tw_kwargs

    def on_mount(self) -> None:
        self.push_screen(TypewriterScreen(**self._tw_kwargs))


@pytest.mark.asyncio
async def test_typewriter_screen_composes():
    """TypewriterScreen composes with Log, Static status, Header, and Footer."""
    app = TypewriterTestApp(no_audio=True, base_delay_ms=0)
    async with app.run_test() as pilot:
        from textual.widgets import Log, Static

        # Verify the Log widget with the expected id exists
        log = app.screen.query_one("#typewriter-output", Log)
        assert log is not None

        # Verify the status bar Static exists with expected text
        status = app.screen.query_one("#typewriter-status", Static)
        # Access the internal content string (Static stores it as __content)
        assert "TYPEWRITER MODE" in str(status._Static__content)


@pytest.mark.asyncio
async def test_typewriter_screen_captures_printable_key():
    """Pressing a printable key shows the character in the Log widget."""
    app = TypewriterTestApp(no_audio=True, base_delay_ms=0)
    async with app.run_test() as pilot:
        await pilot.press("a")
        # Give the worker a moment to process the queue
        await asyncio.sleep(0.15)
        from textual.widgets import Log

        log = app.screen.query_one("#typewriter-output", Log)
        # Log.lines contains the written content
        content = "\n".join(str(line) for line in log.lines)
        assert "a" in content


@pytest.mark.asyncio
async def test_typewriter_screen_enter_produces_newline():
    """Pressing Enter produces a newline in the Log output."""
    app = TypewriterTestApp(no_audio=True, base_delay_ms=0)
    async with app.run_test() as pilot:
        await pilot.press("x")
        await asyncio.sleep(0.1)
        await pilot.press("enter")
        await asyncio.sleep(0.15)
        from textual.widgets import Log

        log = app.screen.query_one("#typewriter-output", Log)
        content = "\n".join(str(line) for line in log.lines)
        # After "x" + Enter, the log should have received both
        assert "x" in content
        # The newline should have been processed (Log.write("\n") creates a new line)
        assert len(log.lines) >= 2 or "\n" in content


@pytest.mark.asyncio
async def test_typewriter_screen_escape_pops():
    """Pressing Escape pops the TypewriterScreen and returns to default."""
    app = TypewriterTestApp(no_audio=True, base_delay_ms=0)
    async with app.run_test() as pilot:
        # Confirm we're on the TypewriterScreen
        assert isinstance(app.screen, TypewriterScreen)

        await pilot.press("escape")
        await asyncio.sleep(0.1)

        # After escape, the TypewriterScreen should be popped
        assert not isinstance(app.screen, TypewriterScreen)
