"""Tests for printing/detection.py — DeviceKind, Classification, classify() (DET-02)."""

import dataclasses
from unittest.mock import MagicMock, patch

import pytest

from claude_teletype.printing.detection import (
    BRIDGE_CHIP_VIDS,
    BRIDGE_CHIPS,
    KNOWN_MODEL_PIDS,
    NATIVE_PRINTER_VENDOR_VIDS,
    Classification,
    DeviceKind,
    classify,
    detect_native_profile,
)
from claude_teletype.printing.discovery import DiscoveryResult, UsbDeviceInfo
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

    def test_lexmark_vid_suggests_lexmark_forms(self):
        """A printer-class Lexmark device (any PID) suggests lexmark-forms.

        S03 T02 pinned 0x043D on the lexmark-forms profile: the registry
        VID-only match fires BEFORE the NATIVE_PRINTER_VENDOR_VIDS
        fallthrough, upgrading S02's bare "Lexmark" vendor hint to a
        real suggestion (R010/D007).
        """
        result = classify(
            UsbDeviceInfo(
                vendor_id=0x043D, product_id=0xABCD, printer_class=True
            ),
            _registry(),
        )
        assert result.kind is DeviceKind.NATIVE_PRINTER
        assert result.suggested_profile == "lexmark-forms"

    def test_lexmark_forms_suggestion_resolves_in_registry(self):
        """The lexmark-forms suggestion is a real registry key (MEM015 guard)."""
        suggestion = classify(
            UsbDeviceInfo(
                vendor_id=0x043D, product_id=0xABCD, printer_class=True
            ),
            _registry(),
        ).suggested_profile
        assert suggestion is not None
        profile = ProfileRegistry(BUILTIN_PROFILES).get(suggestion)
        assert profile.name == "lexmark-forms"
        assert profile.usb_vendor_id == 0x043D

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


def _miss_registry() -> MagicMock:
    """A registry whose VID:PID index never matches.

    Isolates the native-matrix fallthrough tiers: with the real builtin
    registry, Epson's VID-only entry would shadow the KNOWN_MODEL_PIDS hit.
    """
    registry = MagicMock()
    registry.match_vidpid.return_value = None
    return registry


class TestClassifyNativeMatrix:
    """R010 native matrix: KNOWN_MODEL_PIDS pins and vendor-VID hints."""

    @pytest.mark.parametrize(("vid", "pid"), sorted(KNOWN_MODEL_PIDS))
    def test_known_model_pid_suggests_profile(self, vid, pid):
        """Epson LX-350/LQ-350 pins classify NATIVE_PRINTER with escp2."""
        result = classify(UsbDeviceInfo(vendor_id=vid, product_id=pid), _miss_registry())
        assert result.kind is DeviceKind.NATIVE_PRINTER
        assert result.suggested_profile == KNOWN_MODEL_PIDS[(vid, pid)]

    @pytest.mark.parametrize(("vid", "pid"), sorted(KNOWN_MODEL_PIDS))
    def test_known_model_pid_suggestion_resolves_in_registry(self, vid, pid):
        """Every KNOWN_MODEL_PIDS suggestion is a real builtin catalog key.

        MEM015 guard: a table value that diverges from the catalog key
        makes the CLI fallback silently skip and the setup Select fall
        back to generic. ProfileRegistry.get raising ValueError here
        means the table and the catalog drifted apart.
        """
        suggestion = classify(
            UsbDeviceInfo(vendor_id=vid, product_id=pid), _miss_registry()
        ).suggested_profile
        assert suggestion == "escp2"
        profile = ProfileRegistry(BUILTIN_PROFILES).get(suggestion)
        assert profile.name == "escp2"

    def test_registry_match_beats_known_model_pid(self):
        """A registry (custom-profile) VID:PID claim wins over the table."""
        registry = MagicMock()
        registry.match_vidpid.return_value = BUILTIN_PROFILES["ppds"]

        result = classify(
            UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0046),
            registry,
        )
        assert result.kind is DeviceKind.NATIVE_PRINTER
        assert result.suggested_profile == "ppds"

    @pytest.mark.parametrize("vid", sorted(NATIVE_PRINTER_VENDOR_VIDS))
    def test_vendor_hint_is_native_without_suggestion(self, vid):
        """Star/Lexmark/IBM VIDs classify NATIVE_PRINTER, suggest nothing."""
        result = classify(
            UsbDeviceInfo(vendor_id=vid, product_id=0x1234),
            _miss_registry(),
        )
        assert result.kind is DeviceKind.NATIVE_PRINTER
        assert result.suggested_profile is None
        assert result.transport_note == ""

    def test_model_pin_beats_vendor_hint(self):
        """An exact model pin outranks a bare vendor hint for the same dev."""
        with patch.dict(
            "claude_teletype.printing.detection.KNOWN_MODEL_PIDS",
            {(0x0519, 0x0001): "escp"},
        ):
            result = classify(
                UsbDeviceInfo(vendor_id=0x0519, product_id=0x0001),
                _miss_registry(),
            )
        assert result.suggested_profile == "escp"

    def test_unlisted_device_still_unknown(self):
        result = classify(
            UsbDeviceInfo(vendor_id=0xDEAD, product_id=0xBEEF),
            _miss_registry(),
        )
        assert result.kind is DeviceKind.UNKNOWN


def _discovery_with(*devices: UsbDeviceInfo) -> DiscoveryResult:
    return DiscoveryResult(
        pyusb_available=True,
        libusb_available=True,
        usb_devices=list(devices),
    )


class TestDetectNativeProfile:
    """CLI bare-launch fallback: classify()-routed, never guesses (R011)."""

    def test_native_device_returns_profile(self):
        """A discovered Epson device resolves to the escp profile."""
        with patch(
            "claude_teletype.printing.discovery.discover_all",
            return_value=_discovery_with(
                UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0005)
            ),
        ):
            profile = detect_native_profile(_registry())
        assert profile is not None
        assert profile.name == "escp"

    def test_bridge_only_discovery_returns_none(self):
        """R011 negative: the CH341 Juki bridge must never yield a profile,
        even though the juki-6100 profile pins its VID:PID."""
        with patch(
            "claude_teletype.printing.discovery.discover_all",
            return_value=_discovery_with(
                UsbDeviceInfo(
                    vendor_id=0x1A86, product_id=0x7584, printer_class=False
                )
            ),
        ):
            profile = detect_native_profile(_registry())
        assert profile is None

    def test_vendor_hint_returns_none(self):
        """Q7 negative: Star classifies NATIVE_PRINTER but carries no
        suggested_profile, so the fallback yields None, not a guess."""
        with patch(
            "claude_teletype.printing.discovery.discover_all",
            return_value=_discovery_with(
                UsbDeviceInfo(vendor_id=0x0519, product_id=0x0001)
            ),
        ):
            profile = detect_native_profile(_registry())
        assert profile is None

    def test_empty_discovery_returns_none(self):
        with patch(
            "claude_teletype.printing.discovery.discover_all",
            return_value=DiscoveryResult(),
        ):
            profile = detect_native_profile(_registry())
        assert profile is None

    def test_unknown_device_returns_none(self):
        with patch(
            "claude_teletype.printing.discovery.discover_all",
            return_value=_discovery_with(
                UsbDeviceInfo(vendor_id=0xDEAD, product_id=0xBEEF)
            ),
        ):
            profile = detect_native_profile(_registry())
        assert profile is None

    def test_unresolvable_suggestion_skipped(self):
        """A suggestion that is not a registry key is skipped, not raised:
        classify() returns profile.name, which can diverge from the
        catalog key for custom profiles."""
        registry = MagicMock()
        registry.match_vidpid.return_value = None  # falls to KNOWN_MODEL_PIDS
        registry.get.side_effect = ValueError("unknown profile")

        with patch(
            "claude_teletype.printing.discovery.discover_all",
            return_value=_discovery_with(
                UsbDeviceInfo(vendor_id=0x04B8, product_id=0x0046)
            ),
        ):
            profile = detect_native_profile(registry)
        assert profile is None
        registry.get.assert_called_once_with("escp2")

    def test_first_native_suggestion_wins_over_later_devices(self):
        """Scan order: bridges/unknowns are passed over; the first device
        with a real suggestion resolves."""
        with patch(
            "claude_teletype.printing.discovery.discover_all",
            return_value=_discovery_with(
                UsbDeviceInfo(
                    vendor_id=0x1A86, product_id=0x7523, printer_class=False
                ),  # CH340 bridge — skipped
                UsbDeviceInfo(vendor_id=0x0519, product_id=0x0001),  # Star hint — no suggestion
                UsbDeviceInfo(vendor_id=0x2730, product_id=0x2002),  # Citizen — native
            ),
        ):
            profile = detect_native_profile(_registry())
        assert profile is not None
        assert profile.name == "citizen-cts2000"
