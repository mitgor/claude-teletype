"""Raw teletype mode: keyboard to printer, character by character.

Supports profile-driven newline strategies and init codes:

  Generic (default / no profile)
      LF only.  Works on ESC/POS thermal printers, most USB printers.

  Profile-driven (e.g., --printer juki)
      Sends the profile's init_sequence + line_spacing + char_pitch
      as a single USB bulk transfer so the adapter passes the complete
      ESC sequences to the parallel port without splitting them.
      Uses profile.crlf for newline strategy (CR+LF vs LF-only).
"""

from __future__ import annotations

import sys
import termios
import tty

from claude_teletype.printer import PrinterDriver
from claude_teletype.profiles import PrinterProfile


def run_teletype(driver: PrinterDriver, profile: PrinterProfile | None = None) -> None:
    """Run interactive teletype mode on a raw printer driver.

    Reads single characters from stdin and writes them directly to the
    printer.  Ctrl-C exits cleanly with a form feed.

    Args:
        driver: Raw backend (UsbPrinterDriver or FilePrinterDriver).
                Must NOT be wrapped in ProfilePrinterDriver.
        profile: When provided, sends init codes at startup and
                 uses profile's newline strategy.  When None, uses
                 LF only (generic behavior).
    """
    if profile is not None:
        init_data = (
            profile.init_sequence
            + profile.line_spacing
            + profile.char_pitch
        )
        if init_data:
            driver.write(init_data.decode("ascii"))  # single USB bulk transfer

    print("Teletype mode. Type to print. Ctrl-C to exit.", file=sys.stderr)

    use_crlf = profile is not None and profile.crlf

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            ch = sys.stdin.read(1)
            if not ch or ch == "\x03":
                break
            if ch == "\r" or ch == "\n":
                if use_crlf:
                    driver.write("\r\n")  # CR+LF as single transfer
                else:
                    driver.write("\n")
                sys.stderr.write("\n")
                sys.stderr.flush()
            else:
                driver.write(ch)
                sys.stderr.write(ch)
                sys.stderr.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        if profile is not None and profile.formfeed_on_close:
            driver.write("\f")
        elif profile is None:
            driver.write("\f")  # Always formfeed for generic mode (original behavior)
        if profile is not None and profile.reset_sequence:
            for b in profile.reset_sequence:
                driver.write(chr(b))
        driver.close()
