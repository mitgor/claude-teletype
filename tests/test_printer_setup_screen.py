"""Tests for the PrinterSetupScreen component."""

import dataclasses
from unittest.mock import patch

import pytest
from textual.app import App
from textual.widgets import Button, Log, OptionList, Select

from claude_teletype.printing.discovery import (
    CupsPrinterInfo,
    DiscoveryResult,
    UsbDeviceInfo,
)
from claude_teletype.printing.profiles import BUILTIN_PROFILES
from claude_teletype.screens.printer_setup import PrinterSetupScreen

# --- Test fixtures ---

SAMPLE_USB = UsbDeviceInfo(
    vendor_id=0x1A86, product_id=0x7584, product_name="Juki 6100"
)
SAMPLE_CUPS = CupsPrinterInfo(
    name="HP_LaserJet", uri="usb://HP/LaserJet", model="LaserJet"
)
DISCOVERY_BOTH = DiscoveryResult(
    pyusb_available=True,
    usb_devices=[SAMPLE_USB],
    cups_printers=[SAMPLE_CUPS],
    diagnostics=["1 USB device(s) found"],
)
DISCOVERY_CUPS_ONLY = DiscoveryResult(
    pyusb_available=False,
    cups_printers=[SAMPLE_CUPS],
    diagnostics=["pyusb not installed"],
)
DISCOVERY_EMPTY = DiscoveryResult(
    pyusb_available=False,
    diagnostics=["pyusb not installed", "No CUPS queues found"],
)


class SetupTestApp(App):
    """Minimal test app that pushes a PrinterSetupScreen on mount."""

    def __init__(
        self,
        discovery: DiscoveryResult,
        all_profiles: dict | None = None,
    ):
        super().__init__()
        self._discovery = discovery
        self._all_profiles = all_profiles or dict(BUILTIN_PROFILES)
        self.applied_result = "NOT_SET"  # sentinel to distinguish from None

    def on_mount(self) -> None:
        self.push_screen(
            PrinterSetupScreen(
                discovery=self._discovery,
                all_profiles=self._all_profiles,
            ),
            callback=self._on_result,
        )

    def _on_result(self, result) -> None:
        self.applied_result = result


@pytest.mark.asyncio
async def test_device_list_populated():
    """SETUP-01: OptionList contains USB and CUPS entries."""
    app = SetupTestApp(discovery=DISCOVERY_BOTH)
    async with app.run_test(size=(80, 40)) as pilot:
        option_list = app.screen.query_one("#device-list", OptionList)
        assert option_list.option_count == 2
        # Check text content
        prompt_0 = str(option_list.get_option_at_index(0).prompt)
        prompt_1 = str(option_list.get_option_at_index(1).prompt)
        assert "Juki 6100" in prompt_0
        assert "HP_LaserJet" in prompt_1


@pytest.mark.asyncio
async def test_skip_returns_none():
    """SETUP-04: Clicking Skip dismisses with None."""
    app = SetupTestApp(discovery=DISCOVERY_BOTH)
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.click("#skip-btn")
        await pilot.pause()
        assert app.applied_result is None


@pytest.mark.asyncio
async def test_diagnostics_displayed():
    """SETUP-05: Diagnostics log contains discovery messages."""
    app = SetupTestApp(discovery=DISCOVERY_CUPS_ONLY)
    async with app.run_test(size=(80, 40)) as pilot:
        log_widget = app.screen.query_one("#diagnostics-log", Log)
        log_text = log_widget.lines
        combined = "\n".join(str(line) for line in log_text)
        assert "pyusb not installed" in combined


@pytest.mark.asyncio
async def test_profile_select_populated():
    """SETUP-03: Profile Select has entries for all BUILTIN_PROFILES."""
    app = SetupTestApp(discovery=DISCOVERY_BOTH)
    async with app.run_test(size=(80, 40)) as pilot:
        profile_select = app.screen.query_one("#profile-select", Select)
        # The select should have options for all builtin profiles
        # We check that the option count matches
        assert profile_select.value == "generic"
        # Verify all profile names are available as options
        option_values = {opt[1] for opt in profile_select._options}
        for name in BUILTIN_PROFILES:
            assert name in option_values, f"Missing profile: {name}"


@pytest.mark.asyncio
async def test_connect_disabled_when_no_devices():
    """SETUP-01 edge case: Connect button disabled with empty discovery."""
    app = SetupTestApp(discovery=DISCOVERY_EMPTY)
    async with app.run_test(size=(80, 40)) as pilot:
        connect_btn = app.screen.query_one("#connect-btn", Button)
        assert connect_btn.disabled is True


@pytest.mark.asyncio
async def test_install_button_hidden_when_pyusb_available():
    """DEP-02: Install row hidden when pyusb is available."""
    app = SetupTestApp(discovery=DISCOVERY_BOTH)
    async with app.run_test(size=(80, 40)) as pilot:
        install_row = app.screen.query_one("#install-row")
        assert install_row.display is False


@pytest.mark.asyncio
async def test_install_button_visible_when_pyusb_missing():
    """DEP-02: Install button visible when pyusb is not available."""
    app = SetupTestApp(discovery=DISCOVERY_CUPS_ONLY)
    async with app.run_test(size=(80, 40)) as pilot:
        install_btn = app.screen.query_one("#install-btn", Button)
        # install-row should be visible (display is not False)
        install_row = app.screen.query_one("#install-row")
        assert install_row.display is not False


@pytest.mark.asyncio
async def test_escape_dismisses_with_none():
    """SETUP-04: Pressing Escape dismisses with None."""
    app = SetupTestApp(discovery=DISCOVERY_BOTH)
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.press("escape")
        await pilot.pause()
        assert app.applied_result is None


# --- classify() routing (R011/R012) ---

# CH341 "USB2.0-Print" — the in-hand Juki bridge. The juki profile pins
# this exact VID:PID, which is precisely why it must NOT be auto-suggested.
BRIDGE_USB = UsbDeviceInfo(
    vendor_id=0x1A86, product_id=0x7584, product_name="USB2.0-Print"
)
# CH340 serial-only chip (Arduino-clone), surfaced via the bridge-VID tier.
SERIAL_ONLY_USB = UsbDeviceInfo(
    vendor_id=0x1A86, product_id=0x7523, printer_class=False
)
# Epson — escp profile pins VID 0x04B8 with no PID (VID-only match).
EPSON_USB = UsbDeviceInfo(
    vendor_id=0x04B8, product_id=0x0005, product_name="Epson LX-350"
)
UNKNOWN_USB = UsbDeviceInfo(vendor_id=0x1234, product_id=0x5678)


def _usb_discovery(*devices: UsbDeviceInfo) -> DiscoveryResult:
    return DiscoveryResult(pyusb_available=True, usb_devices=list(devices))


async def _select_device(app: App, pilot, index: int = 0) -> None:
    """Highlight and select a device-list option, letting messages settle.

    The kernel-claim probe is patched off: these tests pin profile
    routing, not the darwin kext fallback (which shells out to ioreg).
    """
    with patch(
        "claude_teletype.screens.printer_setup.kernel_driver_holds_printer",
        return_value=False,
    ):
        option_list = app.screen.query_one("#device-list", OptionList)
        option_list.highlighted = index
        option_list.action_select()
        await pilot.pause()


@pytest.mark.asyncio
async def test_bridge_device_gets_no_profile_suggestion():
    """R011 (Q7 negative): bridge VID:PID pinned by the juki profile still
    routes to generic — the manual family pick is never pre-empted."""
    app = SetupTestApp(discovery=_usb_discovery(BRIDGE_USB))
    async with app.run_test(size=(80, 40)) as pilot:
        await _select_device(app, pilot)
        profile_select = app.screen.query_one("#profile-select", Select)
        assert profile_select.value == "generic"


@pytest.mark.asyncio
async def test_bridge_device_label_carries_transport_note():
    """R012 surface: bridge devices are labeled with the transport note
    and the manual-family-pick hint."""
    app = SetupTestApp(discovery=_usb_discovery(BRIDGE_USB))
    async with app.run_test(size=(80, 40)) as pilot:
        option_list = app.screen.query_one("#device-list", OptionList)
        label = str(option_list.get_option_at_index(0).prompt)
        assert "bridge" in label.lower()
        assert "choose your printer family" in label


@pytest.mark.asyncio
async def test_bridge_tier_device_labeled_unconfirmed_adapter():
    """Bridge-tier devices (printer_class=False) are tagged as
    unconfirmed adapters."""
    app = SetupTestApp(discovery=_usb_discovery(SERIAL_ONLY_USB))
    async with app.run_test(size=(80, 40)) as pilot:
        option_list = app.screen.query_one("#device-list", OptionList)
        label = str(option_list.get_option_at_index(0).prompt)
        assert "unconfirmed adapter" in label


@pytest.mark.asyncio
async def test_serial_only_chip_writes_diagnostics_warning():
    """R012: a known serial-only chip warns in #diagnostics-log that it
    cannot drive a parallel printer."""
    app = SetupTestApp(discovery=_usb_discovery(SERIAL_ONLY_USB))
    async with app.run_test(size=(80, 40)) as pilot:
        log_widget = app.screen.query_one("#diagnostics-log", Log)
        combined = "\n".join(str(line) for line in log_widget.lines)
        assert "serial-only adapter" in combined
        assert "cannot drive a parallel printer" in combined


@pytest.mark.asyncio
async def test_parallel_capable_bridge_writes_no_serial_warning():
    """Q7 negative: the parallel-capable 0x7584 bridge must NOT trigger
    the serial-only warning."""
    app = SetupTestApp(discovery=_usb_discovery(BRIDGE_USB))
    async with app.run_test(size=(80, 40)) as pilot:
        log_widget = app.screen.query_one("#diagnostics-log", Log)
        combined = "\n".join(str(line) for line in log_widget.lines)
        assert "serial-only adapter" not in combined


@pytest.mark.asyncio
async def test_native_epson_gets_escp_suggested():
    """A native Epson (VID pinned by the escp profile) gets escp
    auto-suggested on selection."""
    app = SetupTestApp(discovery=_usb_discovery(EPSON_USB))
    async with app.run_test(size=(80, 40)) as pilot:
        await _select_device(app, pilot)
        profile_select = app.screen.query_one("#profile-select", Select)
        assert profile_select.value == "escp"


@pytest.mark.asyncio
async def test_unknown_device_routes_generic():
    """An unknown VID:PID routes to generic."""
    app = SetupTestApp(discovery=_usb_discovery(UNKNOWN_USB))
    async with app.run_test(size=(80, 40)) as pilot:
        await _select_device(app, pilot)
        profile_select = app.screen.query_one("#profile-select", Select)
        assert profile_select.value == "generic"


@pytest.mark.asyncio
async def test_suggested_profile_missing_from_options_falls_back_generic():
    """Q7 negative: a suggestion whose name is not among the Select's
    options falls back to generic without crashing (suggestion is
    advisory). Built by keying a profile under a dict key that differs
    from its .name — classify() suggests the .name."""
    phantom = dataclasses.replace(BUILTIN_PROFILES["escp"], name="phantom")
    catalog = {"generic": None, "escp-custom": phantom}
    app = SetupTestApp(
        discovery=_usb_discovery(EPSON_USB), all_profiles=catalog
    )
    async with app.run_test(size=(80, 40)) as pilot:
        await _select_device(app, pilot)
        profile_select = app.screen.query_one("#profile-select", Select)
        assert profile_select.value == "generic"


def test_match_profile_by_vid_pid_removed():
    """Done-when pin: the hand-rolled VID:PID matcher is gone — the
    screen routes purely on Classification."""
    assert not hasattr(PrinterSetupScreen, "_match_profile_by_vid_pid")
