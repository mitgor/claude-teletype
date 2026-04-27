"""Printer profiles: named bundles of ESC sequences and behavior.

Built-in profiles for Juki, Epson ESC/P, IBM PPDS, HP PCL, and generic.
Custom profiles loaded from TOML config [printer.profiles.*] tables.
USB auto-detection by VID:PID matching against profile registry.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass


@dataclass(frozen=True)
class PrinterProfile:
    """Named bundle of printer control sequences and behavior.

    All printer-specific differences live in dataclass fields, not in
    conditional code. Adding a new printer = adding a dict entry.
    """

    name: str
    description: str = ""

    # ESC sequences as raw bytes (empty = no-op)
    init_sequence: bytes = b""
    reset_sequence: bytes = b""
    line_spacing: bytes = b""
    char_pitch: bytes = b""

    # Newline strategy
    crlf: bool = False

    # Re-init after newline (Juki needs this for CUPS per-line jobs)
    reinit_on_newline: bool = False
    reinit_sequence: bytes = b""

    # Form feed on close
    formfeed_on_close: bool = True

    # USB auto-detection (optional)
    usb_vendor_id: int | None = None
    usb_product_id: int | None = None

    # Paper width in columns (for word wrap)
    columns: int = 80


BUILTIN_PROFILES: dict[str, PrinterProfile] = {
    "generic": PrinterProfile(
        name="generic",
        description="Generic printer, no ESC codes, LF-only newlines",
    ),
    "juki-6100": PrinterProfile(
        name="juki-6100",
        description="Juki 6100/9100 daisywheel impact printer",
        init_sequence=b"\x1b\x1aI",  # ESC SUB I (full reset)
        line_spacing=b"\x1b\x1e\x09",  # ESC RS 9 (1/6" spacing)
        char_pitch=b"\x1bQ",  # ESC Q (disable proportional)
        crlf=True,
        reinit_on_newline=True,
        reinit_sequence=b"\x1b\x1e\x09\x1bQ",  # LINE_SPACING + FIXED_PITCH
        formfeed_on_close=True,
        usb_vendor_id=0x1A86,  # QinHeng Electronics (CH341 USB-to-printer bridge)
        usb_product_id=0x7584,  # Juki 6100 printer interface
        columns=80,
    ),
    "juki-2200": PrinterProfile(
        name="juki-2200",
        description="Juki 2200 daisywheel typewriter (LPT/Centronics)",
        # Plain-ASCII typewriter: no init/reset ESC sequences. CR+LF newlines
        # are standard for parallel-interface typewriters. No form feed on
        # close — typewriters don't eject pages. The 2200 shares the CH341
        # USB-LPT adapter with the 6100 (same VID:PID), so VID:PID is left
        # unset to avoid hijacking auto-detect; pick this profile explicitly.
        crlf=True,
        formfeed_on_close=False,
        columns=80,
    ),
    "escp": PrinterProfile(
        name="escp",
        description="Epson ESC/P dot matrix (FX/LQ/LX series)",
        init_sequence=b"\x1b@",  # ESC @ (initialize printer)
        reset_sequence=b"\x1b@",  # ESC @ (reset on close)
        line_spacing=b"\x1b\x32",  # ESC 2 (6 LPI)
        char_pitch=b"\x1bP",  # ESC P (10 CPI pica)
        crlf=False,
        formfeed_on_close=True,
        usb_vendor_id=0x04B8,  # Seiko Epson Corp
        columns=80,
    ),
    "ppds": PrinterProfile(
        name="ppds",
        description="IBM PPDS (Proprinter compatible)",
        init_sequence=b"\x1b@",  # ESC @ (initialize)
        reset_sequence=b"\x1b@",  # ESC @ (reset)
        line_spacing=b"\x1b\x32",  # ESC 2 (6 LPI)
        char_pitch=b"\x12",  # DC2 (10 CPI default)
        crlf=False,
        formfeed_on_close=True,
        columns=80,
    ),
    "pcl": PrinterProfile(
        name="pcl",
        description="HP PCL5 (LaserJet/DeskJet/OfficeJet)",
        init_sequence=b"\x1bE",  # ESC E (reset)
        reset_sequence=b"\x1bE",  # ESC E (reset)
        line_spacing=b"\x1b&l6D",  # 6 LPI
        char_pitch=b"\x1b(s10H",  # 10 CPI
        crlf=False,
        formfeed_on_close=True,
        usb_vendor_id=0x03F0,  # HP Inc
        columns=80,
    ),
}

# IBM alias: same ESC sequences as PPDS, brand name users recognize
BUILTIN_PROFILES["ibm"] = dataclasses.replace(
    BUILTIN_PROFILES["ppds"],
    name="ibm",
    description="IBM PPDS (alias for ppds profile)",
)

# Backward-compat alias: "juki" was renamed to "juki-6100" — keep the old
# name working for existing config files and the deprecated --juki flag.
BUILTIN_PROFILES["juki"] = dataclasses.replace(
    BUILTIN_PROFILES["juki-6100"],
    name="juki",
    description="Juki 6100 (alias for juki-6100)",
)


def get_profile(name: str) -> PrinterProfile:
    """Look up a printer profile by name (case-insensitive).

    "ibm" is an alias for "ppds" — both resolve to the IBM PPDS
    (Proprinter compatible) profile with identical ESC sequences.

    Raises ValueError if the profile name is not found, listing
    all available profile names.
    """
    key = name.lower().strip()
    if key not in BUILTIN_PROFILES:
        available = ", ".join(sorted(BUILTIN_PROFILES))
        raise ValueError(
            f"Unknown printer profile: {name!r}. Available: {available}"
        )
    return BUILTIN_PROFILES[key]


def load_custom_profiles(raw_toml: dict) -> dict[str, PrinterProfile]:
    """Parse custom profiles from TOML [printer.profiles.*] tables.

    Hex-encoded strings are converted to bytes via bytes.fromhex().
    USB VID/PID are parsed as hex strings (e.g., "04b8" -> 0x04B8).
    Missing optional fields get defaults (empty bytes, False, etc.).

    Returns an empty dict if no profiles section exists.
    """
    printer_section = raw_toml.get("printer", {})
    custom_profiles = printer_section.get("profiles", {})

    profiles: dict[str, PrinterProfile] = {}
    for name, data in custom_profiles.items():
        profiles[name] = PrinterProfile(
            name=name,
            description=data.get("description", ""),
            init_sequence=bytes.fromhex(data.get("init", "")),
            reset_sequence=bytes.fromhex(data.get("reset", "")),
            line_spacing=bytes.fromhex(data.get("line_spacing", "")),
            char_pitch=bytes.fromhex(data.get("char_pitch", "")),
            crlf=data.get("crlf", False),
            reinit_on_newline=data.get("reinit_on_newline", False),
            reinit_sequence=bytes.fromhex(data.get("reinit_sequence", "")),
            formfeed_on_close=data.get("formfeed_on_close", True),
            usb_vendor_id=(
                int(data["usb_vendor_id"], 16)
                if "usb_vendor_id" in data
                else None
            ),
            usb_product_id=(
                int(data["usb_product_id"], 16)
                if "usb_product_id" in data
                else None
            ),
            columns=data.get("columns", 80),
        )
    return profiles


USB_PRINTER_CLASS = 7


def auto_detect_profile(
    extra_profiles: dict[str, PrinterProfile] | None = None,
) -> PrinterProfile | None:
    """Match a connected USB printer to a profile's VID:PID.

    Enumerates USB devices via pyusb, filters to printer class
    (interface class 7), and matches VID:PID against built-in
    profiles plus optional extra_profiles.

    Returns the matching profile, or None if:
    - pyusb is not installed (ImportError)
    - No USB backend is available (NoBackendError)
    - No connected printer matches any profile

    Exact VID+PID match takes priority over VID-only match.
    """
    try:
        import usb.core  # type: ignore[import-untyped]
    except ImportError:
        return None

    try:
        devices = list(usb.core.find(find_all=True))
    except Exception:
        return None

    # Merge built-in and extra profiles
    all_profiles = dict(BUILTIN_PROFILES)
    if extra_profiles:
        all_profiles.update(extra_profiles)

    # Build lookup maps for VID:PID matching
    exact_map: dict[tuple[int, int], PrinterProfile] = {}
    vid_only_map: dict[int, PrinterProfile] = {}
    for profile in all_profiles.values():
        if profile.usb_vendor_id is not None:
            if profile.usb_product_id is not None:
                exact_map[(profile.usb_vendor_id, profile.usb_product_id)] = profile
            else:
                vid_only_map[profile.usb_vendor_id] = profile

    for dev in devices:
        # Filter to USB printer class (interface class 7)
        is_printer = False
        for cfg in dev:
            for intf in cfg:
                if intf.bInterfaceClass == USB_PRINTER_CLASS:
                    is_printer = True
                    break
            if is_printer:
                break
        if not is_printer:
            continue

        vid, pid = dev.idVendor, dev.idProduct

        # Exact VID+PID match (highest priority)
        if (vid, pid) in exact_map:
            return exact_map[(vid, pid)]

        # VID-only match (profile has no PID = match any product from that vendor)
        if vid in vid_only_map:
            return vid_only_map[vid]

    return None
