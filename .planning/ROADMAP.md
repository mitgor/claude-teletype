# Roadmap: Claude Teletype

## Milestones

- ✅ **v1.0 MVP** - Phases 1-4 (shipped 2026-02-15)
- ✅ **v1.1 Conversation Mode** - Phases 5-7 (shipped 2026-02-17)
- ✅ **v1.2 Configuration, Profiles, Multi-LLM, Settings** - Phases 8-15 (shipped 2026-02-17)
- ✅ **v1.3 Tech Debt Cleanup** - Phases 16-17 (shipped 2026-02-20)
- 🚧 **v1.4 Printer Setup TUI** - Phases 18-20 (in progress)

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

### v1.4 Printer Setup TUI (In Progress)

**Milestone Goal:** Interactive TUI screen for discovering, selecting, and configuring printers at startup -- replacing silent auto-detection with a visible, user-driven setup flow.

- [x] **Phase 18: Discovery Data Layer & Diagnostics** - Structured discovery primitives and CLI diagnose command (completed 2026-04-03)
- [x] **Phase 19: Printer Setup Screen** - Interactive TUI for device selection, profile assignment, and pyusb install (completed 2026-04-03)
- [ ] **Phase 20: Config Persistence & Smart Startup** - Save printer selection to TOML and skip setup on reconnect

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
- [ ] 20-02-PLAN.md -- Smart startup: match saved printer against discovery, skip/show setup

## Progress

**Execution Order:**
Phases execute in numeric order: 18 → 19 → 20

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
| 18. Discovery Data Layer & Diagnostics | v1.4 | 1/1 | Complete    | 2026-04-03 |
| 19. Printer Setup Screen | v1.4 | 3/3 | Complete    | 2026-04-03 |
| 20. Config Persistence & Smart Startup | v1.4 | 1/2 | In Progress|  |
