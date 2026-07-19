"""HP family catalog profiles: PCL5 laser/inkjet machines.

Moved verbatim from profiles.py's BUILTIN_PROFILES literal (ARCH-03) —
bytes and citation comments travel unaltered (R022).
"""

from __future__ import annotations

from claude_teletype.printing.profiles import PrinterProfile

PROFILES: dict[str, PrinterProfile] = {
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
}
