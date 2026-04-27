"""Tests for smart startup: skip setup when saved printer is connected."""

from __future__ import annotations

import pytest

from claude_teletype.printer import (
    CupsPrinterInfo,
    DiscoveryResult,
    PrinterSelection,
    UsbDeviceInfo,
    match_saved_printer,
)


class TestMatchSavedPrinterUsb:
    """match_saved_printer matches USB devices by VID:PID hex string."""

    def test_usb_match_returns_selection_when_vid_pid_matches(self):
        discovery = DiscoveryResult(
            usb_devices=[
                UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0005, product_name="Epson"),
            ]
        )
        result = match_saved_printer("usb", "04b8:0005", discovery)
        assert result is not None
        assert result.connection_type == "usb"
        assert result.device_index == 0

    def test_usb_no_match_returns_none(self):
        discovery = DiscoveryResult(
            usb_devices=[
                UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0005),
            ]
        )
        result = match_saved_printer("usb", "1234:5678", discovery)
        assert result is None

    def test_usb_match_second_device(self):
        discovery = DiscoveryResult(
            usb_devices=[
                UsbDeviceInfo(vendor_id=0x1111, product_id=0x2222),
                UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0005),
            ]
        )
        result = match_saved_printer("usb", "04b8:0005", discovery)
        assert result is not None
        assert result.device_index == 1

    def test_usb_empty_devices_returns_none(self):
        discovery = DiscoveryResult(usb_devices=[])
        result = match_saved_printer("usb", "04b8:0005", discovery)
        assert result is None

    def test_usb_invalid_vid_pid_format_returns_none(self):
        discovery = DiscoveryResult(
            usb_devices=[UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0005)]
        )
        result = match_saved_printer("usb", "not-hex", discovery)
        assert result is None


class TestMatchSavedPrinterCups:
    """match_saved_printer matches CUPS printers by queue name."""

    def test_cups_match_returns_selection(self):
        discovery = DiscoveryResult(
            cups_printers=[
                CupsPrinterInfo(name="HP_LaserJet", uri="usb://HP/LaserJet"),
            ]
        )
        result = match_saved_printer("cups", "HP_LaserJet", discovery)
        assert result is not None
        assert result.connection_type == "cups"
        assert result.cups_printer_name == "HP_LaserJet"

    def test_cups_no_match_returns_none(self):
        discovery = DiscoveryResult(
            cups_printers=[
                CupsPrinterInfo(name="HP_LaserJet", uri="usb://HP/LaserJet"),
            ]
        )
        result = match_saved_printer("cups", "Epson_Dot_Matrix", discovery)
        assert result is None

    def test_cups_disabled_queue_not_matched(self):
        """Disabled CUPS queues are skipped so smart-startup falls through to setup.

        Regression: a stale CUPS queue ("Unable to send data to printer") was
        smart-matched by name only, silently routing characters into a dead
        queue while a working USB Direct device was ignored.
        """
        discovery = DiscoveryResult(
            cups_printers=[
                CupsPrinterInfo(
                    name="USB2.0-Print",
                    uri="usb:///USB2.0-Print",
                    enabled=False,
                ),
            ]
        )
        result = match_saved_printer("cups", "USB2.0-Print", discovery)
        assert result is None

    def test_cups_enabled_queue_still_matched(self):
        discovery = DiscoveryResult(
            cups_printers=[
                CupsPrinterInfo(
                    name="HP_LaserJet",
                    uri="usb://HP/LaserJet",
                    enabled=True,
                ),
            ]
        )
        result = match_saved_printer("cups", "HP_LaserJet", discovery)
        assert result is not None
        assert result.cups_printer_name == "HP_LaserJet"


class TestMatchSavedPrinterEdgeCases:
    """match_saved_printer handles empty/skip/missing saved config."""

    def test_empty_type_returns_none(self):
        discovery = DiscoveryResult(
            usb_devices=[UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0005)]
        )
        result = match_saved_printer("", "04b8:0005", discovery)
        assert result is None

    def test_skip_type_returns_none(self):
        discovery = DiscoveryResult(
            usb_devices=[UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0005)]
        )
        result = match_saved_printer("skip", "04b8:0005", discovery)
        assert result is None

    def test_usb_empty_id_returns_none(self):
        discovery = DiscoveryResult(
            usb_devices=[UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0005)]
        )
        result = match_saved_printer("usb", "", discovery)
        assert result is None

    def test_cups_empty_id_returns_none(self):
        discovery = DiscoveryResult(
            cups_printers=[CupsPrinterInfo(name="HP", uri="usb://HP")]
        )
        result = match_saved_printer("cups", "", discovery)
        assert result is None


class TestNeedsPrinterSetupWithSavedConfig:
    """_needs_printer_setup returns False when saved printer matches discovery."""

    def test_skips_setup_when_discovery_is_none(self):
        """When discovery=None (saved printer matched), setup is skipped."""
        from claude_teletype.tui import TeletypeApp

        # Minimal mock backend
        class FakeBackend:
            def validate(self): pass

        app = TeletypeApp(
            backend=FakeBackend(),
            discovery=None,
            printer=None,
        )
        assert app._needs_printer_setup() is False

    def test_shows_setup_when_discovery_is_set_and_no_printer(self):
        """When discovery is set (saved printer NOT found), setup shows."""
        from claude_teletype.tui import TeletypeApp

        class FakeBackend:
            def validate(self): pass

        app = TeletypeApp(
            backend=FakeBackend(),
            discovery=DiscoveryResult(),
            printer=None,
        )
        assert app._needs_printer_setup() is True
