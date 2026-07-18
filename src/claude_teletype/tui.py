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

from claude_teletype.setup_decision import SetupDecision

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
        Binding("ctrl+o", "open_markdown", "Open MD"),
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
        discovery=None,  # DiscoveryResult | None -- device data for the setup screen
        setup_decision: SetupDecision | None = None,
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
        self._discovery = discovery
        if setup_decision is None and discovery is not None:
            # Back-compat for direct constructions (tests, embedders) that
            # predate SetupDecision: a provided DiscoveryResult meant "show
            # setup". cli.py always passes an explicit decision (REF-04).
            setup_decision = SetupDecision.SHOW_SETUP
        self._setup_decision = setup_decision

    @property
    def session_id(self) -> str | None:
        """Current session ID for resume support. Read by CLI after exit."""
        return self._session_id

    def _needs_printer_setup(self) -> bool:
        """Check if printer setup screen should be shown on startup.

        Shows setup only for SetupDecision.SHOW_SETUP (every skip reason —
        no-tui, --device override, saved-printer match — bypasses it) AND
        when no printer is already configured (None or NullPrinterDriver).
        """
        if self._setup_decision is not SetupDecision.SHOW_SETUP:
            return False
        from claude_teletype.printing.drivers import NullPrinterDriver
        return self.printer is None or isinstance(self.printer, NullPrinterDriver)

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
            from claude_teletype.printing.drivers import make_printer_output

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

        if self._needs_printer_setup():
            self.call_after_refresh(self._show_setup_screen)

        self.query_one("#prompt", Input).focus()
        self._update_status()

    def _show_setup_screen(self) -> None:
        """Push the printer setup screen (deferred via call_after_refresh)."""
        from claude_teletype.screens.printer_setup import PrinterSetupScreen

        self.push_screen(
            PrinterSetupScreen(
                discovery=self._discovery,
                all_profiles=self._all_profiles,
            ),
            callback=self._handle_setup_result,
        )

    def _handle_setup_result(self, result) -> None:
        """Handle PrinterSelection from setup screen dismiss.

        None = user skipped (simulator mode). PrinterSelection = create driver.
        """
        if result is None:
            # Skip -- simulator mode, printer stays NullPrinterDriver
            # Clear saved printer so setup shows again next time
            self._clear_saved_printer()
            self._update_status()
            self.query_one("#prompt", Input).focus()
            return

        from claude_teletype.printing.drivers import make_printer_output
        from claude_teletype.printing.selection import create_driver_for_selection

        driver = create_driver_for_selection(
            result, self._discovery, all_profiles=self._all_profiles
        )
        self.printer = driver

        # Update profile name from selection
        self._profile_name = result.profile_name

        # Persist printer selection to config (CFG-01)
        self._save_printer_selection(result)

        # Set up printer output if driver is connected
        if driver.is_connected:
            self._printer_write = make_printer_output(driver)

        self._update_status()
        self.query_one("#prompt", Input).focus()

    def _save_printer_selection(self, selection) -> None:
        """Save printer selection from setup screen to config file."""
        from claude_teletype.config import load_config, save_config

        try:
            # Build device identifier first (CR-03): an empty id for a
            # usb/cups selection is a broken state and must never be
            # persisted.
            printer_id = ""
            if selection.connection_type == "usb" and self._discovery is not None:
                if (
                    selection.device_index is not None
                    and selection.device_index < len(self._discovery.usb_devices)
                ):
                    usb_dev = self._discovery.usb_devices[selection.device_index]
                    printer_id = f"{usb_dev.vendor_id:04x}:{usb_dev.product_id:04x}"
            elif selection.connection_type == "cups" and selection.cups_printer_name:
                printer_id = selection.cups_printer_name

            if selection.connection_type in ("usb", "cups") and not printer_id:
                return  # refuse to persist a broken empty-id selection

            cfg = load_config()
            cfg.saved_printer_type = selection.connection_type
            cfg.saved_printer_id = printer_id
            cfg.saved_printer_profile = selection.profile_name
            save_config(cfg)
        except Exception as exc:
            self.notify(f"Could not save printer config: {exc}", severity="error")

    def _clear_saved_printer(self) -> None:
        """Clear saved printer selection from config."""
        from claude_teletype.config import load_config, save_config

        try:
            cfg = load_config()
            if cfg.saved_printer_type:
                cfg.saved_printer_type = ""
                cfg.saved_printer_id = ""
                cfg.saved_printer_profile = ""
                save_config(cfg)
        except Exception:
            pass  # Non-critical

    async def on_unmount(self) -> None:
        """Clean up printer, transcript, and subprocess on app exit."""
        await self._kill_process()
        if self.printer is not None:
            self.printer.close()
        if self._transcript_close is not None:
            self._transcript_close()

    def _printer_info(self) -> str:
        """Return printer status string like 'juki/usb/connected' or 'none'."""
        from claude_teletype.printing.drivers import (
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
        from claude_teletype.screens.typewriter import TypewriterScreen

        self.push_screen(TypewriterScreen(
            base_delay_ms=self.base_delay_ms,
            printer=self.printer,
            no_audio=self.no_audio,
        ))

    def action_open_markdown(self) -> None:
        """Open the markdown file picker and route the chosen path through
        ``_handle_picker_result``.

        Bound to ``ctrl+o`` (mnemonic: "open file"). The picker is rooted at
        ``Path.cwd()`` per PICK-02. Dismiss returns ``Path | None``; the
        callback handles both arms.

        Phase 24 stops at notify() acknowledgement; Phase 26 will replace the
        callback body with the speed dialog + Phase 23's renderer pipeline.
        Until then the binding is the user-visible proof-of-life that the
        picker works end-to-end (PICK-01). The handler name is
        binding-agnostic so the BINDINGS line can be changed (e.g. to
        ctrl+shift+o or ctrl+p) without touching this method.
        """
        from claude_teletype.screens.file_picker import FilePickerScreen

        self.push_screen(FilePickerScreen(), callback=self._handle_picker_result)

    def action_open_settings(self) -> None:
        """Open the settings modal to edit runtime configuration."""
        from claude_teletype.screens.settings import SettingsScreen

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

    def _handle_picker_result(self, result) -> None:
        """Handle FilePickerScreen dismiss.

        ``None`` (escape / q): silent return to chat, no toast, no transcript
        entry, no printer state change (PICK-04). Input focus is restored so
        the user can keep typing.

        ``Path`` (Plan 26-03): determine the default speed mode from the
        active profile's ``instant_output`` flag (FLOW-02), stash the path
        on ``self._pending_print_path`` so the speed-mode callback can
        access it, then push ``SpeedModeScreen``. The render + transcript
        pipeline runs in ``_handle_speed_mode_result`` after the user
        chooses typewriter/instant or cancels.
        """
        from pathlib import Path

        if result is None:
            # Cancel: silent no-op + restore focus
            self.query_one("#prompt", Input).focus()
            return

        path: Path = result
        # FLOW-02: default speed-mode follows active profile.instant_output.
        # Receipt/laser printers (citizen-cts2000) -> 'instant' default;
        # daisywheel/dot-matrix (juki, oki) -> 'typewriter' default.
        active_profile = (
            self._all_profiles.get(self._profile_name)
            if self._all_profiles
            else None
        )
        default_mode = (
            "instant"
            if (
                active_profile is not None
                and getattr(active_profile, "instant_output", False)
            )
            else "typewriter"
        )

        # Store the path for the speed-mode callback. This is the cleanest
        # way to thread context through Textual's screen-callback API
        # without a closure.
        self._pending_print_path = path

        from claude_teletype.screens.speed_mode import SpeedModeScreen

        self.push_screen(
            SpeedModeScreen(default_mode=default_mode),
            callback=self._handle_speed_mode_result,
        )

    def _handle_speed_mode_result(self, speed_mode) -> None:
        """SpeedModeScreen dismiss callback (Plan 26-03).

        ``None``: user cancelled the dialog -> abort print, refocus prompt.
        ``"typewriter"`` / ``"instant"``: run the render + transcript pipeline.
        """
        pending = getattr(self, "_pending_print_path", None)
        # Always clear so a stale pending path can't leak into the next
        # dialog cycle.
        self._pending_print_path = None

        if speed_mode is None or pending is None:
            self.query_one("#prompt", Input).focus()
            return

        self._run_print_pipeline(pending, speed_mode)
        self.query_one("#prompt", Input).focus()

    def _run_print_pipeline(self, path, speed_mode: str) -> None:
        """Execute renderer + transcript fan-out for a printed markdown file.

        Synchronous (matches Plan 25-02's MarkdownPickerApp._on_pick locked
        choice). Catches all exceptions and surfaces them via notify() so
        the chat session survives a bad print.

        FLOW-05: ``renderer.close()`` runs in ``finally`` so cancel mid-render
        leaves the printer style state clean (no leaked bold/italic ESC bytes).

        TXN-01..03: when ``self._transcript_write`` is non-None, the renderer's
        text channel is fanned out into a parallel collector (TXN-02:
        plain-text only, no ESC bytes) and ``write_printed_file`` records a
        "Printed file: <abs path>" header followed by the body (TXN-01).
        """
        from claude_teletype.printing.drivers import chunk_writes
        from claude_teletype.rendering.markdown import MarkdownRenderer
        from claude_teletype.rendering.wordwrap import WordWrapper
        from claude_teletype.transcript import write_printed_file

        if self.printer is None or not self.printer.is_connected:
            self.notify(
                "No printer connected -- print skipped", severity="warning",
            )
            return

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self.notify(f"Cannot read {path.name}: {exc}", severity="error")
            return

        profile = (
            self._all_profiles.get(self._profile_name)
            if self._all_profiles
            else None
        )
        columns = (
            profile.columns
            if profile is not None and profile.columns
            else 80
        )
        buffer_bytes = (
            profile.buffer_bytes
            if profile is not None and getattr(profile, "buffer_bytes", None)
            else 256
        )

        transcript_buffer: list[str] = []

        if speed_mode == "typewriter":
            import time

            from claude_teletype.audio import make_bell_output
            from claude_teletype.rendering.pacer import CHAR_DELAYS, classify_char

            base_delay = (self.base_delay_ms or 0.0) / 1000.0
            bell_fn = (
                (lambda c: None) if self.no_audio else make_bell_output()
            )

            def text_dest(char: str) -> None:
                self.printer.write(char)
                bell_fn(char)
                if base_delay > 0:
                    time.sleep(
                        base_delay * CHAR_DELAYS[classify_char(char)],
                    )

            wrapper = WordWrapper(columns, text_dest)
            style_dest = self.printer.write_bytes
        else:
            wrapper = WordWrapper(columns, self.printer.write)

            def style_dest(data: bytes) -> None:
                chunk_writes(self.printer, data, buffer_bytes)

        # TXN-02 parallel collector: tap the renderer's text channel only.
        # Style channel never reaches transcript_buffer.
        def text_with_capture(char: str) -> None:
            wrapper.feed(char)
            transcript_buffer.append(char)

        renderer = MarkdownRenderer(
            text_output_fn=text_with_capture,
            style_output_fn=style_dest,
            profile=profile,
            columns=columns,
        )

        self.notify(f"Printing {path.name}...")
        try:
            renderer.render(text)
            wrapper.flush()
            end_response = getattr(self.printer, "end_response", None)
            if end_response is not None:
                end_response()
            # TXN-01 + TXN-03: helper guards None internally
            write_printed_file(
                self._transcript_write, path, "".join(transcript_buffer),
            )
            self.notify(f"Printed {path.name}")
        except Exception as exc:  # noqa: BLE001 - print should never crash chat
            self.notify(f"Print failed: {exc}", severity="error")
        finally:
            # FLOW-05: cancel safety -- close any open style spans even on error
            renderer.close()

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
        from claude_teletype.printing.discovery import (
            discover_cups_printers,
            discover_usb_device,
        )
        from claude_teletype.printing.drivers import (
            CupsPrinterDriver,
            ProfilePrinterDriver,
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
        from claude_teletype.rendering.output import make_output_fn
        from claude_teletype.rendering.pacer import pace_characters
        from claude_teletype.rendering.wordwrap import WordWrapper

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
                        # Receipt/laser profiles set instant_output=True to
                        # skip the typewriter pacing — line-buffered hardware
                        # gains nothing from per-char delays.
                        active_profile = self._all_profiles.get(self._profile_name)
                        delay_ms = (
                            0.0
                            if active_profile is not None and active_profile.instant_output
                            else self.base_delay_ms
                        )
                        await pace_characters(
                            item,
                            base_delay_ms=delay_ms,
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
