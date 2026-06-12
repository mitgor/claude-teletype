"""Star family catalog profiles: Star line mode (R020).

Source (fetched and verified during S03 T04):

- "Dot Impact Printer STAR Command Specifications" Rev. 1.91:
  starmicronics.com/support/Mannualfolder/dot_star_cm_en.pdf
  "This specifications document describes the command specifications
  for the STAR MODE on dot impact printers."
  (cited below as "STAR Command Spec Rev. 1.91" with section/page).

SP500/SP700-class units DIP-switch-select between Star line mode and
ESC/POS emulation — a unit switched to ESC/POS prints garbage through
this profile (and vice versa). Check the DIP switches before blaming
the bytes.
"""

from __future__ import annotations

from claude_teletype.printing.profiles import PrinterProfile

PROFILES: dict[str, PrinterProfile] = {
    "star-line": PrinterProfile(
        name="star-line",
        description=(
            "Star dot impact in Star line mode (SP500/SP700 class) — "
            "DIP switches select Star mode vs ESC/POS; wrong mode prints "
            "garbage"
        ),
        init_sequence=b"\x1b@",  # ESC @ (1B 40) "Command initialization" — STAR Command Spec Rev. 1.91, §3-3-15 Others, p. 3-74, Star line mode
        reset_sequence=b"\x1b@",  # ESC @ "Command initialization" (reset on close) — same citation; DIPSW/memory-switch state is NOT re-read (p. 3-74)
        line_spacing=b"\x1bz\x01",  # ESC z 1 (1B 7A 01) "Set line feed to 1/6 inch" — STAR Command Spec Rev. 1.91, §3-3-4 Line Spacing, p. 3-19, Star line mode
        # char_pitch intentionally EMPTY (verified absence, not a gap):
        # Star line mode has no cpi-select command — §3-3-2 selects fonts
        # (7x9 / 5x9), and the spec documents no pica/elite/cpi escape.
        # Pitch follows the printer's font and memory-switch state.
        bold_on=b"\x1bE",  # ESC E (1B 45) "Select emphasized printing" — STAR Command Spec Rev. 1.91, §3-3-3 Print mode, p. 3-10, Star line mode
        bold_off=b"\x1bF",  # ESC F (1B 46) "Cancel emphasized printing" — STAR Command Spec Rev. 1.91, §3-3-3 Print mode, p. 3-10, Star line mode
        # italic intentionally EMPTY (verified absence): the Star line
        # mode spec documents no italic command anywhere — the §3-3-3
        # print modes are emphasized, underline, upperline, inversion,
        # expanded, rotated. The renderer falls back to underline.
        underline_on=b"\x1b-\x01",  # ESC - n, n=1 "Specifies underline" (1B 2D 01) — STAR Command Spec Rev. 1.91, §3-3-3 Print mode, p. 3-11, Star line mode
        underline_off=b"\x1b-\x00",  # ESC - n, n=0 "Cancels underline" (1B 2D 00) — same table, p. 3-11
        # LF (0A) "Line feed: after printing data in the line buffer,
        # paper is fed" (§3-3-4, p. 3-17). CR behavior is memory-switch
        # dependent ("Specifies the function according to the memory
        # switch value", same section) — bare LF is the deterministic
        # newline; CR+LF could double-feed depending on memory switches.
        crlf=False,
        # FF lives under §3-4 "Black Mark Related Commands" (p. 3-80) —
        # it feeds to the black mark, not a page eject. Receipt-class
        # media has no page concept; don't fire it on close.
        formfeed_on_close=False,
        # Star Micronics is the SOLE claimant of 0x0519 in the registry's
        # VID-only index (D007) — a class-7 Star device auto-suggests
        # star-line via registry.match_vidpid. No product_id: the pin is
        # vendor-wide on purpose.
        usb_vendor_id=0x0519,
        columns=80,  # default — real carriage width varies by model; see human_needed
        # Codepage (R024): ESC GS t n (1B 1D 74 n) "Select code page" —
        # STAR Command Spec Rev. 1.91, §3-3-1 Font style and character
        # set, p. 3-6: n=1 -> "CodePage437 (USA, Std. Europe)".
        codepage_command=b"\x1b\x1dt\x01",  # ESC GS t 1 — CodePage437 (STAR Command Spec Rev. 1.91, §3-3-1)
        text_codec="cp437",
        human_needed=(
            "end_of_response (feed + cut) left empty: cutter presence "
            "varies across Star dot impact models, and the spec's ESC d n "
            "sits under Black Mark Related Commands (§3-4, p. 3-79) — "
            "needs the model-specific spec sheet or real hardware to "
            "confirm a safe cut sequence.",
            "columns left at the default 80: the command spec covers "
            "multiple carriage widths (SP500/SP700 receipt units are far "
            "narrower) — needs the model spec sheet to pin the real "
            "Star-mode column count.",
        ),
    ),
}
