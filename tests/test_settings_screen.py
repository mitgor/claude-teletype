"""Tests for the SettingsScreen modal component."""

import pytest
from textual.app import App
from textual.widgets import Button, Input, Select, Switch

from claude_teletype.settings_screen import SettingsScreen

DEFAULT_KWARGS = {
    "current_delay": 75.0,
    "current_no_audio": False,
    "current_backend": "claude-cli",
    "current_model": "",
    "current_profile": "generic",
    "available_profiles": ["generic", "juki", "escp"],
}


class SettingsTestApp(App):
    """Minimal test app that pushes a SettingsScreen on mount."""

    def __init__(self, **settings_kwargs):
        super().__init__()
        self._settings_kwargs = settings_kwargs
        self.applied_result = "NOT_SET"  # sentinel to distinguish from None

    def on_mount(self) -> None:
        self.push_screen(
            SettingsScreen(**self._settings_kwargs),
            callback=self._on_settings_result,
        )

    def _on_settings_result(self, result) -> None:
        self.applied_result = result


@pytest.mark.asyncio
async def test_settings_screen_composes():
    """SettingsScreen composes with all expected form widgets."""
    app = SettingsTestApp(**DEFAULT_KWARGS)
    async with app.run_test(size=(80, 50)) as pilot:
        assert app.screen.query_one("#delay-input", Input) is not None
        assert app.screen.query_one("#audio-switch", Switch) is not None
        assert app.screen.query_one("#profile-select", Select) is not None
        assert app.screen.query_one("#backend-select", Select) is not None
        assert app.screen.query_one("#model-input", Input) is not None
        assert app.screen.query_one("#save-btn", Button) is not None
        assert app.screen.query_one("#cancel-btn", Button) is not None


@pytest.mark.asyncio
async def test_settings_cancel_returns_none():
    """Clicking Cancel dismisses the modal and returns None."""
    app = SettingsTestApp(**DEFAULT_KWARGS)
    async with app.run_test(size=(80, 50)) as pilot:
        await pilot.click("#cancel-btn")
        await pilot.pause()
        assert app.applied_result is None


@pytest.mark.asyncio
async def test_settings_escape_returns_none():
    """Pressing Escape dismisses the modal and returns None."""
    app = SettingsTestApp(**DEFAULT_KWARGS)
    async with app.run_test(size=(80, 50)) as pilot:
        await pilot.press("escape")
        await pilot.pause()
        assert app.applied_result is None


@pytest.mark.asyncio
async def test_settings_save_returns_values():
    """Clicking Save dismisses the modal and returns a dict with current values."""
    app = SettingsTestApp(**DEFAULT_KWARGS)
    async with app.run_test(size=(80, 50)) as pilot:
        await pilot.click("#save-btn")
        await pilot.pause()
        assert app.applied_result is not None
        assert app.applied_result["delay"] == 75.0
        assert app.applied_result["no_audio"] is False
        assert app.applied_result["backend"] == "claude-cli"
        assert app.applied_result["profile"] == "generic"
