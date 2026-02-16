"""Tests for raw teletype mode."""

from unittest.mock import MagicMock, patch

from claude_teletype.printer import JukiPrinterDriver
from claude_teletype.teletype import run_teletype


def _make_mock_driver():
    driver = MagicMock()
    driver.is_connected = True
    return driver


def _written_bytes(driver):
    """Collect all data written to the mock driver as a bytes object."""
    result = b""
    for c in driver.write.call_args_list:
        result += c.args[0].encode("ascii")
    return result


# ---------------------------------------------------------------------------
# Generic mode (no --juki)
# ---------------------------------------------------------------------------


@patch("claude_teletype.teletype.termios")
@patch("claude_teletype.teletype.tty")
@patch("claude_teletype.teletype.sys")
def test_generic_no_init_codes(mock_sys, mock_tty, mock_termios):
    """Generic mode sends no init codes — only form feed on exit."""
    driver = _make_mock_driver()
    mock_sys.stdin.fileno.return_value = 0
    mock_sys.stdin.read.return_value = "\x03"
    mock_sys.stderr = MagicMock()

    run_teletype(driver)

    raw = _written_bytes(driver)
    assert raw == b"\f"


@patch("claude_teletype.teletype.termios")
@patch("claude_teletype.teletype.tty")
@patch("claude_teletype.teletype.sys")
def test_generic_enter_sends_lf_only(mock_sys, mock_tty, mock_termios):
    """Generic mode: Enter sends LF only (no CR)."""
    driver = _make_mock_driver()
    mock_sys.stdin.fileno.return_value = 0
    mock_sys.stdin.read.side_effect = ["\r", "\x03"]
    mock_sys.stderr = MagicMock()

    run_teletype(driver)

    raw = _written_bytes(driver)
    assert raw == b"\n\f"


# ---------------------------------------------------------------------------
# Juki mode (--juki)
# ---------------------------------------------------------------------------


@patch("claude_teletype.teletype.termios")
@patch("claude_teletype.teletype.tty")
@patch("claude_teletype.teletype.sys")
def test_juki_sends_init_codes(mock_sys, mock_tty, mock_termios):
    """Juki mode sends RESET + LINE_SPACING + FIXED_PITCH on start."""
    driver = _make_mock_driver()
    mock_sys.stdin.fileno.return_value = 0
    mock_sys.stdin.read.return_value = "\x03"
    mock_sys.stderr = MagicMock()

    run_teletype(driver, juki=True)

    raw = _written_bytes(driver)
    expected_init = (
        JukiPrinterDriver.RESET
        + JukiPrinterDriver.LINE_SPACING
        + JukiPrinterDriver.FIXED_PITCH
    )
    assert raw.startswith(expected_init)


@patch("claude_teletype.teletype.termios")
@patch("claude_teletype.teletype.tty")
@patch("claude_teletype.teletype.sys")
def test_juki_enter_sends_cr_lf(mock_sys, mock_tty, mock_termios):
    """Juki mode: Enter sends CR+LF as single write."""
    driver = _make_mock_driver()
    mock_sys.stdin.fileno.return_value = 0
    mock_sys.stdin.read.side_effect = ["\r", "\x03"]
    mock_sys.stderr = MagicMock()

    run_teletype(driver, juki=True)

    raw = _written_bytes(driver)
    init_len = len(
        JukiPrinterDriver.RESET
        + JukiPrinterDriver.LINE_SPACING
        + JukiPrinterDriver.FIXED_PITCH
    )
    after_init = raw[init_len:]
    assert after_init == b"\r\n\f"


@patch("claude_teletype.teletype.termios")
@patch("claude_teletype.teletype.tty")
@patch("claude_teletype.teletype.sys")
def test_juki_newline_input_sends_cr_lf(mock_sys, mock_tty, mock_termios):
    """Juki mode: \\n input also sends CR+LF."""
    driver = _make_mock_driver()
    mock_sys.stdin.fileno.return_value = 0
    mock_sys.stdin.read.side_effect = ["\n", "\x03"]
    mock_sys.stderr = MagicMock()

    run_teletype(driver, juki=True)

    raw = _written_bytes(driver)
    init_len = len(
        JukiPrinterDriver.RESET
        + JukiPrinterDriver.LINE_SPACING
        + JukiPrinterDriver.FIXED_PITCH
    )
    after_init = raw[init_len:]
    assert after_init == b"\r\n\f"


# ---------------------------------------------------------------------------
# Character forwarding (both modes)
# ---------------------------------------------------------------------------


@patch("claude_teletype.teletype.termios")
@patch("claude_teletype.teletype.tty")
@patch("claude_teletype.teletype.sys")
def test_printable_chars_forwarded(mock_sys, mock_tty, mock_termios):
    """Printable characters are forwarded to the driver."""
    driver = _make_mock_driver()
    mock_sys.stdin.fileno.return_value = 0
    mock_sys.stdin.read.side_effect = ["H", "i", "\x03"]
    mock_sys.stderr = MagicMock()

    run_teletype(driver)

    raw = _written_bytes(driver)
    assert b"Hi" in raw


# ---------------------------------------------------------------------------
# Exit behavior
# ---------------------------------------------------------------------------


@patch("claude_teletype.teletype.termios")
@patch("claude_teletype.teletype.tty")
@patch("claude_teletype.teletype.sys")
def test_formfeed_on_exit(mock_sys, mock_tty, mock_termios):
    """Form feed sent on exit."""
    driver = _make_mock_driver()
    mock_sys.stdin.fileno.return_value = 0
    mock_sys.stdin.read.return_value = "\x03"
    mock_sys.stderr = MagicMock()

    run_teletype(driver)

    raw = _written_bytes(driver)
    assert raw.endswith(b"\f")


@patch("claude_teletype.teletype.termios")
@patch("claude_teletype.teletype.tty")
@patch("claude_teletype.teletype.sys")
def test_driver_closed_on_exit(mock_sys, mock_tty, mock_termios):
    """Driver.close() called on exit."""
    driver = _make_mock_driver()
    mock_sys.stdin.fileno.return_value = 0
    mock_sys.stdin.read.return_value = "\x03"
    mock_sys.stderr = MagicMock()

    run_teletype(driver)

    driver.close.assert_called_once()


@patch("claude_teletype.teletype.termios")
@patch("claude_teletype.teletype.tty")
@patch("claude_teletype.teletype.sys")
def test_ctrl_c_exits_cleanly(mock_sys, mock_tty, mock_termios):
    """Ctrl-C exits the loop cleanly."""
    driver = _make_mock_driver()
    mock_sys.stdin.fileno.return_value = 0
    mock_sys.stdin.read.side_effect = ["A", "\x03"]
    mock_sys.stderr = MagicMock()

    run_teletype(driver)

    driver.close.assert_called_once()


@patch("claude_teletype.teletype.termios")
@patch("claude_teletype.teletype.tty")
@patch("claude_teletype.teletype.sys")
def test_empty_read_exits(mock_sys, mock_tty, mock_termios):
    """EOF exits the loop."""
    driver = _make_mock_driver()
    mock_sys.stdin.fileno.return_value = 0
    mock_sys.stdin.read.return_value = ""
    mock_sys.stderr = MagicMock()

    run_teletype(driver)

    driver.close.assert_called_once()


# ---------------------------------------------------------------------------
# Terminal restoration
# ---------------------------------------------------------------------------


@patch("claude_teletype.teletype.termios")
@patch("claude_teletype.teletype.tty")
@patch("claude_teletype.teletype.sys")
def test_terminal_restored_on_clean_exit(mock_sys, mock_tty, mock_termios):
    """termios.tcsetattr called to restore terminal on clean exit."""
    driver = _make_mock_driver()
    mock_sys.stdin.fileno.return_value = 0
    mock_sys.stdin.read.return_value = "\x03"
    mock_sys.stderr = MagicMock()
    mock_termios.TCSADRAIN = 1
    saved = mock_termios.tcgetattr.return_value

    run_teletype(driver)

    mock_termios.tcsetattr.assert_called_once_with(0, 1, saved)


@patch("claude_teletype.teletype.termios")
@patch("claude_teletype.teletype.tty")
@patch("claude_teletype.teletype.sys")
def test_terminal_restored_on_error(mock_sys, mock_tty, mock_termios):
    """termios.tcsetattr called even when stdin.read() raises."""
    driver = _make_mock_driver()
    mock_sys.stdin.fileno.return_value = 0
    mock_sys.stdin.read.side_effect = OSError("read error")
    mock_sys.stderr = MagicMock()
    mock_termios.TCSADRAIN = 1
    saved = mock_termios.tcgetattr.return_value

    try:
        run_teletype(driver)
    except OSError:
        pass

    mock_termios.tcsetattr.assert_called_once_with(0, 1, saved)
    driver.close.assert_called_once()


# ---------------------------------------------------------------------------
# Terminal echo
# ---------------------------------------------------------------------------


@patch("claude_teletype.teletype.termios")
@patch("claude_teletype.teletype.tty")
@patch("claude_teletype.teletype.sys")
def test_chars_echoed_to_stderr(mock_sys, mock_tty, mock_termios):
    """Printable chars are echoed to stderr."""
    driver = _make_mock_driver()
    mock_sys.stdin.fileno.return_value = 0
    mock_sys.stdin.read.side_effect = ["A", "\x03"]
    mock_stderr = MagicMock()
    mock_sys.stderr = mock_stderr

    run_teletype(driver)

    mock_stderr.write.assert_any_call("A")


@patch("claude_teletype.teletype.termios")
@patch("claude_teletype.teletype.tty")
@patch("claude_teletype.teletype.sys")
def test_enter_echoes_newline_to_stderr(mock_sys, mock_tty, mock_termios):
    """Enter echoes newline to stderr."""
    driver = _make_mock_driver()
    mock_sys.stdin.fileno.return_value = 0
    mock_sys.stdin.read.side_effect = ["\r", "\x03"]
    mock_stderr = MagicMock()
    mock_sys.stderr = mock_stderr

    run_teletype(driver)

    mock_stderr.write.assert_any_call("\n")


# ---------------------------------------------------------------------------
# CLI teletype tests
# ---------------------------------------------------------------------------


@patch("claude_teletype.printer.discover_usb_device_verbose")
@patch("claude_teletype.printer.subprocess.run")
def test_cli_teletype_shows_diagnostics_on_failure(mock_run, mock_verbose):
    """--teletype shows diagnostic messages when USB discovery fails."""
    from typer.testing import CliRunner

    from claude_teletype.cli import app

    mock_verbose.return_value = (None, ["pyusb not installed. Install with: uv sync --extra usb"])
    mock_run.return_value = MagicMock(stdout="", returncode=0)

    runner = CliRunner()
    result = runner.invoke(app, ["--teletype"])

    assert result.exit_code != 0
    assert "pyusb not installed" in result.output
    assert "No USB printer available" in result.output


@patch("claude_teletype.printer.discover_usb_device_verbose")
@patch("claude_teletype.printer.subprocess.run")
def test_cli_teletype_shows_cups_info(mock_run, mock_verbose):
    """--teletype shows CUPS USB printers when USB discovery fails."""
    from typer.testing import CliRunner

    from claude_teletype.cli import app

    mock_verbose.return_value = (
        None,
        ["libusb backend not found. Install with: brew install libusb"],
    )
    mock_run.return_value = MagicMock(
        stdout="device for MyPrinter: usb://Vendor/Model?serial=123\n",
        returncode=0,
    )

    runner = CliRunner()
    result = runner.invoke(app, ["--teletype"])

    assert result.exit_code != 0
    assert "CUPS sees USB printers" in result.output
    normalized = " ".join(result.output.split())
    assert "direct USB access" in normalized


@patch("claude_teletype.teletype.termios")
@patch("claude_teletype.teletype.tty")
@patch("claude_teletype.teletype.sys")
@patch("claude_teletype.printer.discover_usb_device_verbose")
def test_cli_teletype_device_fallback(mock_verbose, mock_sys, mock_tty, mock_termios, tmp_path):
    """--teletype --device falls back to FilePrinterDriver when USB fails."""
    from typer.testing import CliRunner

    from claude_teletype.cli import app

    mock_verbose.return_value = (None, ["pyusb not installed. Install with: uv sync --extra usb"])
    mock_sys.stdin.fileno.return_value = 0
    mock_sys.stdin.read.return_value = "\x03"
    mock_sys.stderr = MagicMock()
    mock_sys.platform = "darwin"

    dev = tmp_path / "dev"
    dev.touch()

    runner = CliRunner()
    result = runner.invoke(app, ["--teletype", "--device", str(dev)])

    assert "Falling back to device file" in result.output


@patch("claude_teletype.teletype.run_teletype")
@patch("claude_teletype.printer.discover_usb_device_verbose")
def test_cli_teletype_passes_juki_false(mock_verbose, mock_run_teletype):
    """--teletype without --juki passes juki=False."""
    from claude_teletype.cli import app
    from claude_teletype.printer import UsbPrinterDriver

    from typer.testing import CliRunner

    mock_driver = MagicMock(spec=UsbPrinterDriver)
    mock_verbose.return_value = (mock_driver, ["USB printer found: endpoint OUT 1"])

    runner = CliRunner()
    runner.invoke(app, ["--teletype"])

    mock_run_teletype.assert_called_once_with(mock_driver, juki=False)


@patch("claude_teletype.teletype.run_teletype")
@patch("claude_teletype.printer.discover_usb_device_verbose")
def test_cli_teletype_passes_juki_true(mock_verbose, mock_run_teletype):
    """--teletype --juki passes juki=True."""
    from claude_teletype.cli import app
    from claude_teletype.printer import UsbPrinterDriver

    from typer.testing import CliRunner

    mock_driver = MagicMock(spec=UsbPrinterDriver)
    mock_verbose.return_value = (mock_driver, ["USB printer found: endpoint OUT 1"])

    runner = CliRunner()
    runner.invoke(app, ["--teletype", "--juki"])

    mock_run_teletype.assert_called_once_with(mock_driver, juki=True)
