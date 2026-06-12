"""Tests for SpeedModeScreen ModalScreen (Phase 26-01, FLOW-01, FLOW-02).

Pilot-style tests using Textual's run_test harness, mirroring the pattern
established by tests/test_settings_screen.py. The screen dismisses with
"typewriter", "instant", or None (cancel/escape).
"""

from __future__ import annotations

import pytest
from textual.app import App
from textual.screen import ModalScreen
from textual.widgets import Button, RadioButton, RadioSet, Static

from claude_teletype.screens.speed_mode import SpeedModeScreen


class _SpeedTestApp(App):
    """Minimal test app that pushes a SpeedModeScreen on mount."""

    def __init__(self, default_mode: str = "typewriter") -> None:
        super().__init__()
        self._default_mode = default_mode
        self.result: object = "NOT_SET"  # sentinel to distinguish from None

    def on_mount(self) -> None:
        self.push_screen(
            SpeedModeScreen(default_mode=self._default_mode),
            callback=self._on_result,
        )

    def _on_result(self, value) -> None:
        self.result = value


def test_speed_mode_screen_subclasses_modal_screen():
    """D-01: SpeedModeScreen must be a ModalScreen subclass."""
    assert issubclass(SpeedModeScreen, ModalScreen)


def test_invalid_default_mode_falls_back_to_typewriter():
    """Defensive: junk default_mode shouldn't crash; falls back to typewriter."""
    s = SpeedModeScreen(default_mode="garbage")
    assert s._default_mode == "typewriter"


@pytest.mark.asyncio
async def test_compose_yields_radio_and_buttons():
    """compose() yields title + RadioSet (with two RadioButtons) + button row."""
    app = _SpeedTestApp()
    async with app.run_test(size=(80, 30)) as pilot:
        screen = app.screen
        assert screen.query_one("#speed-title", Static) is not None
        assert screen.query_one("#speed-radio", RadioSet) is not None
        assert screen.query_one("#mode-typewriter", RadioButton) is not None
        assert screen.query_one("#mode-instant", RadioButton) is not None
        assert screen.query_one("#print-btn", Button) is not None
        assert screen.query_one("#cancel-btn", Button) is not None


@pytest.mark.asyncio
async def test_default_typewriter_preselects_typewriter_radio():
    """default_mode='typewriter' (impact/daisywheel) preselects typewriter."""
    app = _SpeedTestApp(default_mode="typewriter")
    async with app.run_test(size=(80, 30)) as pilot:
        rb_typewriter = app.screen.query_one("#mode-typewriter", RadioButton)
        rb_instant = app.screen.query_one("#mode-instant", RadioButton)
        assert rb_typewriter.value is True
        assert rb_instant.value is False


@pytest.mark.asyncio
async def test_default_instant_preselects_instant_radio():
    """FLOW-02: profile.instant_output -> default 'instant' preselected."""
    app = _SpeedTestApp(default_mode="instant")
    async with app.run_test(size=(80, 30)) as pilot:
        rb_typewriter = app.screen.query_one("#mode-typewriter", RadioButton)
        rb_instant = app.screen.query_one("#mode-instant", RadioButton)
        assert rb_typewriter.value is False
        assert rb_instant.value is True


@pytest.mark.asyncio
async def test_print_button_dismisses_with_selected_mode_typewriter():
    """Print button + typewriter preselected -> dismiss('typewriter')."""
    app = _SpeedTestApp(default_mode="typewriter")
    async with app.run_test(size=(80, 30)) as pilot:
        await pilot.click("#print-btn")
        await pilot.pause()
        assert app.result == "typewriter"


@pytest.mark.asyncio
async def test_print_button_dismisses_with_selected_mode_instant():
    """Print button + instant preselected -> dismiss('instant')."""
    app = _SpeedTestApp(default_mode="instant")
    async with app.run_test(size=(80, 30)) as pilot:
        await pilot.click("#print-btn")
        await pilot.pause()
        assert app.result == "instant"


@pytest.mark.asyncio
async def test_cancel_button_dismisses_with_none():
    """Cancel button -> dismiss(None) (FLOW-05 abort path)."""
    app = _SpeedTestApp()
    async with app.run_test(size=(80, 30)) as pilot:
        await pilot.click("#cancel-btn")
        await pilot.pause()
        assert app.result is None


@pytest.mark.asyncio
async def test_escape_dismisses_with_none():
    """escape key binding -> dismiss(None) (FLOW-05 abort path)."""
    app = _SpeedTestApp()
    async with app.run_test(size=(80, 30)) as pilot:
        await pilot.press("escape")
        await pilot.pause()
        assert app.result is None
