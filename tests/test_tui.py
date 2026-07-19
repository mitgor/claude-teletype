"""Tests for the Textual split-screen TUI application."""

from unittest.mock import MagicMock, patch

import pytest
import typer
from textual.widgets import Footer, Header, Input, Log, Static

from claude_teletype.cli import check_claude_installed
from claude_teletype.printing.registry import ProfileRegistry
from claude_teletype.screens.settings import SettingsScreen
from claude_teletype.tui import TeletypeApp


async def test_layout_has_log_and_input():
    """Verify the split-screen layout contains Log and Input widgets."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:  # noqa: F841
        assert app.query_one("#output", Log) is not None
        assert app.query_one("#prompt", Input) is not None


async def test_layout_has_header_and_footer():
    """Verify Header and Footer are present."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:  # noqa: F841
        assert app.query_one(Header) is not None
        assert app.query_one(Footer) is not None


async def test_app_title():
    """App title is 'Claude Teletype'."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:  # noqa: F841
        assert app.title == "Claude Teletype"


async def test_enter_clears_input():
    """Input field clears after pressing Enter with text."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:
        await pilot.press(*"hello")
        await pilot.press("enter")
        input_widget = app.query_one("#prompt", Input)
        assert input_widget.value == ""


async def test_prompt_echoed_to_log():
    """Submitted prompt appears in the Log with 'You: ' label."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:
        await pilot.press(*"test prompt")
        await pilot.press("enter")
        await pilot.pause()
        log = app.query_one("#output", Log)
        log_text = "\n".join(str(line) for line in log.lines)
        assert "You: test prompt" in log_text


async def test_empty_input_not_submitted():
    """Pressing Enter with empty input does not write to the log."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:
        initial_line_count = len(app.query_one("#output", Log).lines)
        await pilot.press("enter")
        await pilot.pause()
        assert len(app.query_one("#output", Log).lines) == initial_line_count


async def test_whitespace_only_not_submitted():
    """Pressing Enter with whitespace-only input does not write to the log."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:
        initial_line_count = len(app.query_one("#output", Log).lines)
        await pilot.press("space", "space", "space")
        await pilot.press("enter")
        await pilot.pause()
        # Whitespace-only input should not be submitted
        # The input should still contain the spaces (not cleared)
        assert len(app.query_one("#output", Log).lines) == initial_line_count


async def test_custom_delay_stored():
    """base_delay_ms is stored on the app instance."""
    app = TeletypeApp(base_delay_ms=42.0)
    assert app.base_delay_ms == 42.0


async def test_default_delay():
    """Default base_delay_ms is 75.0."""
    app = TeletypeApp()
    assert app.base_delay_ms == 75.0


async def test_typing_sends_chars_to_printer():
    """Each typed character is sent to the printer in real-time."""
    app = TeletypeApp(base_delay_ms=0)
    printed: list[str] = []
    async with app.run_test() as pilot:
        app._printer_write = lambda ch: printed.append(ch)
        await pilot.press(*"hi")
        await pilot.pause()
    # First char triggers prefix "\nYou: " then "h", then "i"
    assert printed == ["\n", "Y", "o", "u", ":", " ", "h", "i"]


async def test_submit_sends_newlines_and_label_to_printer():
    """On submit, printer gets two newlines then 'Claude: ' label."""
    app = TeletypeApp(base_delay_ms=0)
    printed: list[str] = []
    async with app.run_test() as pilot:
        app._printer_write = lambda ch: printed.append(ch)
        await pilot.press(*"ab")
        await pilot.pause()
        printed.clear()  # Reset to only capture submit output
        await pilot.press("enter")
        await pilot.pause()
    # Two newlines for end-of-prompt, then "Claude: " label
    assert printed == ["\n", "\n", "C", "l", "a", "u", "d", "e", ":", " "]


async def test_backspace_does_not_send_to_printer():
    """Backspace/deletion does not send anything to the printer."""
    app = TeletypeApp(base_delay_ms=0)
    printed: list[str] = []
    async with app.run_test() as pilot:
        app._printer_write = lambda ch: printed.append(ch)
        await pilot.press(*"abc")
        await pilot.pause()
        printed.clear()
        await pilot.press("backspace")
        await pilot.pause()
    assert printed == []


async def test_no_printer_write_does_not_crash():
    """on_input_changed exits early when no printer is attached."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:
        # _printer_write is None by default, should not crash
        await pilot.press(*"hello")
        await pilot.pause()


async def test_status_bar_exists():
    """Status bar Static widget with id 'status-bar' is present in layout."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:  # noqa: F841
        status = app.query_one("#status-bar", Static)
        assert status is not None


async def test_input_disabled_during_streaming():
    """Input widget is disabled after submitting a prompt (before worker completes)."""
    disabled_seen = False

    app = TeletypeApp(base_delay_ms=0)
    # Replace stream_response with a no-op to prevent the finally block from re-enabling
    original_stream = app.stream_response
    app.stream_response = lambda prompt: None  # type: ignore[assignment]

    async with app.run_test() as pilot:
        await pilot.press(*"hello")
        await pilot.press("enter")
        await pilot.pause()
        input_widget = app.query_one("#prompt", Input)
        disabled_seen = input_widget.disabled

    app.stream_response = original_stream  # type: ignore[assignment]
    assert disabled_seen is True


async def test_escape_binding_exists():
    """Escape key binding is registered for cancel_stream action."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:  # noqa: F841
        binding_keys = [b.key for b in app.BINDINGS]
        assert "escape" in binding_keys


async def test_claude_label_in_log():
    """'Claude:' label appears in the log after submitting a prompt.

    Note: The space after 'Claude:' is deferred by WordWrapper (pending_space)
    and will appear when the first response word arrives. At test time, only
    'Claude:' is visible in the log.
    """
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:
        await pilot.press(*"hello")
        await pilot.press("enter")
        await pilot.pause()
        log = app.query_one("#output", Log)
        log_text = "\n".join(str(line) for line in log.lines)
        assert "Claude:" in log_text


async def test_turn_count_increments():
    """Turn count increments on each prompt submission."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:
        assert app._turn_count == 0
        await pilot.press(*"hello")
        await pilot.press("enter")
        assert app._turn_count == 1


async def test_tui_wrapper_initialized_to_none():
    """_tui_wrapper is None before streaming starts."""
    app = TeletypeApp(base_delay_ms=0)
    assert app._tui_wrapper is None


async def test_on_resize_handler_exists():
    """TeletypeApp has on_resize method for dynamic wrap width."""
    app = TeletypeApp(base_delay_ms=0)
    assert hasattr(app, "on_resize")
    assert callable(app.on_resize)


def test_check_claude_installed_missing():
    """check_claude_installed raises typer.Exit when claude binary not found."""
    import pytest

    with patch("claude_teletype.cli.shutil.which", return_value=None):
        with pytest.raises(typer.Exit) as exc_info:
            check_claude_installed()
        assert exc_info.value.exit_code == 1


def test_check_claude_installed_found():
    """check_claude_installed succeeds when claude binary is on PATH."""
    with patch("claude_teletype.cli.shutil.which", return_value="/usr/local/bin/claude"):
        # Should not raise
        check_claude_installed()


async def test_enter_typewriter_mode():
    """ctrl+t pushes TypewriterScreen onto TeletypeApp."""
    from claude_teletype.screens.typewriter import TypewriterScreen

    app = TeletypeApp(no_audio=True)
    async with app.run_test() as pilot:
        # Verify we start on default screen
        assert app.screen.__class__.__name__ != "TypewriterScreen"

        # Press ctrl+t to enter typewriter mode
        await pilot.press("ctrl+t")

        # Verify TypewriterScreen is now active
        assert isinstance(app.screen, TypewriterScreen)

        # Verify typewriter output widget exists
        log = app.screen.query_one("#typewriter-output")
        assert log is not None

        # Press Escape to return to chat
        await pilot.press("escape")

        # Verify we're back on default screen
        assert not isinstance(app.screen, TypewriterScreen)


def test_system_prompt_preserved_on_backend_swap():
    """system_prompt survives backend/model hot-swap via settings modal."""
    mock_backend = MagicMock()
    mock_backend.validate = MagicMock()

    app = TeletypeApp(
        base_delay_ms=0,
        backend=MagicMock(),
        backend_name="openai",
        model_config="gpt-4o",
        system_prompt="You are a helpful assistant.",
    )

    mock_create = MagicMock(return_value=mock_backend)
    with patch("claude_teletype.backends.create_backend", mock_create):
        app._apply_settings({
            "delay": 75.0,
            "no_audio": False,
            "backend": "openrouter",
            "model": "openai/gpt-4o",
            "profile": "generic",
        })

    mock_create.assert_called_once_with(
        backend="openrouter",
        model="openai/gpt-4o",
        system_prompt="You are a helpful assistant.",
        api_key=None,
    )
    assert app._system_prompt == "You are a helpful assistant."


@pytest.mark.asyncio
async def test_open_settings_via_shortcut():
    """ctrl+comma pushes SettingsScreen onto TeletypeApp."""
    mock_backend = MagicMock()
    mock_backend.validate = MagicMock()

    app = TeletypeApp(
        no_audio=True,
        base_delay_ms=0,
        backend=mock_backend,
        backend_name="claude-cli",
        model_config="",
        profile_name="generic",
        registry=ProfileRegistry({"generic": MagicMock()}),
    )
    async with app.run_test(size=(80, 50)) as pilot:
        # Verify we start on default screen
        assert not isinstance(app.screen, SettingsScreen)

        # Press ctrl+comma to open settings
        await pilot.press("ctrl+comma")
        await pilot.pause()

        # Verify SettingsScreen is now active
        assert isinstance(app.screen, SettingsScreen)

        # Verify a specific widget is present
        app.screen.query_one("#delay-input")

        # Press Escape to close settings
        await pilot.press("escape")
        await pilot.pause()

        # Verify we're back on default screen
        assert not isinstance(app.screen, SettingsScreen)


def test_profile_hotswap_wraps_connected_driver():
    """Switching profile wraps an existing connected driver in ProfilePrinterDriver."""
    from claude_teletype.printing.drivers import ProfilePrinterDriver
    from claude_teletype.printing.profiles import get_profile

    mock_driver = MagicMock()
    mock_driver.is_connected = True

    juki_profile = get_profile("juki")

    app = TeletypeApp(
        base_delay_ms=0,
        printer=mock_driver,
        profile_name="generic",
        registry=ProfileRegistry({"generic": MagicMock(), "juki": juki_profile}),
    )

    with patch("claude_teletype.config.load_config"), \
         patch("claude_teletype.config.save_config"):
        app._apply_settings({
            "delay": 75.0,
            "no_audio": False,
            "backend": "claude-cli",
            "model": "",
            "profile": "juki",
        })

    assert isinstance(app.printer, ProfilePrinterDriver)
    assert app._profile_name == "juki"
    assert app._printer_write is not None


def test_profile_hotswap_discovers_usb_when_null():
    """Switching profile from NullPrinter triggers TUI-safe USB discovery."""
    from claude_teletype.printing.drivers import NullPrinterDriver, ProfilePrinterDriver
    from claude_teletype.printing.profiles import get_profile

    juki_profile = get_profile("juki")
    mock_usb = MagicMock()
    mock_usb.is_connected = True

    app = TeletypeApp(
        base_delay_ms=0,
        printer=NullPrinterDriver(),
        profile_name="generic",
        registry=ProfileRegistry({"generic": MagicMock(), "juki": juki_profile}),
    )

    with patch("claude_teletype.printing.discovery.discover_usb_device", return_value=mock_usb), \
         patch("claude_teletype.config.load_config"), \
         patch("claude_teletype.config.save_config"):
        app._apply_settings({
            "delay": 75.0,
            "no_audio": False,
            "backend": "claude-cli",
            "model": "",
            "profile": "juki",
        })

    assert isinstance(app.printer, ProfilePrinterDriver)
    assert app._printer_write is not None


def test_profile_hotswap_cups_fallback_when_no_usb():
    """Switching profile falls back to CUPS auto-select when USB unavailable."""
    from claude_teletype.printing.drivers import CupsPrinterDriver, ProfilePrinterDriver
    from claude_teletype.printing.profiles import get_profile

    juki_profile = get_profile("juki")

    app = TeletypeApp(
        base_delay_ms=0,
        printer=MagicMock(is_connected=False),
        profile_name="generic",
        registry=ProfileRegistry({"generic": MagicMock(), "juki": juki_profile}),
    )

    cups_list = [{"name": "Juki_6100", "uri": "usb://Juki/6100"}]

    with patch("claude_teletype.printing.discovery.discover_usb_device", return_value=None), \
         patch("claude_teletype.printing.discovery.discover_cups_printers", return_value=cups_list), \
         patch("claude_teletype.config.load_config"), \
         patch("claude_teletype.config.save_config"):
        app._apply_settings({
            "delay": 75.0,
            "no_audio": False,
            "backend": "claude-cli",
            "model": "",
            "profile": "juki",
        })

    assert isinstance(app.printer, ProfilePrinterDriver)
    assert isinstance(app.printer._inner, CupsPrinterDriver)


def test_settings_save_persists_profile():
    """_save_settings writes current profile to config file."""
    from claude_teletype.config import TeletypeConfig

    app = TeletypeApp(
        base_delay_ms=100.0,
        profile_name="juki",
        backend_name="claude-cli",
        model_config="",
    )
    app.no_audio = False

    saved_cfg = None

    def capture_save(cfg, config_path=None):
        nonlocal saved_cfg
        saved_cfg = cfg

    with patch("claude_teletype.config.load_config", return_value=TeletypeConfig()), \
         patch("claude_teletype.config.save_config", side_effect=capture_save):
        app._save_settings()

    assert saved_cfg is not None
    assert saved_cfg.printer_profile == "juki"


# --- WR-04: setup-flow selection diagnostics must reach self.notify ---


@pytest.mark.asyncio
async def test_setup_result_unknown_profile_notifies():
    """_handle_setup_result surfaces selection diagnostics via notify (WR-04)."""
    from claude_teletype.config import TeletypeConfig
    from claude_teletype.printing.discovery import PrinterSelection
    from claude_teletype.printing.profiles import PrinterProfile

    # discovery=None: the cups-by-name path never touches discovery, and
    # leaving it None keeps the setup screen from auto-pushing on mount.
    app = TeletypeApp(
        base_delay_ms=0,
        no_audio=True,
        registry=ProfileRegistry({"generic": PrinterProfile(name="generic")}),
    )
    selection = PrinterSelection(
        connection_type="cups",
        cups_printer_name="Some_Queue",
        profile_name="no-such-profile",
    )
    notified: list[str] = []

    async with app.run_test():
        app.notify = lambda msg, **kw: notified.append(msg)
        with patch("claude_teletype.config.load_config", return_value=TeletypeConfig()), \
             patch("claude_teletype.config.save_config"):
            app._handle_setup_result(selection)

    assert any("no-such-profile" in m for m in notified), (
        f"Expected an unknown-profile diagnostic notify; got {notified!r}"
    )


# --- CR-03: _save_printer_selection must never persist an empty id ---


def test_save_printer_selection_refuses_empty_cups_id():
    """connection_type='cups' with cups_printer_name=None → save_config NOT called."""
    from claude_teletype.config import TeletypeConfig
    from claude_teletype.printing.discovery import PrinterSelection

    app = TeletypeApp(base_delay_ms=0)
    selection = PrinterSelection(connection_type="cups", cups_printer_name=None)

    with patch("claude_teletype.config.load_config", return_value=TeletypeConfig()), \
         patch("claude_teletype.config.save_config") as mock_save:
        app._save_printer_selection(selection)

    mock_save.assert_not_called()


def test_save_printer_selection_refuses_empty_usb_id():
    """usb selection with no resolvable device → save_config NOT called."""
    from claude_teletype.config import TeletypeConfig
    from claude_teletype.printing.discovery import PrinterSelection

    app = TeletypeApp(base_delay_ms=0)  # no discovery attached
    selection = PrinterSelection(connection_type="usb", device_index=None)

    with patch("claude_teletype.config.load_config", return_value=TeletypeConfig()), \
         patch("claude_teletype.config.save_config") as mock_save:
        app._save_printer_selection(selection)

    mock_save.assert_not_called()


def test_save_printer_selection_valid_cups_persists():
    """A valid CUPS selection still persists as before."""
    from claude_teletype.config import TeletypeConfig
    from claude_teletype.printing.discovery import PrinterSelection

    app = TeletypeApp(base_delay_ms=0)
    selection = PrinterSelection(
        connection_type="cups", cups_printer_name="HP_LaserJet", profile_name="juki"
    )

    saved_cfg = None

    def capture_save(cfg, config_path=None):
        nonlocal saved_cfg
        saved_cfg = cfg

    with patch("claude_teletype.config.load_config", return_value=TeletypeConfig()), \
         patch("claude_teletype.config.save_config", side_effect=capture_save):
        app._save_printer_selection(selection)

    assert saved_cfg is not None
    assert saved_cfg.saved_printer_type == "cups"
    assert saved_cfg.saved_printer_id == "HP_LaserJet"
    assert saved_cfg.saved_printer_profile == "juki"


# ---------------------------------------------------------------------------
# Phase 33 Plan 02: print thread-worker adapter (WR-01) + printer mutual
# exclusion (T-33-07). Patch-at-source-module convention: _print_worker
# imports render_document locally from claude_teletype.printing.pipeline.
# ---------------------------------------------------------------------------

import asyncio  # noqa: E402

from claude_teletype.printing.pipeline import PrintCancelled  # noqa: E402


class FakePrinter:
    """Recording driver: write = text channel, write_bytes = style channel."""

    is_connected = True

    def __init__(self):
        self.written: list[str] = []
        self.byte_writes: list[bytes] = []

    def write(self, ch: str) -> None:
        self.written.append(ch)

    def write_bytes(self, data: bytes) -> None:
        self.byte_writes.append(data)

    def end_response(self) -> None:
        pass

    def close(self) -> None:
        pass


def _make_doc(tmp_path, body: str = "hello world\n"):
    path = tmp_path / "doc.md"
    path.write_text(body, encoding="utf-8")
    return path


async def _wait_workers(app) -> None:
    """Poll until all workers finish AND the print thread really exited.

    Worker.is_finished lies for cancelled thread workers (CR-01): the state
    flips to CANCELLED while the executor thread keeps running. The
    app-level ``_print_thread_done`` event is the ground truth.
    """
    for _ in range(400):  # 4s cap
        ev = getattr(app, "_print_thread_done", None)
        thread_done = ev is None or ev.is_set()
        if thread_done and all(w.is_finished for w in app.workers):
            return
        await asyncio.sleep(0.01)
    raise AssertionError("workers did not finish in time")


def _slow_render(seen: dict):
    """A render_document fake that loops on cancel_check until cancelled."""

    def render(driver, profile, text, **kwargs):
        import time as _time

        cancel_check = kwargs["cancel_check"]
        for _ in range(150):  # ~3s cap so a broken cancel path can't hang
            if cancel_check():
                seen["flipped"] = True
                raise PrintCancelled()
            _time.sleep(0.02)
        raise AssertionError("cancel never reached the pipeline")

    return render


async def test_print_dispatches_worker_through_shared_pipeline(tmp_path):
    """_run_print_pipeline returns promptly; render_document runs in the
    worker with the app's settings and a non-None cancel_check."""
    printer = FakePrinter()
    app = TeletypeApp(base_delay_ms=3.0, printer=printer, no_audio=True)
    path = _make_doc(tmp_path)
    notified: list[str] = []

    with patch("claude_teletype.printing.pipeline.render_document") as rd:
        async with app.run_test():
            app.notify = lambda msg, **kw: notified.append(msg)
            app._run_print_pipeline(path, "typewriter")
            await app.workers.wait_for_complete()
            expected_transcript = app._transcript_write

    assert rd.call_count == 1
    args, kwargs = rd.call_args
    assert args[0] is printer
    assert args[2] == "hello world\n"
    assert kwargs["speed_mode"] == "typewriter"
    assert kwargs["base_delay_ms"] == 3.0
    assert kwargs["no_audio"] is True
    assert kwargs["transcript_write"] is expected_transcript
    assert kwargs["source_path"] == path
    assert kwargs["cancel_check"] is not None
    # WR-02: the TUI injects a cancellable sleep (the pipeline docstring's
    # seam contract) instead of relying on the default time.sleep.
    assert kwargs["sleep_fn"] is not None
    assert any(m.startswith("Printed ") for m in notified)


async def test_escape_cancels_in_flight_print(tmp_path):
    """escape → action_cancel_stream → worker.cancel() → is_cancelled
    reaches the pipeline's cancel_check (WR-01)."""
    printer = FakePrinter()
    app = TeletypeApp(base_delay_ms=0, printer=printer, no_audio=True)
    path = _make_doc(tmp_path)
    notified: list[str] = []
    seen: dict = {"flipped": False}

    with patch(
        "claude_teletype.printing.pipeline.render_document",
        side_effect=_slow_render(seen),
    ):
        async with app.run_test() as pilot:
            app.notify = lambda msg, **kw: notified.append(msg)
            app._run_print_pipeline(path, "typewriter")
            await asyncio.sleep(0.1)  # let the worker thread start looping
            await pilot.press("escape")
            await _wait_workers(app)

    assert seen["flipped"] is True
    assert any("cancelled" in m.lower() for m in notified)


async def test_cancel_interrupts_char_sleep(tmp_path):
    """WR-02: the injected sleep_fn returns early on cancel — a 10s
    char-sleep must not delay Escape response."""

    def sleepy_render(driver, profile, text, **kwargs):
        kwargs["sleep_fn"](10.0)  # far beyond the 4s _wait_workers cap
        if kwargs["cancel_check"]():
            raise PrintCancelled()
        raise AssertionError("sleep was not interrupted by cancel")

    printer = FakePrinter()
    app = TeletypeApp(base_delay_ms=0, printer=printer, no_audio=True)
    path = _make_doc(tmp_path)
    notified: list[str] = []

    with patch(
        "claude_teletype.printing.pipeline.render_document",
        side_effect=sleepy_render,
    ):
        async with app.run_test() as pilot:
            app.notify = lambda msg, **kw: notified.append(msg)
            app._run_print_pipeline(path, "typewriter")
            await asyncio.sleep(0.1)  # thread is inside the 10s sleep
            await pilot.press("escape")
            await _wait_workers(app)  # 4s cap: passes only if interrupted

    assert any("cancelled" in m.lower() for m in notified)


async def test_cancelled_print_leaves_style_state_clean(tmp_path):
    """Integration: real render_document, bold-heavy doc, cancel mid-render
    → the shared core's finally emitted bold_off (escp ESC F) style bytes."""
    from claude_teletype.printing.profiles import get_profile

    printer = FakePrinter()
    app = TeletypeApp(
        base_delay_ms=2.0,
        printer=printer,
        no_audio=True,
        profile_name="escp",
        registry=ProfileRegistry({"escp": get_profile("escp")}),
    )
    # One giant bold span of many words: WordWrapper emits (and paces) one
    # chunk per word, so the render takes ~1s+ unless cancelled.
    path = _make_doc(tmp_path, "**" + "word " * 500 + "**\n")
    notified: list[str] = []

    async with app.run_test():
        app.notify = lambda msg, **kw: notified.append(msg)
        app._run_print_pipeline(path, "typewriter")
        await asyncio.sleep(0.05)  # mid-render, inside the open bold span
        for worker in list(app.workers):
            if worker.group == "print" and not worker.is_finished:
                worker.cancel()
        await _wait_workers(app)

    # The render did NOT complete...
    assert any("cancelled" in m.lower() for m in notified)
    # ...yet bold_off reached the driver: finally: renderer.close() ran.
    assert b"\x1bF" in b"".join(printer.byte_writes)


async def test_print_active_survives_worker_cancel_until_thread_exits(tmp_path):
    """CR-01 regression: after Worker.cancel() the worker reports finished
    while the executor thread is still running — _print_active() must stay
    True until the thread's own finally sets _print_thread_done."""
    import threading

    release = threading.Event()

    def stuck_render(driver, profile, text, **kwargs):
        # Simulates a thread stuck in a char-sleep past the cancel point.
        release.wait(5.0)
        raise PrintCancelled()

    printer = FakePrinter()
    app = TeletypeApp(base_delay_ms=0, printer=printer, no_audio=True)
    path = _make_doc(tmp_path)

    with patch(
        "claude_teletype.printing.pipeline.render_document",
        side_effect=stuck_render,
    ):
        async with app.run_test():
            app.notify = lambda msg, **kw: None
            app._run_print_pipeline(path, "typewriter")
            await asyncio.sleep(0.05)  # let the thread enter stuck_render

            for worker in list(app.workers):
                if worker.group == "print":
                    worker.cancel()
            # Wait for the WORKER STATE to report finished (the lie)...
            for _ in range(200):
                if all(w.is_finished for w in app.workers):
                    break
                await asyncio.sleep(0.01)
            assert all(w.is_finished for w in app.workers)
            # ...while the thread is still alive: the guard must hold.
            assert app._print_active() is True

            release.set()
            await _wait_workers(app)
            assert app._print_active() is False


async def test_print_failure_survives_session(tmp_path):
    """render_document raising → 'Print failed:' notify; chat still alive."""
    printer = FakePrinter()
    app = TeletypeApp(base_delay_ms=0, printer=printer, no_audio=True)
    path = _make_doc(tmp_path)
    notified: list[str] = []

    with patch(
        "claude_teletype.printing.pipeline.render_document",
        side_effect=RuntimeError("boom"),
    ):
        async with app.run_test() as pilot:
            app.notify = lambda msg, **kw: notified.append(msg)
            app._run_print_pipeline(path, "typewriter")
            await app.workers.wait_for_complete()
            assert app.is_running
            prompt = app.query_one("#prompt", Input)
            prompt.focus()
            await pilot.pause()
            assert app.focused is prompt

    assert any(m.startswith("Print failed:") for m in notified)


async def test_quit_during_print_waits_for_thread_before_closing_driver(tmp_path):
    """CR-02 regression: app shutdown mid-print must wait for the print
    thread's real exit (style-off already emitted) before printer.close(),
    and the worker's shutdown-time notify must not raise RuntimeError."""
    printer = FakePrinter()
    closed_after_thread_done: list[bool] = []

    app = TeletypeApp(base_delay_ms=0, printer=printer, no_audio=True)
    printer.close = lambda: closed_after_thread_done.append(
        app._print_thread_done is not None and app._print_thread_done.is_set()
    )
    path = _make_doc(tmp_path)
    seen: dict = {"flipped": False}

    with patch(
        "claude_teletype.printing.pipeline.render_document",
        side_effect=_slow_render(seen),
    ):
        async with app.run_test():
            app.notify = lambda msg, **kw: None
            app._run_print_pipeline(path, "typewriter")
            await asyncio.sleep(0.1)  # print in flight
            # Exiting the context shuts the app down: cancel_all → on_unmount.

    assert seen["flipped"] is True  # thread saw the cancel and exited cleanly
    assert closed_after_thread_done == [True]  # close AFTER thread done


def test_notify_from_thread_swallows_stopped_app_runtime_error():
    """CR-02: shutdown-time notify must not raise out of the worker thread."""
    app = TeletypeApp(base_delay_ms=0)

    def boom(*args, **kwargs):
        raise RuntimeError("App is not running")

    app.call_from_thread = boom
    app._notify_from_thread("late notify", severity="warning")  # no raise


async def test_print_skipped_when_no_printer(tmp_path):
    """printer None → warning notify, render_document never called."""
    app = TeletypeApp(base_delay_ms=0)
    path = _make_doc(tmp_path)
    notified: list[tuple] = []

    with patch("claude_teletype.printing.pipeline.render_document") as rd:
        async with app.run_test():
            app.notify = lambda msg, **kw: notified.append((msg, kw))
            app._run_print_pipeline(path, "typewriter")
            await app.workers.wait_for_complete()

    rd.assert_not_called()
    assert any(
        "No printer" in msg and kw.get("severity") == "warning"
        for msg, kw in notified
    )


async def test_chat_refused_while_print_active(tmp_path):
    """T-33-07: chat submission refuses while a print worker is unfinished —
    no stream dispatch, no driver bytes from the chat path — and works
    again once the print is cancelled."""
    printer = FakePrinter()
    app = TeletypeApp(base_delay_ms=0, printer=printer, no_audio=True)
    path = _make_doc(tmp_path)
    notified: list[str] = []
    stream_calls: list[str] = []
    app.stream_response = lambda prompt: stream_calls.append(prompt)
    seen: dict = {"flipped": False}

    with patch(
        "claude_teletype.printing.pipeline.render_document",
        side_effect=_slow_render(seen),
    ):
        async with app.run_test() as pilot:
            app.notify = lambda msg, **kw: notified.append(msg)
            app._run_print_pipeline(path, "typewriter")
            await asyncio.sleep(0.05)

            await pilot.press(*"hi")
            await pilot.press("enter")
            await pilot.pause()

            assert any("Print in progress" in m for m in notified)
            assert stream_calls == []  # stream_response NOT dispatched
            assert printer.written == []  # no chat bytes reached the driver
            # user keeps their typed prompt
            assert app.query_one("#prompt", Input).value == "hi"

            # cancel the print → guard clears → chat works again
            await pilot.press("escape")
            await _wait_workers(app)
            await pilot.press("enter")
            await pilot.pause()
            assert stream_calls == ["hi"]


async def test_settings_refused_while_print_active(tmp_path):
    """WR-01: ctrl+comma refuses while a print is in flight — a profile
    hot-swap would mutate the driver under the writer thread."""
    from claude_teletype.screens.settings import SettingsScreen

    printer = FakePrinter()
    app = TeletypeApp(base_delay_ms=0, printer=printer, no_audio=True)
    path = _make_doc(tmp_path)
    notified: list[str] = []
    seen: dict = {"flipped": False}

    with patch(
        "claude_teletype.printing.pipeline.render_document",
        side_effect=_slow_render(seen),
    ):
        async with app.run_test() as pilot:
            app.notify = lambda msg, **kw: notified.append(msg)
            app._run_print_pipeline(path, "typewriter")
            await asyncio.sleep(0.05)

            await pilot.press("ctrl+comma")
            await pilot.pause()
            assert not isinstance(app.screen, SettingsScreen)
            assert any("Printer busy" in m for m in notified)

            await pilot.press("escape")
            await _wait_workers(app)

            # Guard clears once the print thread really exits.
            await pilot.press("ctrl+comma")
            await pilot.pause()
            assert isinstance(app.screen, SettingsScreen)


async def test_print_refused_while_stream_active(tmp_path):
    """T-33-07: _run_print_pipeline refuses while a non-print (chat stream)
    worker is unfinished."""
    printer = FakePrinter()
    app = TeletypeApp(base_delay_ms=0, printer=printer, no_audio=True)
    path = _make_doc(tmp_path)
    notified: list[str] = []

    with patch("claude_teletype.printing.pipeline.render_document") as rd:
        async with app.run_test() as pilot:
            app.notify = lambda msg, **kw: notified.append(msg)

            # Stand-in for an unfinished stream_response worker: same
            # default worker group, stays running until cancelled.
            async def _hang():
                await asyncio.sleep(30)

            worker = app.run_worker(_hang(), exclusive=True)
            await pilot.pause()

            app._run_print_pipeline(path, "typewriter")
            await pilot.pause()

            rd.assert_not_called()
            assert any("Printer busy" in m for m in notified)

            worker.cancel()
            await _wait_workers(app)


async def test_print_refused_while_typewriter_mounted(tmp_path):
    """T-33-07: TypewriterScreen's key worker counts as a driver writer —
    ctrl+o's _run_print_pipeline refuses while the screen is mounted."""
    from claude_teletype.screens.typewriter import TypewriterScreen

    printer = FakePrinter()
    app = TeletypeApp(base_delay_ms=0, printer=printer, no_audio=True)
    path = _make_doc(tmp_path)
    notified: list[str] = []

    with patch("claude_teletype.printing.pipeline.render_document") as rd:
        async with app.run_test() as pilot:
            app.notify = lambda msg, **kw: notified.append(msg)

            await pilot.press("ctrl+t")
            assert isinstance(app.screen, TypewriterScreen)

            # The app-level ctrl+o binding stays reachable from this screen;
            # call its handler's dispatch target directly.
            app._run_print_pipeline(path, "typewriter")
            await pilot.pause()

            rd.assert_not_called()
            assert any("Printer busy" in m for m in notified)

            await pilot.press("escape")  # leave typewriter mode


async def test_startup_diagnostics_are_notified_on_mount():
    """WR-03: cli-collected saved-match diagnostics reach notify(), not stderr."""
    app = TeletypeApp(
        base_delay_ms=0,
        startup_diagnostics=["USB direct unavailable — falling back to CUPS queue Q"],
    )
    with patch.object(TeletypeApp, "notify") as mock_notify:
        async with app.run_test():
            pass
    notified = [c.args[0] for c in mock_notify.call_args_list]
    assert any("falling back to CUPS queue Q" in m for m in notified)


async def test_no_startup_diagnostics_no_extra_notify():
    """Default construction (no diagnostics) notifies nothing extra."""
    app = TeletypeApp(base_delay_ms=0)
    with patch.object(TeletypeApp, "notify") as mock_notify:
        async with app.run_test():
            pass
    notified = [c.args[0] for c in mock_notify.call_args_list]
    assert not any("falling back" in m for m in notified)
