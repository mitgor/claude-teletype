# Stack Research — v1.6 "Printer Fleet & Standalone"

**Domain:** USB dot-matrix printer detection + ESC/P control-code generation + standalone packaging (subsequent milestone, additive to shipped v1.5)
**Researched:** 2026-06-12
**Confidence:** HIGH (bridge-chip VID:PIDs from canonical usb.ids; PyInstaller version + hooks verified on PyPI/docs; ESC/POS-vs-ESC/P library scope verified via Context7 + PyPI)

> Scope note: The validated v1.5 stack (Python 3.12+, Textual 7.x, Rich, Typer, sounddevice/numpy, openai SDK, tomllib/platformdirs, pyusb optional) is NOT re-researched. This document covers ONLY the three v1.6 questions: (a) broad USB detection + VID:PID data, (b) PyInstaller packaging, (c) ESC/P command-generation libraries.

---

## TL;DR Recommendations

| Question | Recommendation | One-liner |
|----------|----------------|-----------|
| (a) VID:PID source | **Vendor a curated VID:PID data module** (Python dict, not full usb.ids), seeded from canonical `usb.ids` | You need ~40 specific IDs, not 25,704 lines; curated table is reviewable, citable, and lets you attach the right profile per device |
| (a) Detection gap | **Add a second detection path: bridge-chip VID:PID allowlist** alongside the existing class-7 filter | CH340/CH341/PL2305/FTDI bridges enumerate as class 255/CDC, NEVER class 7 — current code can't see them |
| (b) Packaging | **PyInstaller 6.20.0, `--onedir` (NOT onefile), with ad-hoc codesign + optional notarization** | onedir avoids the per-launch temp-extraction tax and libusb dylib resolution bugs; PyInstaller ships hooks for sounddevice + pyusb already |
| (c) ESC/P library | **Do NOT adopt any library — keep hand-rolled byte profiles** | Every Python "escpos" library is thermal-receipt ESC/POS, not Epson ESC/P / ESC/P2 dot-matrix, and none speak IBM Proprinter PPDS; they also own the transport, conflicting with your pyusb seam |

---

## (a) USB Detection & VID:PID Data

### Recommended Stack

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| pyusb (existing) | >=1.3.0 | USB enumeration + bulk writes | Already validated; no change needed for the transport layer |
| libusb (existing, `brew install libusb`) | 1.0.x | pyusb backend | Already a documented runtime dep |
| **Curated VID:PID data module** (new, in-repo) | n/a | Map VID:PID → printer family / bridge type → profile | Authoritative, reviewable, citable; avoids shipping a 1MB+ usb.ids you'd have to parse at runtime |

### Decision: vendor a curated data file, do NOT hardcode inline, do NOT ship full usb.ids

Three options were weighed:

| Option | Verdict | Reasoning |
|--------|---------|-----------|
| Hardcode IDs inline in `profiles.py` / detection code | ✗ Avoid | Scatters magic numbers across logic; hard to review/audit against sources; couples data churn to code churn |
| Ship the full `usb.ids` (25,704 lines) + parse at runtime | ✗ Avoid | You need ~40 IDs, not the whole registry; parsing adds startup cost + a file-bundling problem for PyInstaller; most entries are irrelevant non-printers |
| **Vendor a curated Python dict module** (e.g. `usb_ids.py` / `device_db.py`) | ✓ Recommend | Small, diff-able, each entry carries a source comment + the profile to attach; pure data, no parse step; trivially bundles into PyInstaller as code |

This matches the project's existing **"data-driven profiles via frozen dataclass"** decision — the VID:PID table is the same philosophy applied to detection. Each entry should carry: `vid`, `pid`, family/bridge label, suggested profile name, and a `# usb.ids` source comment.

### Authoritative source: canonical usb.ids

The single citable authority is the Linux USB ID Repository, mirrored everywhere:

- Primary: `http://www.linux-usb.org/usb.ids` (note: HTTPS cert has an altname mismatch — fetch over HTTP or via a package mirror)
- Mirror in `usbutils` package; also `systemd/hwdata`
- This is the same database `lsusb`, libusb, and udev resolve names against — the de-facto standard.

Verify entries against the vendor datasheet where the bridge mode matters (parallel vs serial mode share a VID but differ by PID).

### Bridge-chip VID:PIDs (verified against usb.ids 2026-06-12)

These are the **USB-LPT bridge** devices that reach vintage parallel printers. CRITICAL: none of these are USB printer class (7) — they are vendor-specific (255) or CDC. **The existing `_find_usb_printer` class-7 filter will never match them.**

| VID:PID | Device | Mode | Notes |
|---------|--------|------|-------|
| `1a86:5584` | WCH CH341 | **parallel** ("usb to printer port converter") | THE key vintage-printer path; the bridge already handled for CR+LF atomicity |
| `1a86:5512` | WCH CH341 | EPP/MEM/I2C (EPP/I2C adapter) | Parallel-capable variant |
| `1a86:5523` | WCH CH341 | serial | Serial mode — likely not a printer path but enumerate for completeness |
| `1a86:7522` / `1a86:7523` | WCH CH340 | serial | CH340 is serial-only; include for diagnostics/recognition |
| `067b:2305` | Prolific **PL2305** | **parallel port** | Classic USB-to-parallel cable chip |
| `067b:2303` / `067b:aaa3` | Prolific PL2303(x) | serial | Serial; recognize but not a printer path |
| `0403:6001` | FTDI FT232 (UART) | serial | Common; serial |
| `0403:6010`/`6011`/`6014` | FTDI FT2232/FT4232/FT232H | UART/**FIFO** | FT245-style FIFO mode can drive parallel; treat per-cable |
| `0403:601e`/`601f` | FTDI FT600/FT601 | FIFO | FIFO bridges |

Generic IEEE-1284 USB-parallel bridges also exist under many vendor IDs (verified present in usb.ids as product strings): `"USB-Parallel Bridge"`, `"UC-1284 Printer Port"`, `"UC-1284B Printer Port"`, `"USB-1284 BRIDGE"`, `"USB To Parallel adapter"`, `"Bi-directional to Parallel Printer Converter"`, `"F5U120-PC Parallel Printer Port"` (Belkin), `"GLUSB98PT Parallel Port"`. These are best matched by a fallback heuristic (interface class 7 OR known bridge VID:PID) rather than an exhaustive enumeration.

### Printer-family vendor IDs (verified against usb.ids 2026-06-12)

For modern native-USB impact/receipt models, these are the vendor IDs to anchor the family profiles. Per-model PIDs vary widely — match by VID + class 7, then refine by PID where a specific model is known:

| VID | Vendor | Families in scope |
|-----|--------|-------------------|
| `04b8` | Seiko Epson Corp. | Epson FX/LQ/LX (ESC/P, ESC/P2), TM (ESC/POS) |
| `06bc` | Oki Data Corp. | OKI Microline |
| `04d7` | Oki Semiconductor | (secondary OKI) |
| `0519` | Star Micronics Co., Ltd | Star |
| `08bd` / `1343` | Citizen Watch Co. / Citizen Systems | Citizen |
| `04da` | Panasonic (Matsushita) | Panasonic KX-P |
| `0619` | Seiko Instruments, Inc. | Seiko |
| `043d` | Lexmark International | IBM/Lexmark Proprinter (PPDS) |
| `04b3` | IBM Corp. | IBM Proprinter / Infoprint |
| `04f9` | Brother Industries | (adjacent dot-matrix) |
| `03f0` | HP, Inc | (PCL — already profiled) |

> Tally / TallyGenicom does not have a single stable USB-IF vendor block in usb.ids; many Tally units shipped parallel-only and reach the host via a bridge chip (use the bridge VID:PID path), or under a reseller VID. Flag Tally native-USB detection as LOW confidence — match via bridge path primarily.

### Integration point with existing code

`printer.py::_find_usb_printer()` currently does:
```python
if intf.bInterfaceClass != USB_PRINTER_CLASS:  # class 7
    continue
```
This is correct for native-USB printers but **silently skips every bridge chip**. The v1.6 change is to add a **second match path**:

1. Keep the class-7 scan (native printers).
2. Add: for each enumerated device, if `(idVendor, idProduct)` is in the curated bridge allowlist, treat it as a printer candidate and find its bulk-OUT endpoint regardless of interface class.
3. Suggest the profile from the curated table (bridge → "generic ESC/P" or user-selected; native → family profile by VID).

This reuses the existing `UsbDeviceInfo` / `DiscoveryResult` dataclasses and the `PrinterSelection` flow — the data table just feeds richer `usb_vendor_id`/`usb_product_id` fields already present on `PrinterProfile`.

---

## (b) PyInstaller Packaging (macOS primary, Linux bonus)

### Recommended Stack

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **PyInstaller** | **6.20.0** (released 2026-04-22) | Freeze app to standalone bundle | Current stable; supports Python <3.15 >=3.8 (covers 3.12); "works with code signing on macOS"; ships hooks for sounddevice and pyusb |
| (built-in hooks, no extra install) | bundled | sounddevice PortAudio dylib + pyusb | PyInstaller already carries `hook-sounddevice` (bundles PortAudio binary) and a pyusb import hook |

Install as a dev/build dependency only (not a runtime dep):
```bash
uv add --dev pyinstaller
```

### Decision: `--onedir`, NOT `--onefile`

| Mode | Verdict | Reasoning |
|------|---------|-----------|
| `--onefile` | ✗ Avoid | Extracts to a temp dir on every launch (slow startup, antivirus friction); historically the source of "Unable to find libusb-1.0" resolution bugs because the dylib path is a moving temp target; harder to codesign/notarize cleanly |
| **`--onedir`** | ✓ Recommend | No per-launch extraction; dylibs (libusb, PortAudio) sit at predictable relative paths; standard bundle layout; codesigning/notarization works on the bundle tree. Distribute as a zipped bundle or `.dmg` |

This is a TUI/CLI tool, so you build a plain console-mode onedir executable rather than a `--windowed` `.app` (a terminal app needs a controlling TTY; `--windowed` suppresses the console). If a double-clickable `.app` is wanted later, wrap the onedir bundle in a launcher that opens Terminal.

### Known packaging concerns (concrete spec-file guidance)

1. **libusb dylib** — PyInstaller's pyusb hook handles the import, but the native `libusb-1.0.dylib` (from `brew install libusb`) must be bundled. Add it explicitly to `binaries` in the spec:
   ```python
   # libusb path from: brew --prefix libusb -> .../lib/libusb-1.0.0.dylib
   binaries=[('/opt/homebrew/lib/libusb-1.0.0.dylib', '.')],
   ```
   On Apple Silicon vs Intel the prefix differs (`/opt/homebrew` vs `/usr/local`) — resolve via `brew --prefix libusb` in the build script, don't hardcode.

2. **sounddevice / PortAudio** — covered by the bundled `hook-sounddevice`; the PortAudio dylib ships from the sounddevice wheel automatically. Verify the dylib is present in the onedir output; no manual action expected.

3. **Hidden imports** — Textual and Typer load widgets/commands dynamically. Add as needed:
   ```python
   hiddenimports=['claude_teletype.backends.openai_backend',  # plugin-style modules
                  'claude_teletype.backends.openrouter_backend',
                  # Textual occasionally needs explicit widget modules
                  ]
   ```
   The openai SDK and Textual are generally well-handled by recent PyInstaller; run the frozen build and grep the warn-log for `missing module` rather than pre-listing speculatively.

4. **TOML data / config templates** — your handwritten config template and any packaged `.toml` defaults must go in `datas=[...]`. platformdirs is pure-Python and freezes cleanly.

5. **The curated VID:PID table** — because it's a Python module (not a data file), it freezes automatically with no `datas` entry. (Another reason to prefer the module over a vendored `usb.ids` file.)

6. **universal2** — only achievable if Python + every wheel (numpy, sounddevice, the libusb dylib) are universal2. Easiest path: build separately on Apple Silicon and Intel, or ship arm64-only and document Rosetta. Flag as a build-matrix decision, not a code decision.

### Codesigning & notarization (macOS)

- **Ad-hoc signing** (`codesign --sign -`) lets the bundle run locally and on the build machine, but Gatekeeper will block downloaded copies.
- **Developer ID signing + notarization** is required for distribution outside the App Store (download without right-click-open). Flow: codesign every dylib + the main binary with a Developer ID Application cert (with `--options runtime` for hardened runtime), zip, submit via `notarytool`, then `xcrun stapler staple`.
- Hardened runtime + a bundled non-Apple `libusb` dylib requires the dylib be signed with the same identity; unsigned nested dylibs fail notarization. The build script must sign nested binaries.
- Flag for the milestone: **notarization needs an Apple Developer account ($99/yr)**. If unavailable, document "right-click → Open" as the install instruction (ad-hoc sign only). This is a project decision to surface in the roadmap, not a blocker.

### Linux (bonus)

PyInstaller onedir works; libusb is typically present as a system package (`libusb-1.0-0`), so bundling is optional but recommended for portability. No codesigning. Lower priority per the project's macOS-primary constraint.

---

## (c) ESC/P / ESC/POS / IBM Proprinter Command-Generation Libraries

### Decision: adopt NOTHING — keep the hand-rolled byte profiles

This is the strongest recommendation in this document. Verified via Context7 + PyPI: **every Python "escpos" package targets thermal-receipt ESC/POS, not the dot-matrix command sets you need.**

| Library | Version | What it actually is | Why NOT for this project |
|---------|---------|---------------------|--------------------------|
| `python-escpos` | 1.0.x / 3.x dev | "ESC/POS **thermal** receipt printers" | Command set is cut/cash-drawer/QR/barcode — meaningless on impact printers; **owns the transport** (USB/serial/network connection objects), conflicting with your pyusb bulk-write seam; no ESC/P2 or PPDS |
| `escpos-python`, `escposprinter`, `PyESCPOS`, `python-printer-escpos` | various | Same ESC/POS thermal scope | Same mismatch; varying maintenance; redundant |

Critical distinctions the libraries get wrong for your domain:

- **ESC/POS ≠ ESC/P.** ESC/POS is Epson's *receipt-printer* language (cut paper, open drawer, print logo). ESC/P and ESC/P2 are Epson's *dot-matrix/inkjet* page languages (pitch, NLQ fonts, vertical tabs, graphics) — overlapping prefix bytes but different semantics. The libraries implement the former.
- **IBM Proprinter PPDS is entirely absent** from every Python library — there is no maintained PPDS generator. Your hand-rolled IBM PPDS profile (already shipped in v1.5) is the only viable path.
- **OKI Microline, Star, Citizen, Panasonic KX-P, Tally** native modes are likewise not covered.
- **Architecture conflict:** python-escpos is built around a `Printer` object that opens and owns the connection. Your design deliberately separates byte-generation (profiles) from transport (`PrinterDriver` Protocol + pyusb bulk writes + the CH341 CR+LF atomicity quirk). Adopting a library would mean fighting it to inject your transport — a net loss.

This validates the existing **"Encoding-table-as-contract"** and **"hand-written renderer (no library)"** decisions. Continue the conservative **leave-empty-where-undocumented** rule. The only "library" worth consulting is the published manuals (Epson ESC/P Reference, IBM Proprinter Programmer's Manual) — as data sources for byte values, not as code dependencies.

> Narrow exception to keep in mind, not adopt: if a future thermal TM-series receipt path needs barcodes/QR, python-escpos could generate *just those byte blobs* offline. Out of scope for v1.6; note only.

---

## Installation Summary

```bash
# Runtime: no new runtime dependencies. (pyusb/libusb already documented.)

# Build-time only:
uv add --dev pyinstaller   # 6.20.0

# Build (macOS, onedir):
pyinstaller claude-teletype.spec        # spec carries libusb binary + datas + hiddenimports
# then codesign nested dylibs + main binary, notarize, staple (if distributing)
```

No new runtime packages. The VID:PID table is in-repo Python (no dependency). No ESC/P library.

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| python-escpos / any `escpos` PyPI package | Thermal-receipt ESC/POS only; no ESC/P2, no IBM PPDS; owns transport | Continue hand-rolled byte profiles |
| Shipping/parsing full `usb.ids` at runtime | 25k lines for ~40 needed IDs; parse cost; PyInstaller bundling friction | Curated in-repo Python VID:PID dict, seeded from usb.ids |
| PyInstaller `--onefile` | Temp-extraction startup tax; libusb dylib path instability; harder notarization | `--onedir` |
| `--windowed` mode | Suppresses the console a TUI needs | Console-mode onedir; optional Terminal-launcher wrapper |
| Hardcoding `/opt/homebrew/lib/...` libusb path in the spec | Breaks on Intel macs and CI | Resolve via `brew --prefix libusb` in build script |
| Relying on class-7 filter alone for detection | Bridge chips (CH340/CH341/PL2305/FTDI) are class 255/CDC, never class 7 | Add a bridge VID:PID allowlist second path |

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| pyinstaller 6.20.0 | Python 3.8–3.14 | Covers project's 3.12+; supports macOS 10.15+ universal2 builds |
| pyinstaller 6.x | sounddevice >=0.5, pyusb >=1.3 | Built-in hooks present for both; verify libusb dylib in onedir output |
| libusb 1.0.x (Homebrew) | pyusb 1.3.0 | Bundle the dylib explicitly in spec `binaries`; sign for hardened runtime |

---

## Sources

- `http://www.linux-usb.org/usb.ids` (canonical Linux USB ID Repository, fetched 2026-06-12) — bridge-chip and printer-vendor VID:PID entries (CH340/CH341 `1a86`, Prolific `067b` incl. PL2305 `2305`, FTDI `0403`, Epson `04b8`, OKI Data `06bc`, Star `0519`, Citizen `08bd`/`1343`, Panasonic `04da`, Seiko `0619`, Lexmark `043d`, IBM `04b3`, generic IEEE-1284 bridge product strings) — **HIGH**
- PyPI `pyinstaller` page (fetched 2026-06-12) — version 6.20.0, release date 2026-04-22, Python 3.12 support, macOS codesigning + universal2 notes — **HIGH**
- PyInstaller 6.20.0 docs (usage / spec-files / when-things-go-wrong) — hooks, hidden imports, binaries/datas, onefile-vs-onedir behavior — **HIGH**
- PyInstaller PR #4498 (sounddevice hook) + issue #2633 (libusb bundling) — confirms built-in sounddevice/pyusb hooks and the historical libusb-resolution pitfall driving the onedir recommendation — **MEDIUM** (verified against current docs)
- Context7 `/python-escpos/python-escpos` + PyPI escpos listings — confirms all Python escpos libraries are thermal-receipt ESC/POS scope, no ESC/P2 / PPDS — **HIGH**
- Existing code `src/claude_teletype/printer.py::_find_usb_printer` (read 2026-06-12) — confirms class-7-only filter gap for bridge chips — **HIGH**

---
*Stack research for: v1.6 USB printer fleet detection + standalone packaging*
*Researched: 2026-06-12*
