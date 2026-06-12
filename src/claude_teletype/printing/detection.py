"""Device classification: native printer vs bridge chip vs unknown (DET-02).

Discovery answers "what USB devices are present"; this module answers
"what is this device". It supersedes the conflated legacy auto-detect
path (retired from profiles.py), which mixed "found a device" with
"know what it is" by returning a bare ``PrinterProfile | None``.

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
    from claude_teletype.printing.registry import ProfileRegistry

@dataclass(frozen=True)
class BridgeChip:
    """Curated knowledge about one bridge-chip vendor.

    ``parallel_pids`` are products known to expose an IEEE-1284 parallel
    (printer) side; ``serial_pids`` are products known to be serial-only.
    A PID listed in neither set has unknown capability: it still
    classifies BRIDGE (the VID identifies the cable) but with
    ``serial_only=False`` because we cannot prove it lacks a parallel side.
    """

    note: str
    parallel_pids: frozenset[int]
    serial_pids: frozenset[int]


# Curated bridge-chip registry: vendor ID → chip family knowledge.
# Each entry carries its provenance so future edits can re-verify.
BRIDGE_CHIPS: dict[int, BridgeChip] = {
    # QinHeng/WCH — CH340/CH341 USB-LPT bridge family.
    # Provenance: project hardware notes (Juki 2200 runs on the 0x7584
    # "USB2.0-Print" bridge) + the-sz USB ID DB.
    # human_needed(0x5584): CH341 parallel-mode alt-setting behavior
    # (alt 0 unidirectional printer-class / alt 1 bidirectional /
    # alt 2 vendor raw) needs a real CH341 + `lsusb -v` to confirm.
    0x1A86: BridgeChip(
        note="QinHeng/WCH CH340/CH341 USB-LPT bridge",
        parallel_pids=frozenset({
            0x5584,  # CH341 parallel-mode
            0x7584,  # "USB2.0-Print" — the in-hand Juki bridge
        }),
        serial_pids=frozenset({
            0x7523,  # CH340 serial — the Arduino-clone chip
            0x5523,  # CH341 serial-mode
        }),
    ),
    # Prolific. Provenance: linux-hardware.org + devicehunt.
    0x067B: BridgeChip(
        note="Prolific USB bridge",
        parallel_pids=frozenset({
            0x2305,  # PL2305 IEEE-1284 parallel
        }),
        serial_pids=frozenset({
            0x2303,  # PL2303 serial
        }),
    ),
    # MosChip. Provenance: devicehunt.
    # LOW confidence on both PIDs — verify on hardware.
    0x9710: BridgeChip(
        note="MosChip USB-parallel bridge",
        parallel_pids=frozenset({
            0x7705,  # MCS7705 parallel — LOW confidence, verify on hardware
            0x7715,  # MCS7715 parallel+serial combo — LOW confidence
        }),
        serial_pids=frozenset(),
    ),
    # FTDI — no IEEE-1284 product exists; all listed PIDs are serial-only.
    # Provenance: usb.ids.
    0x0403: BridgeChip(
        note="FTDI USB-serial bridge",
        parallel_pids=frozenset(),
        serial_pids=frozenset({
            0x6001,  # FT232
            0x6010,  # FT2232
            0x6011,  # FT4232
        }),
    ),
}

# USB vendor IDs of known printer-bridge chips, mapped to a short
# human-readable transport note for the setup screen. Derived from
# BRIDGE_CHIPS; kept as a module-level dict so the existing patch target
# ``claude_teletype.printing.detection.BRIDGE_CHIP_VIDS`` and classify()'s
# lookup keep working.
BRIDGE_CHIP_VIDS: dict[int, str] = {
    vid: chip.note for vid, chip in BRIDGE_CHIPS.items()
}

# Vendors known to ship native USB printers. A hit classifies
# NATIVE_PRINTER with no suggested_profile: real printer, nothing to
# suggest — keeps the device out of the bridge/unknown buckets without
# guessing a command set. Star (star-line) and Lexmark (lexmark-forms)
# now carry registry VID pins that fire BEFORE this fallthrough, so for
# those two this table is only a backstop when the registry profile is
# overridden away; IBM stays suggestion-less on purpose (a VID on ppds
# would cascade into every replace(ppds) alias — D007).
# MEDIUM confidence — VIDs from usb.ids.
NATIVE_PRINTER_VENDOR_VIDS: dict[int, str] = {
    0x0519: "Star Micronics",
    0x043D: "Lexmark",
    0x04B3: "IBM",
}

# Specific (VID, PID) models pinned to a profile suggestion.
# HIGH confidence — IDs via the-sz USB ID DB. Both are ESC/P2 machines,
# pinned to the catalog's escp2 profile. The string must equal the
# catalog key EXACTLY — divergence makes the CLI fallback silently skip
# and the setup Select fall back to generic.
KNOWN_MODEL_PIDS: dict[tuple[int, int], str] = {
    (0x04B8, 0x0046): "escp2",  # Epson LX-350
    (0x04B8, 0x0047): "escp2",  # Epson LQ-350
}


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
    ``serial_only`` is True only for BRIDGE devices whose PID is a known
    serial-only product (no parallel printer side behind it).
    """

    kind: DeviceKind
    suggested_profile: str | None = None
    transport_note: str = ""
    serial_only: bool = False


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
        # serial_only is True only when the PID is a curated serial-only
        # product. An unlisted PID under a bridge VID has unknown
        # capability and stays serial_only=False — we cannot prove it
        # lacks a parallel side.
        chip = BRIDGE_CHIPS.get(dev.vendor_id)
        serial_only = (
            chip is not None
            and dev.product_id in chip.serial_pids
            and dev.product_id not in chip.parallel_pids
        )
        return Classification(
            kind=DeviceKind.BRIDGE,
            suggested_profile=None,
            transport_note=bridge_note,
            serial_only=serial_only,
        )

    profile = registry.match_vidpid(dev.vendor_id, dev.product_id)
    if profile is not None:
        return Classification(
            kind=DeviceKind.NATIVE_PRINTER,
            suggested_profile=profile.name,
        )

    # Native matrix (R010): the registry miss falls through to curated
    # model pins first (exact beats vendor-wide), then bare vendor hints.
    # Registry precedence above means a custom profile claiming the same
    # VID:PID still wins over these tables.
    model_suggestion = KNOWN_MODEL_PIDS.get((dev.vendor_id, dev.product_id))
    if model_suggestion is not None:
        return Classification(
            kind=DeviceKind.NATIVE_PRINTER,
            suggested_profile=model_suggestion,
        )

    if dev.vendor_id in NATIVE_PRINTER_VENDOR_VIDS:
        # Known printer vendor, no shipped profile: NATIVE_PRINTER with
        # no suggestion (dataclass defaults represent exactly this).
        return Classification(kind=DeviceKind.NATIVE_PRINTER)

    return Classification(kind=DeviceKind.UNKNOWN)


def detect_native_profile(registry: ProfileRegistry) -> PrinterProfile | None:
    """Bare-launch auto-detect fallback: first native suggestion's profile.

    Replaces the retired profiles auto-detect path (R010/R011). Every discovered device
    goes through ``classify()`` — the same seam the setup screen uses — so
    BRIDGE devices can never produce a profile (a CH341's VID identifies
    the cable, not the printer behind it), and a vendor-hint
    NATIVE_PRINTER with no ``suggested_profile`` yields nothing rather
    than a guess.

    Returns None when discovery finds nothing, finds only bridges or
    unknowns, or the suggestion does not resolve in the registry (custom
    profiles may carry a ``name`` that diverges from their catalog key).
    """
    # Function-local import: discovery imports this module at load time
    # (BRIDGE_CHIP_VIDS), so the reverse import must not run at module load.
    from claude_teletype.printing.discovery import discover_all

    result = discover_all()
    for dev in result.usb_devices:
        classification = classify(dev, registry)
        if (
            classification.kind is DeviceKind.NATIVE_PRINTER
            and classification.suggested_profile
        ):
            try:
                return registry.get(classification.suggested_profile)
            except ValueError:
                continue
    return None
