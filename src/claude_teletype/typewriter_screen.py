"""Typewriter mode screen for the Textual TUI.

Captures keystrokes via ``on_key``, buffers them in an ``asyncio.Queue``,
and processes each character through ``pace_characters()`` with multiplexed
output to the Log widget, optional printer, and optional audio destinations.

Escape pops the screen back to chat mode.
"""

from __future__ import annotations

import asyncio

from textual import events, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Log, Static


class TypewriterScreen(Screen):
    """Typewriter mode: keystrokes to screen with pacing and sound."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back to Chat"),
    ]

    CSS = """
    #typewriter-output {
        height: 1fr;
    }
    #typewriter-status {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        base_delay_ms: float = 75.0,
        printer=None,
        no_audio: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._base_delay_ms = base_delay_ms
        self._printer = printer
        self._no_audio = no_audio
        self._key_queue: asyncio.Queue[str] | None = None
        self._output_fn = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Log(id="typewriter-output", auto_scroll=True)
        printer_status = (
            "connected"
            if (self._printer is not None and self._printer.is_connected)
            else "none"
        )
        yield Static(
            f"TYPEWRITER MODE | Printer: {printer_status}",
            id="typewriter-status",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Wire up the keystroke queue and multiplexed output destinations."""
        from claude_teletype.audio import make_bell_output, make_keystroke_output
        from claude_teletype.output import make_output_fn
        from claude_teletype.printer import make_printer_output

        self._key_queue = asyncio.Queue()

        log = self.query_one("#typewriter-output", Log)
        destinations: list = [log.write]

        if self._printer is not None and self._printer.is_connected:
            destinations.append(make_printer_output(self._printer))

        if not self._no_audio:
            destinations.append(make_keystroke_output())
            destinations.append(make_bell_output())

        self._output_fn = make_output_fn(*destinations)
        self._process_keys()

    def on_key(self, event: events.Key) -> None:
        """Capture printable keys, Enter, and Tab into the keystroke queue."""
        if self._key_queue is None:
            return
        if event.is_printable and event.character:
            event.prevent_default()
            event.stop()
            self._key_queue.put_nowait(event.character)
        elif event.key == "enter":
            event.prevent_default()
            event.stop()
            self._key_queue.put_nowait("\n")
        elif event.key == "tab":
            event.prevent_default()
            event.stop()
            self._key_queue.put_nowait("\t")
        # Backspace intentionally ignored (typewriter authenticity -- append-only)

    @work(exclusive=True)
    async def _process_keys(self) -> None:
        """Continuously drain the keystroke queue with typewriter pacing."""
        from claude_teletype.pacer import pace_characters

        while True:
            char = await self._key_queue.get()
            await pace_characters(
                char,
                base_delay_ms=self._base_delay_ms,
                output_fn=self._output_fn,
            )
