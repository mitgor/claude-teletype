"""Tests for discovery data layer and diagnose command."""

from unittest.mock import MagicMock, patch

import pytest


class TestDiscoverAll:
    """Tests for discover_all() structured discovery."""

    def test_pyusb_not_installed_returns_false(self):
        """When pyusb is not installed, discover_all() returns pyusb_available=False."""
        from claude_teletype.printer import DiscoveryResult, discover_all

        with patch("importlib.util.find_spec", return_value=None):
            with patch(
                "claude_teletype.printer.discover_cups_printers", return_value=[]
            ):
                result = discover_all()

        assert isinstance(result, DiscoveryResult)
        assert result.pyusb_available is False
        assert result.libusb_available is False
        assert result.usb_devices == []
        assert any("pyusb not installed" in d for d in result.diagnostics)

    def test_pyusb_available_no_libusb_backend(self):
        """When pyusb installed but no libusb backend, returns libusb_available=False."""
        from claude_teletype.printer import DiscoveryResult, discover_all

        mock_spec = MagicMock()  # truthy value for find_spec

        original_find_spec = __import__("importlib.util", fromlist=["find_spec"]).find_spec

        def patched_find_spec(name, *args, **kwargs):
            if name == "usb":
                return mock_spec
            return original_find_spec(name, *args, **kwargs)

        # Mock usb.core to raise NoBackendError on find()
        NoBackendError = type("NoBackendError", (Exception,), {})
        mock_usb_core = MagicMock()
        mock_usb_core.NoBackendError = NoBackendError
        mock_usb_core.find.side_effect = NoBackendError()

        # Build parent mock with .core pointing to our mock_usb_core
        mock_usb = MagicMock()
        mock_usb.core = mock_usb_core

        import sys

        with patch("importlib.util.find_spec", side_effect=patched_find_spec):
            with patch.dict(
                sys.modules,
                {"usb": mock_usb, "usb.core": mock_usb_core, "usb.util": MagicMock()},
            ):
                with patch(
                    "claude_teletype.printer.discover_cups_printers", return_value=[]
                ):
                    result = discover_all()

        assert result.pyusb_available is True
        assert result.libusb_available is False
        assert any("libusb backend not found" in d for d in result.diagnostics)

    def test_always_includes_cups_printers(self):
        """discover_all() always calls discover_cups_printers regardless of pyusb."""
        from claude_teletype.printer import discover_all

        with patch("importlib.util.find_spec", return_value=None):
            with patch(
                "claude_teletype.printer.discover_cups_printers",
                return_value=[{"name": "TestPrinter", "uri": "usb://Test/Printer"}],
            ):
                result = discover_all()

        assert len(result.cups_printers) == 1
        assert result.cups_printers[0].name == "TestPrinter"
        assert result.cups_printers[0].uri == "usb://Test/Printer"

    def test_never_raises_exceptions(self):
        """discover_all() catches all exceptions and records in diagnostics."""
        from claude_teletype.printer import DiscoveryResult, discover_all

        with patch("importlib.util.find_spec", side_effect=RuntimeError("boom")):
            with patch(
                "claude_teletype.printer.discover_cups_printers",
                side_effect=RuntimeError("cups boom"),
            ):
                # Should not raise
                result = discover_all()

        assert isinstance(result, DiscoveryResult)

    def test_cups_printers_with_vendor_model_serial(self):
        """CupsPrinterInfo captures vendor, model, serial from CUPS discovery."""
        from claude_teletype.printer import discover_all

        cups_data = [
            {
                "name": "Juki_6100",
                "uri": "usb://Juki/6100?serial=ABC123",
                "vendor": "Juki",
                "model": "6100",
                "serial": "ABC123",
            }
        ]

        with patch("importlib.util.find_spec", return_value=None):
            with patch(
                "claude_teletype.printer.discover_cups_printers",
                return_value=cups_data,
            ):
                result = discover_all()

        p = result.cups_printers[0]
        assert p.vendor == "Juki"
        assert p.model == "6100"
        assert p.serial == "ABC123"

    def test_usb_device_info_fields(self):
        """UsbDeviceInfo has all expected fields with correct defaults."""
        from claude_teletype.printer import UsbDeviceInfo

        dev = UsbDeviceInfo(vendor_id=0x1A86, product_id=0x7584)
        assert dev.vendor_id == 0x1A86
        assert dev.product_id == 0x7584
        assert dev.product_name == ""
        assert dev.manufacturer == ""
        assert dev.serial == ""
        assert dev.bus == 0
        assert dev.address == 0

    def test_discovery_result_defaults(self):
        """DiscoveryResult has sensible defaults."""
        from claude_teletype.printer import DiscoveryResult

        r = DiscoveryResult()
        assert r.pyusb_available is False
        assert r.libusb_available is False
        assert r.usb_devices == []
        assert r.cups_printers == []
        assert r.diagnostics == []

    def test_no_usb_printers_found_diagnostic(self):
        """When pyusb+libusb present but no printer devices, records diagnostic."""
        from claude_teletype.printer import discover_all

        mock_spec = MagicMock()
        original_find_spec = __import__("importlib.util", fromlist=["find_spec"]).find_spec

        def patched_find_spec(name, *args, **kwargs):
            if name == "usb":
                return mock_spec
            return original_find_spec(name, *args, **kwargs)

        # Mock usb.core.find to return non-printer devices
        mock_dev = MagicMock()
        mock_intf = MagicMock()
        mock_intf.bInterfaceClass = 3  # HID, not printer
        mock_cfg = MagicMock()
        mock_cfg.__iter__ = MagicMock(return_value=iter([mock_intf]))
        mock_dev.__iter__ = MagicMock(return_value=iter([mock_cfg]))

        NoBackendError = type("NoBackendError", (Exception,), {})
        mock_usb_core = MagicMock()
        mock_usb_core.NoBackendError = NoBackendError
        mock_usb_core.find.return_value = [mock_dev]

        mock_usb = MagicMock()
        mock_usb.core = mock_usb_core

        import sys

        with patch("importlib.util.find_spec", side_effect=patched_find_spec):
            with patch.dict(
                sys.modules,
                {"usb": mock_usb, "usb.core": mock_usb_core, "usb.util": MagicMock()},
            ):
                with patch(
                    "claude_teletype.printer.discover_cups_printers", return_value=[]
                ):
                    result = discover_all()

        assert result.pyusb_available is True
        assert result.libusb_available is True
        assert result.usb_devices == []
        assert any("No USB printer-class devices found" in d for d in result.diagnostics)
