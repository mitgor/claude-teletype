"""IBM family catalog profiles: PPDS (Proprinter compatible) + aliases.

Moved verbatim from profiles.py's BUILTIN_PROFILES literal (ARCH-03) —
bytes and citation comments travel unaltered (R022).
"""

from __future__ import annotations

import dataclasses

from claude_teletype.printing.profiles import PrinterProfile

PROFILES: dict[str, PrinterProfile] = {
    "ppds": PrinterProfile(
        name="ppds",
        description="IBM PPDS (Proprinter compatible)",
        # init/reset intentionally EMPTY (verified absence, not a gap):
        # the IBM ProPrinter command set documents NO initialize/reset
        # escape. The previous `ESC @` here was uncited Epson syntax —
        # the ProPrinter XL24 Quick Reference (PSi PP 40x/80x
        # Programmer's Guide, Appendix D) lists ESC @ only in its
        # ESC/P2 table (Table 9, graphics-mode note), never in the
        # ProPrinter command tables (Tables 2-7). Proprinters power up
        # in their default state; no software init is required. See
        # human_needed for the open ESC [ K question on 4019-class PPDS.
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
        # Code Page Switching: ESC [ T n1 n2 NUL NUL P1 P2 with n1=4,
        # n2=0 and the code-page number in P1 P2, most significant byte
        # first (1*256 + 181 = 437). Verbatim from the ProPrinter XL24
        # Quick Reference, Table 7 "Character Set Selection" (quick-ref
        # footer p. [4], PDF p. 13): "P1 P2 / 1 181 : CP 437 U.S.A.".
        codepage_command=b"\x1b[T\x04\x00\x00\x00\x01\xb5",
        text_codec="cp437",
        human_needed=(
            "init/reset left empty: the ProPrinter XL24 guide documents "
            "no initialize/reset command (ESC @ is Epson/ESC-P2 syntax). "
            "Later IBM 4019/4029-class PPDS devices may accept "
            "ESC [ K (Set Initial Conditions) — needs a 4019 PPDS "
            "technical reference or real hardware to confirm.",
        ),
    ),
}

# IBM alias: same ESC sequences as PPDS, brand name users recognize
PROFILES["ibm"] = dataclasses.replace(
    PROFILES["ppds"],
    name="ibm",
    description="IBM PPDS (alias for ppds profile)",
)

# Lexmark Forms Printers (23xx/24xx/25xx) implement IBM PPDS — same byte
# sequences as ppds, with the Lexmark USB vendor id pinned so S02's bare
# "Lexmark" vendor hint upgrades to a real suggestion (R010). 0x043D has
# no other claimant in the registry's VID-only index (D007); ppds itself
# stays unpinned, and IBM's 0x04B3 is pinned NOWHERE — a VID on ppds
# would cascade into every replace(ppds) alias and collide (D007).
PROFILES["lexmark-forms"] = dataclasses.replace(
    PROFILES["ppds"],
    name="lexmark-forms",
    description=(
        "Lexmark Forms Printer (23xx/24xx/25xx) — IBM PPDS command set"
    ),
    usb_vendor_id=0x043D,  # Lexmark International
)
