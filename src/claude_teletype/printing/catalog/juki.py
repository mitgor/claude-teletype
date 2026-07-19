"""Juki family catalog profiles: 6100/9100 and 2200 daisywheel machines.

Moved verbatim from profiles.py's BUILTIN_PROFILES literal (ARCH-03) —
bytes and citation comments travel unaltered (R022).
"""

from __future__ import annotations

import dataclasses

from claude_teletype.printing.profiles import PrinterProfile

PROFILES: dict[str, PrinterProfile] = {
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
}

# Backward-compat alias: "juki" was renamed to "juki-6100" — keep the old
# name working for existing config files and the deprecated --juki flag.
PROFILES["juki"] = dataclasses.replace(
    PROFILES["juki-6100"],
    name="juki",
    description="Juki 6100 (alias for juki-6100)",
)
