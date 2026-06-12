"""Printer profiles: named bundles of ESC sequences and behavior.

Built-in profiles for Juki, Epson ESC/P, IBM PPDS, HP PCL, and generic.
Custom profiles loaded from TOML config [printer.profiles.*] tables.
USB auto-detection by VID:PID matching against profile registry.

Style capability fields (bold/italic/underline on/off) follow a documented
fallback chain consumed by the markdown renderer: italic falls back to
underline, bold falls back to underline, and underline falls back to plain
text when codes are empty. See ``resolve_style`` for the chain.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claude_teletype.printing.registry import ProfileRegistry


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

    # Inline style capabilities. Empty bytes = capability not supported;
    # the markdown renderer's fallback chain (italic -> underline -> plain,
    # bold -> underline -> plain) consults the empty/non-empty state.
    # Phase 22 will encode the actual byte values per printer family;
    # Phase 21 ships only the dataclass shape with empty defaults.
    bold_on: bytes = b""
    bold_off: bytes = b""
    italic_on: bytes = b""
    italic_off: bytes = b""
    underline_on: bytes = b""
    underline_off: bytes = b""

    # Newline strategy
    crlf: bool = False

    # Re-init after newline (Juki needs this for CUPS per-line jobs)
    reinit_on_newline: bool = False
    reinit_sequence: bytes = b""

    # End-of-response sequence — sent after each completed LLM response
    # (and on close if the response wasn't flushed cleanly). Empty for
    # printers that don't need a per-response separator. Receipt printers
    # use this for paper feed + cut so each response is its own receipt.
    end_of_response_sequence: bytes = b""

    # Form feed on close
    formfeed_on_close: bool = True

    # Skip per-character typewriter pacing for this printer. Daisywheel
    # impact printers benefit from the animation (and physically can't
    # outrun it anyway); thermal receipt and laser printers are line- or
    # job-buffered, so the artificial delay just adds latency with no
    # mechanical justification. Setting True forces zero-delay output for
    # both the receipt and the on-screen TUI mirror.
    instant_output: bool = False

    # USB auto-detection (optional)
    usb_vendor_id: int | None = None
    usb_product_id: int | None = None

    # Paper width in columns (for word wrap)
    columns: int = 80

    # Instant-mode write chunk size. Phase 26's instant-mode chunker
    # writes at this byte boundary to prevent buffer overruns on
    # impact printers (Juki/CH341 in particular). 256 is a safe default
    # for unknown hardware; receipt printers can safely go smaller and
    # USB-bulk printers can safely go larger.
    buffer_bytes: int = 256

    # Non-ASCII text encoding. When ``text_codec`` is non-empty, the
    # ProfilePrinterDriver lazily switches to that codec the first time a
    # non-ASCII character appears in the stream — sending
    # ``codepage_command`` once, then encoding subsequent non-ASCII chars
    # with ``text_codec`` and emitting them as raw bytes (bypassing the
    # ASCII decode path). Empty defaults preserve the original
    # ASCII-with-replace behavior for profiles that do not opt in.
    #
    # Example for Citizen CT-S2000 (Cyrillic via CP866):
    #   codepage_command=b"\x1bt\x11"  # ESC t 17 — select CP866 (Russian)
    #   text_codec="cp866"
    codepage_command: bytes = b""
    text_codec: str = ""

    # Per-character transliteration map applied BEFORE codec encoding.
    # Each (key, value) replaces the key char with the value string
    # whenever the key appears in the stream. Use this to handle:
    #   - Letters present in Unicode but absent from the printer's
    #     code page (e.g. Ukrainian "і" → Latin "i" on CP866; "ґ" → "г")
    #   - Typographic glyphs not in the code page (e.g. em-dash "—" → "--",
    #     ellipsis "…" → "...", curly quotes "" "" → straight quotes)
    # Values may be multi-character strings, including ASCII or other
    # Cyrillic chars that ARE in the active code page. Substitution runs
    # before _needs_codepage() so a chunk that becomes pure-ASCII after
    # substitution skips the codepage path entirely.
    text_fallback: dict[str, str] = field(default_factory=dict)

    # Capabilities that could NOT be verified from vendor documentation
    # and need a human with the real hardware (or the paper manual) to
    # confirm. Each entry is a short free-text note naming the unverified
    # capability and what would verify it. `claude-teletype diagnose`
    # renders these per profile so catalog gaps are visible instead of
    # silently absent (R022: never fabricate byte sequences — leave the
    # field empty and record the gap here).
    human_needed: tuple[str, ...] = ()


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
        # Daisywheel impact — bold via overstrike requires duplicate-strike per
        # char (breaks streaming pipeline) so bold stays empty. Italic NOT
        # SUPPORTED on the daisywheel hardware. Underline IS supported.
        underline_on=b"\x1b-\x01",  # ESC - 1
        underline_off=b"\x1b-\x00",  # ESC - 0
        crlf=True,
        reinit_on_newline=True,
        reinit_sequence=b"\x1b\x1e\x09\x1bQ",  # LINE_SPACING + FIXED_PITCH
        formfeed_on_close=True,
        usb_vendor_id=0x1A86,  # QinHeng Electronics (CH341 USB-to-printer bridge)
        usb_product_id=0x7584,  # Juki 6100 printer interface
        columns=80,
        buffer_bytes=64,  # CH341 USB-LPT bridge is byte-fragile — small chunks
    ),
    "juki-2200": PrinterProfile(
        name="juki-2200",
        description="Juki 2200 daisywheel typewriter (LPT/Centronics)",
        # Plain-ASCII typewriter: no init/reset ESC sequences. CR+LF newlines
        # are standard for parallel-interface typewriters. No form feed on
        # close — typewriters don't eject pages. The 2200 shares the CH341
        # USB-LPT adapter with the 6100 (same VID:PID), so VID:PID is left
        # unset to avoid hijacking auto-detect; pick this profile explicitly.
        # Plain-ASCII typewriter shares Juki 6100 underline support; bold via
        # overstrike not supported by streaming pipeline; italic NOT SUPPORTED.
        underline_on=b"\x1b-\x01",  # ESC - 1
        underline_off=b"\x1b-\x00",  # ESC - 0
        crlf=True,
        formfeed_on_close=False,
        columns=80,
        buffer_bytes=64,  # same CH341 adapter as 6100
    ),
    "escp": PrinterProfile(
        name="escp",
        description="Epson ESC/P dot matrix (FX/LQ/LX series)",
        init_sequence=b"\x1b@",  # ESC @ (initialize printer)
        reset_sequence=b"\x1b@",  # ESC @ (reset on close)
        line_spacing=b"\x1b\x32",  # ESC 2 (6 LPI)
        char_pitch=b"\x1bP",  # ESC P (10 CPI pica)
        bold_on=b"\x1bE",  # ESC E
        bold_off=b"\x1bF",  # ESC F
        italic_on=b"\x1b4",  # ESC 4
        italic_off=b"\x1b5",  # ESC 5
        underline_on=b"\x1b-\x01",  # ESC - 1
        underline_off=b"\x1b-\x00",  # ESC - 0
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
        bold_on=b"\x1bE",  # ESC E
        bold_off=b"\x1bF",  # ESC F
        italic_on=b"\x1b%G",  # ESC %G
        italic_off=b"\x1b%H",  # ESC %H
        underline_on=b"\x1b-\x01",  # ESC - 1
        underline_off=b"\x1b-\x00",  # ESC - 0
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
        bold_on=b"\x1b(s3B",  # ESC (s3B
        bold_off=b"\x1b(s0B",  # ESC (s0B
        italic_on=b"\x1b(s1S",  # ESC (s1S
        italic_off=b"\x1b(s0S",  # ESC (s0S
        underline_on=b"\x1b&dD",  # ESC &dD
        underline_off=b"\x1b&d@",  # ESC &d@
        crlf=False,
        formfeed_on_close=True,
        usb_vendor_id=0x03F0,  # HP Inc
        columns=80,
    ),
    "oki-3390": PrinterProfile(
        name="oki-3390",
        description="OKI Microline 3390 24-pin dot matrix (Epson FX-2 mode, USB)",
        # ML 3390 ships with selectable emulations (OKI native, IBM PPDS,
        # Epson FX-2). This profile assumes the printer's front-panel emulation
        # menu is set to Epson FX-2 — the most common modern factory default
        # and the closest match to the existing escp profile. If the printer
        # is set to IBM PPDS instead, use the ppds/ibm profile.
        init_sequence=b"\x1b@",  # ESC @ (Epson initialize)
        reset_sequence=b"\x1b@",  # ESC @ (reset on close)
        line_spacing=b"\x1b\x32",  # ESC 2 (6 LPI)
        char_pitch=b"\x1bP",  # ESC P (10 CPI pica)
        # Microline command set is a superset of Epson ESC/P. Bold and underline
        # are stable; italic on the 3390 uses an ESC! mode-bit composite that
        # varies by firmware revision — leave italic empty rather than fabricate.
        bold_on=b"\x1bE",  # ESC E (Epson FX-2 bold)
        bold_off=b"\x1bF",  # ESC F (Epson FX-2 bold off)
        underline_on=b"\x1b-\x01",  # ESC - 1
        underline_off=b"\x1b-\x00",  # ESC - 0
        crlf=False,
        formfeed_on_close=True,
        usb_vendor_id=0x06BC,  # OKI Data Corp
        # PID left unset: VID-only match auto-detects any OKI USB printer.
        # If you have multiple OKI devices and want narrower matching, add
        # the 3390's specific product ID once verified via `claude-teletype
        # diagnose` on the live device.
        columns=80,
    ),
    "citizen-cts2000": PrinterProfile(
        name="citizen-cts2000",
        description="Citizen CT-S2000 thermal receipt printer (ESC/POS, USB)",
        init_sequence=b"\x1b@",  # ESC @ — Initialize printer
        reset_sequence=b"\x1b@",  # ESC @ — re-init on close (cut handled per-response)
        # ESC/POS thermal receipt: bold = ESC E n (n is binary 1/0, NOT ASCII).
        # Italic NOT SUPPORTED on thermal receipt. Underline supported as ESC - n.
        bold_on=b"\x1bE\x01",  # ESC E 1 (emphasized on, binary 1)
        bold_off=b"\x1bE\x00",  # ESC E 0 (emphasized off, binary 0)
        underline_on=b"\x1b-\x01",  # ESC - 1
        underline_off=b"\x1b-\x00",  # ESC - 0
        # After each completed LLM response: feed 5 lines so the cut clears
        # the print head, then full-cut. The cut also fires on close if the
        # last response wasn't flushed cleanly (cancel/error mid-stream).
        end_of_response_sequence=b"\x1bd\x05\x1dV\x00",  # ESC d 5 + GS V 0
        crlf=False,                             # ESC/POS uses LF only
        formfeed_on_close=False,                # receipt printers ignore \f
        instant_output=True,                    # thermal: no per-char pacing
        # Live CT-S2000 units enumerate as 0x2730:0x2002 (USB Vendor Name
        # "CITIZEN", product string "Thermal Printer") — verified via ioreg.
        # The "official" Citizen Systems Japan VID 0x1d90 is reserved for a
        # different product line and doesn't apply to the CT-S series.
        usb_vendor_id=0x2730,
        usb_product_id=0x2002,
        columns=42,                             # Font A on 80mm thermal paper
        buffer_bytes=128,                       # 80mm receipt buffer is ~512B; modest chunks
        # Cyrillic / Russian markdown: switch to CP866 lazily on first
        # non-ASCII char. ESC t 17 selects code page 17 (CP866) on Citizen
        # ESC/POS firmware. Adjust the command byte if your specific unit
        # documents a different table number.
        codepage_command=b"\x1bt\x11",          # ESC t 17 — CP866 (Russian)
        text_codec="cp866",
        # CP866 has full Russian coverage but Ukrainian "і/І/ґ/Ґ" are
        # missing (CP866 carries ї/Ї/є/Є at 0xf2-0xf5, but not the four
        # listed below). Fall back to visually-close substitutes so
        # Ukrainian-tinged text prints legibly instead of "?". Also
        # transliterate common typographic glyphs Unicode introduces
        # (em-dash, ellipsis, curly quotes) since CP866 lacks them.
        text_fallback={
            # Ukrainian letters absent from CP866
            "і": "i", "І": "I",
            "ґ": "г", "Ґ": "Г",
            # Typographic glyphs absent from CP866 (also from CP1125)
            "—": "--", "–": "-",
            "…": "...",
            "“": '"', "”": '"',  # left/right double quote
            "‘": "'", "’": "'",  # left/right single quote
            "«": '"', "»": '"',
            "∞": "oo",
        },
    ),
}


def _load_catalog() -> dict[str, PrinterProfile]:
    """Merge every catalog module's PROFILES dict into one mapping.

    The catalog package imports PrinterProfile from THIS module at its
    module top, so the reverse import here MUST stay function-local —
    the same cycle-break idiom as detection.detect_native_profile.
    Importing the catalog at profiles.py module top would close the
    import cycle and crash at load time.
    """
    from claude_teletype.printing.catalog import epson

    merged: dict[str, PrinterProfile] = {}
    for module in (epson,):
        merged.update(module.PROFILES)
    return merged


# Catalog merge ordering constraint: this update() must run AFTER the
# BUILTIN_PROFILES literal above (the catalog extends it) and BEFORE the
# ibm/juki alias blocks below, so future alias entries built with
# dataclasses.replace can target catalog profiles as well as literal ones.
BUILTIN_PROFILES.update(_load_catalog())

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

    Style capability fields (bold_on/off, italic_on/off, underline_on/off)
    are hex-encoded byte strings — same convention as init/reset/line_spacing.
    buffer_bytes is a plain integer (count of bytes), NOT a hex string —
    distinct from usb_vendor_id and usb_product_id which ARE hex strings
    because they are USB identifiers, not byte counts.

    Returns an empty dict if no profiles section exists.
    """
    printer_section = raw_toml.get("printer", {})
    custom_profiles = printer_section.get("profiles", {})

    profiles: dict[str, PrinterProfile] = {}
    for name, data in custom_profiles.items():
        # Validate buffer_bytes: must be a positive int. Reject str (would
        # crash Phase 26 chunker arithmetic), bool (truthy ints that don't
        # represent real byte counts), and zero/negative (would cause infinite
        # loops or zero-byte writes downstream). Built-in profiles enforce
        # this same invariant via test_builtin_profiles_have_positive_buffer_bytes;
        # custom profiles need it more, since the input is foreign.
        buf = data.get("buffer_bytes", 256)
        if not isinstance(buf, int) or isinstance(buf, bool) or buf <= 0:
            raise ValueError(
                f"Profile {name!r}: buffer_bytes must be a positive integer, "
                f"got {buf!r}"
            )
        profiles[name] = PrinterProfile(
            name=name,
            description=data.get("description", ""),
            init_sequence=bytes.fromhex(data.get("init", "")),
            reset_sequence=bytes.fromhex(data.get("reset", "")),
            line_spacing=bytes.fromhex(data.get("line_spacing", "")),
            char_pitch=bytes.fromhex(data.get("char_pitch", "")),
            bold_on=bytes.fromhex(data.get("bold_on", "")),
            bold_off=bytes.fromhex(data.get("bold_off", "")),
            italic_on=bytes.fromhex(data.get("italic_on", "")),
            italic_off=bytes.fromhex(data.get("italic_off", "")),
            underline_on=bytes.fromhex(data.get("underline_on", "")),
            underline_off=bytes.fromhex(data.get("underline_off", "")),
            crlf=data.get("crlf", False),
            reinit_on_newline=data.get("reinit_on_newline", False),
            reinit_sequence=bytes.fromhex(data.get("reinit_sequence", "")),
            end_of_response_sequence=bytes.fromhex(
                data.get("end_of_response_sequence", "")
            ),
            formfeed_on_close=data.get("formfeed_on_close", True),
            instant_output=data.get("instant_output", False),
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
            buffer_bytes=buf,
            codepage_command=bytes.fromhex(data.get("codepage_command", "")),
            text_codec=data.get("text_codec", ""),
            text_fallback=dict(data.get("text_fallback", {})),
            human_needed=tuple(data.get("human_needed", [])),
        )
    return profiles


def resolve_style(
    profile: PrinterProfile,
    style: str,
) -> tuple[bytes, bytes]:
    """Return the (on_bytes, off_bytes) the renderer should emit for ``style``.

    Applies the documented fallback chain so the markdown renderer (Phase 23)
    can ask "what should I emit for italic?" without branching on profile
    capabilities itself. Empty-byte returns mean "emit plain text" — the
    renderer treats `(b"", b"")` as a no-op and just writes the text.

    Fallback chain:

    - ``italic`` -> italic codes if non-empty, else underline codes if
      non-empty, else ``(b"", b"")``. Italic typewriters are rare on
      impact printers; underline is the closest visual stand-in on Epson
      ESC/P, IBM PPDS, and similar families.
    - ``bold`` -> bold codes if non-empty, else underline codes if
      non-empty, else ``(b"", b"")``. Same reasoning: a printer without
      a bold sequence still has underline on most ESC/P-family hardware.
    - ``underline`` -> underline codes if non-empty, else ``(b"", b"")``.
      No further fallback — underline is the terminal node of the chain.

    A pair is "non-empty" when its ``_on`` byte string is non-empty. The
    ``_off`` companion travels with it — the function does NOT mix-and-
    match across capabilities, so the renderer can always trust that the
    returned ``off_bytes`` closes whatever the returned ``on_bytes``
    opened.

    Args:
        profile: The active ``PrinterProfile`` (built-in or custom).
        style: One of ``"bold"``, ``"italic"``, ``"underline"``.

    Returns:
        A ``(on_bytes, off_bytes)`` tuple. ``(b"", b"")`` means the
        renderer should emit plain text with no styling.

    Raises:
        ValueError: If ``style`` is not one of the three supported names.
    """
    if style == "italic":
        if profile.italic_on:
            return (profile.italic_on, profile.italic_off)
        if profile.underline_on:
            return (profile.underline_on, profile.underline_off)
        return (b"", b"")
    if style == "bold":
        if profile.bold_on:
            return (profile.bold_on, profile.bold_off)
        if profile.underline_on:
            return (profile.underline_on, profile.underline_off)
        return (b"", b"")
    if style == "underline":
        if profile.underline_on:
            return (profile.underline_on, profile.underline_off)
        return (b"", b"")
    raise ValueError(
        f"Unknown style: {style!r}. Expected 'bold', 'italic', or 'underline'."
    )
