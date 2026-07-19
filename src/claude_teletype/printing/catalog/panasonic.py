"""Panasonic family catalog profiles: KX-P emulation aliases.

Moved verbatim from profiles.py (ARCH-03) — comments travel unaltered
(R022). Aliases derive from sibling catalog modules via explicit imports
(epson.escp, ibm.ppds).
"""

from __future__ import annotations

import dataclasses

from claude_teletype.printing.catalog import epson as _epson
from claude_teletype.printing.catalog import ibm as _ibm
from claude_teletype.printing.profiles import PrinterProfile

PROFILES: dict[str, PrinterProfile] = {}

# Panasonic KX-P / Tally emulation aliases (R021). The KX-P dot matrix
# line ships both Epson ESC/P and IBM Proprinter emulations selectable
# from the printer's own setup menu / DIP switches; Tally (later
# TallyGenicom) dot matrix machines likewise offer Epson and IBM modes.
# Each alias carries NO new bytes — it states which emulation the
# printer must be switched to. Both replace(escp)-derived aliases MUST
# null usb_vendor_id: inheriting Epson's 0x04B8 would log a registry
# VID collision and steal escp's auto-detect slot (D007). replace(ppds)
# aliases inherit None (ppds is unpinned) — nothing to null.
PROFILES["panasonic-kxp-epson"] = dataclasses.replace(
    _epson.PROFILES["escp"],
    name="panasonic-kxp-epson",
    description=(
        "Panasonic KX-P dot matrix in Epson ESC/P emulation — the "
        "printer's setup menu / DIP emulation setting must match"
    ),
    usb_vendor_id=None,
)

PROFILES["panasonic-kxp-ibm"] = dataclasses.replace(
    _ibm.PROFILES["ppds"],
    name="panasonic-kxp-ibm",
    description=(
        "Panasonic KX-P dot matrix in IBM Proprinter emulation — the "
        "printer's setup menu / DIP emulation setting must match"
    ),
)
