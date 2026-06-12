"""Tests for printing/detection.py — DeviceKind, Classification, classify() (DET-02)."""

import dataclasses
from unittest.mock import MagicMock, patch

import pytest

from claude_teletype.printing.detection import (
    BRIDGE_CHIP_VIDS,
    BRIDGE_CHIPS,
    Classification,
    DeviceKind,
    classify,
)
from claude_teletype.printing.discovery import UsbDeviceInfo
from claude_teletype.printing.profiles import BUILTIN_PROFILES
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

    def test_bridge_chip_vids_derived_from_bridge_chips(self):
        """BRIDGE_CHIP_VIDS is the vid→note projection of BRIDGE_CHIPS."""
        assert BRIDGE_CHIP_VIDS == {
            vid: chip.note for vid, chip in BRIDGE_CHIPS.items()
        }
        assert BRIDGE_CHIP_VIDS, "registry must be populated (R009)"


class TestClassifyBridgeRealData:
    """classify() against the real curated BRIDGE_CHIPS data (R009, R012)."""

    @pytest.mark.parametrize(
        ("vid", "pid", "serial_only"),
        [
            (0x1A86, 0x7584, False),  # CH341 "USB2.0-Print" — the Juki bridge
            (0x1A86, 0x7523, True),  # CH340 serial (Arduino-clone chip)
            (0x067B, 0x2303, True),  # PL2303 serial
            (0x067B, 0x2305, False),  # PL2305 IEEE-1284 parallel
            (0x0403, 0x6001, True),  # FT232 — FTDI has no parallel product
            (0x9710, 0x7705, False),  # MCS7705 parallel
        ],
    )
    def test_curated_bridge_classification(self, vid, pid, serial_only):
        result = classify(UsbDeviceInfo(vendor_id=vid, product_id=pid), _registry())
        assert result.kind is DeviceKind.BRIDGE
        assert result.suggested_profile is None
        assert result.serial_only is serial_only
        assert result.transport_note == BRIDGE_CHIP_VIDS[vid]

    def test_unlisted_pid_under_bridge_vid_is_bridge_unknown_capability(self):
        """A PID listed in neither set stays BRIDGE with serial_only=False."""
        result = classify(
            UsbDeviceInfo(vendor_id=0x1A86, product_id=0xFFFF),
            _registry(),
        )
        assert result.kind is DeviceKind.BRIDGE
        assert result.serial_only is False

    def test_juki_profile_vid_pin_shadowed_by_bridge_check(self):
        """Deliberate behavior change (R011): juki-6100 pins 0x1A86:0x7584,
        but the bridge-first check now wins — the CH341 identifies the
        cable, not the printer, so no native profile may be suggested."""
        registry = _registry()
        pinned = registry.match_vidpid(0x1A86, 0x7584)
        assert pinned is not None, "precondition: juki profile still pins the VID"

        result = classify(
            UsbDeviceInfo(vendor_id=0x1A86, product_id=0x7584),
            registry,
        )
        assert result.kind is DeviceKind.BRIDGE
        assert result.suggested_profile is None


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
