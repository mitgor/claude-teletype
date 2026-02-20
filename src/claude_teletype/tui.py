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
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Log, Static

MAX_RETRIES: int = 3
BASE_DELAY: float = 1.0


class ConfirmSwapScreen(ModalScreen[bool]):
    """Confirmation dialog for backend hot-swap warning.

    Warns user that switching away from claude-cli will lose session context.
    Dismisses with True (confirm swap) or False (cancel).
    """

    CSS = """
    #confirm-dialog {
        align: center middle;
        width: 55;
        height: auto;
        border: thick $warning;
        background: $surface;
        padding: 1 2;
    }
    #confirm-title {
        text-style: bold;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }
    #confirm-message {
        margin-bottom: 1;
    }
    #confirm-button-row {
        margin-top: 1;
        align: center middle;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Static("Backend Switch Warning", id="confirm-title")
            yield Static(
                "Switching backends will lose your current session "
                "context. Conversation history from the claude-cli "
                "session cannot be transferred to the new backend."
                "\n\n"
                "Continue?",
                id="confirm-message",
            )
            with Horizontal(id="confirm-button-row"):
                yield Button(
                    "Switch Backend", variant="warning", id="confirm-swap-btn"
                )
                yield Button("Cancel", id="cancel-swap-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-swap-btn":
            self.dismiss(True)
        elif event.button.id == "cancel-swap-btn":
            self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)


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
        Binding("ctrl+t", "enter_typewriter", "Typewriter"),
        Binding("ctrl+comma", "open_settings", "Settings"),
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
        backend_name: str = "claude-cli",
        model_config: str = "",
        system_prompt: str = "",
        profile_name: str = "generic",
        all_profiles: dict | None = None,
        openai_api_key: str = "",
        openrouter_api_key: str = "",
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
        self._backend_name = backend_name
        self._model_config = model_config
        self._system_prompt = system_prompt
        self._profile_name = profile_name
        self._all_profiles = all_profiles or {}
        self._openai_api_key = openai_api_key
        self._openrouter_api_key = openrouter_api_key

    @property
    def session_id(self) -> str | None:
        """Current session ID for resume support. Read by CLI after exit."""
        return self._session_id

    def compose(self) -> ComposeResult:
        yield Header()
        yield Log(id="output", auto_scroll=True)
        yield Static("Turn 0 | Context: -- | -- | Printer: --", id="status-bar")
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

        # Check for system_prompt + claude-cli conflict (TUI-native toast)
        from claude_teletype.warnings import check_system_prompt_warning, should_warn_startup

        startup_warning = check_system_prompt_warning(
            self._backend_name, self._system_prompt
        )
        if startup_warning and should_warn_startup(
            self._backend_name, self._system_prompt
        ):
            self.notify(startup_warning, severity="warning", timeout=8)

        self.query_one("#prompt", Input).focus()
        self._update_status()

    async def on_unmount(self) -> None:
        """Clean up printer, transcript, and subprocess on app exit."""
        await self._kill_process()
        if self.printer is not None:
            self.printer.close()
        if self._transcript_close is not None:
            self._transcript_close()

    def _printer_info(self) -> str:
        """Return printer status string like 'juki/usb/connected' or 'none'."""
        from claude_teletype.printer import (
            CupsPrinterDriver,
            FilePrinterDriver,
            ProfilePrinterDriver,
            UsbPrinterDriver,
        )

        if self.printer is None:
            return "none"

        # Determine connection type from driver class
        driver = self.printer
        profile_name = self._profile_name

        if isinstance(driver, ProfilePrinterDriver):
            inner = driver._inner
        else:
            inner = driver

        if isinstance(inner, UsbPrinterDriver):
            conn_type = "usb"
        elif isinstance(inner, CupsPrinterDriver):
            conn_type = "cups"
        elif isinstance(inner, FilePrinterDriver):
            conn_type = "file"
        else:
            conn_type = "none"

        connected = "connected" if self.printer.is_connected else "disconnected"

        if profile_name and profile_name != "generic":
            return f"{profile_name}/{conn_type}/{connected}"
        if conn_type != "none":
            return f"{conn_type}/{connected}"
        return "none"

    def _update_status(self) -> None:
        """Update the status bar with current turn, context, and model info."""
        try:
            self.query_one("#status-bar", Static).update(
                f"Turn {self._turn_count} | Context: {self._context_pct} | {self._model_name} | Printer: {self._printer_info()}"
            )
        except Exception:
            pass

    def _flush_printer(self) -> None:
        """Flush the printer's WordWrapper so the last word isn't stranded."""
        pw = self._printer_write
        if pw is not None and hasattr(pw, "flush"):
            pw.flush()

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

    def action_enter_typewriter(self) -> None:
        """Switch to typewriter mode (no LLM, direct keyboard to screen+printer)."""
        from claude_teletype.typewriter_screen import TypewriterScreen

        self.push_screen(TypewriterScreen(
            base_delay_ms=self.base_delay_ms,
            printer=self.printer,
            no_audio=self.no_audio,
        ))

    def action_open_settings(self) -> None:
        """Open the settings modal to edit runtime configuration."""
        from claude_teletype.settings_screen import SettingsScreen

        self.push_screen(
            SettingsScreen(
                current_delay=self.base_delay_ms,
                current_no_audio=self.no_audio,
                current_backend=self._backend_name,
                current_model=self._model_config,
                current_profile=self._profile_name,
                available_profiles=(
                    sorted(self._all_profiles.keys())
                    if self._all_profiles
                    else ["generic"]
                ),
            ),
            callback=self._apply_settings,
        )

    def _apply_settings(self, result: dict | None) -> None:
        """Apply changed settings from the SettingsScreen modal.

        Updates delay, audio, backend, and profile based on the result dict.
        Backend changes create a new validated backend instance. When switching
        away from claude-cli, a confirmation dialog is shown first (context loss).
        Profile changes mutate the printer driver so the new profile's ESC
        sequences take effect on the next write. Settings are persisted to
        the config file.
        """
        if result is None:
            return

        self.base_delay_ms = result["delay"]
        self.no_audio = result["no_audio"]

        # Backend or model change: create new validated backend
        backend_changing = (
            result["backend"] != self._backend_name
            or result["model"] != self._model_config
        )

        if backend_changing:
            # Warn when switching AWAY FROM claude-cli (session context will be lost).
            # Switching between API backends (openai <-> openrouter) needs no warning
            # since they don't maintain persistent sessions.
            if (
                result["backend"] != self._backend_name
                and self._backend_name == "claude-cli"
            ):
                # Store pending result and show confirmation before swapping
                self._pending_swap_result = result
                self.push_screen(
                    ConfirmSwapScreen(),
                    callback=self._handle_swap_confirmation,
                )
            else:
                # Model-only change or non-claude-cli swap: proceed directly
                self._do_backend_swap(result)

        # Profile change: swap printer driver's profile or wrap/re-discover
        if result["profile"] != self._profile_name:
            self._profile_name = result["profile"]
            new_profile = self._all_profiles.get(result["profile"])
            if new_profile is not None:
                self._apply_printer_profile(new_profile)

        # Persist settings to config file
        self._save_settings()
        self._update_status()

    def _handle_swap_confirmation(self, confirmed: bool) -> None:
        """Handle the result of the backend swap confirmation dialog.

        If confirmed, proceed with backend swap using the stored pending result.
        If cancelled, discard the pending swap (other settings already applied).
        """
        result = getattr(self, "_pending_swap_result", None)
        self._pending_swap_result = None

        if confirmed and result is not None:
            self._do_backend_swap(result)
            self._save_settings()
            self._update_status()

    def _do_backend_swap(self, result: dict) -> None:
        """Execute the backend swap (create new backend, validate, update state)."""
        from claude_teletype.backends import BackendError, create_backend

        try:
            key_map = {"openai": self._openai_api_key, "openrouter": self._openrouter_api_key}
            new_backend = create_backend(
                backend=result["backend"],
                model=result["model"] or None,
                system_prompt=self._system_prompt or None,
                api_key=key_map.get(result["backend"]) or None,
            )
            new_backend.validate()
            self._backend = new_backend
            self._backend_name = result["backend"]
            self._model_config = result["model"]
        except BackendError as e:
            self.notify(str(e), severity="error")

    def _apply_printer_profile(self, new_profile) -> None:
        """Apply a new printer profile, wrapping or re-discovering if needed.

        Uses TUI-safe discovery (no interactive prompts, no stderr prints)
        when the current printer is disconnected or absent.
        """
        from claude_teletype.printer import (
            CupsPrinterDriver,
            ProfilePrinterDriver,
            discover_cups_printers,
            discover_usb_device,
            make_printer_output,
        )

        if isinstance(self.printer, ProfilePrinterDriver):
            # Already wrapped — just swap the profile
            self.printer.swap_profile(new_profile)
            return

        if new_profile.name == "generic":
            return

        # Printer is a raw driver (or NullPrinter) — need to wrap or discover
        if self.printer is not None and self.printer.is_connected:
            # Wrap the existing connected driver
            self.printer = ProfilePrinterDriver(self.printer, new_profile)
            self._printer_write = make_printer_output(self.printer)
        else:
            # No connected printer — TUI-safe discovery (no interactive input())
            driver = discover_usb_device()
            if driver is None:
                # Fallback: auto-select first CUPS USB printer (non-interactive)
                cups_printers = discover_cups_printers()
                if cups_printers:
                    driver = CupsPrinterDriver(cups_printers[0]["name"])
            if driver is not None:
                self.printer = ProfilePrinterDriver(driver, new_profile)
                self._printer_write = make_printer_output(self.printer)
                self.notify(f"Printer connected ({new_profile.name})")
            else:
                self.notify("No printer found", severity="warning")

    def _save_settings(self) -> None:
        """Persist current settings to the config file."""
        from claude_teletype.config import load_config, save_config

        try:
            cfg = load_config()
            cfg.delay = self.base_delay_ms
            cfg.no_audio = self.no_audio
            cfg.printer_profile = self._profile_name
            cfg.backend = self._backend_name
            cfg.model = self._model_config
            save_config(cfg)
        except Exception as exc:
            self.notify(f"Could not save settings: {exc}", severity="error")

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
                                msg = ERROR_MESSAGES[category]
                                if item.error_message:
                                    msg += f"\n  Detail: {item.error_message}"
                                log.write(f"\n[{msg}]\n")
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

                # Flush wrappers to emit any buffered word
                self._tui_wrapper.flush()
                log.write("\n")
                self._flush_printer()
                break

        except asyncio.CancelledError:
            if self._tui_wrapper is not None:
                self._tui_wrapper.flush()
                self._tui_wrapper = None
            log.write(" [interrupted]")
            self._flush_printer()
            raise
        except Exception as exc:
            from claude_teletype.errors import ErrorCategory

            if self._tui_wrapper is not None:
                self._tui_wrapper.flush()

            self._flush_printer()

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
