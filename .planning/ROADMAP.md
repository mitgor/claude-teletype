# Roadmap: Claude Teletype

## Milestones

- ✅ **v1.0 MVP** - Phases 1-4 (shipped 2026-02-15)
- ✅ **v1.1 Conversation Mode** - Phases 5-7 (shipped 2026-02-17)
- ✅ **v1.2 Configuration, Profiles, Multi-LLM, Settings** - Phases 8-15 (shipped 2026-02-17)
- ✅ **v1.3 Tech Debt Cleanup** - Phases 16-17 (shipped 2026-02-20)
- ✅ **v1.4 Printer Setup TUI** - Phases 18-20 (shipped 2026-04-03)
- 🚧 **v1.5 Markdown File Printing** - Phases 21-26 (in progress)

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

### v1.5 Markdown File Printing (In Progress)

**Milestone Goal:** Open and print local Markdown files through the TUI or CLI, rendering bold/italic/headings/lists/code/tables on capability-aware printer profiles, with per-print speed selection.

- [x] **Phase 21: Profile Capability Fields & Custom-TOML Support** - Extend `PrinterProfile` with style byte fields, fallback chain, and `buffer_bytes`; route the same fields through custom-TOML loader (completed 2026-04-28)
- [ ] **Phase 22: Encoded Style Sequences for Built-In Profiles** - Verified bold/italic/underline byte sequences for Epson ESC/P, IBM PPDS, HP PCL, Juki, OKI, and Citizen built-ins
- [ ] **Phase 23: Streaming Markdown Renderer** - Block-and-inline renderer that consumes profile capabilities, composes with `WordWrapper`, and preserves the CR+LF + reinit atomic newline pattern
- [ ] **Phase 24: TUI File Picker** - Markdown file picker rooted at cwd, launched from the main session via a keybinding, with cancel-back-to-chat semantics
- [ ] **Phase 25: `claude-teletype print` CLI Subcommand** - One-shot print path with and without an explicit file argument, honoring all existing config layers
- [ ] **Phase 26: Speed Dialog, Buffer Chunking, Cancel & Transcript Integration** - Per-print speed dialog, instant-mode `buffer_bytes` chunking, safe cancel semantics, and transcript fan-out for printed files

## Phase Details

### Phase 18: Discovery Data Layer & Diagnostics
**Goal**: Users can run a single diagnose command to see all discoverable printers, USB status, and pyusb availability -- and the app handles missing pyusb without crashing
**Depends on**: Phase 17 (v1.3 complete)
**Requirements**: DIAG-01, DEP-01
**Success Criteria** (what must be TRUE):
  1. User can run `claude-teletype diagnose` and see a structured report listing USB devices, CUPS queues, pyusb status, and libusb backend availability
  2. When pyusb is not installed, the app shows only CUPS printers in discovery output and does not crash or show tracebacks
  3. The diagnose command output distinguishes between "no devices found" and "pyusb not installed" states
**Plans**: 1 plan

Plans:
- [x] 18-01-PLAN.md -- Discovery dataclasses, discover_all(), diagnose CLI command

### Phase 19: Printer Setup Screen
**Goal**: Users see an interactive setup screen on startup where they can browse discovered devices, pick a connection method, assign a printer profile, install pyusb if missing, or skip to simulator mode
**Depends on**: Phase 18
**Requirements**: SETUP-01, SETUP-02, SETUP-03, SETUP-04, SETUP-05, DEP-02
**Success Criteria** (what must be TRUE):
  1. User sees a list of all discovered USB devices and CUPS printers on the setup screen at startup
  2. User can select between USB Direct and CUPS Queue connection methods for a chosen device
  3. User can assign a printer profile (juki/escp/ppds/pcl/generic) to a USB device, with the correct profile auto-suggested when VID:PID matches a known printer
  4. User can choose "Skip / Simulator" to bypass printer setup and use the app without hardware
  5. User sees inline discovery progress and connection status messages (e.g., "Scanning USB...", "3 CUPS queues found", "pyusb not installed -- USB detection unavailable") while the setup screen loads
  6. When pyusb is missing, user can trigger installation from within the setup screen and see a progress indicator while `uv sync --extra usb` runs asynchronously
**Plans**: 3 plans

Plans:
- [x] 19-01-PLAN.md -- PrinterSelection dataclass and create_driver_for_selection() factory
- [x] 19-02-PLAN.md -- PrinterSetupScreen widget layout, interactions, and tests
- [x] 19-03-PLAN.md -- TUI/CLI integration: wire setup screen into startup flow

### Phase 20: Config Persistence & Smart Startup
**Goal**: Users configure their printer once and the app remembers -- setup is skipped on subsequent launches when the saved printer is still connected
**Depends on**: Phase 19
**Requirements**: CFG-01, CFG-02
**Success Criteria** (what must be TRUE):
  1. After completing printer setup, the user's printer type, device identifier, and profile selection are saved to the TOML config file
  2. On next launch, if the saved printer is still connected (USB matched by VID:PID, CUPS matched by queue name), the setup screen is skipped and the app goes straight to chat
  3. On next launch, if the saved printer is NOT connected, the setup screen reappears so the user can reconfigure
**Plans**: 2 plans

Plans:
- [x] 20-01-PLAN.md -- Config fields, atomic save, persist printer selection after setup
- [x] 20-02-PLAN.md -- Smart startup: match saved printer against discovery, skip/show setup

### Phase 21: Profile Capability Fields & Custom-TOML Support
**Goal**: `PrinterProfile` exposes style byte fields and a buffer-size knob so the renderer (Phase 23) and instant-mode chunker (Phase 26) can consume them as data — and custom-TOML profiles can declare the same fields
**Depends on**: Phase 20 (v1.4 complete)
**Requirements**: CAP-01, CAP-02, CAP-03, CAP-06
**Success Criteria** (what must be TRUE):
  1. A user inspecting `PrinterProfile` (e.g. via `python -c "from claude_teletype.profiles import get_profile; print(get_profile('escp'))"`) sees `bold_on`, `bold_off`, `italic_on`, `italic_off`, `underline_on`, `underline_off`, and `buffer_bytes` fields with sensible defaults
  2. A user dropping a `[printer.profiles.my-printer]` block in `config.toml` with hex-encoded `bold_on`, `italic_on`, `underline_on`, etc. and an integer `buffer_bytes` sees those fields populate on `claude-teletype config show` (or via `load_custom_profiles`) without errors
  3. A renderer caller asking the profile "what should I emit for italic?" gets back italic codes when present, falls back to underline codes when italic is empty but underline is set, and falls back to plain text when both are empty — same chain for bold → underline → plain
  4. All existing v1.4 tests continue to pass (no regressions in profile loading, USB auto-detect, smart-startup matching, or `ProfilePrinterDriver` newline handling)
**Plans**: 3 plans

Plans:
- [x] 21-01-PLAN.md — Add PrinterProfile style capability fields (bold/italic/underline on/off) and buffer_bytes
- [x] 21-02-PLAN.md — Extend load_custom_profiles to read the seven new TOML keys
- [x] 21-03-PLAN.md — Add resolve_style fallback-chain helper (italic→underline→plain, bold→underline→plain)

### Phase 22: Encoded Style Sequences for Built-In Profiles
**Goal**: Each built-in profile ships with the bold/italic/underline byte sequences that real hardware actually accepts, so users on Epson, IBM PPDS, HP PCL, Juki, OKI, and Citizen printers see styled output without writing custom-TOML
**Depends on**: Phase 21
**Requirements**: CAP-04, CAP-05
**Success Criteria** (what must be TRUE):
  1. User running the renderer (forward-look from Phase 23) on the `escp` profile sees `**bold**` text print in actual bold and `*italic*` text print in italic — using the documented Epson ESC E / ESC F (bold) and ESC 4 / ESC 5 (italic) sequences
  2. User on the `ppds` (IBM) and `pcl` (HP) profiles sees the corresponding bold and italic sequences emitted with each style verified against the printer family's published reference manual
  3. User on the `juki-6100`, `juki-2200`, `oki-3390`, and `citizen-cts2000` profiles sees whichever style codes are documented for that family populated; any style the family does not support is left as empty bytes (no fabricated codes that would print garbage)
  4. `claude-teletype diagnose` (or an equivalent inspection path) shows for each profile which style capabilities are populated vs. empty, so users can see at a glance what to expect on their printer
**Plans**: TBD

### Phase 23: Streaming Markdown Renderer
**Goal**: A streaming renderer turns markdown text into a sequence of `(plain_char, optional_style_bytes)` events that compose with the existing `WordWrapper` and `ProfilePrinterDriver` newline pattern — so wrapped lines preserve list indentation, blockquote prefixes, and the atomic CR+LF + reinit transfer
**Depends on**: Phase 21 (capability fields), Phase 22 (encoded codes for visible output)
**Requirements**: MD-01, MD-02, MD-03, MD-04, MD-05, MD-06, MD-07, MD-08
**Success Criteria** (what must be TRUE):
  1. User feeding a markdown string with `**bold**` and `*italic*` inline emphasis to the renderer sees those spans wrapped in the active profile's style-on/style-off byte pairs (or the documented fallback) in the renderer's output stream
  2. User rendering a document with `#` through `######` ATX headings sees each heading printed in bold with one extra blank line above; lists (`-`/`*`/`+` and ordered numbers) print with stable bullet/number glyphs and indentation that survives word-wrap; blockquotes (`>`) emit a quote-marker prefix on every wrapped line
  3. User rendering a fenced code block (```` ``` ````) sees its contents printed verbatim with no inline-emphasis processing — `*not italic*` stays as literal `*not italic*` inside the block
  4. User rendering a GitHub-flavored table sees an ASCII grid that fits within `profile.columns` (column widths chosen from cell content, gracefully truncated when a row would otherwise overflow)
  5. User watching the printer through a sample document sees newlines emit the existing CR+LF + reinit atomic transfer (Juki/CH341 still prints every line) — verified by reusing `ProfilePrinterDriver.write` for `\n` rather than re-implementing newline handling
**Plans**: TBD

### Phase 24: TUI File Picker
**Goal**: Users in the main chat session press a keybinding, browse markdown files starting from the cwd, see the resolved path of the highlighted file, and either pick one to print or cancel back to the chat
**Depends on**: Phase 23 (picker is the entry that hands a path to the renderer)
**Requirements**: PICK-01, PICK-02, PICK-03, PICK-04, PICK-05
**Success Criteria** (what must be TRUE):
  1. User in the main TUI session presses the picker keybinding and a markdown file picker opens, rooted at the directory `claude-teletype` was launched from
  2. User can navigate into subdirectories and back to the parent (`..`) entry; only `.md` and `.markdown` files plus directories appear in the list
  3. User sees the absolute path of the currently-highlighted file displayed in the picker so they know exactly what they're about to print
  4. User pressing escape (or selecting an explicit "Cancel" entry) closes the picker and returns to the chat session with no print job started, no transcript entry, and no printer-state side effects
  5. User selecting a file dispatches the renderer (Phase 23) against that path and the picker closes back to the chat
**Plans**: TBD
**UI hint**: yes

### Phase 25: `claude-teletype print` CLI Subcommand
**Goal**: Users print a markdown file in one shot from the shell — either by passing the path directly or by launching the picker and exiting after the print — without ever entering the chat TUI
**Depends on**: Phase 23 (renderer), Phase 24 (picker, for the no-arg path)
**Requirements**: CLI-01, CLI-02, CLI-03, CLI-04
**Success Criteria** (what must be TRUE):
  1. User running `claude-teletype print README.md` sees the file print to the active printer with the renderer's output and the process exits cleanly with status 0 when done
  2. User running `claude-teletype print` with no path sees the same TUI file picker from Phase 24, prints the chosen file, and exits when the print completes (no chat session started)
  3. User's TOML config, env vars, and CLI flags (delay, audio, printer profile, saved-printer matching) are all honored by `print` exactly as they are by the chat command — verified by `--printer escp claude-teletype print foo.md` and `CLAUDE_TELETYPE_DELAY=10 claude-teletype print foo.md` producing the expected style codes and pacing
  4. User running `claude-teletype print /nonexistent.md` or `claude-teletype print /etc` (a directory) sees a clear error message and the process exits with a non-zero status
**Plans**: TBD
**UI hint**: yes

### Phase 26: Speed Dialog, Buffer Chunking, Cancel & Transcript Integration
**Goal**: Each markdown print job opens with a speed-mode dialog whose default reflects the active profile, instant mode chunks writes at the profile's `buffer_bytes` boundary, the user can cancel mid-print without crashing or stranding open style codes, and printed files appear in the active session transcript as plain text
**Depends on**: Phase 23 (renderer), Phase 24 (TUI entry), Phase 25 (CLI entry)
**Requirements**: FLOW-01, FLOW-02, FLOW-03, FLOW-04, FLOW-05, TXN-01, TXN-02, TXN-03
**Success Criteria** (what must be TRUE):
  1. User triggering a print job from either the picker or the CLI subcommand sees a dialog asking "Typewriter pacing or instant?", with the default selection set to the active profile's `instant_output` value
  2. User picking typewriter mode sees the file print with the same `pace_characters` cadence and audio cues as conversation streaming — pacing pipeline is reused, not re-implemented
  3. User picking instant mode on an impact printer (e.g. Juki via CH341) sees the file print without buffer overruns because writes are chunked at the active profile's `buffer_bytes` boundary; the CR+LF + reinit atomic newline pattern is still preserved
  4. User pressing cancel mid-print returns to the chat session (or exits the CLI subcommand) cleanly: no traceback, the printer is not left in bold/italic/underline state (every opened style code is paired with its corresponding close), and re-opening the picker works immediately
  5. User with an active conversation session sees a "Printed file: `<absolute_path>`" header followed by the plain-text rendered body appended to the session transcript — with no raw ESC bytes — and a user with no active session sees no transcript file created (existing optional-transcript behavior preserved)
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 21 → 22 → 23 → 24 → 25 → 26

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
| 21. Profile Capability Fields & Custom-TOML Support | v1.5 | 3/3 | Complete   | 2026-04-28 |
| 22. Encoded Style Sequences for Built-In Profiles | v1.5 | 0/TBD | Not started | — |
| 23. Streaming Markdown Renderer | v1.5 | 0/TBD | Not started | — |
| 24. TUI File Picker | v1.5 | 0/TBD | Not started | — |
| 25. `claude-teletype print` CLI Subcommand | v1.5 | 0/TBD | Not started | — |
| 26. Speed Dialog, Buffer Chunking, Cancel & Transcript Integration | v1.5 | 0/TBD | Not started | — |
