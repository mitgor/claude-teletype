# Project Research Summary — v1.6 "Printer Fleet & Standalone"

**Project:** Claude Teletype
**Domain:** USB dot-matrix printer fleet detection + per-family ESC/P control-code profiles + standalone macOS packaging
**Researched:** 2026-06-12
**Confidence:** HIGH (stack + architecture + pitfalls); MEDIUM (features — command-language facts HIGH, per-model USB PIDs LOW)

---

## Executive Summary

Claude Teletype v1.6 extends a working v1.5 TUI/CLI typewriter app into a product that can auto-detect a broad fleet of vintage and modern USB dot-matrix printers and ship as a standalone macOS binary. The research reveals a fundamental design split that governs nearly all of v1.6: **vintage parallel printers reach the host via USB-LPT bridge chips (CH340/CH341/PL2305/FTDI), which expose the cable's VID:PID — not the printer's.** Modern native-USB impact and POS printers enumerate as USB printer class (class 7) with manufacturer VID:PIDs. These two paths demand two different detection behaviors. Bridge chips can only confirm "a parallel adapter is here — pick your printer family." Native-USB printers permit profile auto-suggestion. The existing single-path `auto_detect_profile()` conflates these cases; fixing that is the architectural centerpiece of v1.6.

The recommended implementation sequence is strictly ordered by dependency: **refactor first, fleet expansion second, PyInstaller packaging last.** The refactor (package split into `printing/`, `rendering/`, `screens/` sub-packages, plus a `ProfileRegistry` and a `Classification`-based detection model) is the prerequisite for adding profiles correctly and for freezing a stable import graph. PyInstaller packaging should be deferred until the module map is settled, because spec-file tuning is wasted on a moving codebase. The only new runtime dependency is no dependency at all — no ESC/P library exists that fits (every Python "escpos" package targets thermal-receipt printers, not dot-matrix); profiles remain hand-rolled from vendor manuals.

The dominant risk is threefold: (1) bridge-chip VID:PIDs matching non-printer devices (Arduinos, GPS dongles) if detection is not two-tier; (2) fabricated control-code sequences printing garbage when the "leave-empty-when-unsure" rule is not enforced across nine new families; and (3) libusb/PortAudio dylibs failing to resolve inside the PyInstaller bundle on a clean machine. All three are avoidable with existing project discipline applied consistently.

---

## Key Findings

### Recommended Stack

No new runtime dependencies are needed. The v1.5 stack (Python 3.12+, Textual 7.x, Rich, Typer, sounddevice/numpy, openai SDK, tomllib/platformdirs, pyusb/libusb) covers all v1.6 needs. The single addition is **PyInstaller 6.20.0** as a build-time-only dev dependency (`uv add --dev pyinstaller`), which ships built-in hooks for both sounddevice (PortAudio dylib) and pyusb.

**Core technologies:**
- **pyusb + libusb (existing):** USB enumeration and bulk writes — no change to the transport layer
- **Curated in-repo VID:PID Python module (new):** ~40 entries seeded from `linux-usb.org/usb.ids`; bridges and native-printer vendor IDs in separate data sets; no runtime parse cost; trivially frozen by PyInstaller as normal code
- **PyInstaller 6.20.0, `--onedir`, console mode (new, build-time only):** onedir avoids per-launch temp-extraction and libusb dylib path instability; `--onefile` is explicitly avoided for the macOS primary build; `--windowed` is explicitly avoided (TUI needs a live TTY)
- **No ESC/P library:** Every Python "escpos" package is thermal-receipt ESC/POS only; none cover ESC/P2, IBM PPDS, OKI MICROLINE native, or Star line mode; all own the transport connection object in conflict with the project's pyusb seam. Continue hand-rolled byte profiles from vendor manuals.

Critical version notes: PyInstaller 6.20.0 supports Python 3.8–3.14 (covers 3.12+); libusb must be explicitly bundled via `binaries=[...]` in the spec (not auto-collected, because pyusb dlopens it at runtime); resolve the Homebrew prefix via `brew --prefix libusb` in the build script rather than hardcoding `/opt/homebrew`.

### Expected Features

**Must have (table stakes):**
- **Two-tier USB detection** — bridge-chip registry (CH341 `1a86:5584` parallel mode, Prolific `067b:2305`, FTDI, MosChip) feeds "adapter found — pick your family" prompt; native-USB class-7 printers auto-suggest profile; no merge of the two paths
- **Per-command-language built-in profiles** for high-population families: Epson ESC/P (FX/LX), Epson ESC/P2 (LQ), IBM/Lexmark PPDS, OKI MICROLINE (via IBM/Epson emulation), Panasonic KX-P (emulation) — one profile per command language, not per SKU
- **`ESC @` init sequence** across all ESC/P, ESC/P2, IBM PPDS families (already supported via `init_sequence` field; populate per family from manuals)
- **Formalized codepage/`text_codec`/`text_fallback`** — untracked work from v1.5 promoted to tracked requirement and extended per family; `ESC t n` / `ESC R n` for Epson; IBM PPDS code-page select
- **"Bridge found, pick family" fallback** — reuses existing v1.4 PrinterSetupScreen profile picker; adds branch: bridge-detected-no-PID-match → jump to family list
- **macOS standalone `.app` (onedir)** via PyInstaller — first-run reuses existing v1.4 setup screen; no new UX needed

**Should have (differentiators):**
- Verified-from-manual control codes with inline provenance citations (manual name + page + assumed emulation mode) — the "leave-empty-when-unsure" rule extended to all new families
- `capabilities()` introspection method on `PrinterProfile` — powers `diagnose` fleet matrix; shows which families still have empty style codes pending hardware confirmation
- `ProfileRegistry` with single VID:PID index — kills duplicated map-building in `auto_detect_profile` and `_find_usb_printer`; detects VID collision at index-build time
- `Classification` result type (NATIVE_PRINTER / BRIDGE / UNKNOWN) in `printing/detection.py` — explicit representation of the bridge ambiguity; fixes the `juki-2200` "leave VID:PID unset to avoid hijacking" workaround

**Defer to v2+:**
- OKI MICROLINE native mode (emulation modes cover the need; native adds depth, not capability)
- Star native STAR line mode + Tally / Seiko profiles (lower install base, lower data confidence; add when target hardware is available)
- Status/busy readback over USB-LPT bridges (write-only on most bridge chips; bidirectional polling risks false confidence)
- macOS notarization + universal2 binary (requires Apple Developer account; valid distribution hardening but not a launch blocker)
- Linux standalone binary (bonus track; lower priority per macOS-primary constraint)

### Architecture Approach

The existing flat 23-module package is reorganized into three sub-packages — `printing/`, `rendering/`, `screens/` — using a **move + re-export shim** pattern that keeps all 700 absolute-path-import tests green across the physical move. The `printing/` package gains two new modules: `detection.py` (bridge-chip classifier) and `registry.py` (single `ProfileRegistry` replacing scattered per-call-site VID:PID map building), plus a `catalog/` sub-package of per-family profile modules. Profiles stay as Python dataclass literals — not externalized to TOML/JSON — because that preserves byte-provenance citations, eliminates PyInstaller `datas` wiring, and keeps invariant checks at import time rather than runtime.

**Major components:**
1. `printing/detection.py` (new) — classifies a `UsbDeviceInfo` as NATIVE_PRINTER (profile suggestion) / BRIDGE (transport + prompt) / UNKNOWN; bridge VIDs are a separate constant set, never entries in the profile registry
2. `printing/registry.py` (new) — `ProfileRegistry` assembles built-ins from `catalog/` + merges custom TOML; builds VID:PID index once; exposes `match_vidpid()`, `get()`, `names()`
3. `printing/catalog/` (new) — per-family modules (`epson.py`, `oki.py`, `ibm.py`, `star_citizen.py`, `juki.py`, `misc.py`) assembled into `BUILTIN_PROFILES`; co-located VID:PIDs feed the registry index
4. `printing/drivers.py` / `discovery.py` / `selection.py` (moved from flat `printer.py`) — unchanged behavior; `selection.py` also fixes the `create_driver_for_selection` device-index bug
5. PyInstaller `.spec` (new, repo root) — console mode, onedir, explicit `libusb-1.0.dylib` in `binaries`, `collect_data_files("textual")` for `.tcss` assets, conditional `collect_submodules("usb")`

### Critical Pitfalls

1. **Bridge-chip VID:PIDs match millions of non-printer devices** — CH340/FTDI VID:PIDs are shared with Arduino clones, GPS dongles, CNC controllers. Never auto-select or auto-skip a bridge-chip match; require explicit user confirmation + manual profile pick. Two-tier detection (NATIVE via class-7 + VID, BRIDGE via separate allowlist) prevents this.

2. **macOS kernel driver claims native-USB class-7 printers before pyusb can** — `libusb_claim_interface` fails with LIBUSB_ERROR_ACCESS on macOS 12.4+ for printer-class devices the OS already manages. Detect claim failure, fall back to the existing CUPS path, show a friendly message. Never auto-detach the kernel driver (it breaks CUPS for that device until replug).

3. **Fabricated control sequences print garbage** — nine new printer families mean dozens of init/codepage/paper-handling byte sequences. The "leave-empty-when-unsure" rule must be enforced across every family. Every non-empty byte field must cite manual name + page + assumed emulation mode. Unverified families tagged `human_needed`.

4. **Big-bang package refactor breaks 700 tests via stale mock patch targets** — `unittest.mock.patch` requires patching where the name is *looked up*, not defined. Moving modules without incremental green checkpoints turns hundreds of tests red in a single commit and makes failures ambiguous. Use move-with-shim → repoint internals → migrate tests (three separately green steps).

5. **libusb dylib missing in PyInstaller bundle** — pyusb finds libusb via `ctypes.util.find_library()` at runtime; PyInstaller's static analysis cannot see this. Explicitly add `libusb-1.0.dylib` via `binaries=[...]` and point pyusb's backend at the bundled copy via a `find_library` lambda. Smoke-test the bundle on a clean machine (no Homebrew, no dev Python).

---

## Implications for Roadmap

The feature and architecture research converges on a strict three-stage ordering. The suggested phase structure follows directly.

### Phase 1: Refactor — Package Split + Registry + Detection Model
**Rationale:** Fleet profiles land in `printing/catalog/`; the `ProfileRegistry` and `Classification` detection model are prerequisites for representing bridge ambiguity correctly. Doing this first means new profiles are authored into the clean structure rather than bloating `printer.py` (1036 LOC) and being moved later.
**Delivers:** `printing/`, `rendering/`, `screens/` sub-packages (all 700 tests green via shims); `ProfileRegistry` replacing per-call-site map building; `detection.py` with NATIVE/BRIDGE/UNKNOWN classifier; tech-debt fixes (device-index bug in `create_driver_for_selection`, `discovery=None` dual-meaning split, `cli.py` profile-resolution duplication extracted)
**Addresses:** Feature: bridge-found-no-PID fallback (needs Classification type); Feature: single VID:PID index (needs ProfileRegistry)
**Avoids:** Pitfall 4 (big-bang refactor) — incremental move-with-shim enforced; Pitfall 1 (bridge false positives) — classifier built from the start with correct separation

### Phase 2: Fleet Expansion — Per-Family Profiles + Bridge Detection Registry
**Rationale:** Depends on Phase 1's registry + detection seam. Each family module is additive and independently testable. Bridge-chip registry (the single highest-leverage item for "broad detection") requires the `Classification` type from Phase 1.
**Delivers:** `catalog/` family modules for Epson ESC/P, ESC/P2, IBM/Lexmark PPDS, OKI MICROLINE (emulation), Panasonic KX-P (emulation); `BRIDGE_CHIP_VIDS` constant set; expanded native VID:PID matrix; formalized codepage/text_codec/text_fallback per family; `capabilities()` method on `PrinterProfile`; `diagnose` fleet capability matrix; richer fields (status, paper-handling policy) as empty-default frozen additions
**Uses:** Curated VID:PID data module seeded from `linux-usb.org/usb.ids`; Epson ESC/P Reference Manual, IBM PPDS Programmer's Guide, OKI ML user guides, Star STAR command spec
**Avoids:** Pitfall 1 (bridge false positives) — bridge VIDs live in `BRIDGE_CHIP_VIDS`, never in the registry; Pitfall 5 (fabricated codes) — leave-empty rule + manual provenance enforced per family; unverified families tagged `human_needed`

### Phase 3: Standalone Packaging — PyInstaller macOS Build
**Rationale:** Freeze the app only after the module map and dependency graph are stable; every Phase 1–2 refactor would invalidate spec hidden-imports/datas tuning. The app's existing graceful pyusb degradation (CUPS fallback when libusb absent) means a bundling hiccup won't block launch.
**Delivers:** Checked-in `.spec` (console mode, onedir); explicit `libusb-1.0.dylib` bundling with backend lambda; `collect_data_files("textual")` for `.tcss` assets; `collect_submodules("claude_teletype.backends")`; macOS ad-hoc codesign (notarization + universal2 deferred); clean-machine smoke-test passing USB + audio + print
**Uses:** PyInstaller 6.20.0 (`uv add --dev pyinstaller`); `brew --prefix libusb` resolution in build script
**Avoids:** Pitfall 3 (libusb missing in bundle) — explicit `binaries=[...]` + backend path override; sounddevice PortAudio — clean-machine verification required

### Phase Ordering Rationale

- Phase 1 before Phase 2: the `Classification` return type and `ProfileRegistry` are structural prerequisites for representing bridge-chip detection correctly; authoring profiles into pre-split `profiles.py` would require immediate re-migration
- Phase 2 before Phase 3: PyInstaller spec tuning is sensitive to the exact module import graph; refactoring after freezing means redoing all hidden-imports and datas entries
- Codepage/text_codec formalization inside Phase 2 (not later): it is the foundation all new families build on for non-ASCII printing; the existing untracked work needs to become tracked before being extended nine times
- `human_needed` tags throughout Phase 2: consistent with existing Phase-22 discipline; spec-verified does not equal hardware-verified

### Research Flags

Phases likely needing deeper research or hardware verification during planning:

- **Phase 2 (bridge-chip interface-class behavior):** Does a CH341 USB-LPT adapter in parallel mode enumerate as class 7 or CDC/vendor-specific? Determines whether the class-7 fast path survives or must become fully advisory. Needs a real CH341 adapter + `lsusb -v`. Mark MEDIUM confidence until verified.
- **Phase 2 (native-USB printer PIDs):** Only Epson LX-350 (0x0046) and LQ-350 (0x0047) have HIGH-confidence PIDs; all other model-level PIDs are LOW confidence. The registry VID-only fallback is the safe default.
- **Phase 3 (libusb bundling + macOS signing):** Exact dylib path varies by arch; ad-hoc vs notarized signing is a project decision requiring an Apple Developer account ($99/yr). Needs a real build iteration on both Intel and Apple Silicon.

Phases with standard patterns (research-phase likely skippable):

- **Phase 1 (package refactor):** Move-with-shim is a well-documented Python technique; three-step protocol has no novel unknowns.
- **Phase 2 (Epson ESC/P + IBM PPDS profiles):** Vendor manuals available and cited; `ESC @` and codepage commands are HIGH-confidence from primary sources. Profile authoring is mechanical.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | PyInstaller 6.20.0 verified on PyPI (released 2026-04-22); bridge-chip VID:PIDs verified against canonical `linux-usb.org/usb.ids`; ESC/P library landscape verified via Context7 + PyPI (all thermal-receipt scope confirmed) |
| Features | MEDIUM | Command-language assignments HIGH from vendor manuals; specific native-USB PIDs HIGH only for Epson LX-350/LQ-350; all other model PIDs LOW — most vintage targets have no USB PID (bridge-only) |
| Architecture | HIGH | Follows directly from existing codebase structure and logged project decisions; re-export-shim pattern is standard; Classification/Registry design directly evidenced by the `juki-2200` bridge-VID comment in production code |
| Pitfalls | HIGH | macOS kernel-driver claim failure verified against libusb issue tracker; PyInstaller dylib bundling verified against PyInstaller issues; mock patch-target rule is Python stdlib docs; bridge false-positive risk grounded in project hardware notes |

**Overall confidence:** HIGH on approach; MEDIUM on per-model hardware specifics

### Gaps to Address

- **Bridge interface-class behavior (MEDIUM):** Whether CH341 USB-LPT adapters in parallel mode enumerate as class 7 or CDC/vendor-specific needs hardware verification — determines whether class-7 filtering can serve as a fast path or must be fully advisory. Address in Phase 2 planning; flag with `human_needed`.
- **Native-USB printer PIDs (LOW):** Model-level PIDs for OKI, Star, Citizen, Lexmark Forms-Plus USB are unverified. The registry VID-only fallback covers this safely; per-model PIDs fill in via `diagnose`-on-real-device sessions over time.
- **libusb arch and signing (MEDIUM):** Exact bundling incantation and ad-hoc vs notarized signing needs a real build iteration. Apple Developer account requirement ($99/yr) is a project decision. Resolve before Phase 3 planning.
- **Multiple-printer selection scope (TBD):** The `create_driver_for_selection` device-index bug fix enables selecting among several USB printers simultaneously; clarify whether full multi-printer selection is in scope for v1.6 or just the index-bug fix.

---

## Sources

### Primary (HIGH confidence)
- `http://www.linux-usb.org/usb.ids` — bridge-chip and printer-vendor VID:PIDs (CH340/CH341, Prolific PL2305/PL2303, FTDI, Epson, OKI, Star, Citizen, Panasonic, Lexmark, IBM)
- Epson ESC/P Reference Manual (Dec 1997, `escp2ref.pdf`) — ESC/P command set, `ESC @`, `ESC t n`, `ESC R n`
- IBM PPDS & Epson ESC/P control codes list (`ibm.com/support/pages/...`) — PPDS byte sequences, `ESC @`, code-page select
- IBM Proprinter XL24 Programmer's Guide (psi-matrix.eu) — PPDS full command reference
- OKI Microline 320/321 Turbo User's Guide — emulation modes, ML native commands (p. 94)
- Star dot-impact STAR command spec rev 1.91 (`starmicronics.com`) — Star line-mode commands
- PyInstaller 6.20.0 docs (PyPI + official docs) — hooks, spec format, onedir/onefile behavior, codesigning guidance
- PyInstaller issues #2633 (libusb bundling), #7816 (PortAudio path resolution), #5107 (macOS Big Sur dyld cache)
- libusb issues #1153, #575, #364 — macOS 12.4+ claim failure, CUPS interaction
- Python docs `unittest.mock` — "where to patch" canonical rule
- Existing codebase `printer.py`, `profiles.py`, `PROJECT.md`, `pyproject.toml`, `project_juki_2200_hardware.md`

### Secondary (MEDIUM confidence)
- `the-sz.com` USB ID DB — CH341 mode PIDs (0x5584 parallel verified); Epson VID LX-350/LQ-350 model PIDs
- `devicehunt.com` — OKI VID 0x06BC product listings
- Linux CH341 driver source (RichStrong/CH341A_linux_driver) — CH341 mode enumeration
- macOS code signing + notarization gist (txoof, Feb 2025) — signing workflow
- Arduino IDE VID/PID list (per1234/zzInoVIDPID) — evidence that CH340/FTDI VID:PIDs are chip-level not device-level

### Tertiary (LOW confidence)
- Model-level PIDs for OKI ML390, Star SP500/SP700, Citizen CBM-1000, Lexmark Forms-Plus USB — not confirmed for specific models; fill at hardware-verification time

---
*Research completed: 2026-06-12*
*Milestone: v1.6 "Printer Fleet & Standalone"*
*Ready for roadmap: yes*
