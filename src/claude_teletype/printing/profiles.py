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
}


def _load_catalog() -> dict[str, PrinterProfile]:
    """Merge every catalog module's PROFILES dict into one mapping.

    The catalog package imports PrinterProfile from THIS module at its
    module top, so the reverse import here MUST stay function-local —
    the same cycle-break idiom as detection.detect_native_profile.
    Importing the catalog at profiles.py module top would close the
    import cycle and crash at load time.

    Modules are auto-discovered via pkgutil (ARCH-03): adding a printer
    family is exactly one new catalog/<family>.py file — no edits here.
    Sorted iteration makes merge order deterministic; key collisions
    across catalog modules are a bug (the snapshot test pins the key set).
    """
    import importlib
    import pkgutil

    from claude_teletype.printing import catalog

    merged: dict[str, PrinterProfile] = {}
    for info in sorted(pkgutil.iter_modules(catalog.__path__), key=lambda i: i.name):
        module = importlib.import_module(
            f"claude_teletype.printing.catalog.{info.name}"
        )
        merged.update(module.PROFILES)
    return merged


# Catalog merge extends the generic-only literal; aliases live in their
# family catalog modules.
BUILTIN_PROFILES.update(_load_catalog())


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
