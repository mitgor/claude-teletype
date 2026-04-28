"""Tests for printer driver backends, discovery, and resilient output wrapper."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from claude_teletype.printer import (
    A4_COLUMNS,
    CupsPrinterDriver,
    FilePrinterDriver,
    JukiPrinterDriver,
    NullPrinterDriver,
    ProfilePrinterDriver,
    UsbPrinterDriver,
    discover_cups_printers,
    discover_macos_usb_printers,
    discover_printer,
    discover_usb_device,
    discover_usb_device_verbose,
    make_printer_output,
    select_printer,
)
from claude_teletype.profiles import PrinterProfile, get_profile

# ---------------------------------------------------------------------------
# NullPrinterDriver tests
# ---------------------------------------------------------------------------


def test_null_driver_is_not_connected():
    """NullPrinterDriver().is_connected is False."""
    driver = NullPrinterDriver()
    assert driver.is_connected is False


def test_null_driver_write_is_noop():
    """write('A') does not raise."""
    driver = NullPrinterDriver()
    driver.write("A")  # should not raise


def test_null_driver_close_is_noop():
    """close() does not raise."""
    driver = NullPrinterDriver()
    driver.close()  # should not raise


# ---------------------------------------------------------------------------
# FilePrinterDriver tests (use tmp_path fixture for a real temp file)
# ---------------------------------------------------------------------------


def test_file_driver_is_connected_after_open(tmp_path: Path):
    """is_connected is True after opening."""
    dev = tmp_path / "dev"
    dev.touch()
    driver = FilePrinterDriver(str(dev))
    assert driver.is_connected is True
    driver.close()


def test_file_driver_writes_ascii_bytes(tmp_path: Path):
    """write('A') writes b'A' to the file."""
    dev = tmp_path / "dev"
    dev.touch()
    driver = FilePrinterDriver(str(dev))
    driver.write("A")
    driver.close()
    assert dev.read_bytes() == b"A"


def test_file_driver_replaces_non_ascii(tmp_path: Path):
    """write('\\u2603') writes b'?' (ascii replace)."""
    dev = tmp_path / "dev"
    dev.touch()
    driver = FilePrinterDriver(str(dev))
    driver.write("\u2603")
    driver.close()
    assert dev.read_bytes() == b"?"


def test_file_driver_disconnect_on_write_error(tmp_path: Path):
    """Close the fd, then write() sets is_connected=False (no raise)."""
    dev = tmp_path / "dev"
    dev.touch()
    driver = FilePrinterDriver(str(dev))
    # Forcibly close the underlying file descriptor
    driver._fd.close()
    driver.write("A")  # should not raise
    assert driver.is_connected is False


def test_file_driver_close(tmp_path: Path):
    """close() closes the file handle."""
    dev = tmp_path / "dev"
    dev.touch()
    driver = FilePrinterDriver(str(dev))
    driver.close()
    assert driver._fd.closed


# ---------------------------------------------------------------------------
# CupsPrinterDriver tests (per-line flush for real-time output)
# ---------------------------------------------------------------------------


def test_cups_driver_is_connected():
    """is_connected is True initially."""
    driver = CupsPrinterDriver("TestPrinter")
    assert driver.is_connected is True


@patch("claude_teletype.printer.subprocess.run")
def test_cups_driver_flushes_on_newline(mock_run: MagicMock):
    """write('A'), write('B') buffers; write('\\n') flushes line via lp."""
    driver = CupsPrinterDriver("TestPrinter")
    driver.write("A")
    driver.write("B")
    mock_run.assert_not_called()

    driver.write("\n")
    mock_run.assert_called_once_with(
        ["lp", "-o", "raw", "-d", "TestPrinter"],
        input=b"AB\n",
        capture_output=True,
        timeout=30,
    )


@patch("claude_teletype.printer.subprocess.run")
def test_cups_driver_disconnect_on_subprocess_error(mock_run: MagicMock):
    """After subprocess error on flush, is_connected is False."""
    mock_run.side_effect = subprocess.SubprocessError("fail")
    driver = CupsPrinterDriver("TestPrinter")
    driver.write("A")
    driver.write("\n")
    assert driver.is_connected is False


def test_cups_driver_noop_when_disconnected():
    """When _connected=False, write() does not call subprocess."""
    driver = CupsPrinterDriver("TestPrinter")
    driver._connected = False
    with patch("claude_teletype.printer.subprocess.run") as mock_run:
        driver.write("A")
        driver.write("\n")
        mock_run.assert_not_called()


@patch("claude_teletype.printer.subprocess.run")
def test_cups_driver_flush_on_close(mock_run: MagicMock):
    """write('AB') then close() flushes remaining buffer."""
    driver = CupsPrinterDriver("TestPrinter")
    driver.write("A")
    driver.write("B")
    mock_run.assert_not_called()
    driver.close()
    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs["input"] == b"AB"


# ---------------------------------------------------------------------------
# Discovery tests (mock subprocess.run for lpstat)
# ---------------------------------------------------------------------------


def test_discover_device_override_returns_file_driver(tmp_path: Path):
    """discover_printer(device_override=...) returns FilePrinterDriver."""
    dev = tmp_path / "dev"
    dev.touch()
    driver = discover_printer(device_override=str(dev))
    assert isinstance(driver, FilePrinterDriver)
    driver.close()


@patch("claude_teletype.printer.subprocess.run")
def test_discover_cups_usb_printer(mock_run: MagicMock):
    """Mock lpstat returning USB printer -> CupsPrinterDriver."""
    mock_run.return_value = MagicMock(
        stdout="device for MyPrinter: usb://Vendor/Model?serial=123\n",
        returncode=0,
    )
    driver = discover_printer()
    assert isinstance(driver, CupsPrinterDriver)


@patch("claude_teletype.printer.subprocess.run")
def test_discover_cups_ignores_network_printers(mock_run: MagicMock):
    """Mock lpstat returning network printer -> falls through to NullPrinterDriver."""
    mock_run.return_value = MagicMock(
        stdout="device for NetPrinter: ipp://10.0.0.1/ipp/print\n",
        returncode=0,
    )
    driver = discover_printer()
    assert isinstance(driver, NullPrinterDriver)


@patch("claude_teletype.printer.subprocess.run")
def test_discover_fallback_null_driver(mock_run: MagicMock):
    """Mock lpstat empty -> NullPrinterDriver."""
    mock_run.return_value = MagicMock(stdout="", returncode=0)
    driver = discover_printer()
    assert isinstance(driver, NullPrinterDriver)


@patch("claude_teletype.printer.subprocess.run")
def test_discover_cups_printers_handles_lpstat_failure(mock_run: MagicMock):
    """Mock lpstat raising FileNotFoundError -> returns empty, falls to Null."""
    mock_run.side_effect = FileNotFoundError("lpstat not found")
    driver = discover_printer()
    assert isinstance(driver, NullPrinterDriver)


# ---------------------------------------------------------------------------
# make_printer_output tests
# ---------------------------------------------------------------------------


def test_make_printer_output_delegates_to_driver(tmp_path: Path):
    """output_fn delegates writes to the driver (flushed on newline)."""
    dev = tmp_path / "dev"
    dev.touch()
    driver = FilePrinterDriver(str(dev))
    output_fn = make_printer_output(driver)
    output_fn("X")
    output_fn("\n")  # flush buffered word through WordWrapper
    driver.close()
    assert dev.read_bytes() == b"X\n"


def test_make_printer_output_degrades_on_error():
    """On OSError, output_fn degrades to no-op; first write triggers disconnect."""
    driver = MagicMock()
    driver.write.side_effect = OSError("disconnected")
    output_fn = make_printer_output(driver)
    # Feed char + newline to trigger flush through WordWrapper
    output_fn("A")
    output_fn("\n")  # flushes "A" to driver, which raises OSError
    output_fn("B")  # should be no-op (disconnected)
    output_fn("\n")
    # Only 1 call: the first char "A" triggers OSError -> disconnected
    assert driver.write.call_count == 1


def test_make_printer_output_flush_calls_end_response():
    """printer_write.flush() invokes driver.end_response() for cut-aware drivers."""
    driver = MagicMock(spec=ProfilePrinterDriver)
    driver.is_connected = True
    output_fn = make_printer_output(driver)

    output_fn("A")
    output_fn.flush()

    driver.end_response.assert_called_once()


def test_make_printer_output_flush_tolerates_driver_without_end_response():
    """printer_write.flush() does not crash when driver lacks end_response."""
    driver = MagicMock(spec=["is_connected", "write", "close"])
    driver.is_connected = True
    output_fn = make_printer_output(driver)

    output_fn("A")
    output_fn.flush()  # must not raise


def test_make_printer_output_compatible_with_make_output_fn(tmp_path: Path):
    """Printer output_fn works with make_output_fn multiplexer."""
    from claude_teletype.output import make_output_fn

    dev = tmp_path / "dev"
    dev.touch()
    driver = FilePrinterDriver(str(dev))
    collected: list[str] = []
    output_fn = make_output_fn(collected.append, make_printer_output(driver))
    output_fn("H")
    output_fn("i")
    output_fn("\n")  # flush buffered word through WordWrapper
    driver.close()
    assert collected == ["H", "i", "\n"]
    assert dev.read_bytes() == b"Hi\n"


# ---------------------------------------------------------------------------
# A4 word-wrap tests (WordWrapper-based)
# ---------------------------------------------------------------------------


def test_a4_columns_constant():
    """A4_COLUMNS is 80."""
    assert A4_COLUMNS == 80


def test_printer_wraps_at_word_boundary():
    """Long text wraps at word boundary, not mid-word."""
    driver = MagicMock()
    driver.is_connected = True
    output_fn = make_printer_output(driver)

    # Feed 70 a's, then space, then 20 b's, then newline
    for ch in "a" * 70 + " " + "b" * 20 + "\n":
        output_fn(ch)

    calls = [c.args[0] for c in driver.write.call_args_list]
    text = "".join(calls)
    # 70 a's + space + 20 b's = 91 > 80, so "b"*20 wraps to new line
    # pending_space dropped at wrap point
    assert text == "a" * 70 + "\n" + "b" * 20 + "\n"


def test_printer_no_wrap_when_fits():
    """Short text does not get wrapped."""
    driver = MagicMock()
    driver.is_connected = True
    output_fn = make_printer_output(driver)

    for ch in "hello world\n":
        output_fn(ch)

    calls = [c.args[0] for c in driver.write.call_args_list]
    text = "".join(calls)
    assert text == "hello world\n"


def test_printer_hard_breaks_long_word():
    """Single word longer than A4_COLUMNS is hard-broken at column 80."""
    driver = MagicMock()
    driver.is_connected = True
    output_fn = make_printer_output(driver)

    for ch in "x" * 100 + "\n":
        output_fn(ch)

    calls = [c.args[0] for c in driver.write.call_args_list]
    text = "".join(calls)
    assert text == "x" * 80 + "\n" + "x" * 20 + "\n"


def test_printer_newline_resets_wrapping():
    """Explicit newline resets column; 80 chars fit on new line without wrap."""
    driver = MagicMock()
    driver.is_connected = True
    output_fn = make_printer_output(driver)

    # 80 X's (single word) then newline
    for ch in "X" * A4_COLUMNS + "\n":
        output_fn(ch)
    # 80 Y's (single word) then newline -- should fit without extra wrap
    for ch in "Y" * A4_COLUMNS + "\n":
        output_fn(ch)

    calls = [c.args[0] for c in driver.write.call_args_list]
    text = "".join(calls)
    assert text == "X" * 80 + "\n" + "Y" * 80 + "\n"


def test_printer_graceful_degradation_preserved():
    """On OSError, output_fn degrades to no-op; first flush triggers disconnect."""
    driver = MagicMock()
    driver.write.side_effect = OSError("disconnected")
    output_fn = make_printer_output(driver)
    output_fn("A")
    output_fn("\n")  # flushes "A" to driver -> OSError -> disconnected
    output_fn("B")  # should be no-op (disconnected)
    output_fn("\n")
    # Only 1 call: "A" triggers OSError -> disconnected
    assert driver.write.call_count == 1


def test_printer_formfeed_resets_column():
    """Form feed flushes buffer, passes through, and resets column."""
    driver = MagicMock()
    driver.is_connected = True
    output_fn = make_printer_output(driver)

    # 50 X's then formfeed
    for ch in "X" * 50:
        output_fn(ch)
    output_fn("\f")

    # After formfeed, 80 chars should fit without wrap
    for ch in "Y" * A4_COLUMNS + "\n":
        output_fn(ch)

    calls = [c.args[0] for c in driver.write.call_args_list]
    text = "".join(calls)
    # X's flushed on \f, then \f, then Y's + newline
    assert text == "X" * 50 + "\f" + "Y" * 80 + "\n"
    # Verify no auto-wrap newlines between Y's
    y_section = text[text.index("\f") + 1 :]
    assert y_section.count("\n") == 1  # only the explicit newline


def test_printer_cr_resets_column():
    """Carriage return flushes buffer, passes through, and resets column."""
    driver = MagicMock()
    driver.is_connected = True
    output_fn = make_printer_output(driver)

    for ch in "X" * 50:
        output_fn(ch)
    output_fn("\r")

    # After CR, 80 chars should fit without wrap
    for ch in "Y" * A4_COLUMNS + "\n":
        output_fn(ch)

    calls = [c.args[0] for c in driver.write.call_args_list]
    text = "".join(calls)
    assert text == "X" * 50 + "\r" + "Y" * 80 + "\n"


# ---------------------------------------------------------------------------
# select_printer() tests
# ---------------------------------------------------------------------------


def test_select_printer_no_printers():
    """Empty list returns None."""
    assert select_printer([]) is None


def test_select_printer_single_auto_selects():
    """Single printer is auto-selected without prompting."""
    printers = [{"name": "USB2.0-Print", "uri": "usb:///USB2.0-Print"}]
    result = select_printer(printers)
    assert result == "USB2.0-Print"


@patch("builtins.input", return_value="2")
def test_select_printer_multiple_interactive(mock_input: MagicMock):
    """With 2+ printers, user picks by number."""
    printers = [
        {"name": "PrinterA", "uri": "usb://A"},
        {"name": "PrinterB", "uri": "usb://B"},
    ]
    result = select_printer(printers)
    assert result == "PrinterB"
    mock_input.assert_called_once()


@patch("builtins.input", side_effect=["bad", "0", "1"])
def test_select_printer_retries_on_invalid(mock_input: MagicMock):
    """Invalid input retries until valid."""
    printers = [
        {"name": "PrinterA", "uri": "usb://A"},
        {"name": "PrinterB", "uri": "usb://B"},
    ]
    result = select_printer(printers)
    assert result == "PrinterA"
    assert mock_input.call_count == 3


# ---------------------------------------------------------------------------
# JukiPrinterDriver tests
# ---------------------------------------------------------------------------


def _collect_raw(inner) -> bytes:
    """Collect all bytes written to a mock inner driver.

    Handles both single-char writes and multi-char writes (atomic ESC
    sequences sent by _send_raw).
    """
    return b"".join(c.args[0].encode("ascii") for c in inner.write.call_args_list)


def test_juki_sends_init_on_first_write():
    """First write sends RESET + LINE_SPACING + FIXED_PITCH init sequence."""
    inner = MagicMock()
    inner.is_connected = True
    juki = JukiPrinterDriver(inner)

    juki.write("A")

    raw = _collect_raw(inner)

    expected_init = (
        b"\x1b\x1aI"  # RESET
        b"\x1b\x1e\x09"  # LINE_SPACING
        b"\x1bQ"  # FIXED_PITCH
    )
    assert raw.startswith(expected_init)
    assert raw[-1:] == b"A"


def test_juki_no_double_init():
    """Init sequence only sent once, not on subsequent writes."""
    inner = MagicMock()
    inner.is_connected = True
    juki = JukiPrinterDriver(inner)

    juki.write("A")
    first_count = inner.write.call_count

    juki.write("B")
    # Second write should add exactly 1 call (just "B")
    assert inner.write.call_count == first_count + 1


def test_juki_converts_newline_to_crlf_and_reinits():
    """\\n is converted to \\r\\n followed by LINE_SPACING + FIXED_PITCH."""
    inner = MagicMock()
    inner.is_connected = True
    juki = JukiPrinterDriver(inner)
    juki._initialized = True  # skip init for clarity

    juki.write("\n")

    raw = _collect_raw(inner)
    expected = b"\r\n" + JukiPrinterDriver.LINE_SPACING + JukiPrinterDriver.FIXED_PITCH
    assert raw == expected


def test_juki_regular_chars_pass_through():
    """Non-newline chars pass through unchanged."""
    inner = MagicMock()
    inner.is_connected = True
    juki = JukiPrinterDriver(inner)
    juki._initialized = True

    juki.write("X")

    inner.write.assert_called_once_with("X")


def test_juki_close_sends_formfeed():
    """close() sends form feed before closing inner driver."""
    inner = MagicMock()
    inner.is_connected = True
    juki = JukiPrinterDriver(inner)
    juki._initialized = True

    juki.close()

    inner.write.assert_called_once_with("\f")
    inner.close.assert_called_once()


def test_juki_close_skips_formfeed_when_not_initialized():
    """close() skips form feed if never initialized (nothing was printed)."""
    inner = MagicMock()
    inner.is_connected = True
    juki = JukiPrinterDriver(inner)

    juki.close()

    inner.write.assert_not_called()
    inner.close.assert_called_once()


def test_juki_is_connected_delegates():
    """is_connected delegates to inner driver."""
    inner = MagicMock()
    inner.is_connected = False
    juki = JukiPrinterDriver(inner)
    assert juki.is_connected is False

    inner.is_connected = True
    assert juki.is_connected is True


def test_juki_write_noop_when_disconnected():
    """write() does nothing when inner is disconnected."""
    inner = MagicMock()
    inner.is_connected = False
    juki = JukiPrinterDriver(inner)

    juki.write("A")
    inner.write.assert_not_called()


# ---------------------------------------------------------------------------
# ProfilePrinterDriver tests
# ---------------------------------------------------------------------------


class TestProfilePrinterDriver:
    """Tests for the generic profile-driven printer wrapper."""

    def test_init_sequence_sent_on_first_write(self):
        """First write sends profile init_sequence + line_spacing + char_pitch."""
        inner = MagicMock()
        inner.is_connected = True
        profile = PrinterProfile(
            name="test",
            init_sequence=b"\x1b@",
            line_spacing=b"\x1b\x32",
            char_pitch=b"\x1bP",
        )
        ppd = ProfilePrinterDriver(inner, profile)

        ppd.write("A")

        raw = _collect_raw(inner)
        expected_init = b"\x1b@\x1b\x32\x1bP"
        assert raw.startswith(expected_init)
        assert raw[-1:] == b"A"

    def test_no_double_init(self):
        """Init sequence only sent once, not on subsequent writes."""
        inner = MagicMock()
        inner.is_connected = True
        profile = PrinterProfile(name="test", init_sequence=b"\x1b@")
        ppd = ProfilePrinterDriver(inner, profile)

        ppd.write("A")
        first_count = inner.write.call_count

        ppd.write("B")
        assert inner.write.call_count == first_count + 1

    def test_crlf_newline_when_true(self):
        """When profile.crlf=True, newline sends CR+LF as single atomic write."""
        inner = MagicMock()
        inner.is_connected = True
        profile = PrinterProfile(name="test", crlf=True)
        ppd = ProfilePrinterDriver(inner, profile)
        ppd._initialized = True

        ppd.write("\n")

        raw = _collect_raw(inner)
        assert raw == b"\r\n"

    def test_lf_only_when_crlf_false(self):
        """When profile.crlf=False, newline sends LF only."""
        inner = MagicMock()
        inner.is_connected = True
        profile = PrinterProfile(name="test", crlf=False)
        ppd = ProfilePrinterDriver(inner, profile)
        ppd._initialized = True

        ppd.write("\n")

        raw = _collect_raw(inner)
        assert raw == b"\n"

    def test_reinit_on_newline_sends_reinit_sequence(self):
        """When reinit_on_newline=True, reinit_sequence sent after newline."""
        inner = MagicMock()
        inner.is_connected = True
        profile = PrinterProfile(
            name="test",
            crlf=True,
            reinit_on_newline=True,
            reinit_sequence=b"\x1b\x32\x1bP",
        )
        ppd = ProfilePrinterDriver(inner, profile)
        ppd._initialized = True

        ppd.write("\n")

        raw = _collect_raw(inner)
        expected = b"\r\n\x1b\x32\x1bP"
        assert raw == expected

    def test_close_sends_formfeed_and_reset(self):
        """close() sends formfeed + reset_sequence when profile says so."""
        inner = MagicMock()
        inner.is_connected = True
        profile = PrinterProfile(
            name="test",
            formfeed_on_close=True,
            reset_sequence=b"\x1b@",
        )
        ppd = ProfilePrinterDriver(inner, profile)
        ppd._initialized = True

        ppd.close()

        raw = _collect_raw(inner)
        assert b"\f" in raw
        assert raw.endswith(b"\x1b@")
        inner.close.assert_called_once()

    def test_close_no_formfeed_when_disabled(self):
        """close() skips formfeed when formfeed_on_close=False."""
        inner = MagicMock()
        inner.is_connected = True
        profile = PrinterProfile(name="test", formfeed_on_close=False)
        ppd = ProfilePrinterDriver(inner, profile)
        ppd._initialized = True

        ppd.close()

        calls = [c.args[0] for c in inner.write.call_args_list]
        assert "\f" not in calls
        inner.close.assert_called_once()

    def test_generic_profile_no_esc_sequences(self):
        """Generic profile sends no ESC sequences at all."""
        inner = MagicMock()
        inner.is_connected = True
        profile = get_profile("generic")
        ppd = ProfilePrinterDriver(inner, profile)

        ppd.write("A")
        ppd.write("B")

        calls = [c.args[0] for c in inner.write.call_args_list]
        assert calls == ["A", "B"]

    def test_is_connected_delegates_to_inner(self):
        """is_connected property delegates to inner driver."""
        inner = MagicMock()
        inner.is_connected = False
        profile = PrinterProfile(name="test")
        ppd = ProfilePrinterDriver(inner, profile)
        assert ppd.is_connected is False

        inner.is_connected = True
        assert ppd.is_connected is True

    def test_write_noop_when_disconnected(self):
        """write() does nothing when inner is disconnected."""
        inner = MagicMock()
        inner.is_connected = False
        profile = PrinterProfile(name="test")
        ppd = ProfilePrinterDriver(inner, profile)

        ppd.write("A")
        inner.write.assert_not_called()

    def test_end_response_flushes_cups_line_buffer(self):
        """Cut sequences contain no \\n — must force-flush CUPS line buffer.

        Regression: earlier the cut bytes were appended to CupsPrinterDriver's
        line buffer but never reached lp because the buffer only flushed on \\n.
        """
        with patch("claude_teletype.printer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
            cups = CupsPrinterDriver("test_queue")
            profile = PrinterProfile(
                name="receipt",
                init_sequence=b"\x1b@",
                end_of_response_sequence=b"\x1bd\x05\x1dV\x00",
            )
            ppd = ProfilePrinterDriver(cups, profile)

            ppd.write("H")
            ppd.write("i")
            ppd.write("\n")
            ppd.end_response()

            sent_to_lp = b"".join(
                c.kwargs.get("input", b"") for c in mock_run.call_args_list
            )
            assert b"\x1d\x56\x00" in sent_to_lp  # cut bytes reached lp

    def test_cups_driver_flush_emits_partial_line(self):
        """CupsPrinterDriver.flush() emits the buffered line even without \\n."""
        with patch("claude_teletype.printer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
            cups = CupsPrinterDriver("test_queue")
            cups.write("X")
            cups.write("Y")
            assert mock_run.call_count == 0  # not yet flushed
            cups.flush()
            assert mock_run.call_count == 1
            assert mock_run.call_args.kwargs["input"] == b"XY"

    def test_cups_driver_flush_noop_when_buffer_empty(self):
        """CupsPrinterDriver.flush() with empty buffer does nothing."""
        with patch("claude_teletype.printer.subprocess.run") as mock_run:
            cups = CupsPrinterDriver("test_queue")
            cups.flush()
            assert mock_run.call_count == 0

    def test_end_response_emits_sequence_after_writes(self):
        """end_response() sends profile.end_of_response_sequence after content writes."""
        inner = MagicMock()
        inner.is_connected = True
        profile = PrinterProfile(
            name="receipt",
            init_sequence=b"\x1b@",
            end_of_response_sequence=b"\x1bd\x05\x1dV\x00",
        )
        ppd = ProfilePrinterDriver(inner, profile)

        ppd.write("H")
        ppd.write("i")
        ppd.end_response()

        raw = _collect_raw(inner)
        assert raw.endswith(b"\x1bd\x05\x1dV\x00")

    def test_end_response_noop_without_writes(self):
        """end_response() is a no-op when nothing has been written (no blank cut)."""
        inner = MagicMock()
        inner.is_connected = True
        profile = PrinterProfile(
            name="receipt",
            end_of_response_sequence=b"\x1bd\x05\x1dV\x00",
        )
        ppd = ProfilePrinterDriver(inner, profile)

        ppd.end_response()

        inner.write.assert_not_called()

    def test_end_response_idempotent(self):
        """Calling end_response() twice in a row only cuts once."""
        inner = MagicMock()
        inner.is_connected = True
        profile = PrinterProfile(
            name="receipt",
            end_of_response_sequence=b"\x1bd\x05\x1dV\x00",
        )
        ppd = ProfilePrinterDriver(inner, profile)
        ppd._initialized = True

        ppd.write("X")
        ppd.end_response()
        first = inner.write.call_count
        ppd.end_response()  # second call: no new writes since last end_response
        assert inner.write.call_count == first

    def test_end_response_noop_without_sequence(self):
        """end_response() is a no-op when profile has no end_of_response_sequence."""
        inner = MagicMock()
        inner.is_connected = True
        profile = PrinterProfile(name="impact")  # no end_of_response_sequence
        ppd = ProfilePrinterDriver(inner, profile)
        ppd._initialized = True
        ppd._has_unflushed_output = True

        ppd.end_response()

        # No additional write should have been triggered for the empty sequence
        inner.write.assert_not_called()

    def test_close_cuts_partial_response(self):
        """close() emits end_of_response_sequence if last response wasn't flushed."""
        inner = MagicMock()
        inner.is_connected = True
        profile = PrinterProfile(
            name="receipt",
            init_sequence=b"\x1b@",
            reset_sequence=b"\x1b@",
            end_of_response_sequence=b"\x1bd\x05\x1dV\x00",
            formfeed_on_close=False,
        )
        ppd = ProfilePrinterDriver(inner, profile)

        ppd.write("partial")
        ppd.close()

        raw = _collect_raw(inner)
        # Cut sequence should appear before the final reset
        cut_idx = raw.find(b"\x1bd\x05\x1dV\x00")
        reset_idx = raw.rfind(b"\x1b@")
        assert cut_idx != -1
        assert reset_idx > cut_idx

    def test_close_skips_cut_when_already_flushed(self):
        """close() does not double-cut when end_response was already called."""
        inner = MagicMock()
        inner.is_connected = True
        profile = PrinterProfile(
            name="receipt",
            init_sequence=b"\x1b@",
            reset_sequence=b"\x1b@",
            end_of_response_sequence=b"\x1bd\x05\x1dV\x00",
            formfeed_on_close=False,
        )
        ppd = ProfilePrinterDriver(inner, profile)

        ppd.write("done")
        ppd.end_response()  # already cut
        before_close = _collect_raw(inner)
        cuts_before = before_close.count(b"\x1bd\x05\x1dV\x00")

        ppd.close()
        after_close = _collect_raw(inner)
        cuts_after = after_close.count(b"\x1bd\x05\x1dV\x00")

        assert cuts_before == 1
        assert cuts_after == 1  # close did not add a second cut

    def test_discover_printer_with_profile(self, tmp_path):
        """discover_printer(profile=...) wraps with ProfilePrinterDriver."""
        dev = tmp_path / "dev"
        dev.touch()
        juki = get_profile("juki")
        driver = discover_printer(device_override=str(dev), profile=juki)
        assert isinstance(driver, ProfilePrinterDriver)
        assert driver._profile.name == "juki"
        driver._inner.close()

    def test_discover_printer_generic_no_wrap(self, tmp_path):
        """discover_printer(profile=generic) does not wrap (generic has no ESC codes)."""
        dev = tmp_path / "dev"
        dev.touch()
        generic = get_profile("generic")
        driver = discover_printer(device_override=str(dev), profile=generic)
        assert isinstance(driver, FilePrinterDriver)
        driver.close()


# ---------------------------------------------------------------------------
# discover_printer() with juki=True tests
# ---------------------------------------------------------------------------


def test_discover_juki_wraps_file_driver(tmp_path: Path):
    """discover_printer(device_override=..., juki=True) wraps in ProfilePrinterDriver."""
    dev = tmp_path / "dev"
    dev.touch()
    driver = discover_printer(device_override=str(dev), juki=True)
    assert isinstance(driver, ProfilePrinterDriver)
    assert isinstance(driver._inner, FilePrinterDriver)
    driver._inner.close()


@patch("claude_teletype.printer.discover_usb_device")
@patch("claude_teletype.printer.subprocess.run")
def test_discover_juki_wraps_cups_driver(mock_run: MagicMock, mock_usb: MagicMock):
    """discover_printer(juki=True) with CUPS printer wraps in ProfilePrinterDriver."""
    mock_usb.return_value = None
    mock_run.return_value = MagicMock(
        stdout="device for MyPrinter: usb://Vendor/Model?serial=123\n",
        returncode=0,
    )
    driver = discover_printer(juki=True)
    assert isinstance(driver, ProfilePrinterDriver)
    assert isinstance(driver._inner, CupsPrinterDriver)


@patch("claude_teletype.printer.discover_usb_device")
@patch("claude_teletype.printer.subprocess.run")
def test_discover_juki_null_not_wrapped(mock_run: MagicMock, mock_usb: MagicMock):
    """discover_printer(juki=True) with no printers returns NullPrinterDriver (not wrapped)."""
    mock_usb.return_value = None
    mock_run.return_value = MagicMock(stdout="", returncode=0)
    driver = discover_printer(juki=True)
    assert isinstance(driver, NullPrinterDriver)


# ---------------------------------------------------------------------------
# UsbPrinterDriver tests
# ---------------------------------------------------------------------------


def test_usb_driver_is_connected():
    """UsbPrinterDriver is connected after construction."""
    dev = MagicMock()
    ep_out = MagicMock()
    driver = UsbPrinterDriver(dev, ep_out)
    assert driver.is_connected is True


def test_usb_driver_write_calls_endpoint():
    """write('A') calls ep_out.write(b'A')."""
    dev = MagicMock()
    ep_out = MagicMock()
    driver = UsbPrinterDriver(dev, ep_out)
    driver.write("A")
    ep_out.write.assert_called_once_with(b"A")


def test_usb_driver_disconnect_on_error():
    """USB error during write sets is_connected=False."""
    dev = MagicMock()
    ep_out = MagicMock()
    ep_out.write.side_effect = Exception("USB error")
    driver = UsbPrinterDriver(dev, ep_out)
    driver.write("A")
    assert driver.is_connected is False


def test_usb_driver_noop_when_disconnected():
    """write() does nothing when already disconnected."""
    dev = MagicMock()
    ep_out = MagicMock()
    driver = UsbPrinterDriver(dev, ep_out)
    driver._connected = False
    driver.write("A")
    ep_out.write.assert_not_called()


def test_usb_driver_close_disposes_resources():
    """close() calls usb.util.dispose_resources."""
    dev = MagicMock()
    ep_out = MagicMock()
    driver = UsbPrinterDriver(dev, ep_out)
    mock_usb_util = MagicMock()
    mock_usb = MagicMock()
    mock_usb.util = mock_usb_util
    with patch.dict("sys.modules", {"usb": mock_usb, "usb.util": mock_usb_util}):
        driver.close()
        mock_usb_util.dispose_resources.assert_called_once_with(dev)
    assert driver._dev is None


def test_usb_driver_close_handles_import_error():
    """close() handles missing usb module gracefully."""
    dev = MagicMock()
    ep_out = MagicMock()
    driver = UsbPrinterDriver(dev, ep_out)
    # Simulate usb not installed: setting to None causes ImportError
    with patch.dict("sys.modules", {"usb": None, "usb.util": None}):
        driver.close()  # should not raise
    assert driver._dev is None


# ---------------------------------------------------------------------------
# discover_usb_device() tests
# ---------------------------------------------------------------------------


def test_discover_usb_returns_none_when_no_pyusb():
    """discover_usb_device() returns None when pyusb is not installed."""
    # Setting sys.modules entries to None causes ImportError on import
    with patch.dict("sys.modules", {"usb": None, "usb.core": None, "usb.util": None}):
        result = discover_usb_device()
    assert result is None


def test_discover_usb_returns_none_when_no_backend():
    """discover_usb_device() returns None when libusb backend is missing."""
    mock_usb_core = MagicMock()
    mock_usb_core.NoBackendError = type("NoBackendError", (Exception,), {})
    mock_usb_core.find.side_effect = mock_usb_core.NoBackendError("no backend")
    mock_usb_util = MagicMock()
    mock_usb = MagicMock()
    mock_usb.core = mock_usb_core
    mock_usb.util = mock_usb_util

    with patch.dict("sys.modules", {"usb": mock_usb, "usb.core": mock_usb_core, "usb.util": mock_usb_util}):
        result = discover_usb_device()
    assert result is None


def test_discover_usb_returns_driver_when_device_found():
    """discover_usb_device() returns UsbPrinterDriver when a printer-class device exists."""
    mock_ep = MagicMock()
    mock_ep.bEndpointAddress = 0x01

    mock_intf = MagicMock()
    mock_intf.bInterfaceClass = 7
    mock_intf.bInterfaceNumber = 0

    mock_cfg = MagicMock()
    mock_cfg.__iter__ = MagicMock(return_value=iter([mock_intf]))

    mock_dev = MagicMock()
    mock_dev.__iter__ = MagicMock(return_value=iter([mock_cfg]))
    mock_dev.is_kernel_driver_active.return_value = False

    mock_usb_core = MagicMock()
    mock_usb_core.NoBackendError = type("NoBackendError", (Exception,), {})
    mock_usb_core.find.return_value = [mock_dev]

    mock_usb_util = MagicMock()
    mock_usb_util.ENDPOINT_OUT = 0x00
    mock_usb_util.endpoint_direction.return_value = 0x00
    mock_usb_util.find_descriptor.return_value = mock_ep

    mock_usb = MagicMock()
    mock_usb.core = mock_usb_core
    mock_usb.util = mock_usb_util

    with patch.dict("sys.modules", {"usb": mock_usb, "usb.core": mock_usb_core, "usb.util": mock_usb_util}):
        result = discover_usb_device()
    assert result is not None
    assert isinstance(result, UsbPrinterDriver)
    assert result.is_connected is True


def test_discover_usb_returns_none_when_no_printer_class():
    """discover_usb_device() returns None when no device has printer class."""
    mock_intf = MagicMock()
    mock_intf.bInterfaceClass = 3  # HID, not printer

    mock_cfg = MagicMock()
    mock_cfg.__iter__ = MagicMock(return_value=iter([mock_intf]))

    mock_dev = MagicMock()
    mock_dev.__iter__ = MagicMock(return_value=iter([mock_cfg]))

    mock_usb_core = MagicMock()
    mock_usb_core.NoBackendError = type("NoBackendError", (Exception,), {})
    mock_usb_core.find.return_value = [mock_dev]

    mock_usb_util = MagicMock()
    mock_usb = MagicMock()
    mock_usb.core = mock_usb_core
    mock_usb.util = mock_usb_util

    with patch.dict("sys.modules", {"usb": mock_usb, "usb.core": mock_usb_core, "usb.util": mock_usb_util}):
        result = discover_usb_device()
    assert result is None


# ---------------------------------------------------------------------------
# discover_printer() USB priority tests
# ---------------------------------------------------------------------------


@patch("claude_teletype.printer.discover_usb_device")
@patch("claude_teletype.printer.subprocess.run")
def test_discover_juki_tries_usb_before_cups(mock_run: MagicMock, mock_usb: MagicMock):
    """discover_printer(juki=True) tries USB first; if found, skips CUPS."""
    mock_usb.return_value = UsbPrinterDriver(MagicMock(), MagicMock())
    driver = discover_printer(juki=True)
    assert isinstance(driver, ProfilePrinterDriver)
    assert isinstance(driver._inner, UsbPrinterDriver)
    mock_run.assert_not_called()  # CUPS not tried


@patch("claude_teletype.printer.discover_usb_device")
@patch("claude_teletype.printer.subprocess.run")
def test_discover_juki_falls_back_to_cups_when_no_usb(mock_run: MagicMock, mock_usb: MagicMock):
    """discover_printer(juki=True) falls back to CUPS when USB returns None."""
    mock_usb.return_value = None
    mock_run.return_value = MagicMock(
        stdout="device for MyPrinter: usb://Vendor/Model?serial=123\n",
        returncode=0,
    )
    driver = discover_printer(juki=True)
    assert isinstance(driver, ProfilePrinterDriver)
    assert isinstance(driver._inner, CupsPrinterDriver)


@patch("claude_teletype.printer.discover_usb_device")
@patch("claude_teletype.printer.subprocess.run")
def test_discover_no_juki_skips_usb(mock_run: MagicMock, mock_usb: MagicMock):
    """discover_printer(juki=False) does not try USB discovery."""
    mock_run.return_value = MagicMock(stdout="", returncode=0)
    discover_printer(juki=False)
    mock_usb.assert_not_called()


# ---------------------------------------------------------------------------
# discover_usb_device_verbose() tests
# ---------------------------------------------------------------------------


def test_verbose_returns_diagnostics_when_no_pyusb():
    """discover_usb_device_verbose() returns diagnostic when pyusb missing."""
    with patch.dict("sys.modules", {"usb": None, "usb.core": None, "usb.util": None}):
        driver, diagnostics = discover_usb_device_verbose()
    assert driver is None
    assert any("pyusb not installed" in d for d in diagnostics)


def test_verbose_returns_diagnostics_when_no_backend():
    """discover_usb_device_verbose() returns diagnostic when no libusb backend."""
    mock_usb_core = MagicMock()
    mock_usb_core.NoBackendError = type("NoBackendError", (Exception,), {})
    mock_usb_core.find.side_effect = mock_usb_core.NoBackendError("no backend")
    mock_usb_util = MagicMock()
    mock_usb = MagicMock()
    mock_usb.core = mock_usb_core
    mock_usb.util = mock_usb_util

    with patch.dict(
        "sys.modules", {"usb": mock_usb, "usb.core": mock_usb_core, "usb.util": mock_usb_util}
    ):
        driver, diagnostics = discover_usb_device_verbose()
    assert driver is None
    assert any("libusb backend not found" in d for d in diagnostics)


def test_verbose_returns_driver_and_success_message():
    """discover_usb_device_verbose() returns driver + success diagnostic."""
    mock_ep = MagicMock()
    mock_ep.bEndpointAddress = 0x01

    mock_intf = MagicMock()
    mock_intf.bInterfaceClass = 7
    mock_intf.bInterfaceNumber = 0

    mock_cfg = MagicMock()
    mock_cfg.__iter__ = MagicMock(return_value=iter([mock_intf]))

    mock_dev = MagicMock()
    mock_dev.__iter__ = MagicMock(return_value=iter([mock_cfg]))
    mock_dev.is_kernel_driver_active.return_value = False
    mock_dev.idVendor = 0x1234
    mock_dev.idProduct = 0x5678
    mock_dev.product = "TestPrinter"

    mock_usb_core = MagicMock()
    mock_usb_core.NoBackendError = type("NoBackendError", (Exception,), {})
    mock_usb_core.find.return_value = [mock_dev]

    mock_usb_util = MagicMock()
    mock_usb_util.ENDPOINT_OUT = 0x00
    mock_usb_util.endpoint_direction.return_value = 0x00
    mock_usb_util.find_descriptor.return_value = mock_ep

    mock_usb = MagicMock()
    mock_usb.core = mock_usb_core
    mock_usb.util = mock_usb_util

    with patch.dict(
        "sys.modules", {"usb": mock_usb, "usb.core": mock_usb_core, "usb.util": mock_usb_util}
    ):
        driver, diagnostics = discover_usb_device_verbose()
    assert driver is not None
    assert isinstance(driver, UsbPrinterDriver)
    assert any("Found USB device: TestPrinter" in d for d in diagnostics)
    assert any("USB printer found: endpoint OUT" in d for d in diagnostics)


def test_verbose_no_printer_class_shows_device_count():
    """discover_usb_device_verbose() reports device count when no printers found."""
    mock_intf = MagicMock()
    mock_intf.bInterfaceClass = 3  # HID

    mock_cfg = MagicMock()
    mock_cfg.__iter__ = MagicMock(return_value=iter([mock_intf]))

    mock_dev = MagicMock()
    mock_dev.__iter__ = MagicMock(return_value=iter([mock_cfg]))

    mock_usb_core = MagicMock()
    mock_usb_core.NoBackendError = type("NoBackendError", (Exception,), {})
    mock_usb_core.find.return_value = [mock_dev]

    mock_usb_util = MagicMock()
    mock_usb = MagicMock()
    mock_usb.core = mock_usb_core
    mock_usb.util = mock_usb_util

    with patch.dict(
        "sys.modules", {"usb": mock_usb, "usb.core": mock_usb_core, "usb.util": mock_usb_util}
    ):
        driver, diagnostics = discover_usb_device_verbose()
    assert driver is None
    assert any("No USB printer-class devices found. 1 other" in d for d in diagnostics)


def test_verbose_kernel_driver_detach_reported():
    """discover_usb_device_verbose() reports kernel driver detach attempt."""
    mock_ep = MagicMock()
    mock_ep.bEndpointAddress = 0x01

    mock_intf = MagicMock()
    mock_intf.bInterfaceClass = 7
    mock_intf.bInterfaceNumber = 0

    mock_cfg = MagicMock()
    mock_cfg.__iter__ = MagicMock(return_value=iter([mock_intf]))

    mock_dev = MagicMock()
    mock_dev.__iter__ = MagicMock(return_value=iter([mock_cfg]))
    mock_dev.is_kernel_driver_active.return_value = True
    mock_dev.detach_kernel_driver.side_effect = OSError("access denied")
    mock_dev.idVendor = 0x1234
    mock_dev.idProduct = 0x5678
    mock_dev.product = "TestPrinter"

    mock_usb_core = MagicMock()
    mock_usb_core.NoBackendError = type("NoBackendError", (Exception,), {})
    mock_usb_core.find.return_value = [mock_dev]

    mock_usb_util = MagicMock()
    mock_usb_util.ENDPOINT_OUT = 0x00
    mock_usb_util.endpoint_direction.return_value = 0x00
    mock_usb_util.find_descriptor.return_value = mock_ep

    mock_usb = MagicMock()
    mock_usb.core = mock_usb_core
    mock_usb.util = mock_usb_util

    with patch.dict(
        "sys.modules", {"usb": mock_usb, "usb.core": mock_usb_core, "usb.util": mock_usb_util}
    ):
        driver, diagnostics = discover_usb_device_verbose()
    assert any("Kernel driver active on interface 0" in d for d in diagnostics)
    assert any("Could not detach kernel driver" in d for d in diagnostics)


# ---------------------------------------------------------------------------
# kernel_driver_holds_printer() probe
# ---------------------------------------------------------------------------


def _build_mocked_usb(*, kernel_active: bool, intf_class: int = 7):
    """Construct a minimal pyusb-style mock chain for kernel-driver probe tests."""
    mock_intf = MagicMock()
    mock_intf.bInterfaceClass = intf_class
    mock_intf.bInterfaceNumber = 0

    mock_cfg = MagicMock()
    mock_cfg.__iter__ = MagicMock(return_value=iter([mock_intf]))

    mock_dev = MagicMock()
    mock_dev.__iter__ = MagicMock(return_value=iter([mock_cfg]))
    mock_dev.is_kernel_driver_active.return_value = kernel_active

    mock_usb_core = MagicMock()
    mock_usb_core.find.return_value = mock_dev

    mock_usb_util = MagicMock()
    mock_usb = MagicMock()
    mock_usb.core = mock_usb_core
    mock_usb.util = mock_usb_util
    return mock_usb, mock_usb_core, mock_usb_util


def test_kernel_driver_holds_printer_true_when_kext_active():
    """kernel_driver_holds_printer() returns True when kernel driver is bound."""
    from claude_teletype.printer import kernel_driver_holds_printer

    mock_usb, mock_core, mock_util = _build_mocked_usb(kernel_active=True)
    with patch.dict(
        "sys.modules", {"usb": mock_usb, "usb.core": mock_core, "usb.util": mock_util}
    ):
        assert kernel_driver_holds_printer(0x1A86, 0x7584) is True


def test_kernel_driver_holds_printer_false_when_kext_inactive():
    """kernel_driver_holds_printer() returns False when no kernel driver is bound."""
    from claude_teletype.printer import kernel_driver_holds_printer

    mock_usb, mock_core, mock_util = _build_mocked_usb(kernel_active=False)
    with patch.dict(
        "sys.modules", {"usb": mock_usb, "usb.core": mock_core, "usb.util": mock_util}
    ):
        assert kernel_driver_holds_printer(0x1A86, 0x7584) is False


def test_kernel_driver_holds_printer_false_for_non_printer_class():
    """Vendor-specific (non-printer-class) interfaces don't trigger the macOS kext."""
    from claude_teletype.printer import kernel_driver_holds_printer

    mock_usb, mock_core, mock_util = _build_mocked_usb(
        kernel_active=True, intf_class=0xFF
    )
    with patch.dict(
        "sys.modules", {"usb": mock_usb, "usb.core": mock_core, "usb.util": mock_util}
    ):
        assert kernel_driver_holds_printer(0x1A86, 0x7584) is False


def test_kernel_driver_holds_printer_false_when_device_missing():
    """No matching device → False (no false alarm)."""
    from claude_teletype.printer import kernel_driver_holds_printer

    mock_usb_core = MagicMock()
    mock_usb_core.find.return_value = None
    mock_usb_util = MagicMock()
    mock_usb = MagicMock()
    mock_usb.core = mock_usb_core
    mock_usb.util = mock_usb_util
    with patch.dict(
        "sys.modules",
        {"usb": mock_usb, "usb.core": mock_usb_core, "usb.util": mock_usb_util},
    ):
        assert kernel_driver_holds_printer(0xDEAD, 0xBEEF) is False


# ---------------------------------------------------------------------------
# discover_macos_usb_printers() tests
# ---------------------------------------------------------------------------


@patch("claude_teletype.printer.sys")
@patch("claude_teletype.printer.subprocess.run")
def test_macos_discovery_parses_ioreg(mock_run: MagicMock, mock_sys: MagicMock):
    """discover_macos_usb_printers() parses ioreg output for printer devices."""
    mock_sys.platform = "darwin"
    mock_run.return_value = MagicMock(
        stdout='''\
+-o USB2.0-Print@1234  <class IOUSBHostDevice>
  {
    "USB Product Name" = "USB2.0-Print"
    "idVendor" = 1234
    "idProduct" = 5678
    "locationID" = 12345678
  }
''',
        returncode=0,
    )

    result = discover_macos_usb_printers()

    assert len(result) == 1
    assert result[0]["name"] == "USB2.0-Print"
    assert result[0]["vid"] == 1234
    assert result[0]["pid"] == 5678


@patch("claude_teletype.printer.sys")
def test_macos_discovery_skips_non_darwin(mock_sys: MagicMock):
    """discover_macos_usb_printers() returns empty on non-macOS."""
    mock_sys.platform = "linux"
    result = discover_macos_usb_printers()
    assert result == []


@patch("claude_teletype.printer.sys")
@patch("claude_teletype.printer.subprocess.run")
def test_macos_discovery_filters_non_printers(mock_run: MagicMock, mock_sys: MagicMock):
    """discover_macos_usb_printers() filters out non-printer devices."""
    mock_sys.platform = "darwin"
    mock_run.return_value = MagicMock(
        stdout='''\
+-o USB Keyboard@1234  <class IOUSBHostDevice>
  {
    "USB Product Name" = "USB Keyboard"
    "idVendor" = 1111
    "idProduct" = 2222
    "locationID" = 11111111
  }
''',
        returncode=0,
    )

    result = discover_macos_usb_printers()
    assert result == []


# ---------------------------------------------------------------------------
# discover_cups_printers() URI enrichment tests
# ---------------------------------------------------------------------------


@patch("claude_teletype.printer.subprocess.run")
def test_cups_discovery_parses_usb_uri(mock_run: MagicMock):
    """discover_cups_printers() extracts vendor, model, serial from USB URI."""
    mock_run.return_value = MagicMock(
        stdout="device for MyPrinter: usb://Acme/LaserJet?serial=ABC123\n",
        returncode=0,
    )
    printers = discover_cups_printers()
    assert len(printers) == 1
    assert printers[0]["vendor"] == "Acme"
    assert printers[0]["model"] == "LaserJet"
    assert printers[0]["serial"] == "ABC123"


@patch("claude_teletype.printer.subprocess.run")
def test_cups_discovery_handles_uri_without_serial(mock_run: MagicMock):
    """discover_cups_printers() works when URI has no serial parameter."""
    mock_run.return_value = MagicMock(
        stdout="device for MyPrinter: usb://Acme/LaserJet\n",
        returncode=0,
    )
    printers = discover_cups_printers()
    assert len(printers) == 1
    assert printers[0]["vendor"] == "Acme"
    assert printers[0]["model"] == "LaserJet"
    assert "serial" not in printers[0]


@patch("claude_teletype.printer.subprocess.run")
def test_cups_discovery_decodes_percent_encoding(mock_run: MagicMock):
    """discover_cups_printers() decodes %20 in vendor/model names."""
    mock_run.return_value = MagicMock(
        stdout="device for MyPrinter: usb://My%20Vendor/My%20Model?serial=X\n",
        returncode=0,
    )
    printers = discover_cups_printers()
    assert printers[0]["vendor"] == "My Vendor"
    assert printers[0]["model"] == "My Model"


@patch("claude_teletype.printer.subprocess.run")
def test_cups_discovery_marks_disabled_queue(mock_run: MagicMock):
    """lpstat -p ``disabled`` line marks the queue enabled=False."""
    mock_run.return_value = MagicMock(
        stdout=(
            "printer USB2.0-Print disabled since Tue Feb 17 00:09:26 2026 -\n"
            "\tUnable to send data to printer.\n"
            "printer HP_OK is idle.  enabled since Wed Mar  1 12:00:00 2026\n"
            "device for USB2.0-Print: usb:///USB2.0-Print\n"
            "device for HP_OK: usb://HP/OK\n"
        ),
        returncode=0,
    )
    printers = {p["name"]: p for p in discover_cups_printers()}
    assert printers["USB2.0-Print"]["enabled"] is False
    assert printers["HP_OK"]["enabled"] is True


@patch("claude_teletype.printer.subprocess.run")
def test_cups_discovery_defaults_enabled_when_state_missing(mock_run: MagicMock):
    """When lpstat output has no state line for a queue, default to enabled=True."""
    mock_run.return_value = MagicMock(
        stdout="device for MyPrinter: usb://Acme/LaserJet\n",
        returncode=0,
    )
    printers = discover_cups_printers()
    assert printers[0]["enabled"] is True
