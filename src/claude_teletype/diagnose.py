"""Structured printer diagnostics for troubleshooting.

Produces a Rich-formatted report of USB devices, CUPS queues,
pyusb availability, and libusb backend status.
"""

from __future__ import annotations

import platform
import shutil
import sys

from rich.console import Console
from rich.table import Table

from claude_teletype.printing.detection import Classification, DeviceKind, classify
from claude_teletype.printing.discovery import UsbDeviceInfo, discover_all
from claude_teletype.printing.profiles import BUILTIN_PROFILES
from claude_teletype.printing.registry import ProfileRegistry


def _classification_row(
    dev: UsbDeviceInfo, registry: ProfileRegistry
) -> tuple[str, str, str, str]:
    """(kind, suggested profile, transport note, readback) for one device.

    Never raises: a classification failure degrades to an 'unknown' row so
    run_diagnose can always render the full table. No live readback is
    attempted — opening a device here could claim it out from under CUPS,
    so NATIVE_PRINTER readback reports 'untested (no open device)'.
    """
    try:
        classification = classify(dev, registry)
    except Exception:
        classification = Classification(kind=DeviceKind.UNKNOWN)

    if classification.kind is DeviceKind.BRIDGE:
        kind = "bridge" if dev.printer_class else "bridge (unconfirmed adapter)"
        readback = "absent (bridge)"
    elif classification.kind is DeviceKind.NATIVE_PRINTER:
        kind = "native printer"
        readback = "untested (no open device)"
    else:
        kind = "unknown"
        readback = "absent"

    note = classification.transport_note
    if classification.serial_only:
        note = f"{note} (serial-only)" if note else "serial-only"

    return kind, classification.suggested_profile or "—", note, readback


def run_diagnose() -> None:
    """Run printer diagnostics and print structured Rich output."""
    console = Console()
    result = discover_all()

    console.print()
    console.print("[bold]Printer Diagnostics[/bold]")
    console.print()

    # --- Dependencies ---
    dep_table = Table(title="Dependencies", show_header=True)
    dep_table.add_column("Component", style="cyan")
    dep_table.add_column("Status")
    dep_table.add_column("Detail", style="dim")

    pyusb_status = "[green]Installed[/green]" if result.pyusb_available else "[red]Not installed[/red]"
    pyusb_detail = "" if result.pyusb_available else "Install with: uv sync --extra usb"
    dep_table.add_row("pyusb", pyusb_status, pyusb_detail)

    if result.pyusb_available:
        libusb_status = "[green]Available[/green]" if result.libusb_available else "[red]Not found[/red]"
        libusb_detail = "" if result.libusb_available else "Install with: brew install libusb"
        dep_table.add_row("libusb", libusb_status, libusb_detail)
    else:
        dep_table.add_row("libusb", "[dim]N/A[/dim]", "Requires pyusb first")

    uv_path = shutil.which("uv")
    uv_status = "[green]Found[/green]" if uv_path else "[yellow]Not found[/yellow]"
    dep_table.add_row("uv", uv_status, uv_path or "")

    console.print(dep_table)
    console.print()

    # --- USB Devices ---
    if result.pyusb_available and result.libusb_available:
        if result.usb_devices:
            registry = ProfileRegistry(BUILTIN_PROFILES)
            usb_table = Table(
                title="USB Devices (printer-class and bridge adapters)",
                show_header=True,
            )
            usb_table.add_column("Device", style="cyan")
            usb_table.add_column("VID:PID")
            usb_table.add_column("Bus:Addr", style="dim")
            usb_table.add_column("Kind")
            usb_table.add_column("Suggested profile")
            usb_table.add_column("Transport note", style="dim")
            usb_table.add_column("Readback", style="dim")
            for dev in result.usb_devices:
                name = dev.product_name or dev.manufacturer or "Unknown"
                kind, suggested, note, readback = _classification_row(dev, registry)
                usb_table.add_row(
                    name,
                    f"0x{dev.vendor_id:04x}:0x{dev.product_id:04x}",
                    f"{dev.bus}:{dev.address}",
                    kind,
                    suggested,
                    note,
                    readback,
                )
            console.print(usb_table)
        else:
            console.print("[yellow]No USB printer-class devices found.[/yellow]")
    elif not result.pyusb_available:
        console.print("[dim]USB device scanning unavailable (pyusb not installed)[/dim]")
    else:
        console.print("[dim]USB device scanning unavailable (libusb not found)[/dim]")
    console.print()

    # --- CUPS Printers ---
    if result.cups_printers:
        cups_table = Table(title="CUPS Printer Queues", show_header=True)
        cups_table.add_column("Queue", style="cyan")
        cups_table.add_column("URI")
        cups_table.add_column("Vendor/Model", style="dim")
        for p in result.cups_printers:
            vendor_model = f"{p.vendor} {p.model}".strip() if (p.vendor or p.model) else ""
            cups_table.add_row(p.name, p.uri, vendor_model)
        console.print(cups_table)
    else:
        console.print("[yellow]No CUPS printer queues found.[/yellow]")
    console.print()

    # --- System Info ---
    console.print(f"[dim]Platform: {platform.system()} {platform.release()}[/dim]")
    console.print(f"[dim]Python: {sys.version.split()[0]}[/dim]")

    # --- Diagnostics Log ---
    if result.diagnostics:
        console.print()
        console.print("[bold]Diagnostics:[/bold]")
        for msg in result.diagnostics:
            console.print(f"  [yellow]{msg}[/yellow]")
    console.print()
