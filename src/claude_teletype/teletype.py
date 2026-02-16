"""Raw teletype mode: keyboard to printer, character by character.

Supports two newline strategies:

  Generic (default)
      LF only.  Works on ESC/POS thermal printers, most USB printers.

  Juki  (--juki flag)
      Sends Juki 6100 init codes (RESET + LINE_SPACING + FIXED_PITCH)
      as a single USB bulk transfer so the adapter passes the complete
      ESC sequences to the parallel port without splitting them.
      Newline is CR+LF sent as one write — CR returns the carriage,
      LF scrolls the paper.
"""

import sys
import termios
import tty

from claude_teletype.printer import JukiPrinterDriver, PrinterDriver


def run_teletype(driver: PrinterDriver, juki: bool = False) -> None:
    """Run interactive teletype mode on a raw printer driver.

    Reads single characters from stdin and writes them directly to the
    printer.  Ctrl-C exits cleanly with a form feed.

    Args:
        driver: Raw backend (UsbPrinterDriver or FilePrinterDriver).
                Must NOT be wrapped in JukiPrinterDriver.
        juki:   When True, sends Juki 6100 init codes at startup and
                uses CR+LF for newlines.  When False, uses LF only.
    """
    if juki:
        init = (
            JukiPrinterDriver.RESET
            + JukiPrinterDriver.LINE_SPACING
            + JukiPrinterDriver.FIXED_PITCH
        )
        driver.write(init.decode("ascii"))  # single USB bulk transfer

    print("Teletype mode. Type to print. Ctrl-C to exit.", file=sys.stderr)

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            ch = sys.stdin.read(1)
            if not ch or ch == "\x03":
                break
            if ch == "\r" or ch == "\n":
                if juki:
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
        driver.write("\f")
        driver.close()
