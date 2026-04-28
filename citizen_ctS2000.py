#!/usr/bin/env python3
"""Citizen CT-S2000 thermal receipt printer test.

Sends a structured ESC/POS test print to a Citizen CT-S2000 USB receipt
printer to verify connectivity, character set, formatting commands, line
feed, and paper cut.

Unlike the Juki probe (juki2200.py) which fights a Centronics-bridge
adapter, the CT-S2000 is a proper USB Printer Class device that speaks
ESC/POS natively. The only macOS gotcha is the same one as every other
USB printer: the AppleUSBPrinter kext / CUPS USB backend will claim the
device, so kernel-driver detach is best-effort before claim.

This script is line-based: each text line is sent as one USB bulk
transfer (text + LF). Receipt printers buffer whole lines internally
and print them when an LF arrives — no per-byte handshake is needed,
unlike daisywheel impact printers.

Default Citizen Systems Japan vendor ID is 0x1d90. Override via --vid /
--pid if your unit enumerates differently (some OEM-rebadged units use
a different VID). Use the macOS `ioreg -p IOUSB -l | grep -i citizen`
or `lsusb` on Linux to confirm.

Usage:
    uv run python citizen_ctS2000.py
    uv run python citizen_ctS2000.py --vid 1d90 --pid 2070
    uv run python citizen_ctS2000.py --no-cut       # skip paper cut at end
    uv run python citizen_ctS2000.py --feed-only    # smallest possible test
"""
from __future__ import annotations

import argparse
import sys
import time

try:
    import usb.core
    import usb.util
except ImportError:
    print("pyusb is required: uv sync --extra usb (or pip install pyusb)", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# ESC/POS command set (Citizen CT-S2000 supports the standard Epson subset)
# ---------------------------------------------------------------------------

ESC = b"\x1b"
GS = b"\x1d"
LF = b"\n"

INIT = ESC + b"@"                           # ESC @ — initialize printer
ALIGN_LEFT = ESC + b"a\x00"
ALIGN_CENTER = ESC + b"a\x01"
ALIGN_RIGHT = ESC + b"a\x02"
BOLD_ON = ESC + b"E\x01"
BOLD_OFF = ESC + b"E\x00"
UNDERLINE_ON = ESC + b"-\x01"
UNDERLINE_OFF = ESC + b"-\x00"
DOUBLE_SIZE = GS + b"!\x11"                 # GS ! 0x11 — double width + double height
NORMAL_SIZE = GS + b"!\x00"
FEED_3_LINES = ESC + b"d\x03"               # ESC d 3 — print and feed 3 lines
FEED_5_LINES = ESC + b"d\x05"
FULL_CUT = GS + b"V\x00"                    # GS V 0 — full cut (auto-cutter)
PARTIAL_CUT = GS + b"V\x01"                 # GS V 1 — partial cut (leaves a tab)

USB_PRINTER_CLASS = 7

# Citizen Systems Japan vendor ID (used across the CT-S series).
# Some rebadged OEM units use a different VID — override via --vid/--pid.
DEFAULT_VID = 0x1D90


# ---------------------------------------------------------------------------
# Test payload — list of (label, bytes) pairs sent line-by-line as separate
# USB bulk transfers. Each text line ends with LF so the printer flushes
# its line buffer before the next transfer arrives.
# ---------------------------------------------------------------------------

def build_test_payload() -> list[tuple[str, bytes]]:
    """Construct the structured test print as discrete line transfers."""
    return [
        ("init",                 INIT),
        ("align center + bold",  ALIGN_CENTER + BOLD_ON),
        ("header line",          b"CITIZEN CT-S2000 TEST" + LF),
        ("bold off",             BOLD_OFF),
        ("separator",            b"========================================" + LF),
        ("align left",           ALIGN_LEFT),
        ("body line 1",          b"Hello from claude-teletype." + LF),
        ("body line 2",          b"This is a line-based ESC/POS test." + LF),
        ("body line 3",          b"42 columns at 10cpi (Font A) ........X" + LF),
        ("blank line",           LF),
        ("ascii print test",     b"ASCII: !\"#$%&'()*+,-./0123456789:;<=>?" + LF),
        ("ascii cont.",          b"@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abc" + LF),
        ("blank line",           LF),
        ("bold demo on",         BOLD_ON),
        ("bold demo line",       b"BOLD TEXT" + LF),
        ("bold demo off",        BOLD_OFF),
        ("underline demo on",    UNDERLINE_ON),
        ("underline demo line",  b"underlined text" + LF),
        ("underline demo off",   UNDERLINE_OFF),
        ("double size on",       ALIGN_CENTER + DOUBLE_SIZE),
        ("double size line",     b"BIG TEXT" + LF),
        ("double size off",      NORMAL_SIZE + ALIGN_LEFT),
        ("blank line",           LF),
        ("footer",               ALIGN_CENTER + b"-- end of test --" + LF),
        ("feed before cut",      FEED_5_LINES),
    ]


def build_minimal_payload() -> list[tuple[str, bytes]]:
    """Smallest possible feed-only test — just init + one line + feed."""
    return [
        ("init",         INIT),
        ("hello line",   b"CT-S2000 OK" + LF),
        ("feed",         FEED_3_LINES),
    ]


# ---------------------------------------------------------------------------
# USB plumbing
# ---------------------------------------------------------------------------

def find_device(vid: int | None, pid: int | None):
    """Find a Citizen printer-class device.

    If vid/pid are given, match exactly. Otherwise enumerate every
    USB printer-class device and pick the first one whose VID matches
    the Citizen default; fall back to printing a list if nothing matches.
    """
    if vid is not None and pid is not None:
        return usb.core.find(idVendor=vid, idProduct=pid)

    candidates = []
    for dev in usb.core.find(find_all=True):
        for cfg in dev:
            for intf in cfg:
                if intf.bInterfaceClass == USB_PRINTER_CLASS:
                    candidates.append(dev)
                    break
            else:
                continue
            break

    if not candidates:
        return None

    # Prefer the configured Citizen VID, otherwise return the first printer-class device.
    target = vid if vid is not None else DEFAULT_VID
    for dev in candidates:
        if dev.idVendor == target:
            return dev
    return candidates[0]


def describe_device(dev) -> None:
    print(f"Device: {dev.idVendor:04x}:{dev.idProduct:04x}  "
          f"bcdUSB={dev.bcdUSB:04x}  bcdDevice={dev.bcdDevice:04x}")
    try:
        if dev.product:
            print(f"  product:      {dev.product!r}")
        if dev.manufacturer:
            print(f"  manufacturer: {dev.manufacturer!r}")
        if dev.serial_number:
            print(f"  serial:       {dev.serial_number!r}")
    except Exception:
        pass
    print()
    print("  Interfaces:")
    for cfg in dev:
        for intf in cfg:
            kind = "Printer (class 7)" if intf.bInterfaceClass == USB_PRINTER_CLASS \
                else f"class 0x{intf.bInterfaceClass:02x}"
            ep_summary = ", ".join(
                ("OUT" if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_OUT else "IN")
                + f" 0x{ep.bEndpointAddress:02x}"
                for ep in intf
            )
            print(
                f"    intf {intf.bInterfaceNumber} alt {intf.bAlternateSetting}: "
                f"{kind}  endpoints=[{ep_summary}]"
            )
    print()


def detach_kernel_drivers(dev) -> None:
    """Best-effort detach across all printer-class interfaces."""
    seen: set[int] = set()
    for cfg in dev:
        for intf in cfg:
            num = intf.bInterfaceNumber
            if num in seen:
                continue
            seen.add(num)
            try:
                if dev.is_kernel_driver_active(num):
                    try:
                        dev.detach_kernel_driver(num)
                        print(f"  detached kernel driver from intf {num}")
                    except Exception as e:
                        print(f"  could not detach intf {num}: {e}")
                else:
                    print(f"  intf {num}: no kernel driver bound")
            except Exception as e:
                print(f"  intf {num} probe failed: {e}")


def find_printer_endpoint(dev):
    """Return (interface_number, OUT endpoint) for the first printer-class
    interface with a bulk OUT endpoint. Raises if nothing usable found."""
    for cfg in dev:
        for intf in cfg:
            if intf.bInterfaceClass != USB_PRINTER_CLASS:
                continue
            ep_out = usb.util.find_descriptor(
                intf,
                custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
                == usb.util.ENDPOINT_OUT,
            )
            if ep_out is not None:
                return intf.bInterfaceNumber, ep_out
    raise RuntimeError("no printer-class interface with a bulk OUT endpoint found")


# ---------------------------------------------------------------------------
# Main run loop
# ---------------------------------------------------------------------------

CLAIM_ADVICE = (
    "macOS's print stack is exclusively holding the device. Try, in escalating order:\n"
    "  1. Physically unplug & replug the USB cable, then run this script\n"
    "     within ~2 seconds — before AppleUSBPrinter latches onto it.\n"
    "  2. Delete the auto-created CUPS queue so the USB backend stops\n"
    "     polling the device:\n"
    "         lpadmin -x <queue-name>\n"
    "     Find the queue with `lpstat -p`.\n"
    "  3. Stop CUPS for this session (re-enables on next launchd trigger):\n"
    "         sudo launchctl bootout system/org.cups.cupsd 2>/dev/null\n"
    "Simple `cupsdisable <queue>` is NOT enough — the queue stays\n"
    "registered and the USB backend keeps the device handle."
)


def run_payload(
    ep_out,
    payload: list[tuple[str, bytes]],
    timeout: int,
    inter_line_pause: float,
) -> None:
    """Send each (label, bytes) line as one bulk transfer."""
    print(f"{'#':>3}  {'Step':<24}  Result")
    print("-" * 60)
    for i, (label, data) in enumerate(payload, 1):
        try:
            written = ep_out.write(data, timeout=timeout)
            print(f"{i:>3}  {label:<24}  OK ({written} bytes)")
        except usb.core.USBTimeoutError:
            print(f"{i:>3}  {label:<24}  TIMEOUT — printer not consuming data")
            return
        except Exception as e:
            print(f"{i:>3}  {label:<24}  ERROR: {e}")
            return
        if inter_line_pause > 0:
            time.sleep(inter_line_pause)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--vid", default=None,
                    help=f"USB vendor ID hex (default: auto-detect, prefer {DEFAULT_VID:04x})")
    ap.add_argument("--pid", default=None,
                    help="USB product ID hex (default: auto-detect)")
    ap.add_argument("--timeout", type=int, default=5000,
                    help="Per-write USB timeout in ms (default 5000)")
    ap.add_argument("--pause", type=float, default=0.05,
                    help="Seconds between line writes (default 0.05; "
                         "0 = back-to-back, helpful only for slow printers)")
    ap.add_argument("--no-cut", action="store_true",
                    help="Skip the paper-cut command at end of test")
    ap.add_argument("--partial-cut", action="store_true",
                    help="Use partial cut (leaves a tab) instead of full cut")
    ap.add_argument("--feed-only", action="store_true",
                    help="Send the smallest possible test (init + 1 line + feed)")
    ap.add_argument("--no-detach", action="store_true",
                    help="Skip kernel-driver detach (use if detach itself fails)")
    args = ap.parse_args()

    vid = int(args.vid, 16) if args.vid else None
    pid = int(args.pid, 16) if args.pid else None

    dev = find_device(vid, pid)
    if dev is None:
        if vid is not None and pid is not None:
            print(f"No device at {vid:04x}:{pid:04x}", file=sys.stderr)
        else:
            print("No USB printer-class device found.", file=sys.stderr)
            print("Plug in the printer, power it on, and check it appears in:", file=sys.stderr)
            if sys.platform == "darwin":
                print("  ioreg -p IOUSB -l | grep -i -A2 citizen", file=sys.stderr)
            else:
                print("  lsusb", file=sys.stderr)
        return 1

    describe_device(dev)

    if not args.no_detach:
        print("Kernel-driver detach (best-effort):")
        detach_kernel_drivers(dev)
        print()

    try:
        dev.set_configuration()
    except Exception as e:
        print(f"set_configuration warning: {e}")

    try:
        intf_num, ep_out = find_printer_endpoint(dev)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        usb.util.dispose_resources(dev)
        return 2

    print(f"Using interface {intf_num}, OUT endpoint 0x{ep_out.bEndpointAddress:02x}\n")

    try:
        usb.util.claim_interface(dev, intf_num)
    except Exception as e:
        print(f"claim_interface({intf_num}) failed: {e}\n")
        print(CLAIM_ADVICE)
        usb.util.dispose_resources(dev)
        return 2

    try:
        payload = build_minimal_payload() if args.feed_only else build_test_payload()
        if not args.no_cut:
            cut = PARTIAL_CUT if args.partial_cut else FULL_CUT
            payload.append(("paper cut", cut))

        run_payload(ep_out, payload, args.timeout, args.pause)
        print()
        print("Test complete. Check the printed receipt:")
        print("  • Did 'CITIZEN CT-S2000 TEST' print as a centered bold header?")
        print("  • Did the ASCII range print legibly without missing characters?")
        print("  • Did BOLD, underlined, and BIG demo lines render correctly?")
        if not args.no_cut:
            print("  • Did the paper auto-cut at the end?")
    finally:
        try:
            usb.util.release_interface(dev, intf_num)
        except Exception:
            pass
        usb.util.dispose_resources(dev)

    return 0


if __name__ == "__main__":
    sys.exit(main())
