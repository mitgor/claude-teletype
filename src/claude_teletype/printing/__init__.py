"""Printing package: drivers, discovery, selection, and profiles.

Re-exports the printing public surface so callers can do
``from claude_teletype.printing import X``. Step 2 (Plan 02) repoints the
internal imports to these canonical names; the top-level printer.py /
profiles.py shims remain for pre-split absolute-import compatibility.
"""

from claude_teletype.printing.discovery import (
    CupsPrinterInfo,
    DiscoveryResult,
    PrinterSelection,
    UsbDeviceInfo,
    discover_all,
    discover_cups_printers,
    discover_macos_usb_printers,
    discover_usb_device,
    discover_usb_device_verbose,
    kernel_driver_holds_printer,
)
from claude_teletype.printing.drivers import (
    A4_COLUMNS,
    CupsPrinterDriver,
    FilePrinterDriver,
    JukiPrinterDriver,
    NullPrinterDriver,
    PrinterDriver,
    ProfilePrinterDriver,
    UsbPrinterDriver,
    chunk_writes,
    make_printer_output,
)
from claude_teletype.printing.profiles import (
    BUILTIN_PROFILES,
    PrinterProfile,
    auto_detect_profile,
    get_profile,
    load_custom_profiles,
    resolve_style,
)
from claude_teletype.printing.selection import (
    create_driver_for_selection,
    discover_printer,
    match_saved_printer,
    select_printer,
)

__all__ = [
    "A4_COLUMNS",
    "BUILTIN_PROFILES",
    "CupsPrinterDriver",
    "CupsPrinterInfo",
    "DiscoveryResult",
    "FilePrinterDriver",
    "JukiPrinterDriver",
    "NullPrinterDriver",
    "PrinterDriver",
    "PrinterProfile",
    "PrinterSelection",
    "ProfilePrinterDriver",
    "UsbDeviceInfo",
    "UsbPrinterDriver",
    "auto_detect_profile",
    "chunk_writes",
    "create_driver_for_selection",
    "discover_all",
    "discover_cups_printers",
    "discover_macos_usb_printers",
    "discover_printer",
    "discover_usb_device",
    "discover_usb_device_verbose",
    "get_profile",
    "kernel_driver_holds_printer",
    "load_custom_profiles",
    "make_printer_output",
    "match_saved_printer",
    "resolve_style",
    "select_printer",
]
