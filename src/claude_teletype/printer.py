"""Printer driver backends, auto-discovery, and resilient output wrapper."""

import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class PrinterDriver(Protocol):
    """Interface for all printer backends."""

    @property
    def is_connected(self) -> bool: ...

    def write(self, char: str) -> None: ...

    def close(self) -> None: ...


class NullPrinterDriver:
    """No-op driver for simulator-only mode."""

    @property
    def is_connected(self) -> bool:
        return False

    def write(self, char: str) -> None:
        pass

    def close(self) -> None:
        pass


class FilePrinterDriver:
    """Direct device file I/O driver."""

    def __init__(self, device_path: str) -> None:
        self._path = device_path
        self._fd = open(device_path, "wb", buffering=0)
        self._connected = True

    @property
    def is_connected(self) -> bool:
        return self._connected

    def write(self, char: str) -> None:
        if not self._connected:
            return
        try:
            self._fd.write(char.encode("ascii", errors="replace"))
        except (OSError, ValueError):
            self._connected = False

    def close(self) -> None:
        if self._fd and not self._fd.closed:
            self._fd.close()


class CupsPrinterDriver:
    """CUPS raw queue driver using lp subprocess."""

    def __init__(self, printer_name: str) -> None:
        self._name = printer_name
        self._connected = True
        self._line_buffer: list[str] = []

    @property
    def is_connected(self) -> bool:
        return self._connected

    def write(self, char: str) -> None:
        if not self._connected:
            return
        self._line_buffer.append(char)
        if char == "\n":
            self._flush_line()

    def _flush_line(self) -> None:
        line = "".join(self._line_buffer)
        self._line_buffer.clear()
        try:
            subprocess.run(
                ["lp", "-o", "raw", "-d", self._name],
                input=line.encode("ascii", errors="replace"),
                capture_output=True,
                timeout=10,
            )
        except (subprocess.SubprocessError, OSError):
            self._connected = False

    def close(self) -> None:
        if self._line_buffer:
            self._flush_line()


def discover_cups_printers() -> list[dict[str, str]]:
    """Discover USB printers via CUPS lpstat."""
    try:
        result = subprocess.run(
            ["lpstat", "-v"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return []

    printers = []
    pattern = re.compile(r"device for (\S+):\s+(.+)")
    for line in result.stdout.splitlines():
        match = pattern.match(line)
        if match:
            name, uri = match.group(1), match.group(2).strip()
            if uri.startswith("usb://"):
                printers.append({"name": name, "uri": uri})
    return printers


def discover_printer(device_override: str | None = None) -> PrinterDriver:
    """Select the best available printer backend.

    Priority:
    1. User-specified --device path -> FilePrinterDriver
    2. CUPS USB printer discovery -> CupsPrinterDriver
    3. Linux /dev/usb/lp* probe -> FilePrinterDriver
    4. Fallback -> NullPrinterDriver
    """
    if device_override:
        return FilePrinterDriver(device_override)

    cups_printers = discover_cups_printers()
    if cups_printers:
        return CupsPrinterDriver(cups_printers[0]["name"])

    if sys.platform == "linux":
        for dev in ["/dev/usb/lp0", "/dev/usb/lp1"]:
            if Path(dev).exists():
                return FilePrinterDriver(dev)

    return NullPrinterDriver()


def make_printer_output(driver: PrinterDriver) -> Callable[[str], None]:
    """Create an output_fn that writes to a printer with graceful degradation.

    On IOError/OSError, stops writing permanently. This implements
    PRNT-03 (graceful disconnect).
    """
    disconnected = False

    def printer_write(char: str) -> None:
        nonlocal disconnected
        if disconnected:
            return
        try:
            driver.write(char)
        except OSError:
            disconnected = True

    return printer_write
