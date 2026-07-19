"""Printer selection and driver-factory functions.

Moved from the former top-level printer.py (selection slice). Turns a
user/saved choice into a concrete PrinterDriver.
"""

from __future__ import annotations

import sys
from pathlib import Path

from claude_teletype.printing import discovery as _discovery
from claude_teletype.printing.discovery import (
    DiscoveryResult,
    PrinterSelection,
)
from claude_teletype.printing.drivers import (
    CupsPrinterDriver,
    FilePrinterDriver,
    NullPrinterDriver,
    PrinterDriver,
    ProfilePrinterDriver,
)
from claude_teletype.printing.profiles import PrinterProfile
# WR-05: runtime import (no cycle: registry.py imports nothing from this
# package at runtime) so typing.get_type_hints can resolve the annotation.
from claude_teletype.printing.registry import ProfileRegistry


def _emit(diagnostics: list[str] | None, message: str) -> None:
    """Route a diagnostic to the caller's list, else stderr (WR-04)."""
    if diagnostics is not None:
        diagnostics.append(message)
    else:
        print(message, file=sys.stderr)


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


def match_saved_printer(
    saved_type: str,
    saved_id: str,
    discovery: DiscoveryResult,
    profile_name: str = "generic",
) -> PrinterSelection | None:
    """Check if a saved printer config matches a currently connected device.

    Returns a PrinterSelection if matched, None if the saved printer is not found.
    USB devices are matched by VID:PID (hex string like "1234:5678").
    CUPS printers are matched by queue name. ``profile_name`` is stamped
    onto the returned selection (ARCH-04: the match owns the profile
    hand-off; callers must not mutate the result).
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
                        profile_name=profile_name,
                    )

    elif saved_type == "cups" and saved_id:
        for cups_pr in discovery.cups_printers:
            if cups_pr.name == saved_id and cups_pr.enabled:
                return PrinterSelection(
                    connection_type="cups",
                    cups_printer_name=cups_pr.name,
                    profile_name=profile_name,
                )

    return None


def create_driver_for_selection(
    selection: PrinterSelection,
    discovery: DiscoveryResult,
    *,
    registry: ProfileRegistry | None = None,
    diagnostics: list[str] | None = None,
) -> PrinterDriver:
    """Convert a PrinterSelection from the setup screen into a PrinterDriver.

    Profile resolution goes through a ProfileRegistry — the lookup
    authority and the only catalog input (ARCH-02) — so names resolve
    case-insensitively (WR-01). An unknown profile name emits a
    diagnostic and explicitly falls back to an unwrapped driver (a
    stated policy, not a dict-``.get`` accident).

    Args:
        selection: User's choice from PrinterSetupScreen.
        discovery: Discovery results; ``selection.device_index`` indexes
            ``discovery.usb_devices`` to reconnect the picked USB device.
        registry: Profile lookup authority. If None, defaults to
            ``ProfileRegistry(BUILTIN_PROFILES)``.
        diagnostics: When a list is passed, fallback/unknown-profile
            messages are appended to it for the caller to surface;
            when None they print to stderr (CLI path stays loud, WR-04).

    Returns:
        Configured PrinterDriver (possibly wrapped in ProfilePrinterDriver).
    """
    from claude_teletype.printing.profiles import BUILTIN_PROFILES

    if registry is not None:
        effective_registry = registry
    else:
        effective_registry = ProfileRegistry(BUILTIN_PROFILES)

    if selection.connection_type == "skip":
        return NullPrinterDriver()

    driver: PrinterDriver | None = None

    if selection.connection_type == "usb":
        # Reconnect to the SAME device the user picked, by identity
        # (serial preferred, else VID:PID + bus/address) — NOT first-of-class
        # re-discovery (REF-03). device_index=None keeps the legacy
        # first-printer fallback for single-printer flows.
        identity = None
        if selection.device_index is not None and 0 <= selection.device_index < len(
            discovery.usb_devices
        ):
            identity = discovery.usb_devices[selection.device_index]
        # Resolve _find_usb_printer through the discovery module at call time
        # so test patches targeting
        # ``claude_teletype.printing.discovery._find_usb_printer`` intercept it.
        driver = _discovery._find_usb_printer(identity=identity)
        if driver is None:
            # USB direct failed — typically the OS kernel driver holds the
            # device (macOS AppleUSBPrinter). Fall back to an enabled CUPS
            # queue instead of silently degrading to NullPrinterDriver:
            # prefer a queue whose serial matches the picked device, else
            # the first enabled queue. Profile wrapping below still applies.
            enabled_queues = [q for q in discovery.cups_printers if q.enabled]
            if enabled_queues:
                fallback = None
                if identity is not None and identity.serial:
                    fallback = next(
                        (q for q in enabled_queues if q.serial == identity.serial),
                        None,
                    )
                if fallback is None:
                    fallback = enabled_queues[0]
                _emit(
                    diagnostics,
                    "USB direct unavailable (device may be claimed by the OS) "
                    f"— falling back to CUPS queue {fallback.name}",
                )
                driver = CupsPrinterDriver(fallback.name)
    elif selection.connection_type == "cups":
        if selection.cups_printer_name:
            driver = CupsPrinterDriver(selection.cups_printer_name)
        else:
            # Defensive (CR-03): a cups selection with no queue name must
            # not silently become the simulator while an enabled queue
            # exists — pick the first enabled queue, loudly.
            enabled_queues = [q for q in discovery.cups_printers if q.enabled]
            if enabled_queues:
                _emit(
                    diagnostics,
                    "CUPS selection had no queue name "
                    f"— falling back to CUPS queue {enabled_queues[0].name}",
                )
                driver = CupsPrinterDriver(enabled_queues[0].name)

    if driver is None:
        # WR-04: an explicit usb/cups pick degrading to the simulator must
        # never be silent (skip already returned above; only failed picks
        # with no fallback queue reach here).
        _emit(
            diagnostics,
            "no printer available — running in simulator mode",
        )
        return NullPrinterDriver()

    # Wrap with profile if not generic — registry is the lookup authority
    if selection.profile_name and selection.profile_name != "generic":
        try:
            profile = effective_registry.get(selection.profile_name)
        except ValueError:
            _emit(
                diagnostics,
                f"Unknown printer profile {selection.profile_name!r} — "
                "printing without profile wrapping (no ESC init/CRLF). "
                "Check saved_printer_profile in config.",
            )
            profile = None
        if profile is not None:
            driver = ProfilePrinterDriver(driver, profile)

    return driver


def discover_printer(
    device_override: str | None = None,
    profile: PrinterProfile | None = None,
) -> PrinterDriver:
    """Select the best available printer backend.

    Priority:
    1. User-specified --device path -> FilePrinterDriver
    2. Direct USB via pyusb (when profile has ESC codes) -> UsbPrinterDriver
    3. CUPS USB printer discovery (interactive selection) -> CupsPrinterDriver
    4. Linux /dev/usb/lp* probe -> FilePrinterDriver
    5. Fallback -> NullPrinterDriver

    When a non-generic profile is provided (profile= is the only selector),
    wraps the selected driver in ProfilePrinterDriver.
    """
    # Resolve the discovery helpers through the discovery module at call time
    # so test patches targeting
    # ``claude_teletype.printing.discovery.discover_usb_device`` /
    # ``claude_teletype.printing.discovery.discover_cups_printers``
    # intercept the calls. select_printer is a plain global lookup in this
    # module, so ``claude_teletype.printing.selection.select_printer`` patches
    # intercept it directly.
    driver: PrinterDriver | None = None
    use_profile = profile is not None and profile.name != "generic"

    if device_override:
        driver = FilePrinterDriver(device_override)
    else:
        if use_profile:
            usb_driver = _discovery.discover_usb_device()
            if usb_driver is not None:
                driver = usb_driver
                print(f"USB direct: {usb_driver}", file=sys.stderr)

        if driver is None:
            cups_printers = _discovery.discover_cups_printers()
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
