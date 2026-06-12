"""Printer discovery: USB/CUPS enumeration and discovery dataclasses.

Moved from the former top-level printer.py (discovery slice). Holds the
discovery result dataclasses (including PrinterSelection, placed here so
both selection.py and screens/printer_setup.py can import it without a
cycle) and the USB/CUPS enumeration functions.
"""

from __future__ import annotations

import errno as _errno
import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any

from claude_teletype.printing.detection import BRIDGE_CHIP_VIDS
from claude_teletype.printing.drivers import UsbPrinterDriver


@dataclass
class UsbDeviceInfo:
    """Discovered USB device.

    ``printer_class`` is a provenance marker: True means a class-7
    (printer) interface was found during enumeration; False means the
    device surfaced through the bridge-VID tier — a known bridge chip
    that did not present a printer-class interface (serial/vendor mode).
    """

    vendor_id: int
    product_id: int
    product_name: str = ""
    manufacturer: str = ""
    serial: str = ""
    bus: int = 0
    address: int = 0
    printer_class: bool = True


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


def _device_matches_identity(dev: Any, identity: UsbDeviceInfo) -> bool:
    """True if a pyusb device is the SAME physical device as ``identity``.

    Matches by VID:PID first, then prefers the serial number when the
    discovered identity recorded one, falling back to (bus, address) —
    the identity fields captured on UsbDeviceInfo during discover_all().
    """
    if dev.idVendor != identity.vendor_id or dev.idProduct != identity.product_id:
        return False
    if identity.serial:
        try:
            serial = dev.serial_number or ""
        except Exception:
            serial = ""
        return serial == identity.serial
    return (dev.bus or 0) == identity.bus and (dev.address or 0) == identity.address


def _find_usb_printer(
    diagnostics: list[str] | None = None,
    identity: UsbDeviceInfo | None = None,
) -> UsbPrinterDriver | None:
    """Shared USB printer discovery logic.

    Enumerates USB devices via pyusb, finds printer-class interfaces
    (class 7), detaches kernel drivers, and opens a bulk OUT endpoint.

    Args:
        diagnostics: If provided, human-readable messages are appended
            explaining each step. Pass None for silent operation.
        identity: If provided, only the device matching this discovered
            identity (serial preferred, else VID:PID + bus/address) is
            opened — selection by identity, not first-of-class (REF-03).
            Pass None for the legacy first-printer-found behavior.

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
        if identity is not None and not _device_matches_identity(dev, identity):
            continue
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
                    except Exception as err:
                        # EACCES/EBUSY means a host kernel driver holds the
                        # device (macOS: AppleUSBPrinter kext). Surface it
                        # and bail so callers can fall back to CUPS instead
                        # of returning a driver whose writes will all fail.
                        # Deliberately NO auto-detach here — detaching the
                        # kext breaks CUPS until replug (Pitfall 2).
                        if getattr(err, "errno", None) in (
                            _errno.EACCES,
                            _errno.EBUSY,
                        ):
                            if verbose:
                                diagnostics.append(
                                    "USB open failed: device is held by a host "
                                    "driver — on macOS, AppleUSBPrinter; use the "
                                    "CUPS queue or unload the kext."
                                )
                            return None
                        # Other set_configuration failures stay best-effort:
                        # many devices work without an explicit config set.
                    if verbose:
                        diagnostics.append(f"USB printer found: endpoint OUT {ep_out.bEndpointAddress}")
                    return UsbPrinterDriver(dev, ep_out, interface_number=intf.bInterfaceNumber)

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
            class7_dev_ids: set[int] = set()
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
                            class7_dev_ids.add(id(dev))
                            break  # one entry per device, not per interface
                    else:
                        continue
                    break

            # Keyed to class-7 results only: a bridge-tier-only discovery
            # still reports no printer-class devices (the message stays
            # truthful — bridges are unconfirmed adapters, not printers).
            if result.libusb_available and not class7_dev_ids:
                total = len(devices)
                result.diagnostics.append(
                    f"No USB printer-class devices found. {total} other USB devices present."
                )

            # Bridge tier: known bridge-chip VIDs that did not present a
            # printer-class interface (CH340 in serial mode, PL2303, ...).
            # Descriptor reads ONLY — never write probe bytes, never do
            # control transfers, never set_configuration: a 0x1A86:0x7523
            # is statistically an Arduino and probing corrupts whatever it
            # is doing. Appended after all class-7 entries so index-based
            # consumers keep stable indices within one discovery run.
            for dev in devices:
                if id(dev) in class7_dev_ids:
                    continue
                if dev.idVendor not in BRIDGE_CHIP_VIDS:
                    continue
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
                        printer_class=False,
                    )
                )

    # 3. CUPS discovery (always, regardless of pyusb)
    #
    # Plain module-global call: test patches targeting
    # ``claude_teletype.printing.discovery.discover_cups_printers``
    # intercept it directly.
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
