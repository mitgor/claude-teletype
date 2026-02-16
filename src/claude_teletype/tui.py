"""Textual split-screen TUI application for Claude Teletype.

Provides an interactive terminal simulator with a scrollable output pane (Log)
showing Claude's responses with typewriter pacing, and an input pane (Input)
for submitting prompts.
"""

import asyncio

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Input, Log, Static


class TeletypeApp(App):
    """Split-screen terminal simulator for Claude Teletype."""

    TITLE = "Claude Teletype"

    CSS = """
    #output {
        height: 1fr;
    }
    #status-bar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    #prompt {
        dock: bottom;
    }
    #prompt:disabled {
        opacity: 70%;
    }
    """

    BINDINGS = [
        Binding("ctrl+d", "quit", "Quit"),
        Binding("escape", "cancel_stream", "Cancel", show=False),
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
        self._printer_write = None
        self._prev_input_value = ""
        self._session_id: str | None = None
        self._turn_count: int = 0
        self._proc_holder: list = []
        self._model_name: str = "--"
        self._context_pct: str = "--"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Log(id="output", auto_scroll=True)
        yield Static("Turn 0 | Context: -- | --", id="status-bar")
        yield Input(id="prompt", placeholder="Type a prompt and press Enter...")
        yield Footer()

    def on_mount(self) -> None:
        """Focus the input widget on app start and initialize transcript + printer."""
        from pathlib import Path

        from claude_teletype.transcript import make_transcript_output

        write_fn, close_fn = make_transcript_output(
            Path(self.transcript_dir) if self.transcript_dir else None
        )
        self._transcript_write = write_fn
        self._transcript_close = close_fn

        if self.printer is not None and self.printer.is_connected:
            from claude_teletype.printer import make_printer_output

            self._printer_write = make_printer_output(self.printer)

        self.query_one("#prompt", Input).focus()

    async def on_unmount(self) -> None:
        """Clean up printer, transcript, and subprocess on app exit."""
        await self._kill_process()
        if self.printer is not None:
            self.printer.close()
        if self._transcript_close is not None:
            self._transcript_close()

    def _update_status(self) -> None:
        """Update the status bar with current turn, context, and model info."""
        self.query_one("#status-bar", Static).update(
            f"Turn {self._turn_count} | Context: {self._context_pct} | {self._model_name}"
        )

    def action_cancel_stream(self) -> None:
        """Cancel the current streaming response."""
        for worker in self.workers:
            if not worker.is_finished:
                worker.cancel()

    async def _kill_process(self) -> None:
        """Kill subprocess with SIGTERM -> wait 5s -> SIGKILL."""
        if not self._proc_holder:
            return
        proc = self._proc_holder[0]
        if proc.returncode is not None:
            self._proc_holder.clear()
            return
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        self._proc_holder.clear()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Print each character to printer as user types."""
        if self._printer_write is None:
            return
        new_val = event.value
        old_val = self._prev_input_value
        self._prev_input_value = new_val

        if len(new_val) > len(old_val) and new_val[: len(old_val)] == old_val:
            # Characters added at end (normal typing or paste)
            if not old_val:
                # First char — print prompt prefix
                for ch in "\nYou: ":
                    self._printer_write(ch)
            added = new_val[len(old_val) :]
            for ch in added:
                self._printer_write(ch)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user pressing Enter in the input field."""
        prompt = event.value.strip()
        if not prompt:
            return

        self._turn_count += 1
        event.input.clear()
        self._prev_input_value = ""
        log = self.query_one("#output", Log)

        # Turn separator (blank line before, except first turn)
        if self._turn_count > 1:
            log.write("\n")
            if self._transcript_write is not None:
                self._transcript_write("\n")
            if self._printer_write is not None:
                self._printer_write("\n")

        # Echo user prompt with label
        user_line = f"You: {prompt}\n\n"
        log.write(user_line)

        # Write user prompt to transcript (printer already got chars live)
        for ch in user_line:
            if self._transcript_write is not None:
                self._transcript_write(ch)

        # End-of-prompt newlines to printer
        if self._printer_write is not None:
            self._printer_write("\n")
            self._printer_write("\n")

        # Claude response label
        log.write("Claude: ")
        for ch in "Claude: ":
            if self._transcript_write is not None:
                self._transcript_write(ch)
            if self._printer_write is not None:
                self._printer_write(ch)

        # Indicate thinking state and block input
        input_widget = self.query_one("#prompt", Input)
        input_widget.placeholder = "Thinking..."
        input_widget.disabled = True

        self.stream_response(prompt)

    @work(exclusive=True)
    async def stream_response(self, prompt: str) -> None:
        """Background worker: stream Claude response with typewriter pacing."""
        from claude_teletype.audio import make_bell_output
        from claude_teletype.bridge import (
            StreamResult,
            calc_context_pct,
            extract_model_name,
            stream_claude_response,
        )
        from claude_teletype.output import make_output_fn
        from claude_teletype.pacer import pace_characters

        log = self.query_one("#output", Log)

        destinations = [log.write]
        if self._printer_write is not None:
            destinations.append(self._printer_write)

        if not self.no_audio:
            destinations.append(make_bell_output())

        if self._transcript_write is not None:
            destinations.append(self._transcript_write)

        output_fn = make_output_fn(*destinations)
        input_widget = self.query_one("#prompt", Input)

        try:
            async for item in stream_claude_response(
                prompt,
                session_id=self._session_id,
                proc_holder=self._proc_holder,
            ):
                if isinstance(item, StreamResult):
                    self._session_id = item.session_id
                    self._model_name = extract_model_name(item.model_usage) or "--"
                    self._context_pct = calc_context_pct(item.model_usage)
                    self._update_status()
                else:
                    await pace_characters(
                        item,
                        base_delay_ms=self.base_delay_ms,
                        output_fn=output_fn,
                    )
            log.write("\n")
        except asyncio.CancelledError:
            log.write(" [interrupted]")
            raise
        except Exception as exc:
            log.write_line(f"\n[Error: {exc}]")
        finally:
            await self._kill_process()
            input_widget.disabled = False
            input_widget.focus()
            input_widget.placeholder = "Type a prompt and press Enter..."
