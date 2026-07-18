# Roadmap: Claude Teletype

## Milestones

- ✅ **v1.0 MVP** - Phases 1-4 (shipped 2026-02-15)
- ✅ **v1.1 Conversation Mode** - Phases 5-7 (shipped 2026-02-17)
- ✅ **v1.2 Configuration, Profiles, Multi-LLM, Settings** - Phases 8-15 (shipped 2026-02-17)
- ✅ **v1.3 Tech Debt Cleanup** - Phases 16-17 (shipped 2026-02-20)
- ✅ **v1.4 Printer Setup TUI** - Phases 18-20 (shipped 2026-04-03)
- ✅ **v1.5 Markdown File Printing** - Phases 21-26 (shipped 2026-04-28)
- ✅ **v1.6 Printer Fleet & Standalone** - Phases 27-30 (shipped 2026-06-13, archived 2026-07-18)
- 🚧 **v1.7 Review Hardening** - Phases 31-34 (in progress)

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

<details>
<summary>✅ v1.6 Printer Fleet & Standalone (Phases 27-30) - SHIPPED 2026-06-13</summary>

- [x] Phase 27: Refactor — Package Split, Registry & Detection Seam — completed 2026-06-13 (plan 27-01 GSD-tracked; remainder executed reactively)
- [x] Phase 28: Fleet Detection & Bridge Registry — completed 2026-06-13 (reactive execution)
- [x] Phase 29: Per-Family Profile Catalog — completed 2026-06-13 (reactive execution)
- [x] Phase 30: Standalone macOS Packaging — completed 2026-06-13 (reactive execution; PKG-03 clean-machine run deferred)

Full details: [milestones/v1.6-ROADMAP.md](milestones/v1.6-ROADMAP.md)

Note: Phases 28-30 ran outside GSD phase tracking — no PLAN/SUMMARY artifacts; requirements code-verified at close (27/29, REF-06 + PKG-03 deferred).

</details>

### v1.7 Review Hardening (In Progress)

- [x] **Phase 31: Byte Integrity Criticals** - Fix the ASCII round-trip corruptions in both driver paths and the teletype-mode byte defects, locked in by a regression test (completed 2026-07-18)
- [x] **Phase 32: Setup & Detection Flow Fixes** - Repair the kernel-owns → CUPS misroute and the setup/startup contract gaps (registry case, frozen `uv sync`, profile hand-off) (completed 2026-07-18)
- [ ] **Phase 33: Shared Print Pipeline** - One cancel-safe pipeline for CLI and TUI printing; escape actually cancels; no blocking `input()` under Textual
- [ ] **Phase 34: Architecture Cleanup** - Registry as the real seam, one-file-per-family catalog, dead code removed, no private-attribute reach-ins

## Phase Details (v1.7)

### Phase 31: Byte Integrity Criticals

**Goal**: Every byte a profile declares — codepage commands, style sequences, cp437/cp866 text — reaches the printer verbatim on every driver path, including typewriter mode
**Depends on**: Nothing (first phase of milestone)
**Requirements**: BYTE-01, BYTE-02, BYTE-03, BYTE-04
**Success Criteria** (what must be TRUE):

  1. User printing with a high-byte profile sequence (e.g. ppds `codepage_command` ending 0xb5) gets those exact bytes on the USB wire — `ProfilePrinterDriver._send_raw` routes through `write_bytes`, never a str round-trip (CR-01)
  2. User printing cp437/cp866 text over a CUPS queue sees correct glyphs, not `?` — `CupsPrinterDriver.write_bytes` preserves bytes ≥ 0x80 end-to-end (CR-02)
  3. A regression test round-trips a 0xb5-bearing sequence through both ProfilePrinterDriver and CupsPrinterDriver and fails if any byte is altered
  4. User in typewriter mode with a high-byte custom profile sees no `UnicodeDecodeError`, reset sequences go out as a single `write_bytes` transfer, and Ctrl-C exits cleanly through the restore/formfeed/reset path (WR-02)

**Plans**: 2 plans

Plans:
**Wave 1**

- [x] 31-01-PLAN.md — Fix _send_raw (CR-01) and CupsPrinterDriver byte buffer (CR-02); BYTE-03 regression test

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 31-02-PLAN.md — Typewriter mode WR-02 fixes (init/reset via write_bytes, Ctrl-C clean exit); full-suite gate

### Phase 32: Setup & Detection Flow Fixes

**Goal**: Setup and smart startup always route the user to the driver and profile they chose — never silently to the simulator, a wrong profile, or a foreign-directory `uv sync`
**Depends on**: Phase 31 (CUPS driver byte path must be sound before FLOW-01 routes more users onto it)
**Requirements**: FLOW-01, FLOW-02, FLOW-03, FLOW-04
**Success Criteria** (what must be TRUE):

  1. User whose native-USB printer is kernel-claimed and who accepts the recommended CUPS path gets a working CUPS driver with a resolved queue name — never a silent NullPrinterDriver, and the broken empty-ID state is never persisted to config (CR-03)
  2. User with an uppercase-named custom TOML profile can select it from the setup screen and via `--printer` — `ProfileRegistry` lookups are case-insensitive (WR-03)
  3. User running the frozen `.app` never sees "Install USB Support" trigger `uv sync` against an arbitrary working directory — install is hidden or guarded when frozen (WR-05)
  4. Smart startup reconnect restores the saved profile through an explicit `match_saved_printer` parameter — the caller-side `saved_match.profile_name = ...` mutation is gone (ARCH-04)

**Plans**: TBD

### Phase 33: Shared Print Pipeline

**Goal**: One print-pipeline implementation serves the CLI `print` subcommand and the TUI file-print path, cancelable mid-render without freezing the app
**Depends on**: Phase 31 (pipeline consolidation builds on the corrected byte channel)
**Requirements**: PIPE-01, PIPE-02, PIPE-03
**Success Criteria** (what must be TRUE):

  1. A single shared `render_document`-style function drives both CLI and TUI printing, with `finally: renderer.close()` cancel-safety in both paths — a pipeline change is a one-place edit (ARCH-01); PIPE-01 lands before or with the cancel work since it changes the code the cancel fix touches
  2. User can press escape during an in-TUI paced print and the print stops with printer style state clean — pacing no longer blocks the Textual event loop with synchronous `time.sleep` (WR-01)
  3. User printing via the picker with multiple CUPS queues never hits an invisible blocking `input()` prompt — driver resolution is non-interactive under Textual (WR-04)

**Plans**: 2 plans

Plans:
**Wave 1**

- [x] 33-01-PLAN.md — Extract shared render_document pipeline (PIPE-01) + picker driver pre-resolution (PIPE-03)

**Wave 2** *(blocked on Wave 1)*

- [ ] 33-02-PLAN.md — TUI thread-worker adapter with escape cancel (PIPE-02); full-suite gate

### Phase 34: Architecture Cleanup

**Goal**: `ProfileRegistry` is the single profile seam end-to-end, the catalog is the single home for family data, and shim-era dead code is gone
**Depends on**: Phase 32 (registry case-insensitivity), Phase 33 (pipeline consolidation removes the dead `all_profiles` plumbing it would otherwise fight)
**Requirements**: ARCH-CLEAN-01, ARCH-CLEAN-02, ARCH-CLEAN-03, ARCH-CLEAN-04
**Success Criteria** (what must be TRUE):

  1. The `ProfileRegistry` object flows through cli → TeletypeApp → PrinterSetupScreen → `create_driver_for_selection` with no flatten-to-dict-and-rebuild, and an unknown profile name fails loudly instead of silently skipping profile wrapping (ARCH-02)
  2. Adding a printer family means adding exactly one `catalog/<family>.py` file — `_load_catalog` discovers modules automatically, remaining inline families and alias blocks live in catalog modules (ARCH-03)
  3. Dead code is gone: unused `all_profiles` parameter, the unused 91-line `printing/__init__` facade (trimmed or adopted), stale shim-era docstrings, and redundant juki compat paths beyond the alias profile — with the full test suite green (ARCH-07, ARCH-08, IN-01)
  4. `tui.py` reads connection info through a public driver property — no `_inner` private reach-in (ARCH-06)

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
| 27. Refactor — Package Split, Registry & Detection Seam | v1.6 | 6/6 | ✓ Complete | 2026-06-13 |
| 28. Fleet Detection & Bridge Registry | v1.6 | reactive | ✓ Complete | 2026-06-13 |
| 29. Per-Family Profile Catalog | v1.6 | reactive | ✓ Complete | 2026-06-13 |
| 30. Standalone macOS Packaging | v1.6 | reactive | ✓ Complete | 2026-06-13 |
| 31. Byte Integrity Criticals | v1.7 | 2/2 | Complete    | 2026-07-18 |
| 32. Setup & Detection Flow Fixes | v1.7 | 2/2 | Complete    | 2026-07-18 |
| 33. Shared Print Pipeline | v1.7 | 1/2 | In Progress|  |
| 34. Architecture Cleanup | v1.7 | 0/? | Not started | - |
