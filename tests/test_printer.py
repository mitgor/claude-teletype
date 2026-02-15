"""Tests for printer driver backends, discovery, and resilient output wrapper."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claude_teletype.printer import (
    CupsPrinterDriver,
    FilePrinterDriver,
    NullPrinterDriver,
    discover_printer,
    make_printer_output,
)


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
# CupsPrinterDriver tests (mock subprocess.run)
# ---------------------------------------------------------------------------


def test_cups_driver_is_connected():
    """is_connected is True initially."""
    driver = CupsPrinterDriver("TestPrinter")
    assert driver.is_connected is True


@patch("claude_teletype.printer.subprocess.run")
def test_cups_driver_buffers_until_newline(mock_run: MagicMock):
    """write('A'), write('B') does NOT call subprocess; write('\\n') flushes."""
    driver = CupsPrinterDriver("TestPrinter")
    driver.write("A")
    driver.write("B")
    mock_run.assert_not_called()

    driver.write("\n")
    mock_run.assert_called_once_with(
        ["lp", "-o", "raw", "-d", "TestPrinter"],
        input=b"AB\n",
        capture_output=True,
        timeout=10,
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
    """output_fn delegates writes to the driver."""
    dev = tmp_path / "dev"
    dev.touch()
    driver = FilePrinterDriver(str(dev))
    output_fn = make_printer_output(driver)
    output_fn("X")
    driver.close()
    assert dev.read_bytes() == b"X"


def test_make_printer_output_degrades_on_error():
    """On IOError, output_fn degrades to no-op; write called only once."""
    driver = MagicMock()
    driver.write.side_effect = IOError("disconnected")
    output_fn = make_printer_output(driver)
    output_fn("A")  # should not raise
    output_fn("B")  # should be no-op
    assert driver.write.call_count == 1


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
    driver.close()
    assert collected == ["H", "i"]
    assert dev.read_bytes() == b"Hi"
