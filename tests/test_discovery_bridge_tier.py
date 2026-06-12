"""Tests for the discovery bridge tier: bridge-VID devices without USB class 7.

discover_all() historically enumerated only bInterfaceClass==7 interfaces,
so a CH340 serial adapter or PL2303 was invisible. The bridge tier surfaces
known bridge-chip VIDs (from the curated BRIDGE_CHIPS registry) with
printer_class=False, using descriptor reads only — no probe bytes, no
control transfers, no set_configuration.
"""

import importlib.util
import sys
from contextlib import contextmanager
from unittest.mock import MagicMock, patch


class FakeInterface:
    def __init__(self, interface_class: int):
        self.bInterfaceClass = interface_class
        self.bInterfaceNumber = 0


class FakeConfig:
    def __init__(self, interface_classes: list[int]):
        self._interfaces = [FakeInterface(c) for c in interface_classes]

    def __iter__(self):
        return iter(self._interfaces)


class FakeDevice:
    """Fake pyusb device with repeatable config iteration.

    Records any probing operation (set_configuration, write, ctrl_transfer)
    so tests can assert enumeration stays descriptor-only.
    """

    def __init__(
        self,
        vid: int,
        pid: int,
        interface_classes: list[int] | None = None,
        product: str = "",
        manufacturer: str = "",
        serial: str = "",
        bus: int = 1,
        address: int = 4,
        raise_on_strings: bool = False,
    ):
        self.idVendor = vid
        self.idProduct = pid
        self._configs = [FakeConfig(interface_classes or [])]
        self._product = product
        self._manufacturer = manufacturer
        self._serial = serial
        self.bus = bus
        self.address = address
        self._raise_on_strings = raise_on_strings
        self.probe_calls: list[str] = []

    def __iter__(self):
        return iter(self._configs)

    def _string(self, value: str) -> str:
        if self._raise_on_strings:
            raise ValueError("Access denied (insufficient permissions)")
        return value

    @property
    def product(self):
        return self._string(self._product)

    @property
    def manufacturer(self):
        return self._string(self._manufacturer)

    @property
    def serial_number(self):
        return self._string(self._serial)

    def set_configuration(self, *args, **kwargs):
        self.probe_calls.append("set_configuration")

    def write(self, *args, **kwargs):
        self.probe_calls.append("write")

    def ctrl_transfer(self, *args, **kwargs):
        self.probe_calls.append("ctrl_transfer")


@contextmanager
def _usb_environment(devices: list[FakeDevice]):
    """Patch pyusb so discover_all() enumerates the given fake devices."""
    mock_spec = MagicMock()
    original_find_spec = importlib.util.find_spec

    def patched_find_spec(name, *args, **kwargs):
        if name == "usb":
            return mock_spec
        return original_find_spec(name, *args, **kwargs)

    NoBackendError = type("NoBackendError", (Exception,), {})
    mock_usb_core = MagicMock()
    mock_usb_core.NoBackendError = NoBackendError
    mock_usb_core.find.return_value = devices

    mock_usb = MagicMock()
    mock_usb.core = mock_usb_core

    with patch("importlib.util.find_spec", side_effect=patched_find_spec):
        with patch.dict(
            sys.modules,
            {"usb": mock_usb, "usb.core": mock_usb_core, "usb.util": MagicMock()},
        ):
            with patch(
                "claude_teletype.printing.discovery.discover_cups_printers",
                return_value=[],
            ):
                yield


def _discover(devices: list[FakeDevice]):
    from claude_teletype.printing.discovery import discover_all

    with _usb_environment(devices):
        return discover_all()


class TestBridgeTier:
    def test_bridge_vid_without_class7_surfaces_with_printer_class_false(self):
        """A CH340 in serial mode (no class-7 interface) becomes visible."""
        ch340 = FakeDevice(
            0x1A86, 0x7523, interface_classes=[0xFF], product="USB Serial"
        )
        result = _discover([ch340])

        assert len(result.usb_devices) == 1
        dev = result.usb_devices[0]
        assert dev.vendor_id == 0x1A86
        assert dev.product_id == 0x7523
        assert dev.printer_class is False
        assert dev.product_name == "USB Serial"

    def test_class7_device_surfaces_with_printer_class_true(self):
        """Any class-7 device (bridge VID or not) is a printer-class entry."""
        epson = FakeDevice(0x04B8, 0x0202, interface_classes=[7], product="LX-350")
        result = _discover([epson])

        assert len(result.usb_devices) == 1
        assert result.usb_devices[0].printer_class is True

    def test_dual_presenting_bridge_appears_exactly_once(self):
        """A bridge-VID device that DOES present class 7 (0x7584) — no duplicate."""
        juki_bridge = FakeDevice(
            0x1A86, 0x7584, interface_classes=[7], product="USB2.0-Print"
        )
        result = _discover([juki_bridge])

        assert len(result.usb_devices) == 1
        dev = result.usb_devices[0]
        assert dev.product_id == 0x7584
        assert dev.printer_class is True

    def test_non_bridge_non_class7_device_stays_invisible(self):
        """A vendor-class device with an unknown VID does not appear."""
        hid_thing = FakeDevice(0x046D, 0xC52B, interface_classes=[3])
        result = _discover([hid_thing])

        assert result.usb_devices == []

    def test_class7_entries_precede_bridge_tier_entries(self):
        """Ordering: class-7 entries first, bridge tier appended after —
        even when the bridge device enumerates before the printer."""
        ch340 = FakeDevice(0x1A86, 0x7523, interface_classes=[0xFF])
        epson = FakeDevice(0x04B8, 0x0202, interface_classes=[7])
        result = _discover([ch340, epson])

        assert len(result.usb_devices) == 2
        assert result.usb_devices[0].vendor_id == 0x04B8
        assert result.usb_devices[0].printer_class is True
        assert result.usb_devices[1].vendor_id == 0x1A86
        assert result.usb_devices[1].printer_class is False

    def test_enumeration_is_descriptor_only(self):
        """No code path writes probe bytes, does control transfers, or
        calls set_configuration during enumeration."""
        devices = [
            FakeDevice(0x1A86, 0x7523, interface_classes=[0xFF]),
            FakeDevice(0x067B, 0x2303, interface_classes=[0xFF]),
            FakeDevice(0x04B8, 0x0202, interface_classes=[7]),
        ]
        _discover(devices)

        for dev in devices:
            assert dev.probe_calls == []

    def test_descriptor_string_read_failure_yields_empty_strings(self):
        """Permission-denied string descriptor reads fall back to ''."""
        ch340 = FakeDevice(
            0x1A86,
            0x7523,
            interface_classes=[0xFF],
            product="USB Serial",
            raise_on_strings=True,
        )
        result = _discover([ch340])

        assert len(result.usb_devices) == 1
        dev = result.usb_devices[0]
        assert dev.product_name == ""
        assert dev.manufacturer == ""
        assert dev.serial == ""
        assert dev.printer_class is False

    def test_no_printer_class_diagnostic_stays_keyed_to_class7(self):
        """Bridge-tier-only discovery still appends the 'No USB
        printer-class devices found' diagnostic — the message stays truthful."""
        ch340 = FakeDevice(0x1A86, 0x7523, interface_classes=[0xFF])
        result = _discover([ch340])

        assert len(result.usb_devices) == 1
        assert any(
            "No USB printer-class devices found" in d for d in result.diagnostics
        )

    def test_class7_present_suppresses_no_printer_diagnostic(self):
        """When a class-7 device exists, the diagnostic is not appended."""
        epson = FakeDevice(0x04B8, 0x0202, interface_classes=[7])
        result = _discover([epson])

        assert not any(
            "No USB printer-class devices found" in d for d in result.diagnostics
        )
