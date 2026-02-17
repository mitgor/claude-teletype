# Phase 10: Printer Profiles - Research

**Researched:** 2026-02-17
**Domain:** Printer control codes (ESC/P, PPDS, PCL, Juki), USB device identification, TOML profile configuration
**Confidence:** HIGH (control codes), MEDIUM (USB auto-detect), LOW (Juki 9100 specifics)

## Summary

Phase 10 replaces the current hard-coded `--juki` boolean flag with a generalized printer profile system. A profile is a named bundle of ESC sequences (init, reset, line spacing, character pitch, newline strategy) plus optional USB vendor:product IDs for auto-detection. The system needs five built-in profiles (Juki, Epson ESC/P, IBM PPDS, HP PCL, generic) and support for user-defined custom profiles in the TOML config file.

The core architectural change is extracting the current `JukiPrinterDriver` wrapper pattern into a generic `ProfilePrinterDriver` that reads its ESC sequences from a profile dataclass rather than hard-coded class constants. The profile selection flows through the existing three-layer config merge: `--printer juki` CLI flag > `CLAUDE_TELETYPE_PRINTER` env var > `[printer] profile = "juki"` in config > `"generic"` default. USB auto-detection is an optional bonus layer that runs before the config merge when no explicit profile is set.

The TOML config representation uses `[printer.profiles.<name>]` tables for custom profiles, keeping the schema flat and readable. Built-in profiles are defined in Python code (not loaded from TOML) to avoid shipping/locating external data files. The existing `discover_printer()` function is extended to accept a profile name and return the correct wrapping driver.

**Primary recommendation:** Create a `PrinterProfile` dataclass for profile data, a registry of built-in profiles, a generic `ProfilePrinterDriver` wrapper (replacing `JukiPrinterDriver`), and extend `discover_printer()` to accept profile selection with USB auto-detection fallback.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PRNT-01 | User can select a named printer profile via `--printer <name>` or config default | New `--printer` CLI flag (replaces `--juki`). Config key `[printer] profile = "juki"`. Three-layer merge resolves effective profile name. Profile registry maps name to `PrinterProfile` dataclass. |
| PRNT-02 | User gets built-in profiles for Juki, Epson ESC/P, IBM PPDS, HP PCL, and generic printers | Five `PrinterProfile` instances defined in `profiles.py` with verified ESC sequences (see Control Codes section). Generic profile sends no ESC codes. |
| PRNT-03 | User can define custom printer profiles with arbitrary ESC sequences in config file | TOML `[printer.profiles.<name>]` tables with `init`, `reset`, `newline`, `line_spacing`, `char_pitch` keys as hex-encoded byte strings. Loaded by `load_config()` and merged into profile registry. |
| PRNT-04 | Printer profile auto-selects when a USB device matches a profile's vendor:product ID | Each built-in profile stores optional `usb_vendor_id` and `usb_product_id`. During discovery, `pyusb` enumerates devices; if a connected device matches a profile's VID:PID, that profile is auto-selected. Falls back to config/CLI selection if no match. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| dataclasses | stdlib | `PrinterProfile` dataclass for profile schema | Type-safe, default values, `asdict()` for serialization |
| tomllib | stdlib (3.11+) | Read custom profiles from TOML config | Already used by config module |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pyusb | >=1.3.0 (optional) | USB VID:PID enumeration for auto-detection | Only for PRNT-04 auto-detect feature |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| In-code profile definitions | External TOML/JSON profile files | Shipping/locating data files adds complexity; in-code is simpler for 5 built-in profiles |
| Hex-encoded ESC strings in TOML | Base64-encoded bytes | Hex is more readable for printer people who think in ESC codes; `bytes.fromhex()` is stdlib |
| Single `ProfilePrinterDriver` | Keep `JukiPrinterDriver` + add more specific drivers | One generic driver avoids N driver classes; profile dataclass carries the differences |

**Installation:**
No new dependencies. `pyusb` is already an optional dependency (`[project.optional-dependencies] usb`).

## Architecture Patterns

### Recommended Project Structure
```
src/claude_teletype/
+-- profiles.py         # NEW: PrinterProfile dataclass, built-in registry, TOML loading
+-- printer.py          # MODIFIED: ProfilePrinterDriver replaces JukiPrinterDriver
+-- config.py           # MODIFIED: Add printer.profile field, custom profile loading
+-- cli.py              # MODIFIED: --printer flag replaces --juki, auto-detect logic
```

### Pattern 1: PrinterProfile Dataclass

**What:** A dataclass that bundles all printer-specific behavior into a single named unit.

**When to use:** Every printer profile, whether built-in or custom.

**Example:**
```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PrinterProfile:
    """A named bundle of printer control sequences and behavior."""
    name: str
    description: str = ""

    # ESC sequences as raw bytes (empty = no-op)
    init_sequence: bytes = b""       # Sent once on first write
    reset_sequence: bytes = b""      # Sent on close/eject
    line_spacing: bytes = b""        # Sent after init for line spacing setup
    char_pitch: bytes = b""          # Sent after init for character pitch setup

    # Newline strategy
    crlf: bool = False               # True = CR+LF, False = LF only

    # Re-init after newline (Juki needs this for CUPS per-line jobs)
    reinit_on_newline: bool = False
    reinit_sequence: bytes = b""     # Sent after each newline if reinit_on_newline

    # Form feed on close
    formfeed_on_close: bool = True

    # USB auto-detection (optional)
    usb_vendor_id: int | None = None
    usb_product_id: int | None = None

    # Paper width in columns (for word wrap)
    columns: int = 80
```

### Pattern 2: Built-in Profile Registry

**What:** A dict mapping profile names to `PrinterProfile` instances, defined in Python.

**When to use:** Profile lookup by name from CLI/config.

**Example:**
```python
BUILTIN_PROFILES: dict[str, PrinterProfile] = {
    "generic": PrinterProfile(
        name="generic",
        description="Generic printer, no ESC codes, LF-only newlines",
    ),
    "juki": PrinterProfile(
        name="juki",
        description="Juki 6100/9100 daisywheel impact printer",
        init_sequence=b"\x1b\x1aI",        # ESC SUB I (full reset)
        line_spacing=b"\x1b\x1e\x09",       # ESC RS 9 (1/6" spacing)
        char_pitch=b"\x1bQ",                 # ESC Q (disable proportional)
        crlf=True,
        reinit_on_newline=True,
        reinit_sequence=b"\x1b\x1e\x09\x1bQ",  # LINE_SPACING + FIXED_PITCH
        formfeed_on_close=True,
        columns=80,
    ),
    "escp": PrinterProfile(
        name="escp",
        description="Epson ESC/P dot matrix (FX/LQ/LX series)",
        init_sequence=b"\x1b@",              # ESC @ (initialize printer)
        reset_sequence=b"\x1b@",             # ESC @ (reset on close)
        line_spacing=b"\x1b\x32",            # ESC 2 (6 LPI)
        char_pitch=b"\x1bP",                 # ESC P (10 CPI pica)
        crlf=False,                          # ESC/P uses LF only
        formfeed_on_close=True,
        usb_vendor_id=0x04B8,                # Seiko Epson Corp
        columns=80,
    ),
    "ppds": PrinterProfile(
        name="ppds",
        description="IBM PPDS (Proprinter compatible)",
        init_sequence=b"\x1b@",              # ESC @ (initialize)
        reset_sequence=b"\x1b@",             # ESC @ (reset)
        line_spacing=b"\x1b\x32",            # ESC 2 (6 LPI)
        char_pitch=b"\x12",                  # DC2 (10 CPI default)
        crlf=False,
        formfeed_on_close=True,
        columns=80,
    ),
    "pcl": PrinterProfile(
        name="pcl",
        description="HP PCL5 (LaserJet/DeskJet/OfficeJet)",
        init_sequence=b"\x1bE",              # ESC E (reset)
        reset_sequence=b"\x1bE",             # ESC E (reset)
        line_spacing=b"\x1b&l6D",            # 6 LPI
        char_pitch=b"\x1b(s10H",             # 10 CPI
        crlf=False,
        formfeed_on_close=True,
        usb_vendor_id=0x03F0,                # HP Inc
        columns=80,
    ),
}


def get_profile(name: str) -> PrinterProfile:
    """Look up a printer profile by name (case-insensitive)."""
    key = name.lower().strip()
    if key not in BUILTIN_PROFILES:
        raise ValueError(
            f"Unknown printer profile: {name!r}. "
            f"Available: {', '.join(sorted(BUILTIN_PROFILES))}"
        )
    return BUILTIN_PROFILES[key]
```

### Pattern 3: ProfilePrinterDriver (Replaces JukiPrinterDriver)

**What:** A generic wrapper driver that applies a profile's ESC sequences to any inner driver.

**When to use:** Whenever a non-generic profile is selected.

**Example:**
```python
class ProfilePrinterDriver:
    """Wraps an inner PrinterDriver with profile-specific ESC sequences.

    Replaces the old JukiPrinterDriver with a data-driven approach.
    The profile dataclass carries all the init/reset/newline behavior.
    """

    def __init__(self, inner: PrinterDriver, profile: PrinterProfile) -> None:
        self._inner = inner
        self._profile = profile
        self._initialized = False

    def _send_raw(self, data: bytes) -> None:
        for b in data:
            self._inner.write(chr(b))

    def _ensure_init(self) -> None:
        if not self._initialized:
            self._initialized = True
            init = (
                self._profile.init_sequence
                + self._profile.line_spacing
                + self._profile.char_pitch
            )
            if init:
                self._send_raw(init)

    @property
    def is_connected(self) -> bool:
        return self._inner.is_connected

    def write(self, char: str) -> None:
        if not self._inner.is_connected:
            return
        self._ensure_init()
        if char == "\n":
            if self._profile.crlf:
                self._inner.write("\r")
            self._inner.write("\n")
            if self._profile.reinit_on_newline and self._profile.reinit_sequence:
                self._send_raw(self._profile.reinit_sequence)
        else:
            self._inner.write(char)

    def close(self) -> None:
        if self._initialized and self._inner.is_connected:
            if self._profile.formfeed_on_close:
                self._inner.write("\f")
            if self._profile.reset_sequence:
                self._send_raw(self._profile.reset_sequence)
        self._inner.close()
```

### Pattern 4: USB Auto-Detection by VID:PID

**What:** Enumerate connected USB devices and match against profile VID:PID fields.

**When to use:** When no explicit `--printer` flag is set and no config default is set.

**Example:**
```python
def auto_detect_profile() -> PrinterProfile | None:
    """Match a connected USB device to a built-in profile's VID:PID.

    Returns the matching profile, or None if no match found.
    Requires pyusb (optional dependency).
    """
    try:
        import usb.core
    except ImportError:
        return None

    try:
        devices = list(usb.core.find(find_all=True))
    except Exception:
        return None

    # Build lookup: (vid, pid) -> profile for profiles with USB IDs
    vid_pid_map: dict[tuple[int, int | None], PrinterProfile] = {}
    for profile in BUILTIN_PROFILES.values():
        if profile.usb_vendor_id is not None:
            key = (profile.usb_vendor_id, profile.usb_product_id)
            vid_pid_map[key] = profile

    for dev in devices:
        vid, pid = dev.idVendor, dev.idProduct
        # Exact VID+PID match
        if (vid, pid) in vid_pid_map:
            return vid_pid_map[(vid, pid)]
        # VID-only match (PID is None in profile = match any product from that vendor)
        if (vid, None) in vid_pid_map:
            return vid_pid_map[(vid, None)]

    return None
```

### Pattern 5: Custom Profiles in TOML Config

**What:** User-defined profiles in the config file using hex-encoded byte strings.

**When to use:** PRNT-03 -- users with printers not covered by built-in profiles.

**Example TOML:**
```toml
[printer]
profile = "my-custom-printer"

[printer.profiles.my-custom-printer]
description = "My vintage daisy wheel"
init = "1b40"          # ESC @ in hex
reset = "1b40"
line_spacing = "1b32"  # ESC 2
char_pitch = "1b50"    # ESC P
crlf = true
columns = 132
# Optional USB auto-detect
usb_vendor_id = "04b8"
usb_product_id = "0202"
```

**Python loading:**
```python
def load_custom_profiles(raw_toml: dict) -> dict[str, PrinterProfile]:
    """Parse custom profiles from TOML [printer.profiles.*] tables."""
    profiles = {}
    printer_section = raw_toml.get("printer", {})
    custom_profiles = printer_section.get("profiles", {})

    for name, data in custom_profiles.items():
        profiles[name] = PrinterProfile(
            name=name,
            description=data.get("description", ""),
            init_sequence=bytes.fromhex(data.get("init", "")),
            reset_sequence=bytes.fromhex(data.get("reset", "")),
            line_spacing=bytes.fromhex(data.get("line_spacing", "")),
            char_pitch=bytes.fromhex(data.get("char_pitch", "")),
            crlf=data.get("crlf", False),
            reinit_on_newline=data.get("reinit_on_newline", False),
            reinit_sequence=bytes.fromhex(data.get("reinit_sequence", "")),
            formfeed_on_close=data.get("formfeed_on_close", True),
            usb_vendor_id=int(data["usb_vendor_id"], 16) if "usb_vendor_id" in data else None,
            usb_product_id=int(data["usb_product_id"], 16) if "usb_product_id" in data else None,
            columns=data.get("columns", 80),
        )
    return profiles
```

### Pattern 6: Config Integration

**What:** Extend `TeletypeConfig` with a `printer_profile` field and update the CLI.

**Example:**
```python
# In config.py -- extend TeletypeConfig
@dataclass
class TeletypeConfig:
    # ... existing fields ...
    printer_profile: str = "generic"   # NEW: default profile name

# In cli.py -- replace --juki with --printer
@app.callback(invoke_without_command=True)
def main(
    # ... existing params ...
    printer: str = typer.Option(None, "--printer", "-p", help="Printer profile name"),
    # Remove: juki: bool = typer.Option(False, "--juki", ...)
):
    # Profile resolution:
    # 1. CLI --printer flag (highest priority)
    # 2. CLAUDE_TELETYPE_PRINTER_PROFILE env var
    # 3. config file [printer] profile = "..."
    # 4. USB auto-detect (if no explicit selection)
    # 5. "generic" (default)
    ...
```

### Anti-Patterns to Avoid

- **One driver class per printer model:** Leads to class explosion. Use one `ProfilePrinterDriver` with data-driven behavior from `PrinterProfile`.
- **Loading profiles from external files at runtime:** Shipping/locating TOML/JSON profile files is fragile. Built-in profiles belong in Python code. Only CUSTOM profiles come from the config file.
- **Storing raw bytes in TOML:** TOML has no native bytes type. Use hex-encoded strings (`"1b40"`) and convert with `bytes.fromhex()`. Do NOT use Python `b"\x1b@"` syntax in TOML -- it will be parsed as a regular string.
- **Breaking backward compatibility suddenly:** The `--juki` flag must continue to work (as an alias for `--printer juki`) for at least one version. Deprecation warning, not hard removal.
- **USB auto-detection overriding explicit user choice:** If the user sets `--printer generic` explicitly, do NOT override with USB auto-detection. Auto-detect is a FALLBACK, not an override.
- **Matching USB VID only without checking printer class:** Matching Epson VID `0x04B8` alone would match Epson scanners and cameras. Filter to USB printer class (interface class 7) first, then match VID:PID against profiles.

## Printer Control Codes Reference

### Juki 6100 (Daisywheel Impact) -- VERIFIED from manual
| Function | Sequence | Hex | Source |
|----------|----------|-----|--------|
| Initialize (full reset) | ESC SUB I | `1B 1A 49` | Juki 6100 Operation Manual Sep83 |
| Line spacing (1/6") | ESC RS 9 | `1B 1E 09` | Juki 6100 Operation Manual Sep83 |
| Disable proportional | ESC Q | `1B 51` | Juki 6100 Operation Manual Sep83 |
| Enable proportional | ESC P | `1B 50` | Juki 6100 Operation Manual Sep83 |
| Remote reset | ESC CR P | `1B 0D 50` | Juki 6100 Operation Manual Sep83 |
| Newline strategy | CR + LF | `0D 0A` | Manual + existing code |
| Form feed | FF | `0C` | Standard |

**Note:** The Juki 9100 codes are extrapolated from the 6100 -- this is a known blocker. The existing codebase already uses these codes and they work with USB-LPT adapters, but hardware verification against an actual 9100 is still needed.

### Epson ESC/P (Dot Matrix) -- HIGH confidence
| Function | Sequence | Hex | Source |
|----------|----------|-----|--------|
| Initialize printer | ESC @ | `1B 40` | Epson ESC/P Reference Manual; helppc |
| 6 lines per inch | ESC 2 | `1B 32` | Epson ESC/P Reference Manual |
| 8 lines per inch | ESC 0 | `1B 30` | Epson ESC/P Reference Manual |
| Pica (10 CPI) | ESC P | `1B 50` | Epson ESC/P Reference Manual |
| Elite (12 CPI) | ESC M | `1B 4D` | Epson ESC/P Reference Manual |
| Newline strategy | LF only | `0A` | Standard ESC/P behavior |
| Form feed | FF | `0C` | Standard |

### IBM PPDS (Proprinter Compatible) -- MEDIUM confidence
| Function | Sequence | Hex | Source |
|----------|----------|-----|--------|
| Initialize | ESC @ | `1B 40` | IBM support docs; compatible with ESC/P |
| 6 lines per inch | ESC 2 | `1B 32` | IBM PPDS documentation |
| 10 CPI (default) | DC2 | `12` | IBM PPDS documentation |
| Condensed (17.1 CPI) | SI | `0F` | IBM PPDS documentation |
| 12 CPI | ESC : | `1B 3A` | IBM PPDS documentation |
| Newline strategy | LF only | `0A` | Standard |
| Form feed | FF | `0C` | Standard |

### HP PCL5 (LaserJet/DeskJet) -- HIGH confidence
| Function | Sequence | Hex | Source |
|----------|----------|-----|--------|
| Reset printer | ESC E | `1B 45` | HP PCL5 Technical Reference Manual |
| 6 LPI | ESC &l 6 D | `1B 26 6C 36 44` | HP PCL Commands Reference |
| 8 LPI | ESC &l 8 D | `1B 26 6C 38 44` | HP PCL Commands Reference |
| 10 CPI pitch | ESC (s 10 H | `1B 28 73 31 30 48` | HP PCL Commands Reference |
| Portrait orientation | ESC &l 0 O | `1B 26 6C 30 4F` | HP PCL Commands Reference |
| Newline strategy | LF only | `0A` | Standard |
| Form feed | FF | `0C` | Standard |

### Generic (No Control Codes)
| Function | Sequence | Hex |
|----------|----------|-----|
| Init | (none) | - |
| Reset | (none) | - |
| Newline | LF only | `0A` |
| Form feed | FF | `0C` |

## USB Vendor/Product IDs for Auto-Detection

| Printer Family | USB VID | USB PID | Confidence | Notes |
|----------------|---------|---------|------------|-------|
| Epson (Seiko Epson Corp) | `0x04B8` | varies by model | HIGH | Well-documented. Filter by USB printer class (7) to exclude scanners. |
| HP Inc | `0x03F0` | varies by model | HIGH | Well-documented. Many LaserJet models. Filter by printer class. |
| IBM | `0x04B3` | varies | MEDIUM | Less common on USB. Most PPDS printers are parallel-only. |
| Juki | unknown | unknown | LOW | Juki 6100 is parallel-only (Centronics). Connected via USB-LPT adapter, so USB VID:PID is the ADAPTER's, not Juki's. Auto-detection by VID:PID is NOT possible for Juki. |

**Critical finding on USB-LPT adapters:** Vintage parallel printers (Juki, many dot matrix) connect through USB-to-parallel adapters. These adapters have their own VID:PID (e.g., `4348:5584` WinChipHead CH34x, `067b:2305` Prolific PL2305, `04b4:4100` Cypress). The adapter does NOT pass through the printer's identity. This means:
- Auto-detection by printer VID:PID only works for native USB printers (modern Epson, HP).
- Printers behind USB-LPT adapters cannot be auto-detected by VID:PID -- the user must select the profile manually.
- The auto-detect feature (PRNT-04) is most useful for native USB printers. For adapter-connected printers, the `--printer` flag or config default is required.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Hex byte parsing | Custom parser for ESC sequences | `bytes.fromhex()` | Stdlib, handles edge cases, well-tested |
| USB device enumeration | Custom ioctl/sysfs parsing | `pyusb` `usb.core.find()` | Cross-platform, already a project dependency |
| Profile data structure | Nested dicts with string keys | `dataclass(frozen=True)` | Type-safe, IDE completion, immutable by default |
| Profile name validation | Manual string comparison | Registry dict lookup with `KeyError` -> `ValueError` | Single source of truth for valid names |

**Key insight:** The profile system is a data-driven wrapper, not a code-driven one. All printer-specific differences live in the `PrinterProfile` dataclass fields, not in conditional logic. This makes adding new profiles trivial (just add a dict entry).

## Common Pitfalls

### Pitfall 1: Binary ESC Sequences in TOML
**What goes wrong:** User tries to put raw escape characters in TOML strings. TOML does not support arbitrary binary data in strings.
**Why it happens:** Printer people think in hex (`\x1b@`) but TOML strings are Unicode text.
**How to avoid:** Use hex-encoded strings in TOML (`init = "1b40"`) and convert with `bytes.fromhex()` in Python. Document this clearly in the config template comments.
**Warning signs:** `ValueError` from `bytes.fromhex()`, garbled output on printer.

### Pitfall 2: USB Auto-Detection Matches Non-Printers
**What goes wrong:** Matching Epson VID `0x04B8` matches an Epson scanner or camera, not a printer.
**Why it happens:** USB VID identifies the manufacturer, not the device class.
**How to avoid:** ALWAYS filter by USB interface class 7 (printer) BEFORE matching VID:PID. The existing `discover_usb_device()` already does this -- reuse that filter logic.
**Warning signs:** Profile auto-selects for a connected scanner.

### Pitfall 3: ESC Sequences Split Across USB Transfers
**What goes wrong:** Multi-byte ESC sequences (e.g., `1B 1E 09`) are split across separate USB bulk transfers when sent character-by-character through the adapter.
**Why it happens:** The `_send_raw()` method writes one byte at a time through the inner driver, and each `write()` call may be a separate USB transfer.
**How to avoid:** For USB drivers, batch the entire ESC sequence into a single write. The existing `JukiPrinterDriver._send_raw()` writes byte-by-byte, which works for CUPS (buffered) but may fail for `UsbPrinterDriver` (immediate). Consider adding a `write_bytes(data: bytes)` method to `PrinterDriver` protocol for batch writes, or buffer in `ProfilePrinterDriver`.
**Warning signs:** Init sequences partially applied, garbled output, printer ignores some ESC codes.

### Pitfall 4: Breaking the `--juki` Flag
**What goes wrong:** Removing `--juki` breaks existing users' scripts and muscle memory.
**Why it happens:** Direct flag removal without deprecation period.
**How to avoid:** Keep `--juki` as a deprecated alias that internally sets `profile = "juki"`. Emit a deprecation warning suggesting `--printer juki`. Remove in v1.3.
**Warning signs:** User scripts fail, CI pipelines break.

### Pitfall 5: Custom Profile Overwriting Built-in
**What goes wrong:** User defines `[printer.profiles.escp]` in config, shadowing the built-in.
**Why it happens:** Custom profiles and built-ins share the same namespace.
**How to avoid:** Two options: (a) custom profiles override built-ins intentionally (treat as feature -- "user knows best"), or (b) prefix custom names (fragile, annoying). Recommend option (a): custom profiles CAN override built-ins. Document this behavior.
**Warning signs:** None if intentional; confusing behavior if accidental.

### Pitfall 6: Config Module Flattening Breaks Nested Tables
**What goes wrong:** The current `load_config()` flattens all TOML sections into a flat dict. Nested tables like `[printer.profiles.juki]` would be lost or mishandled.
**Why it happens:** Current code does `flat.update(value)` for each section, which overwrites the `profiles` key.
**How to avoid:** Load custom profiles BEFORE flattening. Extract `raw["printer"]["profiles"]` first, then flatten the rest into `TeletypeConfig` fields. Alternatively, handle the `printer` section specially.
**Warning signs:** Custom profiles silently ignored, `KeyError` during profile loading.

## Code Examples

### Example 1: Complete profiles.py Module

```python
"""Printer profiles: named bundles of ESC sequences and behavior.

Built-in profiles for Juki, Epson ESC/P, IBM PPDS, HP PCL, and generic.
Custom profiles loaded from TOML config [printer.profiles.*] tables.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PrinterProfile:
    """Named bundle of printer control sequences."""
    name: str
    description: str = ""
    init_sequence: bytes = b""
    reset_sequence: bytes = b""
    line_spacing: bytes = b""
    char_pitch: bytes = b""
    crlf: bool = False
    reinit_on_newline: bool = False
    reinit_sequence: bytes = b""
    formfeed_on_close: bool = True
    usb_vendor_id: int | None = None
    usb_product_id: int | None = None
    columns: int = 80


BUILTIN_PROFILES: dict[str, PrinterProfile] = {
    "generic": PrinterProfile(name="generic", description="No ESC codes"),
    "juki": PrinterProfile(
        name="juki",
        description="Juki 6100/9100 daisywheel",
        init_sequence=b"\x1b\x1aI",
        line_spacing=b"\x1b\x1e\x09",
        char_pitch=b"\x1bQ",
        crlf=True,
        reinit_on_newline=True,
        reinit_sequence=b"\x1b\x1e\x09\x1bQ",
        formfeed_on_close=True,
    ),
    "escp": PrinterProfile(
        name="escp",
        description="Epson ESC/P dot matrix",
        init_sequence=b"\x1b@",
        reset_sequence=b"\x1b@",
        line_spacing=b"\x1b\x32",
        char_pitch=b"\x1bP",
        usb_vendor_id=0x04B8,
    ),
    "ppds": PrinterProfile(
        name="ppds",
        description="IBM PPDS Proprinter",
        init_sequence=b"\x1b@",
        reset_sequence=b"\x1b@",
        line_spacing=b"\x1b\x32",
        char_pitch=b"\x12",
    ),
    "pcl": PrinterProfile(
        name="pcl",
        description="HP PCL5 LaserJet",
        init_sequence=b"\x1bE",
        reset_sequence=b"\x1bE",
        line_spacing=b"\x1b&l6D",
        char_pitch=b"\x1b(s10H",
        usb_vendor_id=0x03F0,
    ),
}
```

### Example 2: TOML Config with Custom Profile

```toml
[printer]
# Select active profile (built-in or custom)
profile = "my-daisy"

# Custom profile definition
[printer.profiles.my-daisy]
description = "My vintage daisywheel"
init = "1b40"
reset = "1b40"
line_spacing = "1b32"
crlf = true
formfeed_on_close = true
columns = 132
```

### Example 3: Profile Resolution in CLI

```python
def resolve_printer_profile(
    cli_printer: str | None,
    config: TeletypeConfig,
    custom_profiles: dict[str, PrinterProfile],
) -> PrinterProfile:
    """Resolve the effective printer profile.

    Priority: CLI --printer > config profile > USB auto-detect > generic
    """
    # Merge custom profiles into registry
    all_profiles = {**BUILTIN_PROFILES, **custom_profiles}

    # Explicit selection (CLI or config)
    name = cli_printer or config.printer_profile
    if name and name != "generic":
        if name in all_profiles:
            return all_profiles[name]
        raise typer.BadParameter(
            f"Unknown printer profile: {name!r}. "
            f"Available: {', '.join(sorted(all_profiles))}"
        )

    # USB auto-detection fallback
    detected = auto_detect_profile()
    if detected is not None:
        return detected

    return all_profiles.get(name, BUILTIN_PROFILES["generic"])
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hard-coded `JukiPrinterDriver` with class constants | Data-driven `ProfilePrinterDriver` with profile dataclass | This phase | Adding new printer support = adding a dict entry, not a new class |
| `--juki` boolean flag | `--printer <name>` string flag | This phase | Extensible to any number of printers |
| No USB auto-detection for profile | VID:PID matching during discovery | This phase | Zero-config for native USB printers |

**Deprecated/outdated:**
- `--juki` flag: Will be kept as deprecated alias for one version, then removed.
- `JukiPrinterDriver` class: Replaced by `ProfilePrinterDriver` with Juki profile data.

## Open Questions

1. **Juki 9100 control codes**
   - What we know: 6100 codes are verified from the Sep83 operation manual. 9100 codes are extrapolated from 6100 and work with the existing codebase + USB-LPT adapter.
   - What's unclear: Whether the 9100 has additional/different ESC sequences. No 9100 manual found online.
   - Recommendation: Ship with 6100-verified codes (they work). Mark as "6100/9100" in the profile description. Accept hardware verification as a future task.

2. **USB auto-detect for adapter-connected printers**
   - What we know: USB-LPT adapters expose THEIR VID:PID, not the printer's. Common adapters: WinChipHead CH34x (`4348:5584`), Prolific PL2305 (`067b:2305`).
   - What's unclear: Whether we should maintain a list of known USB-LPT adapter VID:PIDs and prompt the user for a profile when one is detected.
   - Recommendation: For v1.2, do NOT try to detect adapters. Auto-detect only native USB printers. Adapter users must use `--printer` or config. Document this limitation. Consider adapter detection as v1.3 enhancement.

3. **Batch ESC writes for USB drivers**
   - What we know: The current `_send_raw()` writes byte-by-byte through `write(chr(b))`. This works for CUPS (buffered) but may split ESC sequences across USB bulk transfers.
   - What's unclear: Whether this is a real problem in practice (the existing Juki driver does this and reportedly works).
   - Recommendation: Keep byte-by-byte for now (proven to work). Add a `write_raw(data: bytes)` method to `UsbPrinterDriver` as a future optimization if ESC sequence splitting is observed.

4. **IBM PPDS init sequence confidence**
   - What we know: ESC @ (`1B 40`) is documented as the initialize command in multiple sources, and it is shared with ESC/P.
   - What's unclear: Whether all PPDS printers respond to ESC @, or if some require a different init.
   - Recommendation: Ship with ESC @ as the PPDS init. It is the most widely documented command. Note LOW-MEDIUM confidence in the profile description.

5. **`--juki` backward compatibility duration**
   - What we know: `--juki` is used in the CLI, in config (`juki = false`), and in the teletype module.
   - What's unclear: How long to maintain backward compat.
   - Recommendation: Keep `--juki` as a deprecated alias for `--printer juki` in v1.2. Emit a deprecation warning. Plan removal for v1.3. The `juki` config key should also be deprecated in favor of `profile = "juki"`.

## Sources

### Primary (HIGH confidence)
- **Juki 6100 Operation Manual Sep83** (archive.org) - ESC sequences for Juki daisywheel: https://archive.org/stream/bitsavers_jukiJuki61p83_7056599/Juki_6100_Operation_Manual_Sep83_djvu.txt
- **Epson ESC/P control codes** (stanislavs.org/helppc) - ESC @, line spacing, pitch commands with hex values: https://stanislavs.org/helppc/epson_printer_codes.html
- **HP PCL Commands Reference** (people.wou.edu) - ESC E reset, LPI, CPI sequences: https://people.wou.edu/~soukupm/pcl_commands.htm
- **IBM PPDS and ESC/P control codes** (ibm.com) - PPDS CR/LF/FF, line spacing, pitch: https://www.ibm.com/support/pages/list-ibm-ppds-and-epson-escp-control-codes-and-escape-sequences
- **Epson USB VID 0x04B8** (devicehunt.com) - Epson USB vendor ID: https://devicehunt.com/view/type/usb/vendor/04B8
- **HP USB VID 0x03F0** (the-sz.com) - HP USB vendor ID: https://the-sz.com/products/usbid/index.php?v=0x03F0
- **Existing codebase** - `printer.py`, `config.py`, `cli.py`, `teletype.py`, `test_printer.py`, `test_config.py`

### Secondary (MEDIUM confidence)
- **HP PCL5 Technical Reference** (hp.com/ctg/Manual/bpl13210.pdf) - PCL escape command syntax
- **IBM Proprinter Programmers Guide** (psi-matrix.eu) - PPDS command reference
- **Epson ESC/P Reference Manual** (files.support.epson.com) - Full ESC/P2 command set
- **USB-LPT adapter identification** (ubuntu wiki, launchpad bugs) - Common adapter VID:PIDs and limitations

### Tertiary (LOW confidence)
- **Juki 9100 codes** - Extrapolated from 6100 manual, no independent verification. Marked as known blocker.
- **IBM PPDS ESC @ init** - Confirmed in multiple sources but not independently tested against hardware.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, dataclass + existing pyusb + tomllib
- Architecture: HIGH -- data-driven profile pattern is well-understood, existing JukiPrinterDriver proves the wrapper approach works
- Control codes (Epson, HP): HIGH -- documented in official manuals with hex values
- Control codes (IBM PPDS): MEDIUM -- ESC @ init confirmed across sources but not hardware-tested
- Control codes (Juki): MEDIUM -- 6100 verified from manual, 9100 extrapolated
- USB auto-detect: MEDIUM -- works for native USB printers; adapter-connected printers cannot be auto-detected
- Pitfalls: HIGH -- ESC sequence splitting, TOML binary encoding, backward compat identified from codebase analysis

**Research date:** 2026-02-17
**Valid until:** 180 days (printer control codes are decades-stable; USB IDs rarely change)
