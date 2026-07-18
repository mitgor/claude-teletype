# Roadmap: Claude Teletype

## Milestones

- ✅ **v1.0 MVP** - Phases 1-4 (shipped 2026-02-15)
- ✅ **v1.1 Conversation Mode** - Phases 5-7 (shipped 2026-02-17)
- 🚧 **v1.2 Configuration, Profiles, Multi-LLM, Settings** - Phases 8-15 (in progress)

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

### 🚧 v1.2 Configuration, Profiles, Multi-LLM, Settings (In Progress)

- [x] **Phase 8: No-TUI Bug Fix** - Fix --no-tui crash and add test coverage for headless mode (completed 2026-02-17)
- [x] **Phase 9: Configuration System** - Persistent TOML config with CLI overrides and env var support (completed 2026-02-17)
- [x] **Phase 10: Printer Profiles** - Named printer profiles with per-device control codes and auto-detection (completed 2026-02-17)
- [x] **Phase 11: Multi-LLM Backends** - OpenAI and OpenRouter support via openai SDK alongside Claude Code CLI (completed 2026-02-17)
- [x] **Phase 12: Typewriter Mode** - Direct-to-printer typing with pacing and sound, no LLM (completed 2026-02-17)
- [x] **Phase 13: Settings Panel** - TUI modal for runtime configuration of printer, LLM, delay, and audio (completed 2026-02-17)
- [x] **Phase 14: Verify Configuration System & Update Traceability** - Verify Phase 9 CFG requirements, create VERIFICATION.md, update all requirement checkboxes (completed 2026-02-17)
- [x] **Phase 15: Fix system_prompt Backend Hot-Swap** - Preserve system_prompt when switching backends via settings modal (completed 2026-02-17)

## Phase Details

### Phase 8: No-TUI Bug Fix
**Goal**: Headless mode works reliably so users without a terminal can pipe output
**Depends on**: Nothing (standalone fix on existing code)
**Requirements**: FIX-01
**Success Criteria** (what must be TRUE):
  1. User can run `claude-teletype --no-tui` and complete a full conversation without crash
  2. StreamResult metadata is handled gracefully in the non-TUI code path
  3. Automated tests cover the --no-tui conversation flow including StreamResult handling
**Plans**: 1 plan
- [ ] 08-01-PLAN.md — TDD: Fix _chat_async StreamResult crash and add test coverage

### Phase 9: Configuration System
**Goal**: Users can persist and override their preferences without editing CLI flags every run
**Depends on**: Phase 8
**Requirements**: CFG-01, CFG-02, CFG-03, CFG-04, CFG-05
**Success Criteria** (what must be TRUE):
  1. User can create a config file via `--init-config` and find it at the platform-standard location
  2. User can set preferences (delays, sound, default printer) in the TOML file and they take effect on next run
  3. User can override any config value with a CLI flag for a single session without modifying the file
  4. User can run `claude-teletype config show` and see the effective merged configuration (file + env + flags)
  5. User can set `CLAUDE_TELETYPE_*` environment variables that override config file values
**Plans**: 2 plans
- [x] 09-01-PLAN.md — TDD: Config module (TeletypeConfig dataclass, TOML load/save, env overrides, CLI merge)
- [x] 09-02-PLAN.md — CLI restructure with config subcommands and three-layer config integration

### Phase 10: Printer Profiles
**Goal**: Users can target different printer hardware without manually configuring control codes
**Depends on**: Phase 9 (profiles stored in and selected via config)
**Requirements**: PRNT-01, PRNT-02, PRNT-03, PRNT-04
**Success Criteria** (what must be TRUE):
  1. User can select a named printer profile via `--printer juki` or set a default in config
  2. Built-in profiles for Juki, Epson ESC/P, IBM PPDS, HP PCL, and generic printers send correct init/reset sequences
  3. User can define a custom printer profile with arbitrary ESC sequences in their config file
  4. When a known USB device is plugged in, its matching profile is auto-selected without user intervention
**Plans**: 2 plans
- [ ] 10-01-PLAN.md — TDD: PrinterProfile dataclass, built-in profile registry, custom TOML loading, USB auto-detection
- [ ] 10-02-PLAN.md — ProfilePrinterDriver integration, --printer CLI flag, config extension, teletype profile support

### Phase 11: Multi-LLM Backends
**Goal**: Users can choose their preferred LLM provider instead of being locked to Claude Code CLI
**Depends on**: Phase 9 (API key references and backend selection stored in config)
**Requirements**: LLM-01, LLM-02, LLM-03, LLM-04
**Success Criteria** (what must be TRUE):
  1. User can switch between Claude Code CLI, OpenAI, and OpenRouter backends via config or `--backend` flag
  2. User can have a multi-turn conversation with an OpenAI or OpenRouter model with streaming character output
  3. User can select a specific model within a backend via `--model gpt-4o` or config default
  4. User gets a clear, actionable error on startup if the selected backend has no API key or is unreachable
**Plans**: 2 plans
- [ ] 11-01-PLAN.md — TDD: Backend ABC, factory, Claude CLI wrapper, OpenAI/OpenRouter streaming backends with tests
- [ ] 11-02-PLAN.md — Config/CLI/TUI integration: --backend/--model flags, [llm] config section, backend-polymorphic streaming

### Phase 12: Typewriter Mode
**Goal**: Users can use the tool as a pure mechanical typewriter -- keystrokes to paper with pacing and sound
**Depends on**: Phase 10 (printer profile needed for output destination)
**Requirements**: TYPE-01, TYPE-03
**Success Criteria** (what must be TRUE):
  1. User can enter typewriter mode (no LLM) and see their keystrokes appear on screen with typewriter pacing and sound
  2. User's keystrokes are simultaneously sent to the connected printer with correct control codes from the active profile
**Plans**: 2 plans
- [ ] 12-01-PLAN.md — TypewriterScreen + keystroke audio (on_key capture, pacing queue, multiplexed output)
- [ ] 12-02-PLAN.md — TUI integration (ctrl+t binding, push_screen wiring, integration test)

### Phase 13: Settings Panel
**Goal**: Users can adjust runtime settings without leaving the TUI or editing files
**Depends on**: Phase 11 (needs all configurable features to exist)
**Requirements**: SET-01
**Success Criteria** (what must be TRUE):
  1. User can open a settings modal via keyboard shortcut while in the TUI
  2. User can change printer profile, LLM backend/model, character delay, and audio toggle from the modal
  3. Changed settings take effect immediately in the current session without restart
**Plans**: 2 plans
- [ ] 13-01-PLAN.md — SettingsScreen modal with form widgets and tests
- [ ] 13-02-PLAN.md — TUI integration (ctrl+s binding, apply callback, CLI tracking kwargs)

### Phase 14: Verify Configuration System & Update Traceability
**Goal**: Close the 5 orphaned CFG requirements by verifying Phase 9's implementation and updating all milestone traceability
**Depends on**: Phase 9 (verifies its output)
**Requirements**: CFG-01, CFG-02, CFG-03, CFG-04, CFG-05
**Gap Closure:** Closes gaps from audit — Phase 9 executed but never verified (no VERIFICATION.md)
**Success Criteria** (what must be TRUE):
  1. All 5 CFG requirements verified as working in the codebase with evidence
  2. Phase 9 VERIFICATION.md created with pass/fail results
  3. REQUIREMENTS.md checkboxes updated for all 17 v1.2 requirements (12 satisfied + 5 pending verification)
**Plans**: 1 plan
- [ ] 14-01-PLAN.md — Verify Phase 9 CFG-01..05, create VERIFICATION.md, update REQUIREMENTS.md traceability

### Phase 15: Fix system_prompt Backend Hot-Swap
**Goal**: Preserve system_prompt when switching backends via settings modal so users don't lose their custom prompt
**Depends on**: Phase 13 (fixes integration issue in settings apply)
**Requirements**: SET-01, LLM-02 (integration fix)
**Gap Closure:** Closes integration gap from audit — system_prompt dropped during backend hot-swap
**Success Criteria** (what must be TRUE):
  1. system_prompt is preserved when user switches backends via settings modal
  2. TeletypeApp stores system_prompt as tracking attribute
  3. Automated test verifies system_prompt survives backend hot-swap
**Plans**: 1 plan
- [ ] 15-01-PLAN.md — TDD: Add _system_prompt tracking, pass to create_backend in _apply_settings, test coverage



## Progress

**Execution Order:**
Phases execute in numeric order: 8 -> 9 -> 10 -> 11 -> 12 -> 13 -> 14 -> 15

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Streaming Pipeline | v1.0 | 2/2 | ✓ Complete | 2026-02-15 |
| 2. Terminal Simulator | v1.0 | 2/2 | ✓ Complete | 2026-02-15 |
| 3. Printer Hardware | v1.0 | 2/2 | ✓ Complete | 2026-02-15 |
| 4. Audio and Persistence | v1.0 | 2/2 | ✓ Complete | 2026-02-15 |
| 5. Multi-Turn Foundation | v1.1 | 3/3 | ✓ Complete | 2026-02-16 |
| 6. Error Handling | v1.1 | 2/2 | ✓ Complete | 2026-02-17 |
| 7. Word Wrap | v1.1 | 2/2 | ✓ Complete | 2026-02-17 |
| 8. No-TUI Bug Fix | v1.2 | Complete    | 2026-02-17 | - |
| 9. Configuration System | v1.2 | 2/2 | Complete | 2026-02-17 |
| 10. Printer Profiles | v1.2 | Complete    | 2026-02-17 | - |
| 11. Multi-LLM Backends | v1.2 | Complete    | 2026-02-17 | - |
| 12. Typewriter Mode | v1.2 | Complete    | 2026-02-17 | - |
| 13. Settings Panel | v1.2 | Complete    | 2026-02-17 | - |
| 14. Verify Config & Traceability | v1.2 | Complete    | 2026-02-17 | - |
| 15. Fix system_prompt Hot-Swap | v1.2 | Complete    | 2026-02-17 | - |
