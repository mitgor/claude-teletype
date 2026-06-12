# Roadmap: Claude Teletype

## Milestones

- ✅ **v1.0 MVP** - Phases 1-4 (shipped 2026-02-15)
- ✅ **v1.1 Conversation Mode** - Phases 5-7 (shipped 2026-02-17)
- ✅ **v1.2 Configuration, Profiles, Multi-LLM, Settings** - Phases 8-15 (shipped 2026-02-17)
- ✅ **v1.3 Tech Debt Cleanup** - Phases 16-17 (shipped 2026-02-20)
- ✅ **v1.4 Printer Setup TUI** - Phases 18-20 (shipped 2026-04-03)
- ✅ **v1.5 Markdown File Printing** - Phases 21-26 (shipped 2026-04-28)
- 🚧 **v1.6 Printer Fleet & Standalone** - Phases 27-30 (in progress)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-4) - SHIPPED 2026-02-15</summary>

- [x] Phase 1: Streaming Pipeline (2/2 plans) — completed 2026-02-15
- [x] Phase 2: Terminal Simulator (2/2 plans) — completed 2026-02-15
- [x] Phase 3: Printer Hardware (2/2 plans) — completed 2026-02-15
- [x] Phase 4: Audio and Persistence (2/2 plans) — completed 2026-02-15

</details>

<details>
<summary>✅ v1.1 Conversation Mode (Phases 5-7) - SHIPPED 2026-02-17</summary>

- [x] Phase 5: Multi-Turn Conversation Foundation (3/3 plans) — completed 2026-02-16
- [x] Phase 6: Error Handling and Recovery (2/2 plans) — completed 2026-02-17
- [x] Phase 7: Word Wrap for TUI and Printer (2/2 plans) — completed 2026-02-17

</details>

<details>
<summary>✅ v1.2 Configuration, Profiles, Multi-LLM, Settings (Phases 8-15) - SHIPPED 2026-02-17</summary>

- [x] Phase 8: No-TUI Bug Fix (1/1 plan) — completed 2026-02-17
- [x] Phase 9: Configuration System (2/2 plans) — completed 2026-02-17
- [x] Phase 10: Printer Profiles (2/2 plans) — completed 2026-02-17
- [x] Phase 11: Multi-LLM Backends (2/2 plans) — completed 2026-02-17
- [x] Phase 12: Typewriter Mode (2/2 plans) — completed 2026-02-17
- [x] Phase 13: Settings Panel (2/2 plans) — completed 2026-02-17
- [x] Phase 14: Verify Config & Traceability (1/1 plan) — completed 2026-02-17
- [x] Phase 15: Fix system_prompt Hot-Swap (1/1 plan) — completed 2026-02-17

</details>

<details>
<summary>✅ v1.3 Tech Debt Cleanup (Phases 16-17) - SHIPPED 2026-02-20</summary>

- [x] Phase 16: Config and Profile Polish (1/1 plan) — completed 2026-02-20
- [x] Phase 17: Claude-CLI Warnings (1/1 plan) — completed 2026-02-20

</details>

<details>
<summary>✅ v1.4 Printer Setup TUI (Phases 18-20) - SHIPPED 2026-04-03</summary>

- [x] Phase 18: Discovery Data Layer & Diagnostics (1/1 plan) — completed 2026-04-03
- [x] Phase 19: Printer Setup Screen (3/3 plans) — completed 2026-04-03
- [x] Phase 20: Config Persistence & Smart Startup (2/2 plans) — completed 2026-04-03

</details>

<details>
<summary>✅ v1.5 Markdown File Printing (Phases 21-26) - SHIPPED 2026-04-28</summary>

- [x] Phase 21: Profile Capability Fields & Custom-TOML Support (3/3 plans) — completed 2026-04-28
- [x] Phase 22: Encoded Style Sequences for Built-In Profiles (1/1 plan) — completed 2026-04-28
- [x] Phase 23: Streaming Markdown Renderer (3/3 plans) — completed 2026-04-28
- [x] Phase 24: TUI File Picker (2/2 plans) — completed 2026-04-28
- [x] Phase 25: `claude-teletype print` CLI Subcommand (2/2 plans) — completed 2026-04-28
- [x] Phase 26: Speed Dialog, Buffer Chunking, Cancel & Transcript Integration (3/3 plans) — completed 2026-04-28

Full details: [milestones/v1.5-ROADMAP.md](milestones/v1.5-ROADMAP.md)

</details>

### 🚧 v1.6 Printer Fleet & Standalone (Phases 27-30)

- [ ] **Phase 27: Refactor — Package Split, Registry & Detection Seam** - Reorganize into sub-packages, introduce ProfileRegistry + Classification model, fix tech debt, formalize codepage work
- [ ] **Phase 28: Fleet Detection & Bridge Registry** - Two-tier USB classification, bridge-chip registry, expanded native VID:PID matrix, kernel-claim CUPS fallback, status readback
- [ ] **Phase 29: Per-Family Profile Catalog** - Verified-from-manual profiles for Epson/IBM/OKI/Star/Panasonic families with init/codepage sequences and diagnose fleet matrix
- [ ] **Phase 30: Standalone macOS Packaging** - PyInstaller onedir `.app` with bundled libusb/PortAudio/Textual data, verified on a clean machine

## Phase Details

### Phase 27: Refactor — Package Split, Registry & Detection Seam
**Goal**: A reorganized, lower-debt codebase whose registry and detection seams are ready to absorb the printer fleet, with the untracked codepage work now first-class and tested.
**Depends on**: Nothing (first phase of v1.6; builds on shipped v1.5)
**Requirements**: REF-01, REF-02, REF-03, REF-04, REF-05, REF-06, DET-02, DIR-01
**Success Criteria** (what must be TRUE):
  1. The full test suite passes at every incremental step of the package move into `printing/`, `rendering/`, and `screens/` (re-export shims keep existing imports working)
  2. A single `ProfileRegistry` resolves profiles and VID:PID lookups, replacing the flat `BUILTIN_PROFILES` dict and per-call-site map building
  3. Discovery produces an explicit `Classification` (NATIVE_PRINTER / BRIDGE / UNKNOWN) result, replacing the conflated `auto_detect_profile()` path
  4. USB driver selection picks a device by identity (not first-of-class re-discovery), and `discovery=None` no longer carries two meanings
  5. `codepage_command` / `text_codec` / `text_fallback` are tracked, test-covered, and settable from custom TOML profiles
**Plans**: TBD

### Phase 28: Fleet Detection & Bridge Registry
**Goal**: Users can plug in either a USB-LPT bridge or a modern native-USB impact printer and be routed correctly — the app never guesses the printer behind a bridge and degrades gracefully when the OS owns the device.
**Depends on**: Phase 27 (ProfileRegistry + Classification seam)
**Requirements**: DET-01, DET-03, DET-04, DET-05, DET-06, DIR-04
**Success Criteria** (what must be TRUE):
  1. Plugging in a known USB-LPT bridge (CH341 parallel, Prolific PL2305, FTDI, MosChip) is detected via a curated bridge-chip registry kept separate from printer profiles
  2. A modern native-USB impact printer (Epson 0x04B8, OKI 0x06BC, Star 0x0519, Lexmark 0x043D, IBM 0x04B3, Citizen) gets the correct profile auto-suggested from the expanded VID:PID matrix
  3. A detected-but-unknowable bridge sends the user straight to the manual family picker, and bridges never trigger smart-startup auto-skip without a saved selection
  4. Selecting a serial-only chip (e.g. CH340 0x5523) shows a warning that it cannot reliably drive an impact printer
  5. A native-USB printer claimed by the macOS kernel falls back to the CUPS path with a clear message (no traceback, no auto-detach); confirmed bidirectional printers can show paper-out/busy status while bridges report readback as absent-not-broken
**Plans**: TBD
**UI hint**: yes

### Phase 29: Per-Family Profile Catalog
**Goal**: Users with printers across the major impact-printer families get a working, verified-from-manual profile with correct init and codepage behavior, and can see the whole fleet's capability state at a glance.
**Depends on**: Phase 28 (detection routing) and Phase 27 (registry + codepage fields)
**Requirements**: PROF-01, PROF-02, PROF-03, PROF-04, PROF-05, PROF-06, PROF-07, PROF-08, DIR-02, DIR-03, DET-07
**Success Criteria** (what must be TRUE):
  1. Epson LQ (ESC/P2), Epson TM (ESC/POS), IBM/Lexmark PPDS, OKI MICROLINE (IBM/Epson emulation + opt-in native), Star line-mode, and Panasonic KX-P / Tally emulation profiles are each selectable as built-ins
  2. Each new family profile ships a populated `init_sequence`/`reset_sequence` (`ESC @` where documented) and a sensible default codepage (`ESC t n` / `ESC R n` per command language)
  3. Every non-empty byte sequence is verbatim-from-manual with a cited source; undocumented capabilities stay empty bytes with no fabricated codes
  4. `claude-teletype diagnose` shows the fleet matrix — per-device classification and per-profile capability summary, including which families are still pending hardware confirmation (`human_needed`)
**Plans**: TBD

### Phase 30: Standalone macOS Packaging
**Goal**: A user without a Python install can download and run a macOS `.app` that does everything the dev install does — detection, simulator, and printing — and degrades the same way when USB is unavailable.
**Depends on**: Phase 29 (stable module graph and dependency set must be frozen last)
**Requirements**: PKG-01, PKG-02, PKG-03, PKG-04
**Success Criteria** (what must be TRUE):
  1. A macOS `.app` (PyInstaller onedir, console TUI mode) builds from a checked-in spec file and launches without a system Python
  2. The bundle includes libusb (explicit binary with the pyusb backend pointed at it), PortAudio, and Textual data files
  3. On a clean machine (no Homebrew, no dev Python) the launch, detection, simulator, and print paths all work
  4. When USB is unavailable the bundle degrades to the same CUPS/simulator fallback as the dev install
**Plans**: TBD

## Progress

| Phase | Milestone | Plans | Status | Completed |
|-------|-----------|-------|--------|-----------|
| 1. Streaming Pipeline | v1.0 | 2/2 | ✓ Complete | 2026-02-15 |
| 2. Terminal Simulator | v1.0 | 2/2 | ✓ Complete | 2026-02-15 |
| 3. Printer Hardware | v1.0 | 2/2 | ✓ Complete | 2026-02-15 |
| 4. Audio and Persistence | v1.0 | 2/2 | ✓ Complete | 2026-02-15 |
| 5. Multi-Turn Foundation | v1.1 | 3/3 | ✓ Complete | 2026-02-16 |
| 6. Error Handling | v1.1 | 2/2 | ✓ Complete | 2026-02-17 |
| 7. Word Wrap | v1.1 | 2/2 | ✓ Complete | 2026-02-17 |
| 8. No-TUI Bug Fix | v1.2 | 1/1 | ✓ Complete | 2026-02-17 |
| 9. Configuration System | v1.2 | 2/2 | ✓ Complete | 2026-02-17 |
| 10. Printer Profiles | v1.2 | 2/2 | ✓ Complete | 2026-02-17 |
| 11. Multi-LLM Backends | v1.2 | 2/2 | ✓ Complete | 2026-02-17 |
| 12. Typewriter Mode | v1.2 | 2/2 | ✓ Complete | 2026-02-17 |
| 13. Settings Panel | v1.2 | 2/2 | ✓ Complete | 2026-02-17 |
| 14. Verify Config & Traceability | v1.2 | 1/1 | ✓ Complete | 2026-02-17 |
| 15. Fix system_prompt Hot-Swap | v1.2 | 1/1 | ✓ Complete | 2026-02-17 |
| 16. Config and Profile Polish | v1.3 | 1/1 | ✓ Complete | 2026-02-20 |
| 17. Claude-CLI Warnings | v1.3 | 1/1 | ✓ Complete | 2026-02-20 |
| 18. Discovery Data Layer & Diagnostics | v1.4 | 1/1 | ✓ Complete | 2026-04-03 |
| 19. Printer Setup Screen | v1.4 | 3/3 | ✓ Complete | 2026-04-03 |
| 20. Config Persistence & Smart Startup | v1.4 | 2/2 | ✓ Complete | 2026-04-03 |
| 21. Profile Capability Fields & Custom-TOML Support | v1.5 | 3/3 | ✓ Complete | 2026-04-28 |
| 22. Encoded Style Sequences for Built-In Profiles | v1.5 | 1/1 | ✓ Complete | 2026-04-28 |
| 23. Streaming Markdown Renderer | v1.5 | 3/3 | ✓ Complete | 2026-04-28 |
| 24. TUI File Picker | v1.5 | 2/2 | ✓ Complete | 2026-04-28 |
| 25. `claude-teletype print` CLI Subcommand | v1.5 | 2/2 | ✓ Complete | 2026-04-28 |
| 26. Speed Dialog, Buffer Chunking, Cancel & Transcript Integration | v1.5 | 3/3 | ✓ Complete | 2026-04-28 |
| 27. Refactor — Package Split, Registry & Detection Seam | v1.6 | 0/? | Not started | - |
| 28. Fleet Detection & Bridge Registry | v1.6 | 0/? | Not started | - |
| 29. Per-Family Profile Catalog | v1.6 | 0/? | Not started | - |
| 30. Standalone macOS Packaging | v1.6 | 0/? | Not started | - |
