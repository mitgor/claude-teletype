"""Device classification: native printer vs bridge chip vs unknown (DET-02).

Discovery answers "what USB devices are present"; this module answers
"what is this device". It supersedes the conflated ``auto_detect_profile``
path, which mixed "found a device" with "know what it is" by returning a
bare ``PrinterProfile | None``.

``classify()`` examines one already-enumerated device:

1. Bridge check FIRST — a known parallel/serial-to-USB bridge chip
   identifies the *cable*, not the printer behind it, so no native
   profile may be suggested from its VID:PID.
2. Registry match — a VID:PID known to the profile registry is a native
   printer with that profile suggested (advisory; the user confirms).
3. Otherwise the device is UNKNOWN.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from claude_teletype.printing.discovery import UsbDeviceInfo
    from claude_teletype.printing.profiles import PrinterProfile

# USB vendor IDs of known printer-bridge chips, mapped to a short
# human-readable transport note for the setup screen.
#
# Placeholder only: Phase 28 populates the real chip-VID data (e.g. the
# QinHeng CH340/CH341 family, currently pinned as ``usb_vendor_id`` on the
# juki-6100 profile). Keeping this empty preserves today's observable
# detection behavior — every currently-shipped profile still classifies
# NATIVE_PRINTER with the same suggestion auto-detect produced.
BRIDGE_CHIP_VIDS: dict[int, str] = {}


class DeviceKind(enum.Enum):
    """What kind of device a discovered USB device is."""

    NATIVE_PRINTER = "native"
    BRIDGE = "bridge"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Classification:
    """Immutable result of classifying one discovered USB device.

    ``suggested_profile`` is set only for NATIVE_PRINTER and is advisory:
    the setup screen offers it, the user confirms. ``transport_note``
    carries the bridge-chip note for BRIDGE devices ("" otherwise).
    """

    kind: DeviceKind
    suggested_profile: str | None = None
    transport_note: str = ""


class _RegistryLike(Protocol):
    """The slice of ProfileRegistry that classify() consumes (duck-typed)."""

    def match_vidpid(self, vid: int, pid: int) -> PrinterProfile | None: ...


def classify(dev: UsbDeviceInfo, registry: _RegistryLike) -> Classification:
    """Classify one discovered USB device as native printer, bridge, or unknown.

    The bridge-VID check runs FIRST: a bridge chip's identity says nothing
    about the printer behind it, so it must never receive a native-profile
    suggestion even if a profile pins that VID. The native suggestion comes
    from ``registry.match_vidpid`` (exact VID:PID beats VID-only, per the
    registry's index).
    """
    bridge_note = BRIDGE_CHIP_VIDS.get(dev.vendor_id)
    if bridge_note is not None:
        return Classification(
            kind=DeviceKind.BRIDGE,
            suggested_profile=None,
            transport_note=bridge_note,
        )

    profile = registry.match_vidpid(dev.vendor_id, dev.product_id)
    if profile is not None:
        return Classification(
            kind=DeviceKind.NATIVE_PRINTER,
            suggested_profile=profile.name,
        )

    return Classification(kind=DeviceKind.UNKNOWN)
