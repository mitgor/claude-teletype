"""Settings modal screen for the Textual TUI.

Presents form widgets for all configurable settings: character delay,
audio toggle, printer profile, LLM backend, and model name.
Save dismisses with a dict of current values; Cancel/Escape dismisses with None.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static, Switch


class SettingsScreen(ModalScreen[dict | None]):
    """Modal dialog for editing application settings."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    CSS = """
    #settings-dialog {
        align: center middle;
        width: 60;
        height: auto;
        max-height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
        overflow-y: auto;
    }
    #settings-title {
        text-style: bold;
        text-align: center;
        width: 100%;
    }
    .setting-label {
        margin-top: 1;
    }
    #button-row {
        margin-top: 1;
        align: center middle;
    }
    """

    def __init__(
        self,
        current_delay: float = 75.0,
        current_no_audio: bool = False,
        current_backend: str = "claude-cli",
        current_model: str = "",
        current_profile: str = "generic",
        available_profiles: list[str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._current_delay = current_delay
        self._current_no_audio = current_no_audio
        self._current_backend = current_backend
        self._current_model = current_model
        self._current_profile = current_profile
        self._available_profiles = available_profiles or ["generic"]

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-dialog"):
            yield Static("Settings", id="settings-title")

            yield Label("Character Delay (ms)", classes="setting-label")
            yield Input(
                value=str(self._current_delay),
                type="number",
                id="delay-input",
            )

            yield Label("Audio Enabled", classes="setting-label")
            yield Switch(value=not self._current_no_audio, id="audio-switch")

            yield Label("Printer Profile", classes="setting-label")
            yield Select[str](
                [(name, name) for name in self._available_profiles],
                value=self._current_profile,
                allow_blank=False,
                id="profile-select",
            )

            yield Label("LLM Backend", classes="setting-label")
            yield Select[str](
                [
                    ("Claude CLI", "claude-cli"),
                    ("OpenAI", "openai"),
                    ("OpenRouter", "openrouter"),
                ],
                value=self._current_backend,
                allow_blank=False,
                id="backend-select",
            )

            yield Label("Model", classes="setting-label")
            yield Input(
                value=self._current_model,
                id="model-input",
                placeholder="Leave empty for backend default",
            )

            with Horizontal(id="button-row"):
                yield Button("Save", variant="primary", id="save-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle Save and Cancel button clicks."""
        if event.button.id == "save-btn":
            delay_input = self.query_one("#delay-input", Input)
            try:
                delay = float(delay_input.value)
            except (ValueError, TypeError):
                delay = self._current_delay

            audio_switch = self.query_one("#audio-switch", Switch)
            profile_select = self.query_one("#profile-select", Select)
            backend_select = self.query_one("#backend-select", Select)
            model_input = self.query_one("#model-input", Input)

            self.dismiss(
                {
                    "delay": delay,
                    "no_audio": not audio_switch.value,
                    "backend": str(backend_select.value),
                    "model": model_input.value,
                    "profile": str(profile_select.value),
                }
            )
        elif event.button.id == "cancel-btn":
            self.dismiss(None)

    def action_cancel(self) -> None:
        """Handle Escape key binding."""
        self.dismiss(None)
