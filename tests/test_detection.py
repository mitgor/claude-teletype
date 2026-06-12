"""Tests for printing/detection.py — DeviceKind, Classification, classify() (DET-02)."""

import dataclasses
from unittest.mock import MagicMock, patch

import pytest

from claude_teletype.printing.detection import (
    BRIDGE_CHIP_VIDS,
    Classification,
    DeviceKind,
    classify,
)
from claude_teletype.printing.discovery import UsbDeviceInfo
from claude_teletype.printing.profiles import BUILTIN_PROFILES, auto_detect_profile
from claude_teletype.printing.registry import ProfileRegistry


def _registry() -> ProfileRegistry:
    return ProfileRegistry(BUILTIN_PROFILES)


class TestClassifyBridge:
    """Bridge-VID check runs first and never suggests a native profile."""

    def test_bridge_vid_classifies_bridge(self):
        with patch.dict(
            "claude_teletype.printing.detection.BRIDGE_CHIP_VIDS",
            {0x0403: "FTDI USB-to-parallel bridge"},
        ):
            result = classify(
                UsbDeviceInfo(vendor_id=0x0403, product_id=0x6001),
                _registry(),
            )
        assert result.kind is DeviceKind.BRIDGE
        assert result.suggested_profile is None
        assert result.transport_note == "FTDI USB-to-parallel bridge"

    def test_bridge_check_beats_registry_match(self):
        """A VID in BRIDGE_CHIP_VIDS is BRIDGE even if a profile pins it.

        The bridge chip identifies the cable, not the printer behind it, so
        the registry suggestion must not fire (juki-6100 pins 0x1A86:0x7584).
        """
        with patch.dict(
            "claude_teletype.printing.detection.BRIDGE_CHIP_VIDS",
            {0x1A86: "QinHeng CH341 USB-to-printer bridge"},
        ):
            result = classify(
                UsbDeviceInfo(vendor_id=0x1A86, product_id=0x7584),
                _registry(),
            )
        assert result.kind is DeviceKind.BRIDGE
        assert result.suggested_profile is None
        assert "CH341" in result.transport_note

    def test_bridge_chip_vids_is_placeholder_this_phase(self):
        """Phase 27 ships the seam only; Phase 28 populates the data."""
        assert BRIDGE_CHIP_VIDS == {}


class TestClassifyNative:
    """Registry VID:PID matches classify NATIVE_PRINTER with a suggestion."""

    def test_exact_vidpid_match(self):
        # Citizen CT-S2000: exact 0x2730:0x2002 entry in BUILTIN_PROFILES
        result = classify(
            UsbDeviceInfo(vendor_id=0x2730, product_id=0x2002),
            _registry(),
        )
        assert result.kind is DeviceKind.NATIVE_PRINTER
        assert result.suggested_profile == "citizen-cts2000"
        assert result.transport_note == ""

    def test_vid_only_match(self):
        # Epson 0x04B8 is a VID-only entry (no product id pinned)
        registry = _registry()
        expected = registry.match_vidpid(0x04B8, 0xBEEF)
        assert expected is not None, "precondition: epson VID-only entry exists"

        result = classify(
            UsbDeviceInfo(vendor_id=0x04B8, product_id=0xBEEF),
            registry,
        )
        assert result.kind is DeviceKind.NATIVE_PRINTER
        assert result.suggested_profile == expected.name

    def test_suggestion_comes_from_registry(self):
        """classify delegates the native suggestion to registry.match_vidpid."""
        registry = MagicMock()
        registry.match_vidpid.return_value = BUILTIN_PROFILES["escp"]

        result = classify(
            UsbDeviceInfo(vendor_id=0x1234, product_id=0x5678),
            registry,
        )
        registry.match_vidpid.assert_called_once_with(0x1234, 0x5678)
        assert result.kind is DeviceKind.NATIVE_PRINTER
        assert result.suggested_profile == BUILTIN_PROFILES["escp"].name


class TestClassifyUnknown:
    def test_no_match_is_unknown(self):
        result = classify(
            UsbDeviceInfo(vendor_id=0xDEAD, product_id=0xBEEF),
            _registry(),
        )
        assert result.kind is DeviceKind.UNKNOWN
        assert result.suggested_profile is None
        assert result.transport_note == ""


class TestClassificationType:
    def test_classification_is_frozen(self):
        result = Classification(kind=DeviceKind.UNKNOWN)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.kind = DeviceKind.BRIDGE

    def test_device_kind_values(self):
        assert DeviceKind.NATIVE_PRINTER.value == "native"
        assert DeviceKind.BRIDGE.value == "bridge"
        assert DeviceKind.UNKNOWN.value == "unknown"


class TestBehaviorParityWithAutoDetect:
    """A device that auto_detect_profile resolved to profile X must classify
    NATIVE_PRINTER with suggested_profile == X (DET-02 behavior parity)."""

    @staticmethod
    def _fake_usb_with_device(vid: int, pid: int):
        """Build fake usb modules enumerating one printer-class device."""
        mock_intf = MagicMock()
        mock_intf.bInterfaceClass = 7

        mock_cfg = MagicMock()
        mock_cfg.__iter__ = lambda self: iter([mock_intf])

        mock_dev = MagicMock()
        mock_dev.__iter__ = lambda self: iter([mock_cfg])
        mock_dev.idVendor = vid
        mock_dev.idProduct = pid

        mock_usb_core = MagicMock()
        mock_usb_core.NoBackendError = type("NoBackendError", (Exception,), {})
        mock_usb_core.find.return_value = [mock_dev]

        mock_usb = MagicMock()
        mock_usb.core = mock_usb_core
        return {"usb": mock_usb, "usb.core": mock_usb_core}

    @pytest.mark.parametrize(
        ("vid", "pid"),
        [
            (0x2730, 0x2002),  # citizen-cts2000 (exact VID:PID entry)
            (0x04B8, 0x0005),  # epson (VID-only entry)
            (0x1A86, 0x7584),  # juki bridge-VID pin — unchanged this phase
        ],
    )
    def test_classify_matches_auto_detect_profile(self, vid, pid):
        with patch.dict("sys.modules", self._fake_usb_with_device(vid, pid)):
            legacy = auto_detect_profile()
        assert legacy is not None, "precondition: auto-detect matched a profile"

        result = classify(
            UsbDeviceInfo(vendor_id=vid, product_id=pid),
            _registry(),
        )
        assert result.kind is DeviceKind.NATIVE_PRINTER
        assert result.suggested_profile == legacy.name
