"""OKI family catalog profiles: native MICROLINE Standard (R019).

Source (fetched and verified during S03 research):

- "Microline 320/321 Turbo User's Guide" (P/N 59270107, revised March
  2001): ricelake.com/media/aytf5gxr/m_ml320-321_turbo_-user_guide.pdf
  Printer Control Codes chapter, "Oki Data MICROLINE Standard Commands"
  tables, pp. 106-107. Backup mirror:
  archive.org/details/oki-microline-ml-390-391-turbo-users-guide
  (cited below as "ML320/321 UG" with page numbers).

The native MICROLINE command set is NOT Epson-compatible — the same
bytes mean different things in native mode (ESC E toggles the paper-out
sensor, ML320/321 UG p. 107; underline is ESC C / ESC D, not ESC - n;
ESC - selects uni-directional printing). This profile is OPT-IN: the
printer's front-panel Emulation Mode menu must be set to "OKI DATA
MICROLINE Standard" (ML320/321 UG, Emulations p. 33 — the factory
setting is IBM Proprinter III, served by the oki-ml-ibm alias).
"""

from __future__ import annotations

from claude_teletype.printing.profiles import PrinterProfile

PROFILES: dict[str, PrinterProfile] = {
    "oki-microline-native": PrinterProfile(
        name="oki-microline-native",
        description=(
            "OKI MICROLINE native command set (ML320/321 Turbo, opt-in: "
            "front-panel Emulation Mode must be OKI DATA MICROLINE Standard)"
        ),
        # init/reset intentionally EMPTY (R022 — gap, not verified absence):
        # the native command table lists "Software I-Prime: ESC } NUL"
        # (27 125 0) and "Reset: Clear Print Buffer: CAN" (24) on
        # ML320/321 UG p. 107, but the User's Guide gives the names only —
        # no semantics. Whether I-Prime is safe as a session init/reset
        # (menu-default reload? buffer drop?) is documented in the
        # CD-only Microline Reference Manual (ML320/321 UG p. 101). See
        # human_needed below.
        line_spacing=b"\x1b6",  # ESC 6 (27 54) "Line Spacing / Set Spacing to 1/6 inch" — ML320/321 UG p. 106
        char_pitch=b"\x1e",  # RS (30) "Character Pitch / Select 10 cpi" — ML320/321 UG p. 106
        # NOTE: native bold is "Emphasized" ESC T / ESC I — native ESC E
        # is the Paper Out Sensor toggle (p. 107), NOT Epson bold.
        bold_on=b"\x1bT",  # ESC T (27 84) "Emphasized Printing On" — ML320/321 UG p. 106
        bold_off=b"\x1bI",  # ESC I (27 73) "Emphasized Printing Off" — ML320/321 UG p. 106
        italic_on=b"\x1b!/",  # ESC ! / (27 33 47) "Italic On" — ML320/321 UG p. 106
        italic_off=b"\x1b!*",  # ESC ! * (27 33 42) "Italic Off" — ML320/321 UG p. 106
        underline_on=b"\x1bC",  # ESC C (27 67) "Underline Printing On" — ML320/321 UG p. 107
        underline_off=b"\x1bD",  # ESC D (27 68) "Underline Printing Off" — ML320/321 UG p. 107
        # "Line Feed Commands / w/ Carriage Return: LF" (10) — ML320/321
        # UG p. 106: native LF executes the carriage return itself, so
        # bare-LF newlines are correct.
        crlf=False,
        formfeed_on_close=True,  # FF (12) "Form Feed" — ML320/321 UG p. 106
        # NO usb_vendor_id/usb_product_id: 0x06BC is VID-only-claimed by
        # oki-3390 (D007), and the ML320/321 Turbo is a parallel-era
        # machine — select this profile explicitly.
        columns=80,  # ML320 narrow carriage; ML321 (16" forms, UG p. 89) users override
        # codepage intentionally EMPTY (R024 gap): the native table
        # documents character-SET selection (ESC ! 0 Standard, ESC ! 1
        # Block Graphic, ESC ! 2 Line Graphics — p. 106) but no IBM-style
        # code-PAGE select command. See human_needed below.
        human_needed=(
            "init/reset left empty: the native command table lists "
            "Software I-Prime (ESC } NUL, p. 107) and Reset: Clear Print "
            "Buffer (CAN, p. 107) by name only — the User's Guide gives "
            "no semantics. Needs the CD-only Microline Reference Manual "
            "or real hardware to confirm I-Prime is safe as a session "
            "init/reset.",
            "codepage_command left empty: the native table documents "
            "character-set selection (ESC ! 0/1/2, p. 106) but no "
            "code-page select — needs the Microline Reference Manual to "
            "confirm whether a CP437-style code page is selectable in "
            "native mode.",
        ),
    ),
}
