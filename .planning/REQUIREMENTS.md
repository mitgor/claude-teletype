# Requirements: Claude Teletype

**Defined:** 2026-02-17
**Core Value:** The physical typewriter experience — characters appearing on paper one at a time with authentic pacing and sound, making AI conversation feel tangible and mechanical.

## v1.2 Requirements

Requirements for v1.2 milestone. Each maps to roadmap phases.

### Configuration

- [ ] **CFG-01**: User can persist settings in a TOML config file at the platform-standard location
- [ ] **CFG-02**: User gets a config file with documented defaults on first run or via `--init-config`
- [ ] **CFG-03**: User can override any config value with a CLI flag for one session
- [ ] **CFG-04**: User can run `claude-teletype config show` to see effective merged configuration
- [ ] **CFG-05**: User can override config values via `CLAUDE_TELETYPE_*` environment variables

### Printer Profiles

- [ ] **PRNT-01**: User can select a named printer profile via `--printer <name>` or config default
- [ ] **PRNT-02**: User gets built-in profiles for Juki, Epson ESC/P, IBM PPDS, HP PCL, and generic printers
- [ ] **PRNT-03**: User can define custom printer profiles with arbitrary ESC sequences in config file
- [ ] **PRNT-04**: Printer profile auto-selects when a USB device matches a profile's vendor:product ID

### Multi-LLM

- [ ] **LLM-01**: User can switch between LLM backends (Claude Code CLI, OpenAI, OpenRouter) via config or CLI flag
- [ ] **LLM-02**: User can chat with OpenAI or OpenRouter models via direct API using the `openai` library
- [ ] **LLM-03**: User can select a specific model within a backend via `--model` flag or config default
- [ ] **LLM-04**: User gets a clear error message on startup if the selected backend is unreachable or misconfigured

### Settings UI

- [ ] **SET-01**: User can open a settings modal in the TUI via keyboard shortcut to change printer, LLM, delay, and audio

### Typewriter Mode

- [ ] **TYPE-01**: User can enter typewriter mode where keystrokes go directly to screen with pacing and sound, no LLM
- [ ] **TYPE-03**: User's typewriter keystrokes are sent to the connected printer simultaneously

### Bug Fix

- [ ] **FIX-01**: `--no-tui` mode handles StreamResult without crashing and has test coverage

## Future Requirements

Deferred to v1.3+. Tracked but not in current roadmap.

### Settings UI

- **SET-02**: Live settings preview showing pacing speed in real-time
- **SET-03**: Settings persist to config file via `tomli-w` write-back

### Typewriter Mode

- **TYPE-02**: Line counter, character position, and paper edge indicator in status bar

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| GUI configuration editor | TUI settings modal IS the GUI; this is a terminal tool |
| LLM plugin system | Over-engineering for 3 backends; clean protocol makes adding more trivial |
| LiteLLM integration | 67MB+ dependency for what `openai` library handles in ~2MB |
| Network printer support | Destroys character-by-character streaming (page buffering) |
| Conversation history to disk for API backends | Complex; in-memory only for v1.2, `--resume` stays Claude CLI only |
| Encrypted API key storage | Env vars solve this; keyring integration adds OS-specific complexity |
| Real-time config file watching | Over-engineering; settings screen for runtime, config read at startup |
| WYSIWYG paper preview | Requires virtual printer emulator; massive scope creep |
| Printer driver auto-installation | System-level package management varies across distros |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FIX-01 | Phase 8 | Pending |
| CFG-01 | Phase 9 → 14 | Pending |
| CFG-02 | Phase 9 → 14 | Pending |
| CFG-03 | Phase 9 → 14 | Pending |
| CFG-04 | Phase 9 → 14 | Pending |
| CFG-05 | Phase 9 → 14 | Pending |
| PRNT-01 | Phase 10 | Pending |
| PRNT-02 | Phase 10 | Pending |
| PRNT-03 | Phase 10 | Pending |
| PRNT-04 | Phase 10 | Pending |
| LLM-01 | Phase 11 | Pending |
| LLM-02 | Phase 11 | Pending |
| LLM-03 | Phase 11 | Pending |
| LLM-04 | Phase 11 | Pending |
| TYPE-01 | Phase 12 | Pending |
| TYPE-03 | Phase 12 | Pending |
| SET-01 | Phase 13 | Pending |

**Coverage:**
- v1.2 requirements: 17 total
- Mapped to phases: 17
- Unmapped: 0

---
*Requirements defined: 2026-02-17*
*Last updated: 2026-02-17 after roadmap creation*
