"""Tests for the PrinterSetupScreen component."""

import pytest
from textual.app import App
from textual.widgets import Button, Log, OptionList, Select

from claude_teletype.printer import (
    CupsPrinterInfo,
    DiscoveryResult,
    PrinterSelection,
    UsbDeviceInfo,
)
from claude_teletype.printer_setup_screen import PrinterSetupScreen
from claude_teletype.profiles import BUILTIN_PROFILES

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
