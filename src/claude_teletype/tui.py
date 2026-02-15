"""Textual split-screen TUI application for Claude Teletype.

Provides an interactive terminal simulator with a scrollable output pane (Log)
showing Claude's responses with typewriter pacing, and an input pane (Input)
for submitting prompts.
"""

import asyncio

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Input, Log


class TeletypeApp(App):
    """Split-screen terminal simulator for Claude Teletype."""

    TITLE = "Claude Teletype"

    CSS = """
    #output {
        height: 1fr;
    }
    #prompt {
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("ctrl+d", "quit", "Quit"),
    ]

    def __init__(
        self,
        base_delay_ms: float = 75.0,
        printer=None,
        no_audio: bool = False,
        transcript_dir: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.base_delay_ms = base_delay_ms
        self.printer = printer
        self.no_audio = no_audio
        self.transcript_dir = transcript_dir
        self._transcript_write = None
        self._transcript_close = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Log(id="output", auto_scroll=True)
        yield Input(id="prompt", placeholder="Type a prompt and press Enter...")
        yield Footer()

    def on_mount(self) -> None:
        """Focus the input widget on app start and initialize transcript."""
        from pathlib import Path

        from claude_teletype.transcript import make_transcript_output

        write_fn, close_fn = make_transcript_output(
            Path(self.transcript_dir) if self.transcript_dir else None
        )
        self._transcript_write = write_fn
        self._transcript_close = close_fn

        self.query_one("#prompt", Input).focus()

    def on_unmount(self) -> None:
        """Clean up printer and transcript on app exit."""
        if self.printer is not None:
            self.printer.close()
        if self._transcript_close is not None:
            self._transcript_close()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user pressing Enter in the input field."""
        prompt = event.value.strip()
        if not prompt:
            return

        event.input.clear()
        log = self.query_one("#output", Log)
        log.write(f"\n> {prompt}\n\n")

        # Write user prompt to transcript
        if self._transcript_write is not None:
            for ch in f"\n> {prompt}\n\n":
                self._transcript_write(ch)

        # Indicate thinking state
        self.query_one("#prompt", Input).placeholder = "Thinking..."

        self.stream_response(prompt)

    @work(exclusive=True)
    async def stream_response(self, prompt: str) -> None:
        """Background worker: stream Claude response with typewriter pacing."""
        from claude_teletype.audio import make_bell_output
        from claude_teletype.bridge import stream_claude_response
        from claude_teletype.output import make_output_fn
        from claude_teletype.pacer import pace_characters
        from claude_teletype.printer import make_printer_output

        log = self.query_one("#output", Log)

        destinations = [log.write]
        if self.printer is not None and self.printer.is_connected:
            printer_write = make_printer_output(self.printer)
            destinations.append(printer_write)

        if not self.no_audio:
            destinations.append(make_bell_output())

        if self._transcript_write is not None:
            destinations.append(self._transcript_write)

        output_fn = make_output_fn(*destinations)
        input_widget = self.query_one("#prompt", Input)

        try:
            async for chunk in stream_claude_response(prompt):
                await pace_characters(
                    chunk,
                    base_delay_ms=self.base_delay_ms,
                    output_fn=output_fn,
                )
            log.write("\n")
        except asyncio.CancelledError:
            log.write_line("\n[Cancelled]")
        except Exception as exc:
            log.write_line(f"\n[Error: {exc}]")
        finally:
            input_widget.placeholder = "Type a prompt and press Enter..."
