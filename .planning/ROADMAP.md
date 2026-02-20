# Roadmap: Claude Teletype

## Milestones

- ✅ **v1.0 MVP** - Phases 1-4 (shipped 2026-02-15)
- ✅ **v1.1 Conversation Mode** - Phases 5-7 (shipped 2026-02-17)
- ✅ **v1.2 Configuration, Profiles, Multi-LLM, Settings** - Phases 8-15 (shipped 2026-02-17)
- 🚧 **v1.3 Tech Debt Cleanup** - Phases 16-17 (in progress)

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

### 🚧 v1.3 Tech Debt Cleanup (In Progress)

- [ ] **Phase 16: Config and Profile Polish** - IBM alias for PPDS profile and annotated config show output
- [ ] **Phase 17: Claude-CLI Warnings** - Startup and hot-swap warnings for claude-cli backend limitations

## Phase Details

### Phase 16: Config and Profile Polish
**Goal**: Users can easily discover and understand printer profiles and configuration sources
**Depends on**: Nothing (first phase of v1.3; builds on shipped v1.2)
**Requirements**: PROF-01, CONF-01
**Success Criteria** (what must be TRUE):
  1. User can pass `--profile ibm` and it resolves to the PPDS printer profile
  2. User running `config show` sees every effective setting annotated with its source (file, env, or default)
  3. The "ibm" alias appears in profile listing and help text so users can discover it without reading docs
**Plans**: 1 plan

Plans:
- [ ] 16-01-PLAN.md — IBM alias for PPDS profile + annotated config show with source tags

### Phase 17: Claude-CLI Warnings
**Goal**: Users are warned before silent data loss or ignored configuration when using the claude-cli backend
**Depends on**: Phase 16 (sequential execution; no technical dependency)
**Requirements**: WARN-01, WARN-02
**Success Criteria** (what must be TRUE):
  1. User who starts the app with system_prompt configured and backend=claude-cli sees a visible warning explaining that system_prompt is ignored (CLAUDE.md is used instead)
  2. User in the settings modal who switches away from claude-cli to another backend sees a warning that the current session context will be lost
  3. Warnings are informational only -- they do not block the user from proceeding
**Plans**: TBD

Plans:
- [ ] 17-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 16 → 17

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
| 16. Config and Profile Polish | v1.3 | 0/1 | Not started | - |
| 17. Claude-CLI Warnings | v1.3 | 0/1 | Not started | - |
