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

The oki-3390 profile and the oki-ml-ibm/oki-ml-epson emulation aliases
moved here verbatim from profiles.py (ARCH-03) — bytes and citation
comments travel unaltered (R022). The aliases derive from sibling
catalog modules via explicit imports (ibm.ppds, epson.escp).
"""

from __future__ import annotations

import dataclasses

from claude_teletype.printing.catalog import epson as _epson
from claude_teletype.printing.catalog import ibm as _ibm
from claude_teletype.printing.profiles import PrinterProfile

PROFILES: dict[str, PrinterProfile] = {
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

# OKI MICROLINE 320/321 Turbo emulation aliases (R018). The machine ships
# three emulations — "Epson FX (ESC/P)", "IBM Proprinter III (PPSII) —
# factory setting", "OKI DATA MICROLINE Standard" (ML320/321 Turbo User's
# Guide, Emulations p. 33) — so the IBM and Epson modes map byte-for-byte
# onto the existing ppds/escp profiles. Neither alias pins a USB id:
# 0x06BC is VID-only-claimed by oki-3390 (D007), and the ML320/321 is a
# parallel-port-era machine. The native third emulation is the catalog's
# opt-in oki-microline-native profile.
PROFILES["oki-ml-ibm"] = dataclasses.replace(
    _ibm.PROFILES["ppds"],
    name="oki-ml-ibm",
    description=(
        "OKI MICROLINE 320/321 Turbo in IBM Proprinter III emulation "
        "(the factory setting per the OKI User's Guide p. 33) — ppds bytes"
    ),
)

# oki-ml-epson MUST null the usb_vendor_id inherited from escp: leaving
# Epson's 0x04B8 in place would log a registry VID collision AND steal
# escp's VID-only auto-detect slot (last registered wins — D007).
PROFILES["oki-ml-epson"] = dataclasses.replace(
    _epson.PROFILES["escp"],
    name="oki-ml-epson",
    description="MICROLINE in Epson FX mode",
    usb_vendor_id=None,
)
