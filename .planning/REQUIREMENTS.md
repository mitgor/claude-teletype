# Requirements: Claude Teletype

**Defined:** 2026-06-12
**Core Value:** The physical typewriter experience — characters appearing on paper one at a time with authentic pacing and sound, making AI conversation feel tangible and mechanical.

## v1.6 Requirements

Requirements for the **Printer Fleet & Standalone** milestone. Each maps to roadmap phases.

### Detection

- [ ] **DET-01**: User plugging in a USB-LPT bridge (CH341 parallel 0x5584, Prolific PL2305, FTDI, MosChip, IEEE-1284 class adapters) sees it detected via a curated bridge-chip registry kept separate from printer profiles
- [ ] **DET-02**: Discovery classifies every candidate USB device as NATIVE_PRINTER / BRIDGE / UNKNOWN — replacing the conflated `auto_detect_profile()` path
- [ ] **DET-03**: User with a modern native-USB impact printer (Epson 0x04B8 incl. LX-350 0x0046 / LQ-350 0x0047, OKI 0x06BC, Star 0x0519, Lexmark 0x043D, IBM 0x04B3, Citizen) gets the correct profile auto-suggested from an expanded VID:PID matrix
- [ ] **DET-04**: User whose bridge is detected but whose printer is unknowable is taken straight to the manual family picker — the app never guesses the printer behind a bridge, and bridges never trigger smart-startup auto-skip without a saved selection
- [ ] **DET-05**: User selecting a serial-only chip (e.g. CH340 0x5523) sees a warning that it cannot reliably drive an impact printer
- [ ] **DET-06**: User whose native-USB printer is claimed by the macOS kernel sees a graceful fallback to the CUPS path with a clear message (no traceback, no auto-detach)
- [ ] **DET-07**: `claude-teletype diagnose` shows the fleet matrix — per-device classification (native/bridge/unknown) and per-profile capability summary

### Profiles

- [ ] **PROF-01**: User with an Epson LQ-series printer gets an ESC/P2 profile with verified init/codepage/style sequences
- [ ] **PROF-02**: User with an Epson TM POS impact printer gets an ESC/POS profile
- [ ] **PROF-03**: User with an IBM/Lexmark Proprinter-family printer gets an enriched PPDS profile (init, codepage select)
- [ ] **PROF-04**: User with an OKI MICROLINE gets emulation profiles matching factory defaults (IBM Proprinter III, Epson FX)
- [ ] **PROF-05**: User with an OKI MICROLINE can opt into the native MICROLINE command-set profile
- [ ] **PROF-06**: User with a Star dot-impact (SP500/SP700-class) gets a STAR line-mode profile
- [ ] **PROF-07**: User with a Panasonic KX-P or Tally/TallyGenicom unit gets emulation-alias profiles (Epson FX / IBM Proprinter)
- [ ] **PROF-08**: Every new byte sequence is verbatim-from-manual with cited source; undocumented capabilities stay empty bytes (no fabricated codes)

### Direct Mode

- [ ] **DIR-01**: The untracked `codepage_command`/`text_codec`/`text_fallback` work is formalized — tracked requirements, test coverage, custom-TOML support
- [ ] **DIR-02**: Each new family profile ships populated `init_sequence`/`reset_sequence` (`ESC @` where documented)
- [ ] **DIR-03**: Each family ships sensible default codepage values (`ESC t n` / `ESC R n` per command language)
- [ ] **DIR-04**: User with a confirmed bidirectional native-USB printer can see paper-out/busy status; readback is absent (not broken) on bridges, with the limitation documented

### Refactoring

- [ ] **REF-01**: Codebase reorganized into sub-packages (`printing/`, `rendering/`, `screens/`) via move-with-re-export-shims — full test suite green at every incremental step
- [ ] **REF-02**: `ProfileRegistry` + per-family `catalog/` modules replace the flat `BUILTIN_PROFILES` dict
- [ ] **REF-03**: `create_driver_for_selection()` selects USB devices by identity, not first-of-class re-discovery
- [ ] **REF-04**: `discovery=None` dual-meaning sentinel replaced with explicit types
- [ ] **REF-05**: cli.py/main() profile-resolution duplication unified
- [ ] **REF-06**: Code-review pass over the codebase; findings fixed or explicitly filed

### Packaging

- [ ] **PKG-01**: User without a Python install can run a macOS `.app` (PyInstaller onedir, console TUI mode) built from a checked-in spec file
- [ ] **PKG-02**: Bundle includes libusb (explicit binary with pyusb backend pointed at it), PortAudio, and Textual data files
- [ ] **PKG-03**: Bundle verified on a clean machine — launch, detection, simulator, and print path all work
- [ ] **PKG-04**: Bundle degrades gracefully when USB is unavailable (same CUPS/simulator fallback as the dev install)

## Future Requirements

Deferred to v1.7+. Tracked but not in current roadmap.

### Direct Mode Expansion

- **DIR-05**: Per-family paper-handling policy field (tractor / cut-sheet / receipt-cut) with user-triggered form-feed keybinding
- **PROF-09**: Seiko DPU/SLP profiles (LOW data — needs a unit in hand)

### Packaging Expansion

- **PKG-05**: Linux single-file binary (`--onefile`)
- **PKG-06**: universal2 macOS binary (Intel + Apple Silicon)
- **PKG-07**: Code signing + notarization (requires Apple Developer account)

### Carried from v1.5

- **PREV-01**: Print preview in TUI before sending to printer
- **FMT-01**: Page numbers, headers, footers for multi-page documents
- **PICK-06**: Picker remembers recently-printed files
- **PICK-07**: Configurable `notes_dir` overriding cwd as picker root
- **CAP-07**: Inline links (footnote-numbered references)
- **CAP-08**: Task lists with check-glyph rendering

## Out of Scope

| Feature | Reason |
|---------|--------|
| Auto-naming the printer model behind a bridge cable | Physically impossible — bridge exposes only its own VID:PID; the parallel printer is invisible to USB |
| Status/busy/paper-out readback over USB-LPT bridges | Bridges are effectively write-only for impact printers; building UI around unreliable status creates false confidence |
| Per-SKU profile for every model number | Models within a family share command sets; one profile per command language with `columns` as the per-model knob |
| Driving impact printers through serial-only adapters (CH340 0x5523, FTDI RS-232) | USB-to-RS232 chips drop bytes on BUSY/ACK handshake and corrupt output — warn, don't support |
| Graphics / bit-image / barcode printing | Plain text only, typewriter aesthetic (standing project constraint) |
| macOS `--onefile` build | Per-launch temp extraction, Gatekeeper friction, harder to sign — onedir `.app` is correct for a TUI |

## Traceability

Which phases cover which requirements. Filled in by `gsd-roadmapper` during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DET-01 | Phase 28 | Pending |
| DET-02 | Phase 27 | Pending |
| DET-03 | Phase 28 | Pending |
| DET-04 | Phase 28 | Pending |
| DET-05 | Phase 28 | Pending |
| DET-06 | Phase 28 | Pending |
| DET-07 | Phase 29 | Pending |
| PROF-01 | Phase 29 | Pending |
| PROF-02 | Phase 29 | Pending |
| PROF-03 | Phase 29 | Pending |
| PROF-04 | Phase 29 | Pending |
| PROF-05 | Phase 29 | Pending |
| PROF-06 | Phase 29 | Pending |
| PROF-07 | Phase 29 | Pending |
| PROF-08 | Phase 29 | Pending |
| DIR-01 | Phase 27 | Pending |
| DIR-02 | Phase 29 | Pending |
| DIR-03 | Phase 29 | Pending |
| DIR-04 | Phase 28 | Pending |
| REF-01 | Phase 27 | Pending |
| REF-02 | Phase 27 | Pending |
| REF-03 | Phase 27 | Pending |
| REF-04 | Phase 27 | Pending |
| REF-05 | Phase 27 | Pending |
| REF-06 | Phase 27 | Pending |
| PKG-01 | Phase 30 | Pending |
| PKG-02 | Phase 30 | Pending |
| PKG-03 | Phase 30 | Pending |
| PKG-04 | Phase 30 | Pending |

**Coverage:** 29/29 requirements mapped across Phases 27-30. No orphans.

---
*Requirements defined: 2026-06-12*
*Roadmap mapped: 2026-06-12*
