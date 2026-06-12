"""Tests proving create_driver_for_selection drives the picked device (REF-03).

The legacy bug: create_driver_for_selection called _find_usb_printer() with
no selector, which returned the FIRST printer-class device and silently
ignored selection.device_index. These tests prove the indexed device's
identity is the one passed through, and that the matched device is the one
actually opened.
"""

from unittest.mock import MagicMock, patch

from claude_teletype.printing.discovery import (
    DiscoveryResult,
    PrinterSelection,
    UsbDeviceInfo,
    _device_matches_identity,
    _find_usb_printer,
)
from claude_teletype.printing.selection import create_driver_for_selection


def _two_device_discovery() -> DiscoveryResult:
    return DiscoveryResult(
        pyusb_available=True,
        libusb_available=True,
        usb_devices=[
            UsbDeviceInfo(
                vendor_id=0x04B8,
                product_id=0x0005,
                product_name="Epson LX-300",
                serial="EP-AAA",
                bus=1,
                address=4,
            ),
            UsbDeviceInfo(
                vendor_id=0x1A86,
                product_id=0x7584,
                product_name="Juki 6100",
                serial="",
                bus=1,
                address=9,
            ),
        ],
    )


class TestCreateDriverPassesPickedIdentity:
    """selection.device_index resolves to that device's identity."""

    def test_device_index_1_passes_second_device_identity(self):
        discovery = _two_device_discovery()
        sel = PrinterSelection(connection_type="usb", device_index=1)

        with patch(
            "claude_teletype.printing.discovery._find_usb_printer"
        ) as mock_find:
            mock_find.return_value = MagicMock()
            create_driver_for_selection(sel, discovery)

        mock_find.assert_called_once_with(identity=discovery.usb_devices[1])
        passed = mock_find.call_args.kwargs["identity"]
        assert passed is not discovery.usb_devices[0]
        assert (passed.vendor_id, passed.product_id) == (0x1A86, 0x7584)

    def test_device_index_0_passes_first_device_identity(self):
        discovery = _two_device_discovery()
        sel = PrinterSelection(connection_type="usb", device_index=0)

        with patch(
            "claude_teletype.printing.discovery._find_usb_printer"
        ) as mock_find:
            mock_find.return_value = MagicMock()
            create_driver_for_selection(sel, discovery)

        mock_find.assert_called_once_with(identity=discovery.usb_devices[0])

    def test_device_index_none_falls_back_to_first_printer_behavior(self):
        """Legacy single-printer flows: no explicit pick, no identity filter."""
        discovery = _two_device_discovery()
        sel = PrinterSelection(connection_type="usb", device_index=None)

        with patch(
            "claude_teletype.printing.discovery._find_usb_printer"
        ) as mock_find:
            mock_find.return_value = MagicMock()
            create_driver_for_selection(sel, discovery)

        mock_find.assert_called_once_with(identity=None)

    def test_out_of_range_index_falls_back_to_first_printer_behavior(self):
        discovery = _two_device_discovery()
        sel = PrinterSelection(connection_type="usb", device_index=5)

        with patch(
            "claude_teletype.printing.discovery._find_usb_printer"
        ) as mock_find:
            mock_find.return_value = MagicMock()
            create_driver_for_selection(sel, discovery)

        mock_find.assert_called_once_with(identity=None)

    def test_profile_wrapping_tail_still_wraps_non_generic(self):
        from claude_teletype.printing.drivers import ProfilePrinterDriver

        discovery = _two_device_discovery()
        sel = PrinterSelection(
            connection_type="usb", device_index=1, profile_name="juki-6100"
        )

        inner = MagicMock()
        with patch(
            "claude_teletype.printing.discovery._find_usb_printer",
            return_value=inner,
        ):
            driver = create_driver_for_selection(sel, discovery)

        assert isinstance(driver, ProfilePrinterDriver)
        assert driver._inner is inner


def _fake_usb_modules(devices):
    """Fake usb/usb.core/usb.util modules enumerating the given devices."""
    mock_usb_core = MagicMock()
    mock_usb_core.NoBackendError = type("NoBackendError", (Exception,), {})
    mock_usb_core.find.return_value = devices

    mock_ep = MagicMock()
    mock_ep.bEndpointAddress = 0x01
    mock_usb_util = MagicMock()
    mock_usb_util.find_descriptor.return_value = mock_ep

    mock_usb = MagicMock()
    mock_usb.core = mock_usb_core
    mock_usb.util = mock_usb_util
    return {"usb": mock_usb, "usb.core": mock_usb_core, "usb.util": mock_usb_util}


def _fake_printer_device(vid, pid, serial="", bus=0, address=0):
    """A fake pyusb device exposing one printer-class interface."""
    intf = MagicMock()
    intf.bInterfaceClass = 7
    intf.bInterfaceNumber = 0

    cfg = MagicMock()
    cfg.__iter__ = lambda self: iter([intf])

    dev = MagicMock()
    dev.__iter__ = lambda self: iter([cfg])
    dev.idVendor = vid
    dev.idProduct = pid
    dev.serial_number = serial
    dev.bus = bus
    dev.address = address
    dev.is_kernel_driver_active.return_value = False
    return dev


class TestFindUsbPrinterByIdentity:
    """_find_usb_printer(identity=...) opens the matching device only."""

    def test_identity_selects_second_enumerated_device(self):
        first = _fake_printer_device(0x04B8, 0x0005, bus=1, address=4)
        second = _fake_printer_device(0x1A86, 0x7584, bus=1, address=9)
        identity = UsbDeviceInfo(
            vendor_id=0x1A86, product_id=0x7584, bus=1, address=9
        )

        with patch.dict("sys.modules", _fake_usb_modules([first, second])):
            driver = _find_usb_printer(identity=identity)

        assert driver is not None
        assert driver._dev is second
        second.set_configuration.assert_called_once()
        first.set_configuration.assert_not_called()

    def test_identity_prefers_serial_match(self):
        """Same VID:PID twins are told apart by serial number."""
        twin_a = _fake_printer_device(0x04B8, 0x0005, serial="AAA", bus=1, address=4)
        twin_b = _fake_printer_device(0x04B8, 0x0005, serial="BBB", bus=1, address=9)
        identity = UsbDeviceInfo(
            vendor_id=0x04B8, product_id=0x0005, serial="BBB", bus=3, address=7
        )

        with patch.dict("sys.modules", _fake_usb_modules([twin_a, twin_b])):
            driver = _find_usb_printer(identity=identity)

        assert driver is not None
        assert driver._dev is twin_b

    def test_no_identity_keeps_first_printer_behavior(self):
        first = _fake_printer_device(0x04B8, 0x0005)
        second = _fake_printer_device(0x1A86, 0x7584)

        with patch.dict("sys.modules", _fake_usb_modules([first, second])):
            driver = _find_usb_printer()

        assert driver is not None
        assert driver._dev is first

    def test_identity_not_present_returns_none(self):
        """The picked device was unplugged: no silent fallback to another."""
        present = _fake_printer_device(0x04B8, 0x0005, bus=1, address=4)
        identity = UsbDeviceInfo(
            vendor_id=0x1A86, product_id=0x7584, bus=1, address=9
        )

        with patch.dict("sys.modules", _fake_usb_modules([present])):
            driver = _find_usb_printer(identity=identity)

        assert driver is None


class TestDeviceMatchesIdentity:
    def test_vid_pid_mismatch_fails(self):
        dev = _fake_printer_device(0x04B8, 0x0005, bus=1, address=4)
        identity = UsbDeviceInfo(vendor_id=0x1A86, product_id=0x7584, bus=1, address=4)
        assert _device_matches_identity(dev, identity) is False

    def test_bus_address_match_when_no_serial(self):
        dev = _fake_printer_device(0x04B8, 0x0005, bus=1, address=4)
        identity = UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0005, bus=1, address=4)
        assert _device_matches_identity(dev, identity) is True

    def test_bus_address_mismatch_fails_when_no_serial(self):
        dev = _fake_printer_device(0x04B8, 0x0005, bus=1, address=4)
        identity = UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0005, bus=1, address=9)
        assert _device_matches_identity(dev, identity) is False

    def test_unreadable_serial_fails_serial_match(self):
        dev = _fake_printer_device(0x04B8, 0x0005, bus=1, address=4)
        type(dev).serial_number = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("no langid"))
        )
        identity = UsbDeviceInfo(
            vendor_id=0x04B8, product_id=0x0005, serial="AAA", bus=1, address=4
        )
        assert _device_matches_identity(dev, identity) is False
