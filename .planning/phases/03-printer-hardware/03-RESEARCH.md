# Phase 3: Printer Hardware - Research

**Researched:** 2026-02-15
**Domain:** USB-LPT printer discovery, raw printing, device I/O, graceful disconnect on macOS/Linux
**Confidence:** MEDIUM (CUPS approach verified with official docs; direct USB path has LOW confidence on macOS; graceful disconnect patterns are well-understood)

## Summary

Phase 3 adds printer hardware support to an existing async character streaming pipeline. The architecture is already prepared: `make_output_fn()` supports multiple destinations, so adding a printer is `make_output_fn(log.write, printer.write)` -- the pacer and bridge are unchanged.

The central technical challenge is **printer discovery and communication on macOS**. USB-LPT adapters present as USB printer class devices (class 0x07), NOT as parallel ports. macOS does NOT expose `/dev/usb/lp*` device files for USB printers (unlike Linux). The most reliable macOS path is CUPS: discover printers via `lpstat -v`, send raw text via `lp -o raw -d <printer>`. On Linux, direct file I/O to `/dev/usb/lp0` is simpler and more reliable. A tiered approach with automatic fallback is required.

**Primary recommendation:** Implement a `PrinterDriver` protocol with three backends: (1) CUPS raw queue via `lp` subprocess pipe, (2) direct device file I/O for Linux `/dev/usb/lp*` or user-specified `--device` paths, (3) null driver (no-op, simulator-only mode). Discovery scans CUPS first, then falls back to device file probing. All printer I/O runs via `asyncio.to_thread()` to avoid blocking the event loop. Disconnect detection wraps every `write()` in try/except, switching to null driver on failure.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| subprocess (stdlib) | Python 3.12 | CUPS discovery (`lpstat`) and raw printing (`lp`) | CUPS is the macOS/Linux print system. `lpstat -v` lists printers with device URIs. `lp -o raw -d <name>` sends raw bytes through CUPS without filtering. No third-party library needed. |
| asyncio (stdlib) | Python 3.12 | Non-blocking printer I/O | `asyncio.to_thread()` wraps blocking device writes. Already the project's async foundation. |
| os / builtins | Python 3.12 | Direct device file I/O | `open("/dev/usb/lp0", "wb", buffering=0)` for Linux direct path. Zero-dependency. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pyusb | 1.3.1 | USB device enumeration fallback | Only if CUPS discovery fails AND user wants auto-discovery of native USB printers. `usb.core.find(custom_match=find_class(7))` finds printer-class devices. Requires `libusb` (`brew install libusb`). |
| pycups | 2.0.4 | Programmatic CUPS API | Only if `lpstat` subprocess parsing proves fragile. `cups.Connection().getPrinters()` returns structured dict. Requires CUPS headers for compilation. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `lpstat` + `lp` (subprocess) | pycups library | pycups gives structured data but adds a C extension dependency requiring CUPS development headers. subprocess approach is zero-dependency and works everywhere CUPS is installed. Use pycups only if lpstat output parsing becomes unmaintainable. |
| `lp -o raw` pipe for character streaming | Direct device file I/O | Direct file I/O gives true character-by-character control but only works on Linux (`/dev/usb/lp0`) or with user-specified device paths. CUPS pipe is the universal fallback. |
| pyusb for discovery | `system_profiler SPUSBDataType` (macOS) | system_profiler is slow (~2-5 seconds), output format varies between macOS versions, and SPUSBDataType may be missing in macOS Tahoe. pyusb is faster and cross-platform. |
| Custom USB driver | python-escpos | python-escpos is for ESC/POS thermal receipt printers, NOT dot-matrix. Wrong command set. Do not use. |

**Installation:**
```bash
# No new dependencies for Tier 1 (CUPS) -- uses stdlib subprocess
# Optional: for Tier 3 USB fallback
uv add pyusb
# System dependency (macOS, only for pyusb):
brew install libusb
```

## Architecture Patterns

### Recommended Module Structure

```
src/claude_teletype/
    printer.py          # PrinterDriver protocol + all backends + discovery
```

Single module, not a sub-package. Phase 3 has three small backends and a discovery function -- splitting across files would be over-engineering at this scale. If backends grow complex later, extract to a `printer/` package.

### Pattern 1: Strategy Pattern for Printer Backend

**What:** A `PrinterDriver` Protocol with `write(char)`, `close()`, and `is_connected` property. Three implementations: `CupsPrinterDriver`, `FilePrinterDriver`, `NullPrinterDriver`. Selected at startup by discovery logic or `--device` CLI flag.

**When to use:** When the same operation (write char to printer) has fundamentally different transports depending on runtime environment.

**Example:**
```python
from typing import Protocol

class PrinterDriver(Protocol):
    """Interface for all printer backends."""

    @property
    def is_connected(self) -> bool: ...

    def write(self, char: str) -> None:
        """Write a single character. Raises IOError on disconnect."""
        ...

    def close(self) -> None: ...
```

### Pattern 2: CUPS Pipe-Based Character Streaming

**What:** Open `lp -o raw -d <printer>` as a subprocess with `stdin=PIPE`. Write characters to stdin. Flush per-character or per-line. Close stdin when done (sends EOF, triggers print).

**When to use:** macOS (always), Linux (when CUPS is available and printer is configured).

**Critical insight:** `lp` buffers stdin until EOF. For character-by-character output to actually reach the printer in real-time, we have two options: (a) accumulate a line buffer and invoke `lp` per-line (simpler, slight delay at line boundaries), or (b) write directly to the CUPS backend's device URI if it's a file path. Option (a) is the practical choice for v1.

**Example:**
```python
import subprocess

class CupsPrinterDriver:
    def __init__(self, printer_name: str):
        self._name = printer_name
        self._connected = True
        self._line_buffer: list[str] = []

    def write(self, char: str) -> None:
        if not self._connected:
            return
        self._line_buffer.append(char)
        if char == "\n":
            self._flush_line()

    def _flush_line(self) -> None:
        line = "".join(self._line_buffer)
        self._line_buffer.clear()
        try:
            subprocess.run(
                ["lp", "-o", "raw", "-d", self._name],
                input=line.encode("ascii", errors="replace"),
                capture_output=True,
                timeout=10,
            )
        except (subprocess.SubprocessError, OSError):
            self._connected = False
```

### Pattern 3: Direct Device File I/O

**What:** Open a device file (e.g., `/dev/usb/lp0` or user-specified path) in binary write mode with zero buffering. Write each character directly.

**When to use:** Linux with `/dev/usb/lp0` available, or when user specifies `--device /path/to/device`.

**Example:**
```python
class FilePrinterDriver:
    def __init__(self, device_path: str):
        self._path = device_path
        self._fd = open(device_path, "wb", buffering=0)
        self._connected = True

    def write(self, char: str) -> None:
        if not self._connected:
            return
        try:
            self._fd.write(char.encode("ascii", errors="replace"))
        except (IOError, OSError):
            self._connected = False

    def close(self) -> None:
        if self._fd and not self._fd.closed:
            self._fd.close()
```

### Pattern 4: Resilient Write Wrapper for Output Multiplexer

**What:** A wrapper around `PrinterDriver.write()` that catches IOError/OSError, logs a warning once, and degrades to no-op mode. Integrates with `make_output_fn()`.

**When to use:** Always. This is how PRNT-03 (graceful disconnect) is implemented.

**Example:**
```python
def make_printer_output(driver: PrinterDriver) -> Callable[[str], None]:
    """Create an output_fn that writes to a printer with graceful degradation."""
    disconnected = False

    def printer_write(char: str) -> None:
        nonlocal disconnected
        if disconnected:
            return
        try:
            driver.write(char)
        except (IOError, OSError):
            disconnected = True
            # Log warning: "Printer disconnected, continuing in simulator mode"

    return printer_write
```

### Pattern 5: CUPS Printer Discovery

**What:** Parse `lpstat -v` output to find printers with `usb://` device URIs. Filter for USB-connected printers (not network/IPP).

**When to use:** Auto-discovery on startup (PRNT-01).

**Example:**
```python
import subprocess
import re

def discover_cups_printers() -> list[dict[str, str]]:
    """Discover USB printers via CUPS lpstat."""
    try:
        result = subprocess.run(
            ["lpstat", "-v"],
            capture_output=True, text=True, timeout=5,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return []

    printers = []
    # Format: "device for PrinterName: usb://Vendor/Model?serial=XXX"
    pattern = re.compile(r"device for (\S+):\s+(.+)")
    for line in result.stdout.splitlines():
        match = pattern.match(line)
        if match:
            name, uri = match.group(1), match.group(2).strip()
            if uri.startswith("usb://"):
                printers.append({"name": name, "uri": uri})
    return printers
```

### Anti-Patterns to Avoid

- **Opening/closing device per character:** USB device re-enumeration takes milliseconds. Open once at startup, keep handle alive, close on exit.
- **Using pyparallel:** USB-LPT adapters are NOT parallel ports. pyparallel will not work.
- **Running entire tool with sudo:** Only the device open needs elevation (if at all). Never escalate the whole process.
- **Blocking the event loop with device writes:** Always use `asyncio.to_thread()` for `write()` calls, even if they seem fast. USB writes can stall unpredictably.
- **Assuming /dev/usb/lp0 exists on macOS:** It does not. macOS routes USB printers through CUPS exclusively.
- **Per-character subprocess invocation of `lp`:** Spawning a process per character is catastrophically slow. Buffer at minimum per-line.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Printer discovery | Custom USB enumeration with pyusb | `lpstat -v` (CUPS) | CUPS already handles USB device matching, driver loading, and queue setup. Parsing `lpstat` output is 10 lines of code vs. hundreds for raw USB enumeration with permissions handling. |
| USB device communication | Raw libusb calls via pyusb | `lp -o raw` via CUPS or direct device file | CUPS handles kernel driver conflicts, permissions, and USB protocol details. Direct pyusb requires detaching kernel drivers (needs root on macOS), finding bulk endpoints, and handling USB protocol errors. |
| Raw printing protocol | ESC/POS command sequences | Plain ASCII text | Dot-matrix printers accept raw ASCII directly. No printer language needed. Send text bytes, printer prints them. |
| Character encoding translation | Custom codepage mapping | `str.encode("ascii", errors="replace")` | v1 sends ASCII only. Dot-matrix printers understand ASCII natively. Unicode-to-codepage mapping is v2 scope (PRNT-06). |

**Key insight:** The "printer driver" in this project is deceptively simple. For a dot-matrix printer receiving raw ASCII text, the entire "driver" is: open a file/pipe, write bytes. The complexity is in discovery, permissions, and error recovery -- not in the data format.

## Common Pitfalls

### Pitfall 1: CUPS Owns the USB Device -- Direct Access Fails

**What goes wrong:** Developer tries to open `/dev/usb/lp0` or use pyusb to write directly to the printer. CUPS already has the device claimed. Write fails with "Resource busy" or "Permission denied."

**Why it happens:** On both macOS and Linux, when a USB printer is configured in CUPS, the CUPS backend maintains an exclusive lock on the device. Another process cannot open the same device simultaneously.

**How to avoid:** Prefer CUPS path (`lp -o raw`) which goes through CUPS's own device access. Only use direct device file I/O for devices NOT managed by CUPS, or when the user explicitly provides a `--device` path.

**Warning signs:** "Resource busy" errors when opening device files. Works with CUPS stopped (`sudo launchctl stop org.cups.cupsd`) but not when CUPS is running.

### Pitfall 2: lp Buffers Until EOF -- No Real-Time Character Output

**What goes wrong:** Developer opens `lp -o raw` pipe and writes characters one at a time expecting them to appear on paper immediately. Nothing prints until the pipe is closed (EOF sent).

**Why it happens:** `lp` is designed for batch printing. It accepts a complete print job, queues it, and prints it. It does not stream stdin to the printer in real time.

**How to avoid:** Two strategies: (a) Buffer per-line and invoke `lp` per line (acceptable latency for typewriter effect -- lines appear as they complete). (b) For true character-by-character, use direct device file I/O (`--device` path) which bypasses CUPS entirely. For v1, per-line flushing via CUPS is the pragmatic choice.

**Warning signs:** Nothing appears on paper until the process exits or pipe closes. All text appears at once in a burst.

### Pitfall 3: macOS Has No /dev/usb/lp* Device Files

**What goes wrong:** Code assumes `/dev/usb/lp0` exists on macOS like it does on Linux. File not found.

**Why it happens:** macOS routes ALL USB printer communication through the CUPS/IOKit framework. It does not create character device files for USB printers in `/dev/`.

**How to avoid:** On macOS, always use the CUPS path. Only probe for `/dev/usb/lp*` on Linux. The `--device` flag lets users specify arbitrary device paths for unusual setups.

**Warning signs:** `FileNotFoundError` on `/dev/usb/lp0` on macOS. Discovery code that assumes Linux device paths.

### Pitfall 4: CUPS Raw Queues Are Deprecated (But Still Work)

**What goes wrong:** Developer sees CUPS issue #5269 (raw queue deprecation) and panics, thinking raw printing is removed.

**Why it happens:** Apple opened issues #5269 and #5271 in 2018 to plan eventual removal of raw queues and printer drivers. As of 2026, raw queues are formally deprecated but still fully functional. The deprecation produces a warning message when configuring a raw queue via `lpadmin`, but `lp -o raw` continues to work.

**How to avoid:** Use `lp -o raw` confidently for v1. The deprecation is about the CUPS admin interface, not the printing path. Monitor CUPS release notes for actual removal (no timeline announced). Document this risk for future maintainers.

**Warning signs:** `lpadmin` warning messages when setting up raw queues. These are informational, not blocking.

### Pitfall 5: Disconnect Detection Races with Async Writes

**What goes wrong:** Printer disconnects mid-write. The `to_thread()` call raises an exception. But by the time the exception propagates back to the async event loop, the pacer has already queued more characters. Multiple error handlers fire simultaneously.

**Why it happens:** `asyncio.to_thread()` runs in a thread pool. The exception is only visible when the coroutine is awaited. Characters queued between the disconnect and the await do not know the printer is gone.

**How to avoid:** Use a simple boolean flag (`_connected`) checked before every write attempt. Set it to `False` on first error. Subsequent writes become no-ops immediately, without waiting for thread results. The flag acts as a circuit breaker.

**Warning signs:** Multiple "printer disconnected" log messages. Exceptions from write attempts after the printer is already known to be disconnected.

## Code Examples

### Complete Discovery + Driver Selection Flow

```python
# Source: Synthesized from CUPS official docs + project architecture

import subprocess
import re
import sys
from typing import Protocol, Callable
from pathlib import Path


class PrinterDriver(Protocol):
    @property
    def is_connected(self) -> bool: ...
    def write(self, char: str) -> None: ...
    def close(self) -> None: ...


class NullPrinterDriver:
    """No-op driver for simulator-only mode."""
    @property
    def is_connected(self) -> bool:
        return False

    def write(self, char: str) -> None:
        pass

    def close(self) -> None:
        pass


def discover_printer(device_override: str | None = None) -> PrinterDriver:
    """Select the best available printer backend.

    Priority:
    1. User-specified --device path -> FilePrinterDriver
    2. CUPS USB printer discovery -> CupsPrinterDriver
    3. Linux /dev/usb/lp0 probe -> FilePrinterDriver
    4. Fallback -> NullPrinterDriver
    """
    if device_override:
        return FilePrinterDriver(device_override)

    # Try CUPS discovery
    cups_printers = discover_cups_printers()
    if cups_printers:
        return CupsPrinterDriver(cups_printers[0]["name"])

    # Try Linux device file (not available on macOS)
    if sys.platform == "linux":
        for dev in ["/dev/usb/lp0", "/dev/usb/lp1"]:
            if Path(dev).exists():
                return FilePrinterDriver(dev)

    return NullPrinterDriver()
```

### Integrating Printer with Existing Output Multiplexer

```python
# Source: Existing project architecture (output.py + tui.py)

# In TUI stream_response worker:
from claude_teletype.output import make_output_fn

log = self.query_one("#output", Log)
printer_write = make_printer_output(printer_driver)
output_fn = make_output_fn(log.write, printer_write)

# Pacer uses output_fn -- characters go to BOTH log and printer
await pace_characters(chunk, base_delay_ms=self.base_delay_ms, output_fn=output_fn)
```

### Async-Safe Printer Write

```python
# Source: Python asyncio docs + project patterns

import asyncio

async def async_printer_write(driver: PrinterDriver, char: str) -> None:
    """Write a character to the printer without blocking the event loop."""
    if not driver.is_connected:
        return
    try:
        await asyncio.to_thread(driver.write, char)
    except (IOError, OSError):
        pass  # Driver internally marks itself disconnected
```

### CLI --device Flag Integration

```python
# Source: Existing cli.py patterns (Typer)

@app.command()
def chat(
    prompt: str = typer.Argument(None, help="Prompt (omit for interactive TUI)"),
    delay: float = typer.Option(75.0, "--delay", "-d"),
    device: str = typer.Option(None, "--device", help="Printer device path (e.g., /dev/usb/lp0)"),
    no_tui: bool = typer.Option(False, "--no-tui"),
) -> None:
    # ... existing logic ...
    from claude_teletype.printer import discover_printer
    printer = discover_printer(device_override=device)
    tui_app = TeletypeApp(base_delay_ms=delay, printer=printer)
    tui_app.run()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pyparallel for parallel port I/O | CUPS raw queue or direct USB | ~2015+ | pyparallel is dead. USB-LPT adapters are USB devices, not parallel ports. |
| Custom USB drivers via pyusb | CUPS `lp -o raw` for managed printers | Always was better | CUPS handles permissions, kernel driver conflicts, device enumeration. pyusb is only needed for unmanaged devices. |
| CUPS raw queues (first class) | CUPS raw queues (deprecated but functional) | 2018 (issue #5269) | Raw queues still work as of 2026. Deprecation is administrative, not functional. No removal timeline. |
| simpleaudio for audio | sounddevice | 2019 (simpleaudio abandoned) | Not directly Phase 3, but noted for Phase 4 awareness. |

**Deprecated/outdated:**
- pyparallel: Dead project, wrong abstraction for USB-LPT adapters
- CUPS raw queue configuration via `lpadmin`: Deprecated since 2018, shows warning. Raw printing via `lp -o raw` still works.
- `/dev/usb/lp*` on macOS: Never existed. macOS uses CUPS/IOKit exclusively.

## Open Questions

1. **CUPS `lp` per-line latency: is it acceptable for typewriter effect?**
   - What we know: `lp -o raw` buffers until EOF when used via pipe. Per-line `subprocess.run()` invocation means ~10-50ms subprocess overhead per line.
   - What's unclear: Whether the subprocess startup overhead causes visible pauses at line boundaries.
   - Recommendation: Implement per-line flushing for v1. Test with real hardware. If latency is unacceptable, add a `--device` direct path as the recommended fast mode. Document that `--device` gives smoother character-by-character output.

2. **CUPS raw queue deprecation: when will it actually be removed?**
   - What we know: Deprecated since 2018 (issue #5269). Still functional in 2026. No removal milestone assigned.
   - What's unclear: Whether macOS Tahoe (26) or a future macOS version will remove it.
   - Recommendation: Design with the CUPS path as primary but ensure the `--device` direct path works as a complete fallback. If CUPS removes raw support, users can still use `--device`.

3. **USB-LPT adapter kernel driver conflicts on macOS**
   - What we know: macOS CUPS backend claims the USB device exclusively. pyusb cannot detach kernel drivers without root on macOS. libusb 1.0.25+ added `detach_kernel_driver()` for macOS but it requires elevated privileges.
   - What's unclear: Whether ANY direct USB communication path works on macOS without CUPS intermediation.
   - Recommendation: Do NOT pursue direct USB via pyusb on macOS for v1. CUPS is the only reliable macOS path. pyusb is a Linux-only fallback option.

4. **Does `make_output_fn` need to become async?**
   - What we know: Current `make_output_fn` is synchronous. Printer writes should be non-blocking.
   - What's unclear: Whether wrapping printer.write in a resilient closure (that catches errors synchronously, since the actual I/O happens via CUPS subprocess or buffered file write) is sufficient, or whether the output_fn signature needs to change to async.
   - Recommendation: Keep `make_output_fn` synchronous. The CupsPrinterDriver buffers per-line (synchronous list append), and FilePrinterDriver writes are fast enough with unbuffered file I/O. The `lp` subprocess invocation on line flush can run in a background thread via a fire-and-forget pattern. Only make async if testing reveals event loop blocking.

## Sources

### Primary (HIGH confidence)
- [CUPS `lp` man page](https://www.cups.org/doc/man-lp.html) -- `-o raw` option, stdin pipe support
- [CUPS `lpstat` man page](https://www.cups.org/doc/man-lpstat.html) -- `-v` flag output format for device URIs
- [CUPS Command-Line Printing Options](https://www.cups.org/doc/options.html) -- raw printing, printer selection
- [CUPS `lpadmin` man page](https://www.cups.org/doc/man-lpadmin.html) -- raw queue setup
- [Python subprocess docs](https://docs.python.org/3/library/subprocess.html) -- Popen, PIPE, timeout
- [Python asyncio.to_thread() docs](https://docs.python.org/3/library/asyncio-task.html) -- non-blocking I/O delegation
- [PyUSB tutorial](https://github.com/pyusb/pyusb/blob/master/docs/tutorial.rst) -- USB device find, class matching, bulk write

### Secondary (MEDIUM confidence)
- [CUPS raw queue deprecation (issue #5269)](https://github.com/apple/cups/issues/5269) -- deprecated in 2018, no removal
- [CUPS raw queue removal planning (issue #5271)](https://github.com/apple/cups/issues/5271) -- future planning, no timeline
- [CUPS raw queue alternatives discussion (issue #6150)](https://github.com/apple/cups/issues/6150) -- community workarounds
- [python-escpos USB-LPT warning](https://python-escpos.readthedocs.io/en/latest/user/printers.html) -- "Stay away from USB-to-Parallel-Adapter since they are unreliable"
- [libusb macOS kernel driver discussion (#1321)](https://github.com/libusb/libusb/discussions/1321) -- macOS detach limitations
- [pyusb kernel driver detach issue (#374)](https://github.com/pyusb/pyusb/issues/374) -- macOS libusb 1.0.25+ support
- [pyusb resource disposal discussion (#432)](https://github.com/pyusb/pyusb/discussions/432) -- proper cleanup on disconnect

### Tertiary (LOW confidence)
- [lpstat output format examples](https://commandmasters.com/commands/lpstat-common/) -- "device for NAME: URI" format
- [macOS USB device files behavior](https://discussions.apple.com/thread/2041368) -- no /dev/usb/lp* on macOS
- [CUPS raw printing to dot-matrix](https://www.linuxquestions.org/questions/linux-hardware-18/printing-to-a-dot-matrix-printer-with-raw-ascii-from-cups-4175623914/) -- community experience reports
- [CUPs in macOS (2026)](https://dsin.wordpress.com/2026/02/09/cups-in-macos/) -- recent CUPS macOS guide

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- stdlib subprocess + CUPS is well-documented and universally available
- Architecture: HIGH -- Strategy pattern for printer backends, integration with existing make_output_fn is clean
- Discovery (CUPS): MEDIUM -- lpstat output format is not formally specified, but consistent across versions; regex parsing is brittle but adequate
- Discovery (pyusb): LOW on macOS (kernel driver conflicts), MEDIUM on Linux
- Graceful disconnect: HIGH -- try/except + boolean flag is a well-proven pattern
- CUPS raw queue longevity: MEDIUM -- works today, deprecated since 2018, no removal date

**Research date:** 2026-02-15
**Valid until:** 2026-03-15 (stable domain, CUPS rarely changes)
