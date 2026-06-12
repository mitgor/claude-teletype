"""Printer setup screen for the Textual TUI.

Interactive screen for discovering, selecting, and configuring printers.
Shows USB devices and CUPS printers, allows connection method and profile
selection, and supports installing pyusb from within the app.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Label,
    LoadingIndicator,
    Log,
    OptionList,
    RadioButton,
    RadioSet,
    Select,
    Static,
)

from claude_teletype.printing.detection import DeviceKind, classify
from claude_teletype.printing.discovery import (
    DiscoveryResult,
    PrinterSelection,
    kernel_driver_holds_printer,
)
from claude_teletype.printing.registry import ProfileRegistry


class PrinterSetupScreen(Screen[PrinterSelection | None]):
    """Full-screen setup for printer discovery and configuration.

    Consumes a DiscoveryResult and dismisses with a PrinterSelection
    (or None if the user skips).
    """

    BINDINGS = [
        Binding("escape", "skip", "Skip"),
    ]

    CSS = """
    #setup-container {
        padding: 1 2;
    }

    #setup-title {
        text-style: bold;
        text-align: center;
        width: 100%;
    }

    .section-label {
        margin-top: 1;
        text-style: bold;
    }

    #device-list {
        height: 8;
    }

    #diagnostics-log {
        height: 4;
        border: solid $surface-darken-1;
    }

    #button-row {
        margin-top: 1;
        align: center middle;
    }

    #install-row {
        margin-top: 1;
    }

    #install-spinner {
        display: none;
    }
    """

    def __init__(
        self,
        discovery: DiscoveryResult,
        all_profiles: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._discovery = discovery
        self._all_profiles: dict[str, Any] = all_profiles or {"generic": None}
        # VID:PID index over the screen's profile catalog; classify() only
        # consumes match_vidpid. None placeholders (e.g. the default
        # {"generic": None}) carry no VID:PID and are excluded.
        self._registry = ProfileRegistry(
            {n: p for n, p in self._all_profiles.items() if p is not None}
        )
        # Maps OptionList index -> device metadata
        self._device_entries: list[dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="setup-container"):
            yield Header()
            yield Static("Printer Setup", id="setup-title")

            yield Label("Discovered Devices:", classes="section-label")
            yield OptionList(id="device-list")

            yield Label("Connection Method:", classes="section-label")
            with RadioSet(id="connection-method"):
                yield RadioButton("USB Direct", id="radio-usb")
                yield RadioButton("CUPS Queue", id="radio-cups")

            yield Label("Printer Profile:", classes="section-label")
            sorted_names = sorted(self._all_profiles.keys())
            yield Select[str](
                [(name, name) for name in sorted_names],
                value="generic" if "generic" in self._all_profiles else sorted_names[0],
                id="profile-select",
                allow_blank=False,
            )

            with Horizontal(id="install-row"):
                yield Button("Install USB Support", id="install-btn", variant="warning")
                yield LoadingIndicator(id="install-spinner")

            yield Label("Diagnostics:", classes="section-label")
            yield Log(id="diagnostics-log")

            with Horizontal(id="button-row"):
                yield Button("Connect", variant="primary", id="connect-btn")
                yield Button("Skip (Simulator)", id="skip-btn")

            yield Footer()

    def _add_usb_device_options(self, option_list: OptionList, log: Log) -> None:
        """Add one OptionList entry per discovered USB device.

        Labels carry the classification verdict: BRIDGE devices get the
        transport note plus a manual-family-pick hint (the chip identifies
        the cable, not the printer), and bridge-tier devices that never
        presented a printer-class interface are tagged "unconfirmed
        adapter". Serial-only chips additionally write an R012 warning to
        the diagnostics log — they cannot drive a parallel printer.
        """
        for i, usb_dev in enumerate(self._discovery.usb_devices):
            classification = classify(usb_dev, self._registry)
            if usb_dev.product_name:
                label = f"{usb_dev.product_name} (USB {usb_dev.vendor_id:04x}:{usb_dev.product_id:04x})"
            else:
                label = f"USB Device ({usb_dev.vendor_id:04x}:{usb_dev.product_id:04x})"
            if classification.kind is DeviceKind.BRIDGE:
                note = classification.transport_note or "USB bridge"
                label = f"{label} — {note} — choose your printer family"
            if not usb_dev.printer_class:
                label = f"{label} [unconfirmed adapter]"
            option_list.add_option(label)
            self._device_entries.append({
                "type": "usb",
                "index": i,
                "usb_info": usb_dev,
            })
            if classification.serial_only:
                log.write_line(
                    f"Warning: {classification.transport_note} "
                    f"({usb_dev.vendor_id:04x}:{usb_dev.product_id:04x}) is a "
                    "serial-only adapter — it cannot drive a parallel printer."
                )

    def on_mount(self) -> None:
        """Populate widgets with discovery data."""
        option_list = self.query_one("#device-list", OptionList)
        log = self.query_one("#diagnostics-log", Log)

        # Build device entries and populate OptionList
        self._device_entries = []
        self._add_usb_device_options(option_list, log)

        for i, cups_pr in enumerate(self._discovery.cups_printers):
            suffix = f": {cups_pr.model}" if cups_pr.model else ""
            label = f"{cups_pr.name} (CUPS{suffix})"
            option_list.add_option(label)
            self._device_entries.append({
                "type": "cups",
                "index": i,
                "cups_info": cups_pr,
            })

        if not self._device_entries:
            option_list.add_option(
                "No printers found. Check connections or install USB support."
            )

        # Write diagnostics from discovery
        for msg in self._discovery.diagnostics:
            log.write_line(msg)

        # Summary diagnostics
        if self._discovery.usb_devices:
            n = len(self._discovery.usb_devices)
            log.write_line(f"{n} USB device(s) found")
        if self._discovery.cups_printers:
            n = len(self._discovery.cups_printers)
            log.write_line(f"{n} CUPS queue(s) found")
        if not self._discovery.cups_printers:
            log.write_line("No CUPS queues found")

        # Install row visibility
        if self._discovery.pyusb_available:
            self.query_one("#install-row").display = False
        else:
            log.write_line("pyusb not installed -- USB detection unavailable")

        # Disable connect when no devices
        if not self._device_entries:
            self.query_one("#connect-btn", Button).disabled = True

        # Initially disable radio buttons until a device is selected
        self.query_one("#radio-usb", RadioButton).disabled = True
        self.query_one("#radio-cups", RadioButton).disabled = True

    def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        """Handle device selection from the OptionList."""
        idx = event.option_index
        if idx >= len(self._device_entries):
            return  # "no printers found" placeholder

        entry = self._device_entries[idx]
        radio_usb = self.query_one("#radio-usb", RadioButton)
        radio_cups = self.query_one("#radio-cups", RadioButton)
        profile_select = self.query_one("#profile-select", Select)
        connect_btn = self.query_one("#connect-btn", Button)

        connect_btn.disabled = False

        if entry["type"] == "usb":
            usb_info = entry["usb_info"]
            radio_usb.disabled = False
            radio_cups.disabled = False
            log = self.query_one("#diagnostics-log", Log)

            # Probe whether the host kernel driver is actually bound to this
            # device. On macOS that's the AppleUSBPrinter kext, which makes
            # USB Direct writes time out — recommend CUPS in that case.
            kernel_owns = (
                sys.platform == "darwin"
                and kernel_driver_holds_printer(
                    usb_info.vendor_id, usb_info.product_id
                )
            )

            if kernel_owns and self._discovery.cups_printers:
                radio_cups.value = True
                log.write_line(
                    "macOS print driver (AppleUSBPrinter) is using this device "
                    "— CUPS Queue selected. USB Direct will time out unless "
                    "the kext is unloaded."
                )
            else:
                radio_usb.value = True
                if kernel_owns:
                    log.write_line(
                        "macOS print driver is using this device; USB Direct "
                        "may time out. No CUPS queue available — falling back."
                    )

            # Route the profile suggestion through classify(): only a
            # NATIVE_PRINTER verdict carries a suggestion, and it is
            # advisory — applied only when the Select actually offers it.
            # BRIDGE devices always stay on "generic" (forcing the manual
            # family pick — the bridge chip's VID:PID identifies the
            # cable, not the printer, even though a profile may pin that
            # VID). UNKNOWN devices also stay on "generic".
            classification = classify(usb_info, self._registry)
            if (
                classification.kind is DeviceKind.NATIVE_PRINTER
                and classification.suggested_profile in self._all_profiles
            ):
                profile_select.value = classification.suggested_profile
            else:
                profile_select.value = "generic"

        elif entry["type"] == "cups":
            radio_usb.disabled = True
            radio_cups.disabled = False
            radio_cups.value = True
            profile_select.value = "generic"

    def _on_connect(self) -> None:
        """Build PrinterSelection from current widget state and dismiss."""
        option_list = self.query_one("#device-list", OptionList)
        highlighted = option_list.highlighted
        if highlighted is None or highlighted >= len(self._device_entries):
            return

        entry = self._device_entries[highlighted]
        radio_usb = self.query_one("#radio-usb", RadioButton)
        profile_select = self.query_one("#profile-select", Select)

        if radio_usb.value and not radio_usb.disabled:
            connection_type = "usb"
        else:
            connection_type = "cups"

        selection = PrinterSelection(
            connection_type=connection_type,
            device_index=entry["index"],
            cups_printer_name=(
                entry["cups_info"].name if entry["type"] == "cups" else None
            ),
            profile_name=str(profile_select.value) if profile_select.value != Select.BLANK else "generic",
        )
        self.dismiss(selection)

    def _on_skip(self) -> None:
        """Dismiss with None for simulator mode."""
        self.dismiss(None)

    def action_skip(self) -> None:
        """Handle Escape key binding."""
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Dispatch button clicks."""
        if event.button.id == "connect-btn":
            self._on_connect()
        elif event.button.id == "skip-btn":
            self._on_skip()
        elif event.button.id == "install-btn":
            self._install_pyusb()

    @work(exclusive=True, thread=False)
    async def _install_pyusb(self) -> None:
        """Install pyusb via uv sync --extra usb as an async worker."""
        import shutil

        log = self.query_one("#diagnostics-log", Log)
        uv_path = shutil.which("uv")

        if uv_path is None:
            log.write_line("Error: uv not found on PATH")
            return

        # Show progress
        self.query_one("#install-spinner").display = True
        self.query_one("#install-btn", Button).disabled = True
        log.write_line("Installing pyusb via uv sync --extra usb...")

        proc = await asyncio.create_subprocess_exec(
            uv_path, "sync", "--extra", "usb",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        # Hide spinner
        self.query_one("#install-spinner").display = False

        if proc.returncode == 0:
            log.write_line("pyusb installed successfully.")
            if self._reimport_pyusb():
                log.write_line("USB support activated. Re-scanning devices...")
                self._refresh_discovery()
            else:
                log.write_line(
                    "Installed but import failed. Restart app to detect USB devices."
                )
        else:
            log.write_line(f"Install failed: {stderr.decode().strip()}")
            self.query_one("#install-btn", Button).disabled = False

    def _reimport_pyusb(self) -> bool:
        """Attempt to reimport pyusb after installation.

        Clears sys.modules cache for usb.* and invalidates import caches.
        Returns True if import succeeds.
        """
        import importlib

        usb_keys = [k for k in sys.modules if k.startswith("usb")]
        for key in usb_keys:
            del sys.modules[key]
        importlib.invalidate_caches()
        try:
            import usb.core  # noqa: F401

            return True
        except ImportError:
            return False

    def _refresh_discovery(self) -> None:
        """Re-run discovery and update all widgets."""
        from claude_teletype.printing.discovery import discover_all

        self._discovery = discover_all()

        # Clear and repopulate OptionList
        option_list = self.query_one("#device-list", OptionList)
        log = self.query_one("#diagnostics-log", Log)
        option_list.clear_options()
        self._device_entries = []
        self._add_usb_device_options(option_list, log)

        for i, cups_pr in enumerate(self._discovery.cups_printers):
            suffix = f": {cups_pr.model}" if cups_pr.model else ""
            label = f"{cups_pr.name} (CUPS{suffix})"
            option_list.add_option(label)
            self._device_entries.append({
                "type": "cups",
                "index": i,
                "cups_info": cups_pr,
            })

        if not self._device_entries:
            option_list.add_option(
                "No printers found. Check connections or install USB support."
            )

        # Update install-row visibility
        if self._discovery.pyusb_available:
            self.query_one("#install-row").display = False

        # Update connect button
        connect_btn = self.query_one("#connect-btn", Button)
        connect_btn.disabled = not self._device_entries

        # Log new counts
        if self._discovery.usb_devices:
            log.write_line(f"{len(self._discovery.usb_devices)} USB device(s) found")
        if self._discovery.cups_printers:
            log.write_line(f"{len(self._discovery.cups_printers)} CUPS queue(s) found")
