"""Printer driver backends, auto-discovery, and resilient output wrapper."""

import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


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
    """CUPS raw queue driver using lp subprocess.

    Flushes each line as a separate lp job for real-time output.
    """

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
                timeout=30,
            )
        except (subprocess.SubprocessError, OSError):
            self._connected = False

    def close(self) -> None:
        if self._line_buffer:
            self._flush_line()


class UsbPrinterDriver:
    """Direct USB bulk-transfer driver via pyusb, bypassing CUPS."""

    def __init__(self, dev: Any, ep_out: Any) -> None:
        self._dev = dev
        self._ep_out = ep_out
        self._connected = True

    @property
    def is_connected(self) -> bool:
        return self._connected

    def write(self, char: str) -> None:
        if not self._connected:
            return
        try:
            self._ep_out.write(char.encode("ascii", errors="replace"))
        except Exception:
            self._connected = False

    def close(self) -> None:
        if self._dev is not None:
            try:
                import usb.util

                usb.util.dispose_resources(self._dev)
            except Exception:
                pass
            self._dev = None


class JukiPrinterDriver:
    """Juki 6100 daisywheel impact printer driver.

    Wraps an inner PrinterDriver, prepending ESC initialization codes on first
    write and converting bare \\n to \\r\\n (impact printers need explicit CR).
    """

    # Juki 6100 ESC sequences
    RESET = b"\x1b\x1aI"  # ESC SUB I — full reset
    LINE_SPACING = b"\x1b\x1e\x09"  # ESC RS 9 — 1/6" line spacing
    FIXED_PITCH = b"\x1bQ"  # ESC Q — disable proportional spacing

    def __init__(self, inner: PrinterDriver) -> None:
        self._inner = inner
        self._initialized = False

    def _send_raw(self, data: bytes) -> None:
        """Send raw bytes through the inner driver."""
        for b in data:
            self._inner.write(chr(b))

    def _ensure_init(self) -> None:
        if not self._initialized:
            self._initialized = True
            self._send_raw(self.RESET + self.LINE_SPACING + self.FIXED_PITCH)

    @property
    def is_connected(self) -> bool:
        return self._inner.is_connected

    def write(self, char: str) -> None:
        if not self._inner.is_connected:
            return
        self._ensure_init()
        if char == "\n":
            self._inner.write("\r")
            self._inner.write("\n")
            # Re-send settings after newline so each CUPS job starts correctly
            self._send_raw(self.LINE_SPACING + self.FIXED_PITCH)
        else:
            self._inner.write(char)

    def close(self) -> None:
        if self._initialized and self._inner.is_connected:
            self._inner.write("\f")
        self._inner.close()


def select_printer(printers: list[dict[str, str]]) -> str | None:
    """Interactively select a CUPS printer from the discovered list.

    Returns the printer name, or None if no printers available.
    """
    if not printers:
        return None
    if len(printers) == 1:
        print(f"Selected printer: {printers[0]['name']}")
        return printers[0]["name"]

    print("Available USB printers:")
    for i, p in enumerate(printers, 1):
        print(f"  {i}. {p['name']}  ({p['uri']})")

    while True:
        try:
            choice = input(f"Select printer [1-{len(printers)}]: ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(printers):
                print(f"Selected printer: {printers[idx]['name']}")
                return printers[idx]["name"]
        except (ValueError, EOFError):
            pass
        print(f"Please enter a number between 1 and {len(printers)}.")


def discover_usb_device() -> UsbPrinterDriver | None:
    """Try to open a USB printer class device directly via pyusb.

    Returns UsbPrinterDriver on success, None if pyusb is missing, no
    backend is available, or no printer-class device is found.
    """
    try:
        import usb.core
        import usb.util
    except ImportError:
        return None

    try:
        devices = list(usb.core.find(find_all=True))
    except usb.core.NoBackendError:
        return None

    USB_PRINTER_CLASS = 7

    for dev in devices:
        for cfg in dev:
            for intf in cfg:
                if intf.bInterfaceClass != USB_PRINTER_CLASS:
                    continue
                # Try to detach kernel driver (best-effort, may fail on macOS)
                try:
                    if dev.is_kernel_driver_active(intf.bInterfaceNumber):
                        dev.detach_kernel_driver(intf.bInterfaceNumber)
                except Exception:
                    pass
                # Find bulk OUT endpoint
                ep_out = usb.util.find_descriptor(
                    intf,
                    custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
                    == usb.util.ENDPOINT_OUT,
                )
                if ep_out is not None:
                    try:
                        dev.set_configuration()
                    except Exception:
                        pass
                    return UsbPrinterDriver(dev, ep_out)
    return None


def discover_usb_device_verbose() -> tuple[UsbPrinterDriver | None, list[str]]:
    """Try to open a USB printer via pyusb, returning diagnostics.

    Returns (driver, diagnostics) where diagnostics is a list of
    human-readable strings explaining each step of discovery.
    """
    diagnostics: list[str] = []

    try:
        import usb.core
        import usb.util
    except ImportError:
        diagnostics.append("pyusb not installed. Install with: uv sync --extra usb")
        return None, diagnostics

    try:
        devices = list(usb.core.find(find_all=True))
    except usb.core.NoBackendError:
        diagnostics.append("libusb backend not found. Install with: brew install libusb")
        return None, diagnostics

    USB_PRINTER_CLASS = 7
    total_devices = len(devices)
    found_printer = False

    for dev in devices:
        for cfg in dev:
            for intf in cfg:
                if intf.bInterfaceClass != USB_PRINTER_CLASS:
                    continue
                found_printer = True
                try:
                    vendor_name = dev.product or "Unknown"
                except Exception:
                    vendor_name = "Unknown"
                diagnostics.append(
                    f"Found USB device: {vendor_name} (0x{dev.idVendor:04x}:0x{dev.idProduct:04x})"
                )

                # Try to detach kernel driver
                try:
                    if dev.is_kernel_driver_active(intf.bInterfaceNumber):
                        diagnostics.append(
                            f"Kernel driver active on interface {intf.bInterfaceNumber}, detaching..."
                        )
                        dev.detach_kernel_driver(intf.bInterfaceNumber)
                except Exception as err:
                    diagnostics.append(f"Could not detach kernel driver: {err}")

                # Find bulk OUT endpoint
                ep_out = usb.util.find_descriptor(
                    intf,
                    custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
                    == usb.util.ENDPOINT_OUT,
                )
                if ep_out is not None:
                    try:
                        dev.set_configuration()
                    except Exception:
                        pass
                    diagnostics.append(f"USB printer found: endpoint OUT {ep_out.bEndpointAddress}")
                    return UsbPrinterDriver(dev, ep_out), diagnostics

    if not found_printer:
        diagnostics.append(
            f"No USB printer-class devices found. {total_devices} other USB devices present."
        )
    return None, diagnostics


def discover_macos_usb_printers() -> list[dict]:
    """Discover USB printers visible to macOS IOKit via ioreg.

    Returns list of dicts with name, vid, pid, location keys.
    Used for diagnostics — shows what macOS sees even if pyusb can't claim.
    """
    if sys.platform != "darwin":
        return []

    try:
        result = subprocess.run(
            ["ioreg", "-p", "IOUSB", "-l", "-r", "-c", "IOUSBHostDevice"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return []

    printers: list[dict] = []
    current: dict[str, Any] = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if '"USB Product Name"' in line:
            m = re.search(r'"USB Product Name"\s*=\s*"(.+?)"', line)
            if m:
                current["name"] = m.group(1)
        elif '"idVendor"' in line:
            m = re.search(r'"idVendor"\s*=\s*(\d+)', line)
            if m:
                current["vid"] = int(m.group(1))
        elif '"idProduct"' in line:
            m = re.search(r'"idProduct"\s*=\s*(\d+)', line)
            if m:
                current["pid"] = int(m.group(1))
        elif '"locationID"' in line:
            m = re.search(r'"locationID"\s*=\s*(\d+)', line)
            if m:
                current["location"] = int(m.group(1))
        elif line == "}" or line == "}," or line.startswith("+"):
            if "name" in current:
                name_lower = current["name"].lower()
                if any(kw in name_lower for kw in ("print", "usb2.0-print")):
                    printers.append(current)
            current = {}

    return printers


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
    usb_uri_pattern = re.compile(r"usb://([^/]*)/([^?]*)(?:\?(.*))?")
    for line in result.stdout.splitlines():
        match = pattern.match(line)
        if match:
            name, uri = match.group(1), match.group(2).strip()
            if uri.startswith("usb://"):
                entry: dict[str, str] = {"name": name, "uri": uri}
                uri_match = usb_uri_pattern.match(uri)
                if uri_match:
                    vendor_part = uri_match.group(1)
                    model_part = uri_match.group(2)
                    query_part = uri_match.group(3)
                    if vendor_part:
                        entry["vendor"] = vendor_part.replace("%20", " ")
                    if model_part:
                        entry["model"] = model_part.replace("%20", " ")
                    if query_part:
                        for param in query_part.split("&"):
                            if param.startswith("serial="):
                                entry["serial"] = param[7:]
                printers.append(entry)
    return printers


def discover_printer(
    device_override: str | None = None, juki: bool = False
) -> PrinterDriver:
    """Select the best available printer backend.

    Priority:
    1. User-specified --device path -> FilePrinterDriver
    2. Direct USB via pyusb (when juki=True) -> UsbPrinterDriver
    3. CUPS USB printer discovery (interactive selection) -> CupsPrinterDriver
    4. Linux /dev/usb/lp* probe -> FilePrinterDriver
    5. Fallback -> NullPrinterDriver

    When juki=True, wraps the selected driver in JukiPrinterDriver.
    """
    driver: PrinterDriver | None = None

    if device_override:
        driver = FilePrinterDriver(device_override)
    else:
        if juki:
            usb_driver = discover_usb_device()
            if usb_driver is not None:
                driver = usb_driver
                print(f"USB direct: {usb_driver}", file=sys.stderr)

        if driver is None:
            cups_printers = discover_cups_printers()
            selected = select_printer(cups_printers)
            if selected:
                driver = CupsPrinterDriver(selected)
                if juki:
                    print(f"CUPS: {selected}", file=sys.stderr)
            elif sys.platform == "linux":
                for dev in ["/dev/usb/lp0", "/dev/usb/lp1"]:
                    if Path(dev).exists():
                        driver = FilePrinterDriver(dev)
                        break

    if driver is None:
        driver = NullPrinterDriver()

    if juki and not isinstance(driver, NullPrinterDriver):
        driver = JukiPrinterDriver(driver)

    return driver


A4_COLUMNS = 80  # A4 printable width at 10 CPI (pica)


def make_printer_output(driver: PrinterDriver) -> Callable[[str], None]:
    """Create an output_fn that writes to a printer with graceful degradation.

    Tracks column position and auto-wraps at A4_COLUMNS (80) to stay
    within A4 page width.  On IOError/OSError, stops writing permanently.
    This implements PRNT-03 (graceful disconnect).
    """
    disconnected = False
    column = 0

    def printer_write(char: str) -> None:
        nonlocal disconnected, column
        if disconnected:
            return
        try:
            if char in ("\n", "\r", "\f"):
                driver.write(char)
                column = 0
            else:
                if column >= A4_COLUMNS:
                    driver.write("\n")
                    column = 0
                driver.write(char)
                column += 1
        except OSError:
            disconnected = True

    return printer_write
