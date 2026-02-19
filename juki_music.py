#!/usr/bin/env python3
"""Play "We Will Rock You" on a Juki 6100 daisy wheel printer.

Uses the same USB bulk-transfer approach as claude-teletype to send
rapid carriage movement commands that make the printer's stepper motors
and hammer solenoid produce rhythmic sounds.

The Juki 6100 has three sound-producing mechanisms we exploit:
  - Carriage linear stepper motor (horizontal movement)
  - Paper feed rotary stepper motor (vertical movement)
  - Hammer solenoid (percussive strike)

"We Will Rock You" signature rhythm: STOMP-STOMP-CLAP (rest)
  Beat 1: bass hit (carriage slam)
  Beat 2: bass hit (carriage slam)
  Beat 3: snare/clap (hammer strikes)
  Beat 4: rest

Usage:
    python juki_music.py [--bpm 81] [--loops 16] [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

# ---------------------------------------------------------------------------
# USB printer discovery (mirrored from claude_teletype.printer)
# ---------------------------------------------------------------------------

USB_PRINTER_CLASS = 7


def find_usb_printer() -> tuple[Any, Any]:
    """Find and open a USB printer-class device, return (dev, ep_out)."""
    try:
        import usb.core
        import usb.util
    except ImportError:
        print("ERROR: pyusb not installed. Install with: pip install pyusb")
        sys.exit(1)

    try:
        devices = list(usb.core.find(find_all=True))
    except usb.core.NoBackendError:
        print("ERROR: libusb backend not found. Install with: brew install libusb")
        sys.exit(1)

    for dev in devices:
        for cfg in dev:
            for intf in cfg:
                if intf.bInterfaceClass != USB_PRINTER_CLASS:
                    continue

                # Detach kernel driver (best-effort)
                try:
                    if dev.is_kernel_driver_active(intf.bInterfaceNumber):
                        dev.detach_kernel_driver(intf.bInterfaceNumber)
                except Exception:
                    pass

                ep_out = usb.util.find_descriptor(
                    intf,
                    custom_match=lambda e: usb.util.endpoint_direction(
                        e.bEndpointAddress
                    )
                    == usb.util.ENDPOINT_OUT,
                )
                if ep_out is not None:
                    try:
                        dev.set_configuration()
                    except Exception:
                        pass
                    try:
                        name = dev.product or "Unknown"
                    except Exception:
                        name = "Unknown"
                    print(f"Found printer: {name} (0x{dev.idVendor:04x}:0x{dev.idProduct:04x})")
                    return dev, ep_out

    print("ERROR: No USB printer found.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Juki 6100 escape sequences (Diablo 630 compatible)
# ---------------------------------------------------------------------------

# Init / reset
ESC_RESET = b"\x1b\x1aI"  # ESC SUB I — full reset
ESC_LINE_SPACING = b"\x1b\x1e\x09"  # ESC RS 9 — 1/6" line spacing
ESC_FIXED_PITCH = b"\x1bQ"  # ESC Q — disable proportional

# Carriage movement
CR = b"\r"  # Carriage return (full sweep left)
BS = b"\x08"  # Backspace one character position
HT = b"\x09"  # Horizontal tab
ESC_BS = b"\x1b\x08"  # ESC BS — 1/120" micro-backspace
ESC_FWD = b"\x1b\x35"  # ESC 5 — forward print direction
ESC_BWD = b"\x1b\x36"  # ESC 6 — backward print direction

# Paper feed
LF = b"\n"  # Line feed (1/6" or 1/8" depending on setting)
ESC_REV_LF = b"\x1b\n"  # ESC LF — reverse line feed
ESC_HALF_FWD = b"\x1bU"  # ESC U — half line feed forward
ESC_HALF_REV = b"\x1bD"  # ESC D — half line feed reverse

# Graphics mode (finer steps)
ESC_GFX_ON = b"\x1b\x33"  # ESC 3 — graphics mode (1/60" h, 1/48" v)
ESC_GFX_OFF = b"\x1b\x34"  # ESC 4 — graphics mode off

# Bidirectional print
ESC_BIDI_ON = b"\x1b/"  # ESC / — enable bidirectional
ESC_BIDI_OFF = b"\x1b\\"  # ESC \ — disable bidirectional

# Bell (audible alarm ~0.5s)
BEL = b"\x07"

# Character spacing control
# ESC US n — set character spacing index to (n-1)/120 inch
def esc_char_spacing(n: int) -> bytes:
    """ESC US n — set character spacing index. n=1..126."""
    return b"\x1b\x1f" + bytes([n])


# Line spacing control
# ESC RS n — set line spacing index to (n-1)/48 inch
def esc_line_spacing(n: int) -> bytes:
    """ESC RS n — set line spacing index. n=1..126."""
    return b"\x1b\x1e" + bytes([n])


# ---------------------------------------------------------------------------
# Sound primitives
# ---------------------------------------------------------------------------


class JukiMusic:
    """Drive a Juki 6100 as a rhythm instrument."""

    def __init__(self, ep_out: Any, dry_run: bool = False) -> None:
        self.ep = ep_out
        self.dry_run = dry_run
        self._position = 0  # rough carriage position tracking (characters)

    def send(self, data: bytes) -> None:
        """Send raw bytes to printer (atomic write)."""
        if self.dry_run:
            # Show hex for debugging
            hexstr = data.hex(" ")
            printable = data.decode("ascii", errors="replace")
            print(f"  TX: [{hexstr}]  {printable!r}")
            return
        self.ep.write(data)

    def init_printer(self) -> None:
        """Initialize Juki with standard settings."""
        print("Initializing printer...")
        self.send(ESC_RESET + ESC_LINE_SPACING + ESC_FIXED_PITCH)
        time.sleep(1.0)  # let the printer reset

        # Disable bidirectional printing for predictable carriage behavior
        self.send(ESC_BIDI_OFF)
        time.sleep(0.1)

        # Park carriage at left margin
        self.send(CR)
        time.sleep(0.5)
        self._position = 0

    def stomp(self) -> None:
        """Bass drum: rapid carriage back-and-forth oscillation.

        Sends a burst of carriage movements to create a low thump.
        The linear stepper motor vibrates, producing a percussive bass sound.
        """
        # Short burst of rapid micro-movements
        # Alternate between forward spaces and backspaces
        # This makes the carriage motor oscillate quickly
        burst = b""
        for _ in range(6):
            burst += b" " + BS  # move right then back
        self.send(burst)

    def stomp_hard(self) -> None:
        """Heavier bass: carriage sweep + hammer hits for more impact."""
        # Tab forward then carriage-return back — big mechanical movement
        burst = b""
        for _ in range(4):
            burst += b" "
        for _ in range(4):
            burst += BS
        self.send(burst)

    def clap(self) -> None:
        """Snare/clap: rapid hammer strikes via printing characters.

        Print a burst of characters — each one fires the hammer solenoid
        against the daisy wheel, producing a sharp mechanical click.
        Then backspace to overprint (keeping position stable).
        """
        # Print characters to fire the hammer, then backspace over them
        # Using period '.' for light strikes, 'X' for heavy
        strike_pattern = b"..XX.." + (BS * 6)
        self.send(strike_pattern)

    def clap_loud(self) -> None:
        """Loud clap: more hammer strikes, heavier characters."""
        strike_pattern = b"XXXXXXXX" + (BS * 8)
        self.send(strike_pattern)

    def hihat(self) -> None:
        """Hi-hat: single light character print (subtle tick)."""
        self.send(b"." + BS)

    def bell(self) -> None:
        """Ring the printer's built-in bell (~0.5s tone)."""
        self.send(BEL)

    def paper_thump(self) -> None:
        """Paper feed motor thump: rapid half-line-feed oscillation."""
        self.send(ESC_HALF_FWD + ESC_HALF_REV)

    def carriage_return_slam(self) -> None:
        """Full carriage return — dramatic mechanical sweep sound.

        Moves carriage to a position first, then CRs back.
        The linear stepper accelerates across the full width.
        """
        # Move carriage out a bit first if we're at the left
        self.send(b"        ")  # 8 spaces to move carriage right
        time.sleep(0.05)
        self.send(CR)  # slam back

    def rest(self, duration: float) -> None:
        """Silent pause."""
        if self.dry_run:
            print(f"  ... rest {duration:.3f}s")
        time.sleep(duration)

    def advance_paper(self) -> None:
        """Advance paper one line to avoid overprinting the same spot."""
        self.send(CR + LF)
        time.sleep(0.15)
        # Re-init pitch/spacing after newline (Juki needs this)
        self.send(ESC_LINE_SPACING + ESC_FIXED_PITCH)

    def cleanup(self) -> None:
        """Return carriage and advance paper when done."""
        self.send(CR + LF + LF)
        time.sleep(0.2)


# ---------------------------------------------------------------------------
# "We Will Rock You" arrangement
# ---------------------------------------------------------------------------

def play_we_will_rock_you(music: JukiMusic, bpm: float = 81, loops: int = 16) -> None:
    """Play the iconic "We Will Rock You" stomp-stomp-clap pattern.

    Original tempo: ~81 BPM in common time.

    The pattern per measure (4/4 time):
      Beat 1:     STOMP  (bass — carriage movement)
      Beat 1.5:   (and)
      Beat 2:     STOMP  (bass — carriage movement)
      Beat 2.5:   (and)
      Beat 3:     CLAP   (snare — hammer strikes)
      Beat 3.5:   (and)
      Beat 4:     rest
      Beat 4.5:   (and)

    The stomps land on beats 1 and 2, the clap on beat 3.
    Beat 4 is a rest, creating the characteristic gap before the next measure.
    """
    beat_duration = 60.0 / bpm  # duration of one beat in seconds

    print(f"\n  We Will Rock You")
    print(f"  BPM: {bpm}, Beat: {beat_duration:.3f}s")
    print(f"  Pattern: STOMP - STOMP - CLAP - (rest)")
    print(f"  Loops: {loops}")
    print()

    # Small intro: two bell rings
    print("  [intro]")
    music.bell()
    music.rest(beat_duration)
    music.bell()
    music.rest(beat_duration * 2)

    lines_printed = 0

    for loop in range(loops):
        measure = loop + 1
        print(f"  [{measure:2d}]  BOOM  BOOM  CLAP  ...")

        # Beat 1: STOMP
        music.stomp()
        music.paper_thump()
        music.rest(beat_duration)

        # Beat 2: STOMP
        music.stomp()
        music.paper_thump()
        music.rest(beat_duration)

        # Beat 3: CLAP (hammer strikes)
        music.clap_loud()
        music.rest(beat_duration)

        # Beat 4: REST (the iconic pause)
        music.rest(beat_duration)

        # Every 4 measures, advance paper to avoid hammering the same spot
        if measure % 4 == 0:
            music.advance_paper()
            lines_printed += 1

    # Finale: big ending
    print(f"\n  [finale]")
    music.stomp_hard()
    music.rest(beat_duration * 0.5)
    music.stomp_hard()
    music.rest(beat_duration * 0.5)
    music.clap_loud()
    music.bell()
    music.rest(beat_duration * 2)

    music.cleanup()
    print("\n  Done!")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Play "We Will Rock You" on a Juki 6100 daisy wheel printer'
    )
    parser.add_argument(
        "--bpm",
        type=float,
        default=81,
        help="Tempo in beats per minute (default: 81, the original tempo)",
    )
    parser.add_argument(
        "--loops",
        type=int,
        default=16,
        help="Number of stomp-stomp-clap measures to play (default: 16)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands to stdout instead of sending to printer",
    )
    args = parser.parse_args()

    print('Juki 6100 — "We Will Rock You"')
    print("=" * 40)

    if args.dry_run:
        print("DRY RUN — no data sent to printer\n")
        ep_out = None
        dev = None
    else:
        dev, ep_out = find_usb_printer()

    music = JukiMusic(ep_out, dry_run=args.dry_run)

    try:
        music.init_printer()
        play_we_will_rock_you(music, bpm=args.bpm, loops=args.loops)
    except KeyboardInterrupt:
        print("\n\nInterrupted! Parking carriage...")
        music.send(CR)
        music.rest(0.3)
    finally:
        if dev is not None:
            import usb.util
            usb.util.dispose_resources(dev)
            print("USB resources released.")


if __name__ == "__main__":
    main()
