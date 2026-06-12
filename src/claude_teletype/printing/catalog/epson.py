"""Epson family catalog profiles: ESC/P2 (R015).

Sources (both fetched and verified during S03 research):

- "ESC/P2 command summary" — Epson EPL-5800 Reference Guide, Appendix
  ESC/P2 commands: support2.epson.net/manuals/english/page/epl_5800/ref_g/APCOM_3.HTM
  (cited below as "ESC/P2 command summary")
- "Epson ESC/P Reference Manual" (escp2ref.pdf):
  files.support.epson.com/pdf/general/escp2ref.pdf
  (cited below as "ESC/P Reference Manual" with page numbers)
"""

from __future__ import annotations

from claude_teletype.printing.profiles import PrinterProfile

PROFILES: dict[str, PrinterProfile] = {
    "escp2": PrinterProfile(
        name="escp2",
        description="Epson ESC/P2 24/48-pin dot matrix (LQ series, Stylus)",
        # Control codes verified IDENTICAL to the escp profile against the
        # Epson ESC/P2 command summary — ESC/P2 is a superset of ESC/P for
        # these commands, so the bytes match field-for-field.
        init_sequence=b"\x1b@",  # ESC @ "Initialize printer" — ESC/P2 command summary, ESC/P2 mode
        reset_sequence=b"\x1b@",  # ESC @ "Initialize printer" (reset on close) — ESC/P2 command summary, ESC/P2 mode
        line_spacing=b"\x1b\x32",  # ESC 2 "Select 1/6-inch line spacing" — ESC/P2 command summary, ESC/P2 mode
        char_pitch=b"\x1bP",  # ESC P "Select 10 cpi" — ESC/P2 command summary, ESC/P2 mode
        bold_on=b"\x1bE",  # ESC E "Select bold font" — ESC/P2 command summary, ESC/P2 mode
        bold_off=b"\x1bF",  # ESC F "Cancel bold font" — ESC/P2 command summary, ESC/P2 mode
        italic_on=b"\x1b4",  # ESC 4 "Select italic font" — ESC/P2 command summary, ESC/P2 mode
        italic_off=b"\x1b5",  # ESC 5 "Cancel italic font" — ESC/P2 command summary, ESC/P2 mode
        underline_on=b"\x1b-\x01",  # ESC - 1 "Turn underline on" — ESC/P2 command summary, ESC/P2 mode
        underline_off=b"\x1b-\x00",  # ESC - 0 "Turn underline off" — ESC/P2 command summary, ESC/P2 mode
        crlf=False,  # ESC/P2 uses LF-only newlines (same as escp)
        formfeed_on_close=True,
        # NO usb_vendor_id/usb_product_id: 0x04B8 is VID-only-claimed by
        # the escp profile (decision D007); the LX-350/LQ-350 ESC/P2
        # machines route here via detection.KNOWN_MODEL_PIDS instead.
        columns=80,
        # Codepage (R024): ESC t n "Select character table" — ESC/P
        # Reference Manual p. C-76, ESC/P2 mode. n = 1 selects character
        # table 1, whose DEFAULT registered assignment is PC437 (default
        # table: 0=Italic, 1=PC437, 2=user-defined, 3=PC437; same page).
        # Alternative: explicitly assign PC437 to active table 1 first
        # with ESC ( t 3 0 n dd — "ESC ( t 3 0 1 1 0 assigns the PC437
        # (US) table to active Table 1" (ESC/P Reference Manual p. R-16);
        # not sent here because the power-on default already maps table 1
        # to PC437.
        codepage_command=b"\x1bt\x01",  # ESC t 1 — select table 1 = PC437 (ESC/P Reference Manual p. C-76)
        text_codec="cp437",
    ),
}
