"""Tests for PrinterSelection dataclass and create_driver_for_selection() factory."""

from unittest.mock import MagicMock, patch

from claude_teletype.printing.discovery import DiscoveryResult, PrinterSelection
from claude_teletype.printing.drivers import (
    CupsPrinterDriver,
    NullPrinterDriver,
    ProfilePrinterDriver,
    UsbPrinterDriver,
)
from claude_teletype.printing.selection import create_driver_for_selection


class TestCreateDriverForSelection:
    """Tests for create_driver_for_selection() factory function."""

    def test_skip_returns_null_driver(self):
        """connection_type='skip' returns NullPrinterDriver."""
        sel = PrinterSelection(connection_type="skip")
        discovery = DiscoveryResult()
        driver = create_driver_for_selection(sel, discovery)
        assert isinstance(driver, NullPrinterDriver)

    def test_cups_returns_cups_driver(self):
        """connection_type='cups' with printer name returns CupsPrinterDriver."""
        sel = PrinterSelection(
            connection_type="cups",
            cups_printer_name="HP_LaserJet",
        )
        discovery = DiscoveryResult()
        driver = create_driver_for_selection(sel, discovery)
        assert isinstance(driver, CupsPrinterDriver)
        assert driver._name == "HP_LaserJet"

    def test_cups_with_profile_returns_profile_driver(self):
        """connection_type='cups' with non-generic profile wraps in ProfilePrinterDriver."""

        sel = PrinterSelection(
            connection_type="cups",
            cups_printer_name="HP_LaserJet",
            profile_name="escp",
        )
        discovery = DiscoveryResult()
        driver = create_driver_for_selection(sel, discovery)
        assert isinstance(driver, ProfilePrinterDriver)
        assert isinstance(driver._inner, CupsPrinterDriver)
        assert driver._profile.name == "escp"

    def test_usb_find_fails_returns_null_driver(self):
        """connection_type='usb' when _find_usb_printer returns None -> NullPrinterDriver."""
        sel = PrinterSelection(connection_type="usb")
        discovery = DiscoveryResult()
        with patch("claude_teletype.printing.discovery._find_usb_printer", return_value=None):
            driver = create_driver_for_selection(sel, discovery)
        assert isinstance(driver, NullPrinterDriver)

    def test_usb_generic_profile_returns_raw_usb_driver(self):
        """connection_type='usb' with profile_name='generic' returns raw UsbPrinterDriver."""
        mock_dev = MagicMock()
        mock_ep = MagicMock()
        mock_usb_driver = UsbPrinterDriver(mock_dev, mock_ep)

        sel = PrinterSelection(connection_type="usb", profile_name="generic")
        discovery = DiscoveryResult()
        with patch(
            "claude_teletype.printing.discovery._find_usb_printer",
            return_value=mock_usb_driver,
        ):
            driver = create_driver_for_selection(sel, discovery)
        assert isinstance(driver, UsbPrinterDriver)
        assert not isinstance(driver, ProfilePrinterDriver)

    def test_usb_with_profile_returns_profile_driver(self):
        """connection_type='usb' with profile_name='juki' wraps in ProfilePrinterDriver."""
        mock_dev = MagicMock()
        mock_ep = MagicMock()
        mock_usb_driver = UsbPrinterDriver(mock_dev, mock_ep)

        sel = PrinterSelection(connection_type="usb", profile_name="juki")
        discovery = DiscoveryResult()
        with patch(
            "claude_teletype.printing.discovery._find_usb_printer",
            return_value=mock_usb_driver,
        ):
            driver = create_driver_for_selection(sel, discovery)
        assert isinstance(driver, ProfilePrinterDriver)
        assert isinstance(driver._inner, UsbPrinterDriver)
        assert driver._profile.name == "juki"


def test_type_hints_resolve_on_public_factory():
    """WR-05: get_type_hints must not NameError on the ProfileRegistry ref."""
    import typing

    hints = typing.get_type_hints(create_driver_for_selection)
    assert "registry" in hints
