"""Printer driver backends, auto-discovery, and resilient output wrapper."""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from claude_teletype.profiles import PrinterProfile, get_profile


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


@dataclass
class UsbDeviceInfo:
    """Discovered USB printer-class device."""

    vendor_id: int
    product_id: int
    product_name: str = ""
    manufacturer: str = ""
    serial: str = ""
    bus: int = 0
    address: int = 0


@dataclass
class CupsPrinterInfo:
    """Discovered CUPS printer queue."""

    name: str
    uri: str
    vendor: str = ""
    model: str = ""
    serial: str = ""
    enabled: bool = True


@dataclass
class DiscoveryResult:
    """Aggregated printer discovery results."""

    pyusb_available: bool = False
    libusb_available: bool = False
    usb_devices: list[UsbDeviceInfo] = field(default_factory=list)
    cups_printers: list[CupsPrinterInfo] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


@dataclass
class PrinterSelection:
    """Result from PrinterSetupScreen -- captures user's printer choice."""

    connection_type: str  # "usb" | "cups" | "skip"
    device_index: int | None = None  # index into DiscoveryResult.usb_devices
    cups_printer_name: str | None = None
    profile_name: str = "generic"


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


class ProfilePrinterDriver:
    """Profile-driven printer wrapper.

    Wraps an inner PrinterDriver, prepending ESC initialization codes on first
    write and handling newline strategy (CR+LF vs LF-only) based on the
    profile's configuration.
    """

    def __init__(self, inner: PrinterDriver, profile: PrinterProfile) -> None:
        self._inner = inner
        self._profile = profile
        self._initialized = False

    def _send_raw(self, data: bytes) -> None:
        """Send raw bytes through the inner driver as a single write.

        Sending ESC sequences atomically prevents the printer from
        misinterpreting fragmented escape codes (e.g., Juki 6100 drops
        characters when init/reinit bytes arrive as individual USB transfers).
        """
        if data:
            self._inner.write(data.decode("ascii", errors="replace"))

    def _ensure_init(self) -> None:
        if not self._initialized:
            self._initialized = True
            init_data = (
                self._profile.init_sequence
                + self._profile.line_spacing
                + self._profile.char_pitch
            )
            if init_data:
                self._send_raw(init_data)

    @property
    def is_connected(self) -> bool:
        return self._inner.is_connected

    def write(self, char: str) -> None:
        if not self._inner.is_connected:
            return
        self._ensure_init()
        if char == "\n":
            # Send CR+LF+reinit as a single atomic transfer.
            # Fragmented USB transfers cause the Juki 6100 (CH341 bridge)
            # to drop bytes — especially the LF after CR, which results
            # in carriage return without paper advance on wrapped lines.
            newline_data = b""
            if self._profile.crlf:
                newline_data += b"\r"
            newline_data += b"\n"
            if self._profile.reinit_on_newline and self._profile.reinit_sequence:
                newline_data += self._profile.reinit_sequence
            self._send_raw(newline_data)
        else:
            self._inner.write(char)

    def swap_profile(self, new_profile: PrinterProfile) -> None:
        """Replace the current profile and mark as uninitialized.

        The new profile's init sequences will be sent on the next write().
        """
        self._profile = new_profile
        self._initialized = False

    def close(self) -> None:
        if self._initialized and self._inner.is_connected:
            if self._profile.formfeed_on_close:
                self._inner.write("\f")
            if self._profile.reset_sequence:
                self._send_raw(self._profile.reset_sequence)
        self._inner.close()


class JukiPrinterDriver(ProfilePrinterDriver):
    """Juki 6100 daisywheel impact printer driver.

    Deprecated: use ProfilePrinterDriver with get_profile("juki").
    Kept as backward-compatible alias.
    """

    # Juki 6100 ESC sequences (kept for backward compat in tests)
    RESET = b"\x1b\x1aI"  # ESC SUB I — full reset
    LINE_SPACING = b"\x1b\x1e\x09"  # ESC RS 9 — 1/6" line spacing
    FIXED_PITCH = b"\x1bQ"  # ESC Q — disable proportional spacing

    def __init__(self, inner: PrinterDriver) -> None:
        super().__init__(inner, get_profile("juki"))


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


def _find_usb_printer(
    diagnostics: list[str] | None = None,
) -> UsbPrinterDriver | None:
    """Shared USB printer discovery logic.

    Enumerates USB devices via pyusb, finds printer-class interfaces
    (class 7), detaches kernel drivers, and opens a bulk OUT endpoint.

    Args:
        diagnostics: If provided, human-readable messages are appended
            explaining each step. Pass None for silent operation.

    Returns:
        UsbPrinterDriver on success, None otherwise.
    """
    verbose = diagnostics is not None

    try:
        import usb.core
        import usb.util
    except ImportError:
        if verbose:
            diagnostics.append("pyusb not installed. Install with: uv sync --extra usb")
        return None

    try:
        devices = list(usb.core.find(find_all=True))
    except usb.core.NoBackendError:
        if verbose:
            diagnostics.append("libusb backend not found. Install with: brew install libusb")
        return None

    USB_PRINTER_CLASS = 7
    total_devices = len(devices)
    found_printer = False

    for dev in devices:
        for cfg in dev:
            for intf in cfg:
                if intf.bInterfaceClass != USB_PRINTER_CLASS:
                    continue
                found_printer = True

                if verbose:
                    try:
                        vendor_name = dev.product or "Unknown"
                    except Exception:
                        vendor_name = "Unknown"
                    diagnostics.append(
                        f"Found USB device: {vendor_name} (0x{dev.idVendor:04x}:0x{dev.idProduct:04x})"
                    )

                # Try to detach kernel driver (best-effort, may fail on macOS)
                try:
                    if dev.is_kernel_driver_active(intf.bInterfaceNumber):
                        if verbose:
                            diagnostics.append(
                                f"Kernel driver active on interface {intf.bInterfaceNumber}, detaching..."
                            )
                        dev.detach_kernel_driver(intf.bInterfaceNumber)
                except Exception as err:
                    if verbose:
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
                    if verbose:
                        diagnostics.append(f"USB printer found: endpoint OUT {ep_out.bEndpointAddress}")
                    return UsbPrinterDriver(dev, ep_out)

    if verbose and not found_printer:
        diagnostics.append(
            f"No USB printer-class devices found. {total_devices} other USB devices present."
        )
    return None


def kernel_driver_holds_printer(vendor_id: int, product_id: int) -> bool:
    """True if a host kernel driver is bound to a printer-class interface.

    On macOS the AppleUSBPrinter kext claims printer-class USB devices, which
    makes pyusb's USB Direct path time out unless the kext is unloaded. The
    setup screen uses this probe to recommend CUPS only when the conflict is
    real instead of warning unconditionally on every macOS launch.
    """
    try:
        import usb.core  # type: ignore[import-untyped]
        import usb.util  # type: ignore[import-untyped]
    except ImportError:
        return False

    try:
        dev = usb.core.find(idVendor=vendor_id, idProduct=product_id)
    except Exception:
        return False
    if dev is None:
        return False

    held = False
    try:
        seen: set[int] = set()
        for cfg in dev:
            for intf in cfg:
                if intf.bInterfaceClass != 7:
                    continue
                num = intf.bInterfaceNumber
                if num in seen:
                    continue
                seen.add(num)
                try:
                    if dev.is_kernel_driver_active(num):
                        held = True
                        break
                except Exception:
                    continue
            if held:
                break
    finally:
        try:
            usb.util.dispose_resources(dev)
        except Exception:
            pass
    return held


def discover_usb_device() -> UsbPrinterDriver | None:
    """Try to open a USB printer class device directly via pyusb.

    Returns UsbPrinterDriver on success, None if pyusb is missing, no
    backend is available, or no printer-class device is found.
    """
    return _find_usb_printer()


def discover_usb_device_verbose() -> tuple[UsbPrinterDriver | None, list[str]]:
    """Try to open a USB printer via pyusb, returning diagnostics.

    Returns (driver, diagnostics) where diagnostics is a list of
    human-readable strings explaining each step of discovery.
    """
    diagnostics: list[str] = []
    driver = _find_usb_printer(diagnostics)
    return driver, diagnostics


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


def discover_cups_printers() -> list[dict]:
    """Discover USB printers via CUPS lpstat.

    Calls ``lpstat -p -v`` once to capture both queue state ("printer X
    disabled since..." / "printer X is idle. enabled since...") and device
    URIs ("device for X: usb://..."). The "enabled" key on each entry is
    True unless lpstat reports the queue as disabled — smart-startup uses
    this to skip dead queues that would silently swallow print jobs.
    """
    try:
        result = subprocess.run(
            ["lpstat", "-p", "-v"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return []

    # Parse "printer X is idle..." / "printer X disabled since..." lines first
    # so we know each queue's state by the time we see its device line.
    state_pattern = re.compile(r"^printer (\S+) (disabled|is \S+)")
    enabled_by_name: dict[str, bool] = {}
    for line in result.stdout.splitlines():
        m = state_pattern.match(line)
        if m:
            enabled_by_name[m.group(1)] = m.group(2) != "disabled"

    printers = []
    pattern = re.compile(r"device for (\S+):\s+(.+)")
    usb_uri_pattern = re.compile(r"usb://([^/]*)/([^?]*)(?:\?(.*))?")
    for line in result.stdout.splitlines():
        match = pattern.match(line)
        if match:
            name, uri = match.group(1), match.group(2).strip()
            if uri.startswith("usb://"):
                entry: dict = {
                    "name": name,
                    "uri": uri,
                    "enabled": enabled_by_name.get(name, True),
                }
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


def discover_all() -> DiscoveryResult:
    """Aggregate all printer discovery into a single structured result.

    Never raises exceptions. All errors are recorded in diagnostics.
    CUPS discovery always runs regardless of pyusb status.
    """
    result = DiscoveryResult()

    # 1. Check pyusb availability
    try:
        import importlib.util

        pyusb_spec = importlib.util.find_spec("usb")
        result.pyusb_available = pyusb_spec is not None
    except Exception:
        result.pyusb_available = False

    if not result.pyusb_available:
        result.diagnostics.append("pyusb not installed. Install with: uv sync --extra usb")
    else:
        # 2. Check libusb backend and enumerate USB devices
        try:
            import usb.core
            import usb.util
        except ImportError:
            result.diagnostics.append("pyusb import failed despite being installed")
            result.pyusb_available = False
        else:
            try:
                devices = list(usb.core.find(find_all=True))
                result.libusb_available = True
            except usb.core.NoBackendError:
                result.diagnostics.append(
                    "libusb backend not found. Install with: brew install libusb"
                )
                devices = []

            USB_PRINTER_CLASS = 7
            for dev in devices:
                for cfg in dev:
                    for intf in cfg:
                        if intf.bInterfaceClass == USB_PRINTER_CLASS:
                            try:
                                product_name = dev.product or ""
                            except Exception:
                                product_name = ""
                            try:
                                manufacturer = dev.manufacturer or ""
                            except Exception:
                                manufacturer = ""
                            try:
                                serial = dev.serial_number or ""
                            except Exception:
                                serial = ""
                            result.usb_devices.append(
                                UsbDeviceInfo(
                                    vendor_id=dev.idVendor,
                                    product_id=dev.idProduct,
                                    product_name=product_name,
                                    manufacturer=manufacturer,
                                    serial=serial,
                                    bus=dev.bus or 0,
                                    address=dev.address or 0,
                                )
                            )
                            break  # one entry per device, not per interface
                    else:
                        continue
                    break

            if result.libusb_available and not result.usb_devices:
                total = len(devices)
                result.diagnostics.append(
                    f"No USB printer-class devices found. {total} other USB devices present."
                )

    # 3. CUPS discovery (always, regardless of pyusb)
    try:
        cups_raw = discover_cups_printers()
        for p in cups_raw:
            result.cups_printers.append(
                CupsPrinterInfo(
                    name=p["name"],
                    uri=p["uri"],
                    vendor=p.get("vendor", ""),
                    model=p.get("model", ""),
                    serial=p.get("serial", ""),
                    enabled=p.get("enabled", True),
                )
            )
    except Exception as e:
        result.diagnostics.append(f"CUPS discovery failed: {e}")

    return result


def match_saved_printer(
    saved_type: str,
    saved_id: str,
    discovery: DiscoveryResult,
) -> PrinterSelection | None:
    """Check if a saved printer config matches a currently connected device.

    Returns a PrinterSelection if matched, None if the saved printer is not found.
    USB devices are matched by VID:PID (hex string like "1234:5678").
    CUPS printers are matched by queue name.
    """
    if not saved_type or saved_type == "skip":
        return None

    if saved_type == "usb" and saved_id:
        # Parse VID:PID from saved_id
        parts = saved_id.split(":")
        if len(parts) == 2:
            try:
                vid = int(parts[0], 16)
                pid = int(parts[1], 16)
            except ValueError:
                return None
            for i, dev in enumerate(discovery.usb_devices):
                if dev.vendor_id == vid and dev.product_id == pid:
                    return PrinterSelection(
                        connection_type="usb",
                        device_index=i,
                        profile_name="generic",
                    )

    elif saved_type == "cups" and saved_id:
        for cups_pr in discovery.cups_printers:
            if cups_pr.name == saved_id and cups_pr.enabled:
                return PrinterSelection(
                    connection_type="cups",
                    cups_printer_name=cups_pr.name,
                    profile_name="generic",
                )

    return None


def create_driver_for_selection(
    selection: PrinterSelection,
    discovery: DiscoveryResult,
    all_profiles: dict[str, PrinterProfile] | None = None,
) -> PrinterDriver:
    """Convert a PrinterSelection from the setup screen into a PrinterDriver.

    Args:
        selection: User's choice from PrinterSetupScreen.
        discovery: Discovery results (for context, not currently used for USB).
        all_profiles: Profile catalog for profile wrapping. If None, uses BUILTIN_PROFILES.

    Returns:
        Configured PrinterDriver (possibly wrapped in ProfilePrinterDriver).
    """
    from claude_teletype.profiles import BUILTIN_PROFILES

    if selection.connection_type == "skip":
        return NullPrinterDriver()

    driver: PrinterDriver | None = None

    if selection.connection_type == "usb":
        driver = _find_usb_printer()
    elif selection.connection_type == "cups":
        if selection.cups_printer_name:
            driver = CupsPrinterDriver(selection.cups_printer_name)

    if driver is None:
        return NullPrinterDriver()

    # Wrap with profile if not generic
    if selection.profile_name and selection.profile_name != "generic":
        profiles = all_profiles or BUILTIN_PROFILES
        profile = profiles.get(selection.profile_name)
        if profile is not None:
            driver = ProfilePrinterDriver(driver, profile)

    return driver


def discover_printer(
    device_override: str | None = None,
    juki: bool = False,
    profile: PrinterProfile | None = None,
) -> PrinterDriver:
    """Select the best available printer backend.

    Priority:
    1. User-specified --device path -> FilePrinterDriver
    2. Direct USB via pyusb (when profile has ESC codes) -> UsbPrinterDriver
    3. CUPS USB printer discovery (interactive selection) -> CupsPrinterDriver
    4. Linux /dev/usb/lp* probe -> FilePrinterDriver
    5. Fallback -> NullPrinterDriver

    When a non-generic profile is provided, wraps the selected driver in
    ProfilePrinterDriver. The juki parameter is deprecated; use
    profile=get_profile("juki") instead.
    """
    # Backward compat: juki=True without explicit profile
    if juki and profile is None:
        profile = get_profile("juki")

    driver: PrinterDriver | None = None
    use_profile = profile is not None and profile.name != "generic"

    if device_override:
        driver = FilePrinterDriver(device_override)
    else:
        if use_profile:
            usb_driver = discover_usb_device()
            if usb_driver is not None:
                driver = usb_driver
                print(f"USB direct: {usb_driver}", file=sys.stderr)

        if driver is None:
            cups_printers = discover_cups_printers()
            selected = select_printer(cups_printers)
            if selected:
                driver = CupsPrinterDriver(selected)
                if use_profile:
                    print(f"CUPS: {selected}", file=sys.stderr)
            elif sys.platform == "linux":
                for dev in ["/dev/usb/lp0", "/dev/usb/lp1"]:
                    if Path(dev).exists():
                        driver = FilePrinterDriver(dev)
                        break

    if driver is None:
        driver = NullPrinterDriver()

    if use_profile and not isinstance(driver, NullPrinterDriver):
        driver = ProfilePrinterDriver(driver, profile)

    return driver


A4_COLUMNS = 80  # A4 printable width at 10 CPI (pica)


def make_printer_output(
    driver: PrinterDriver, columns: int = A4_COLUMNS
) -> Callable[[str], None]:
    """Create an output_fn that writes to a printer with word-wrap and graceful degradation.

    Uses WordWrapper at the given column width for word-boundary wrapping.
    On IOError/OSError, stops writing permanently (PRNT-03).

    The returned callable has a ``.flush()`` attribute that emits any
    buffered word without adding a trailing newline.  Callers *must*
    invoke it at the end of every response to avoid leaving the last
    word stranded in the buffer.
    """
    from claude_teletype.wordwrap import WordWrapper

    disconnected = False

    def safe_write(char: str) -> None:
        nonlocal disconnected
        if disconnected:
            return
        try:
            driver.write(char)
        except OSError:
            disconnected = True

    wrapper = WordWrapper(columns, safe_write)

    def printer_write(char: str) -> None:
        if disconnected:
            return
        if char in ("\r", "\f"):
            wrapper.flush()
            safe_write(char)
            wrapper.reset_column()
        else:
            wrapper.feed(char)

    def printer_flush() -> None:
        if not disconnected:
            wrapper.flush()

    printer_write.flush = printer_flush  # type: ignore[attr-defined]

    return printer_write
