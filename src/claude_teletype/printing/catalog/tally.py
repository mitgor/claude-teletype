"""Tally / TallyGenicom family catalog profiles: emulation aliases.

Moved verbatim from profiles.py (ARCH-03) — comments travel unaltered
(R022). The R021 rationale comment for the Panasonic/Tally alias group
lives in catalog/panasonic.py; the same reasoning applies here. Aliases
derive from sibling catalog modules via explicit imports (epson.escp,
ibm.ppds); the replace(escp) alias nulls usb_vendor_id (D007).
"""

from __future__ import annotations

import dataclasses

from claude_teletype.printing.catalog import epson as _epson
from claude_teletype.printing.catalog import ibm as _ibm
from claude_teletype.printing.profiles import PrinterProfile

PROFILES: dict[str, PrinterProfile] = {}

PROFILES["tally-epson"] = dataclasses.replace(
    _epson.PROFILES["escp"],
    name="tally-epson",
    description=(
        "Tally / TallyGenicom dot matrix in Epson ESC/P emulation — the "
        "printer's emulation menu must match"
    ),
    usb_vendor_id=None,
)

PROFILES["tally-ibm"] = dataclasses.replace(
    _ibm.PROFILES["ppds"],
    name="tally-ibm",
    description=(
        "Tally / TallyGenicom dot matrix in IBM Proprinter emulation — "
        "the printer's emulation menu must match"
    ),
)
