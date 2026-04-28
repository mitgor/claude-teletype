"""Speed-mode dialog for markdown printing (Phase 26-01, FLOW-01, FLOW-02).

Per Phase 26 D-01: ModalScreen[str | None] dismissing with "typewriter",
"instant", or None on cancel. Default selection follows the active
profile's instant_output flag (D-02): receipt/laser printers default to
instant; daisywheel/dot-matrix default to typewriter pacing.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, RadioButton, RadioSet, Static


class SpeedModeScreen(ModalScreen[str | None]):
    """Two-option speed picker shown before each markdown print job.

    Dismisses with "typewriter" (pacer + audio path), "instant" (no per-char
    delay; instant mode chunks style writes at profile.buffer_bytes), or
    None on cancel/escape. The print job is aborted on None — no driver is
    opened, no transcript entry is written.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    CSS = """
    #speed-dialog {
        align: center middle;
        width: 50;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #speed-title {
        text-style: bold;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }
    #speed-radio {
        margin-bottom: 1;
    }
    #button-row {
        margin-top: 1;
        align: center middle;
    }
    """

    def __init__(self, default_mode: str = "typewriter", **kwargs) -> None:
        """Build the dialog.

        Args:
            default_mode: "typewriter" or "instant" — caller derives this
                from profile.instant_output per FLOW-02. Any other value
                falls back to "typewriter" defensively.
        """
        super().__init__(**kwargs)
        if default_mode not in ("typewriter", "instant"):
            default_mode = "typewriter"
        self._default_mode = default_mode

    def compose(self) -> ComposeResult:
        with Vertical(id="speed-dialog"):
            yield Static("Print speed?", id="speed-title")
            with RadioSet(id="speed-radio"):
                yield RadioButton(
                    "Typewriter pacing",
                    id="mode-typewriter",
                    value=(self._default_mode == "typewriter"),
                )
                yield RadioButton(
                    "Instant",
                    id="mode-instant",
                    value=(self._default_mode == "instant"),
                )
            with Horizontal(id="button-row"):
                yield Button("Print", variant="primary", id="print-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "print-btn":
            radio_set = self.query_one("#speed-radio", RadioSet)
            pressed = radio_set.pressed_button
            if pressed is not None and pressed.id == "mode-instant":
                self.dismiss("instant")
            else:
                # Default arm: typewriter mode (also handles None pressed).
                self.dismiss("typewriter")
        elif event.button.id == "cancel-btn":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
