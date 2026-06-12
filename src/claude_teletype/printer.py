"""Re-export shim — printer.py code moved to claude_teletype.printing.*.

Kept so existing absolute imports (`from claude_teletype.printer import X`)
keep resolving while internal imports and tests migrate (Phase 27 Plans 02/03).
Drivers live in printing.drivers, discovery dataclasses + enumeration in
printing.discovery, selection/factory in printing.selection.
"""

from claude_teletype.printing.discovery import *  # noqa: F401,F403

# Explicit re-exports for names tests reference by attribute (patch targets,
# isinstance checks). Star imports alone do not cover module-private names
# like _find_usb_printer, and explicit names document the public surface.
from claude_teletype.printing.discovery import (  # noqa: F401,F811
    CupsPrinterInfo,
    DiscoveryResult,
    PrinterSelection,
    UsbDeviceInfo,
    _find_usb_printer,
    discover_all,
    discover_cups_printers,
    discover_macos_usb_printers,
    discover_usb_device,
    discover_usb_device_verbose,
    kernel_driver_holds_printer,
)
from claude_teletype.printing.drivers import *  # noqa: F401,F403
from claude_teletype.printing.drivers import (  # noqa: F401,F811
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
from claude_teletype.printing.selection import *  # noqa: F401,F403
from claude_teletype.printing.selection import (  # noqa: F401,F811
    create_driver_for_selection,
    discover_printer,
    match_saved_printer,
    select_printer,
)
