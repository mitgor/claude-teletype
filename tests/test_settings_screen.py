"""Tests for the SettingsScreen modal component and ConfirmSwapScreen."""

import pytest
from textual.app import App
from textual.widgets import Button, Input, Select, Static, Switch

from claude_teletype.settings_screen import SettingsScreen
from claude_teletype.tui import ConfirmSwapScreen

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


# --- ConfirmSwapScreen tests ---


class ConfirmSwapTestApp(App):
    """Minimal test app that pushes a ConfirmSwapScreen on mount."""

    def __init__(self):
        super().__init__()
        self.swap_confirmed = "NOT_SET"

    def on_mount(self) -> None:
        self.push_screen(
            ConfirmSwapScreen(),
            callback=self._on_confirm_result,
        )

    def _on_confirm_result(self, result) -> None:
        self.swap_confirmed = result


@pytest.mark.asyncio
async def test_confirm_swap_screen_composes():
    """ConfirmSwapScreen composes with warning message and buttons."""
    app = ConfirmSwapTestApp()
    async with app.run_test(size=(80, 50)) as pilot:
        assert app.screen.query_one("#confirm-title", Static) is not None
        assert app.screen.query_one("#confirm-message", Static) is not None
        assert app.screen.query_one("#confirm-swap-btn", Button) is not None
        assert app.screen.query_one("#cancel-swap-btn", Button) is not None
        # Verify the warning message mentions session context
        message = app.screen.query_one("#confirm-message", Static)
        assert "session" in str(message.render()).lower()


@pytest.mark.asyncio
async def test_confirm_swap_confirm_returns_true():
    """Clicking 'Switch Backend' dismisses with True."""
    app = ConfirmSwapTestApp()
    async with app.run_test(size=(80, 50)) as pilot:
        await pilot.click("#confirm-swap-btn")
        await pilot.pause()
        assert app.swap_confirmed is True


@pytest.mark.asyncio
async def test_confirm_swap_cancel_returns_false():
    """Clicking 'Cancel' dismisses with False."""
    app = ConfirmSwapTestApp()
    async with app.run_test(size=(80, 50)) as pilot:
        await pilot.click("#cancel-swap-btn")
        await pilot.pause()
        assert app.swap_confirmed is False


@pytest.mark.asyncio
async def test_confirm_swap_escape_returns_false():
    """Pressing Escape dismisses with False."""
    app = ConfirmSwapTestApp()
    async with app.run_test(size=(80, 50)) as pilot:
        await pilot.press("escape")
        await pilot.pause()
        assert app.swap_confirmed is False
