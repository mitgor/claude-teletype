"""Citizen family catalog profiles: CT-S2000 thermal receipt printer.

Moved verbatim from profiles.py's BUILTIN_PROFILES literal (ARCH-03) —
bytes and citation comments travel unaltered (R022).
"""

from __future__ import annotations

from claude_teletype.printing.profiles import PrinterProfile

PROFILES: dict[str, PrinterProfile] = {
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
