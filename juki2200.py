#!/usr/bin/env python3
"""Bruteforce Juki 2200 USB connectivity probe.

The Juki 2200 is a 1985 daisywheel memory typewriter with a Centronics port.
It is a *line-buffered* printer: bytes accumulate in a line buffer and the
hammer doesn't move until a CR+LF terminator arrives. This script tries
every reasonable combination of alt setting × init sequence × line payload
to find what (if anything) actually reaches the platen.

Key gotchas this script tries to defeat:

  1. Line buffering — every test payload ends with CR+LF (0x0D, 0x0A), in
     that order, sent as raw bytes. Files are opened binary; print() is
     never used to talk to the device.
  2. Default margin trap — Praxis-family machines power on with left=30,
     right=90 (10 cpi). Lines past col 90 are beeped and dropped. Test
     payloads are kept short, and the script also tries Juki/Diablo-style
     ESC margin-reset sequences before sending text.
  3. Centronics handshaking — the CH341-based USB-LPT adapter at 1a86:7584
     declares itself a USB Printer-Class device. That's the "cheap" class
     of adapter that buffers in the cable and may ignore /BUSY. The script
     prints the adapter's interface descriptor so you can see for yourself
     whether it's class-7 (buffered) or vendor-specific (raw parallel).
     A separate "slow drip" mode writes one byte every 120 ms to give a
     real Centronics handshake time to settle.
  4. macOS AppleUSBPrinter — the kext often claims printer-class devices.
     The script detaches kernel drivers best-effort; if claim fails on
     macOS the most reliable workaround is `cupsdisable USB2.0-Print` (or
     equivalent), which makes CUPS release the device.

Usage:
    uv run python juki_bruteforce.py
    uv run python juki_bruteforce.py --vid 1a86 --pid 7584
    uv run python juki_bruteforce.py --slow      # one-byte-at-a-time mode
    uv run python juki_bruteforce.py --alt 0     # restrict to one alt
    uv run python juki_bruteforce.py --pause 5   # seconds between tests
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


# Juki / Diablo 630 / Qume daisywheel ESC sequences that show up across
# the family. Different ROM revisions accept different subsets — that's
# why this is a bruteforce and not a precise reset.
JUKI_FULL_RESET = b"\x1b\x1aI"          # ESC SUB I — full re-init
JUKI_LINE_SPACE_6LPI = b"\x1b\x1e\x09"  # ESC RS 9 — 1/6" line spacing
JUKI_FIXED_PITCH = b"\x1bQ"             # ESC Q — disable proportional
DIABLO_LEFT_MARGIN_0 = b"\x1b\x39"      # ESC 9 — set left margin at col
DIABLO_RIGHT_MARGIN = b"\x1b\x30"       # ESC 0 — set right margin at col
DIABLO_HMI_RESET = b"\x1b\x1c\x0c"      # ESC FS NL — restore default HMI

# Line ending — must be CR then LF, two separate bytes, in that order.
EOL = b"\r\n"

# Payloads to try, ordered from least invasive to most. Every text
# payload is short enough to fit between default margins (30..90 = 60
# columns) AND ends with CR+LF.
PAYLOADS: list[tuple[str, bytes]] = [
    ("bare CR+LF (handshake test)", EOL),
    ("short text + CR+LF", b"HELLO JUKI 2200" + EOL),
    ("Juki full-reset + short text", JUKI_FULL_RESET + b"HELLO" + EOL),
    (
        "Juki reset + line-space + pitch + text",
        JUKI_FULL_RESET + JUKI_LINE_SPACE_6LPI + JUKI_FIXED_PITCH + b"HELLO" + EOL,
    ),
    (
        "Diablo HMI reset + text",
        DIABLO_HMI_RESET + b"DIABLO MARGIN RESET TEST" + EOL,
    ),
    ("digits 0-9 + CR+LF", b"0123456789" + EOL),
    ("two short lines", b"FIRST" + EOL + b"SECOND" + EOL),
    ("long line w/o reset (margin-trap test)", b"X" * 80 + EOL),
    ("form feed", b"\x0c"),
    ("carriage-return-only (overprint test)", b"AAAA\rBBBB" + EOL),
]

ALT_SETTINGS = [0, 1, 2]
USB_PRINTER_CLASS = 7
USB_VENDOR_SPECIFIC_CLASS = 0xFF


def find_device(vid: int, pid: int):
    return usb.core.find(idVendor=vid, idProduct=pid)


def describe_device(dev) -> None:
    print(f"Device: {dev.idVendor:04x}:{dev.idProduct:04x}  bcdUSB={dev.bcdUSB:04x}  bcdDevice={dev.bcdDevice:04x}")
    try:
        if dev.product:
            print(f"  product: {dev.product!r}")
        if dev.manufacturer:
            print(f"  manufacturer: {dev.manufacturer!r}")
        if dev.serial_number:
            print(f"  serial: {dev.serial_number!r}")
    except Exception:
        pass
    print()
    print("  Interface alt-settings:")
    for cfg in dev:
        for intf in cfg:
            kind = {
                USB_PRINTER_CLASS: "Printer (class 7)",
                USB_VENDOR_SPECIFIC_CLASS: "Vendor-Specific (class 0xff)",
            }.get(intf.bInterfaceClass, f"class 0x{intf.bInterfaceClass:02x}")
            ep_summary = ", ".join(
                ("OUT" if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_OUT else "IN")
                + f" 0x{ep.bEndpointAddress:02x}"
                for ep in intf
            )
            print(
                f"    intf {intf.bInterfaceNumber} alt {intf.bAlternateSetting}: {kind}  endpoints=[{ep_summary}]"
            )
    print()


def diagnose_adapter_type(dev) -> None:
    """Tell the user which class of adapter they have.

    Class-7 only        → cheap USB-printer-class bridge. Buffers in the
                          cable, may not honor Centronics /BUSY/ACK.
    Vendor-specific too → CH341/CH347-style raw parallel mode is available
                          on a different alt setting; for true handshake
                          you'd drive that with the chip's vendor protocol.
    """
    has_printer = False
    has_vendor = False
    for cfg in dev:
        for intf in cfg:
            if intf.bInterfaceClass == USB_PRINTER_CLASS:
                has_printer = True
            elif intf.bInterfaceClass == USB_VENDOR_SPECIFIC_CLASS:
                has_vendor = True

    print("Adapter analysis:")
    if has_printer and has_vendor:
        print(
            "  Mixed class. Printer-class alts present (host buffers data,"
            " may ignore /BUSY) AND a vendor-specific alt (raw CH341/CH347"
            " parallel mode — needs vendor-specific control transfers)."
        )
    elif has_printer:
        print("  USB Printer-Class only — host-side buffering, may drop characters under handshake stress.")
    elif has_vendor:
        print("  Vendor-specific only — raw parallel mode (needs chip-specific protocol to drive).")
    else:
        print("  Unknown — no printer-class and no vendor-specific interface.")
    print()


def detach_kernel_drivers(dev) -> None:
    """Best-effort kernel-driver detach across all interfaces."""
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


def get_device_id(dev, intf_num: int, timeout: int) -> str:
    """USB Printer Class GET_DEVICE_ID returns the IEEE 1284 ID string.

    Many printers refuse this when their kernel driver was just detached,
    or when no Centronics device is responding on the parallel side.
    """
    try:
        # bmRequestType=0xA1: Class | Interface | Device-to-Host
        # bRequest=0: GET_DEVICE_ID
        # wValue: cfg<<8 | alt → use cfg=1, alt=0
        data = dev.ctrl_transfer(0xA1, 0, 1 << 8, intf_num, 1024, timeout=timeout)
        if len(data) >= 2:
            length = (data[0] << 8) | data[1]
            return bytes(data[2 : 2 + length]).decode("ascii", errors="replace")
        return "<empty>"
    except Exception as e:
        return f"<error: {e}>"


def get_port_status(dev, intf_num: int, timeout: int) -> str:
    """USB Printer Class GET_PORT_STATUS — bit 5 PaperEmpty, bit 4 Select, bit 3 NotError."""
    try:
        data = dev.ctrl_transfer(0xA1, 1, 0, intf_num, 1, timeout=timeout)
        if len(data) >= 1:
            b = data[0]
            flags = []
            if b & 0x20:
                flags.append("PaperEmpty")
            if b & 0x10:
                flags.append("Select")
            if b & 0x08:
                flags.append("NotError")
            return f"0x{b:02x} [{', '.join(flags) or 'none'}]"
        return "<empty>"
    except Exception as e:
        return f"<error: {e}>"


def soft_reset(dev, intf_num: int, timeout: int) -> str:
    """USB Printer Class SOFT_RESET (vendor request type)."""
    try:
        dev.ctrl_transfer(0x21, 2, 0, intf_num, None, timeout=timeout)
        return "OK"
    except Exception as e:
        return f"<error: {e}>"


def find_alt_interface(dev, alt: int):
    cfg = dev.get_active_configuration()
    for intf in cfg:
        if intf.bAlternateSetting == alt:
            return intf
    return None


def _redetach_if_needed(dev, intf_num: int) -> None:
    """Best-effort: re-detach the kernel driver if it has reattached.

    macOS's AppleUSBPrinter / CUPS USB backend tends to re-bind to a
    printer-class interface within a second or two of any release. This
    helper runs before every alt switch so a multi-second --slow test
    doesn't hit Errno 13 on the next claim.
    """
    try:
        if dev.is_kernel_driver_active(intf_num):
            try:
                dev.detach_kernel_driver(intf_num)
            except Exception:
                pass
    except Exception:
        pass


def try_write(
    dev,
    intf_num: int,
    alt: int,
    payload: bytes,
    timeout: int,
    slow: bool = False,
    byte_pause: float = 0.12,
) -> str:
    """Try a single write at a given alt setting; return human-readable outcome.

    Assumes the caller has already claimed ``intf_num``; this function
    only switches alt settings and writes, so the kernel driver doesn't
    get a window to reattach between writes.

    When ``slow`` is set, each byte is sent as a separate USB bulk
    transfer with ``byte_pause`` seconds between them. A real Juki 2200
    daisywheel prints at ~10 cps (100 ms/char) and /BUSY can stay high
    for a full character cycle, so byte_pause should be ≥ 0.12 s. For
    spec-margin tests use 0.5–1.0 s to be sure the chip's internal
    Centronics handshake has time to release between strikes.
    """
    intf = find_alt_interface(dev, alt)
    if intf is None:
        return f"alt {alt} not present"

    _redetach_if_needed(dev, intf_num)

    try:
        dev.set_interface_altsetting(
            interface=intf_num, alternate_setting=alt
        )
    except Exception as e:
        return f"set alt failed: {e}"

    ep_out = usb.util.find_descriptor(
        intf,
        custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
        == usb.util.ENDPOINT_OUT,
    )
    if ep_out is None:
        return f"no OUT ep at alt {alt}"

    try:
        if slow:
            total = 0
            for byte in payload:
                ep_out.write(bytes([byte]), timeout=timeout)
                total += 1
                time.sleep(byte_pause)
            return f"OK slow ({total} bytes @ {byte_pause}s/byte)"
        written = ep_out.write(payload, timeout=timeout)
        return f"OK ({written} bytes)"
    except usb.core.USBTimeoutError:
        return "timeout"
    except Exception as e:
        return f"error: {e}"


def run_minimal_spec_test(
    dev,
    intf_num: int,
    alt: int,
    timeout: int,
    byte_pause: float,
) -> None:
    """Most spec-clean test possible: pulse soft-reset, then drip-feed one
    short ASCII line as separate USB bulk transfers, then wait long enough
    for the daisywheel to physically respond.

    Sequence (matches Diablo 630 / Juki 2200 expectations):
      1. SOFT_RESET (USB Printer Class request 2) — pulses nINIT to reset
         the typewriter's line buffer. Often STALLs on bridge adapters;
         that's harmless, the data path still works.
      2. ESC SUB I — Juki/Diablo full re-init.
      3. ESC FS NL — Diablo HMI reset (restores default margins).
      4. 'A' (single character, well within default 30..90 margins).
      5. CR (0x0D), then LF (0x0A) as two separate writes.
      6. Wait 3 s for the platen to settle before reporting done.

    Each byte is one USB transfer separated by ``byte_pause`` seconds so
    the chip's internal /BUSY handshake gets full /ACK time per char.
    """
    intf = find_alt_interface(dev, alt)
    if intf is None:
        print(f"alt {alt} not present on this device — abort minimal test")
        return

    print(f"Minimal spec test on alt {alt} @ {byte_pause}s/byte ({timeout}ms timeout)")

    print("  step 1/6  SOFT_RESET (class req 2)")
    try:
        dev.ctrl_transfer(0x21, 2, 0, intf_num, None, timeout=timeout)
        print("            OK")
    except Exception as e:
        print(f"            STALL ignored: {e}")
    time.sleep(0.5)

    _redetach_if_needed(dev, intf_num)
    try:
        dev.set_interface_altsetting(interface=intf_num, alternate_setting=alt)
    except Exception as e:
        print(f"  set alt {alt} failed: {e}")
        return
    ep_out = usb.util.find_descriptor(
        intf,
        custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
        == usb.util.ENDPOINT_OUT,
    )
    if ep_out is None:
        print(f"  no OUT endpoint at alt {alt}")
        return

    sequence = [
        ("step 2/6  Juki full reset (ESC SUB I)", JUKI_FULL_RESET),
        ("step 3/6  Diablo HMI reset (ESC FS NL)", DIABLO_HMI_RESET),
        ("step 4/6  payload byte 'A' (0x41)", b"A"),
        ("step 5a/6 carriage return (0x0D)", b"\r"),
        ("step 5b/6 line feed (0x0A)", b"\n"),
    ]
    for label, chunk in sequence:
        print(f"  {label}  ({len(chunk)} byte{'s' if len(chunk) != 1 else ''})")
        for byte in chunk:
            try:
                ep_out.write(bytes([byte]), timeout=timeout)
            except usb.core.USBTimeoutError:
                print(f"            timeout on byte 0x{byte:02x} — host buffer or /BUSY stuck")
                return
            except Exception as e:
                print(f"            error on byte 0x{byte:02x}: {e}")
                return
            time.sleep(byte_pause)
    print("  step 6/6  waiting 3 s for daisywheel to strike...")
    time.sleep(3.0)
    print("  done. Did the typewriter print 'A' on its own line?")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--vid", default="1a86", help="USB vendor ID hex (default 1a86)")
    ap.add_argument("--pid", default="7584", help="USB product ID hex (default 7584)")
    ap.add_argument("--timeout", type=int, default=3000, help="Per-write USB timeout (ms)")
    ap.add_argument(
        "--pause", type=float, default=2.5,
        help="Seconds between tests so the printer can mechanically respond",
    )
    ap.add_argument(
        "--alt", type=int, choices=ALT_SETTINGS, default=None,
        help="Restrict to a single alt setting (default: try all)",
    )
    ap.add_argument(
        "--slow", action="store_true",
        help="Drip-feed bytes one at a time (Centronics pace)",
    )
    ap.add_argument(
        "--byte-pause", type=float, default=0.12,
        help="Seconds between bytes in --slow mode (default 0.12 ≈ 8 cps; "
             "use 0.5–1.0 for spec-margin testing of /BUSY handshake)",
    )
    ap.add_argument(
        "--minimal", action="store_true",
        help="Skip the bruteforce table; run one spec-clean drip-fed "
             "'A\\r\\n' test (use with --alt 0 or --alt 1)",
    )
    ap.add_argument(
        "--reset", action="store_true",
        help="Send dev.reset() before claiming — clears stale chip buffers "
             "(may briefly disconnect the device)",
    )
    ap.add_argument(
        "--no-detach", action="store_true",
        help="Skip kernel-driver detach (use if detach itself is failing)",
    )
    args = ap.parse_args()

    vid = int(args.vid, 16)
    pid = int(args.pid, 16)

    dev = find_device(vid, pid)
    if dev is None:
        print(f"No device at {vid:04x}:{pid:04x}", file=sys.stderr)
        return 1

    describe_device(dev)
    diagnose_adapter_type(dev)

    if args.reset:
        print("Sending dev.reset() to clear chip-internal buffers...")
        try:
            dev.reset()
            time.sleep(0.5)
            # The reset re-enumerates the device; refresh our handle.
            dev = find_device(vid, pid)
            if dev is None:
                print("Device disappeared after reset (re-plug it).", file=sys.stderr)
                return 1
        except Exception as e:
            print(f"  reset failed: {e}")
        print()

    if not args.no_detach:
        print("Kernel-driver detach (best-effort):")
        detach_kernel_drivers(dev)
        print()

    # Set the configuration once before per-alt iteration.
    try:
        dev.set_configuration()
    except Exception as e:
        print(f"set_configuration warning: {e}")

    alts = [args.alt] if args.alt is not None else ALT_SETTINGS

    # Claim interface 0 ONCE and hold it across every test. Releasing
    # between tests gives macOS's print stack a window to re-bind, which
    # makes the next claim fail with EACCES (especially during --slow).
    intf_num = 0
    claim_advice = (
        "macOS's print stack is exclusively holding the device. Try, in order\n"
        "of escalation:\n"
        "  1. Physically unplug & replug the USB cable, then run this script\n"
        "     within ~2 seconds — before AppleUSBPrinter latches onto it.\n"
        "  2. Delete the auto-created CUPS queue so the USB backend stops\n"
        "     polling the device:\n"
        "         lpadmin -x USB2.0-Print\n"
        "     (it'll come back next time you plug the printer in; that's fine.)\n"
        "  3. Stop CUPS for this session (re-enables on next launchd trigger):\n"
        "         sudo launchctl bootout system/org.cups.cupsd 2>/dev/null\n"
        "  4. SIP-permitting machines (rare on Apple Silicon):\n"
        "         sudo kextunload -b com.apple.driver.AppleUSBPrinter\n"
        "Simple `cupsdisable USB2.0-Print` is NOT enough — the queue stays\n"
        "registered and the USB backend keeps the device handle."
    )

    try:
        usb.util.claim_interface(dev, intf_num)
    except Exception as e:
        print(f"Initial claim_interface({intf_num}) failed: {e}")
        print(claim_advice)
        usb.util.dispose_resources(dev)
        return 2

    # Run control queries AFTER the claim — class-specific requests on
    # macOS often STALL with EPIPE if the host doesn't own the interface.
    # Pipe errors here are also normal for cheap CH341 bridges that don't
    # implement these queries at all; the bulk write loop is the real test.
    print("USB Printer Class control queries (intf 0):")
    print(f"  GET_DEVICE_ID:   {get_device_id(dev, intf_num, args.timeout)}")
    print(f"  GET_PORT_STATUS: {get_port_status(dev, intf_num, args.timeout)}")
    print(f"  SOFT_RESET:      {soft_reset(dev, intf_num, args.timeout)}")
    print("  (Pipe errors above are expected on bridge adapters that don't")
    print("   implement Printer-Class control requests — proceed to writes.)")
    print()

    if args.minimal:
        try:
            target_alt = args.alt if args.alt is not None else 0
            run_minimal_spec_test(
                dev, intf_num, target_alt, args.timeout, args.byte_pause
            )
        finally:
            try:
                usb.util.release_interface(dev, intf_num)
            except Exception:
                pass
        usb.util.dispose_resources(dev)
        return 0

    print(f"{'Alt':>3}  {'Payload':<46}  Result")
    print("-" * 90)
    try:
        for alt in alts:
            intf = find_alt_interface(dev, alt)
            if intf is None:
                print(f"{alt:>3}  alt setting not present on this device")
                continue
            for label, payload in PAYLOADS:
                outcome = try_write(
                    dev, intf_num, alt, payload, args.timeout,
                    slow=args.slow, byte_pause=args.byte_pause,
                )
                print(f"{alt:>3}  {label:<46}  {outcome}")
                if "Errno 13" in outcome or "Access denied" in outcome:
                    print(claim_advice)
                time.sleep(args.pause)
            print()
    finally:
        try:
            usb.util.release_interface(dev, intf_num)
        except Exception:
            pass

    print("If every write times out:")
    print("  • Confirm the Juki 2200 is in PRINTER / ONLINE mode (not local")
    print("    typewriter mode). Look for an ON LINE indicator LED.")
    print("  • Centronics cable seated firmly on both ends.")
    print("  • Paper loaded; no error light on the typewriter.")
    print("  • macOS: `cupsdisable USB2.0-Print` so CUPS releases the device,")
    print("    then re-run this script.")
    print("  • If timeouts persist on every alt, the adapter's printer-class")
    print("    firmware is buffering bytes that the typewriter is silently")
    print("    discarding due to /BUSY violations. A true bidirectional")
    print("    USB-to-Centronics adapter (e.g., a real IEEE 1284 ECP one)")
    print("    is the most reliable fix; for the CH341, alt 2 + the chip's")
    print("    vendor-specific protocol is the alternative.")

    usb.util.dispose_resources(dev)
    return 0


if __name__ == "__main__":
    sys.exit(main())
