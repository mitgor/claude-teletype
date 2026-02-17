"""Textual split-screen TUI application for Claude Teletype.

Provides an interactive terminal simulator with a scrollable output pane (Log)
showing Claude's responses with typewriter pacing, and an input pane (Input)
for submitting prompts.
"""

import asyncio
import random

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Input, Log, Static

MAX_RETRIES: int = 3
BASE_DELAY: float = 1.0


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
        resume_session_id: str | None = None,
        backend=None,
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
        self._session_id: str | None = resume_session_id
        self._turn_count: int = 0
        self._backend = backend
        self._model_name: str = "--"
        self._context_pct: str = "--"
        self._tui_wrapper = None

    @property
    def session_id(self) -> str | None:
        """Current session ID for resume support. Read by CLI after exit."""
        return self._session_id

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

        if self._session_id is not None:
            log = self.query_one("#output", Log)
            log.write(f"Resumed session {self._session_id[:8]}...\n\n")
            self.query_one("#prompt", Input).placeholder = (
                "Resumed session. Type a prompt and press Enter..."
            )

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

    def on_resize(self, event) -> None:
        """Update TUI word wrap width when terminal is resized."""
        if self._tui_wrapper is not None:
            log = self.query_one("#output", Log)
            new_width = max(1, log.size.width - log.scrollbar_size_vertical)
            self._tui_wrapper.width = new_width

    def action_cancel_stream(self) -> None:
        """Cancel the current streaming response."""
        for worker in self.workers:
            if not worker.is_finished:
                worker.cancel()

    async def _kill_process(self) -> None:
        """Kill subprocess with SIGTERM -> wait 5s -> SIGKILL.

        For Claude CLI backend, uses the backend's proc_holder for subprocess
        lifecycle management. For API backends, this is a no-op.
        """
        if self._backend is not None and hasattr(self._backend, 'proc_holder'):
            proc_holder = self._backend.proc_holder
        else:
            return
        if not proc_holder:
            return
        proc = proc_holder[0]
        if proc.returncode is not None:
            proc_holder.clear()
            return
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except TimeoutError:
            proc.kill()
            await proc.wait()
        proc_holder.clear()

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

        # Claude response label (transcript + printer only; TUI label flows
        # through WordWrapper in stream_response for accurate column tracking)
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
        """Background worker: stream Claude response with typewriter pacing.

        Implements retry with exponential backoff for transient errors
        (rate_limit, overloaded). Non-retryable errors show classified
        messages. Session recovery resets session_id before retry.
        """
        from claude_teletype.audio import make_bell_output
        from claude_teletype.bridge import (
            StreamResult,
            calc_context_pct,
            extract_model_name,
        )
        from claude_teletype.errors import ERROR_MESSAGES, classify_error, is_retryable
        from claude_teletype.output import make_output_fn
        from claude_teletype.pacer import pace_characters
        from claude_teletype.wordwrap import WordWrapper

        log = self.query_one("#output", Log)

        # TUI output goes through WordWrapper for word-boundary wrapping.
        # Printer, audio, and transcript receive original unwrapped characters
        # via output_fn (no wrapper).
        effective_width = max(1, log.size.width - log.scrollbar_size_vertical)
        self._tui_wrapper = WordWrapper(effective_width, log.write)

        destinations = [self._tui_wrapper.feed]
        if self._printer_write is not None:
            destinations.append(self._printer_write)

        if not self.no_audio:
            destinations.append(make_bell_output())

        if self._transcript_write is not None:
            destinations.append(self._transcript_write)

        output_fn = make_output_fn(*destinations)
        input_widget = self.query_one("#prompt", Input)

        # Write "Claude: " label through wrapper for accurate column tracking
        for ch in "Claude: ":
            self._tui_wrapper.feed(ch)

        retries = 0

        try:
            while True:
                has_text = False
                should_retry = False

                async for item in self._backend.stream(prompt):
                    if isinstance(item, StreamResult):
                        if item.is_error:
                            category = classify_error(item.error_message)

                            # Session recovery: reset session_id BEFORE retry
                            if self._session_id is not None:
                                self._session_id = None

                            # Only retry if no text streamed yet (avoid duplication)
                            if (
                                not has_text
                                and is_retryable(category)
                                and retries < MAX_RETRIES
                            ):
                                retries += 1
                                delay = BASE_DELAY * (2 ** (retries - 1)) + random.uniform(0, 1)
                                log.write(
                                    f"\n[{ERROR_MESSAGES[category]} "
                                    f"Retrying in {delay:.0f}s... "
                                    f"(attempt {retries}/{MAX_RETRIES})]\n"
                                )
                                await asyncio.sleep(delay)
                                should_retry = True
                                break  # Break inner loop to retry
                            else:
                                # Non-retryable or max retries exhausted
                                log.write(f"\n[{ERROR_MESSAGES[category]}]\n")
                        else:
                            # Update session_id from backend (Claude CLI updates it;
                            # API backends don't use it)
                            if hasattr(self._backend, 'session_id'):
                                self._session_id = self._backend.session_id

                        self._model_name = (
                            extract_model_name(item.model_usage) or item.model or "--"
                        )
                        self._context_pct = calc_context_pct(item.model_usage)
                        self._update_status()
                    else:
                        has_text = True
                        await pace_characters(
                            item,
                            base_delay_ms=self.base_delay_ms,
                            output_fn=output_fn,
                        )

                if should_retry:
                    continue  # Retry the outer while loop

                # Flush wrapper before final newline to emit buffered word
                self._tui_wrapper.flush()
                log.write("\n")
                break

        except asyncio.CancelledError:
            if self._tui_wrapper is not None:
                self._tui_wrapper.flush()
                self._tui_wrapper = None
            log.write(" [interrupted]")
            raise
        except Exception as exc:
            from claude_teletype.errors import ErrorCategory

            if self._tui_wrapper is not None:
                self._tui_wrapper.flush()

            category = classify_error(str(exc))
            if category != ErrorCategory.UNKNOWN:
                log.write(f"\n[{ERROR_MESSAGES[category]}]\n")
            else:
                log.write(f"\n[Error: {exc}]\n")
        finally:
            self._tui_wrapper = None
            await self._kill_process()
            input_widget.disabled = False
            input_widget.focus()
            input_widget.placeholder = "Type a prompt and press Enter..."
