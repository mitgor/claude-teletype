# Requirements: Claude Teletype

**Defined:** 2026-02-14
**Core Value:** The physical typewriter experience — characters appearing on paper one at a time with authentic pacing and sound, making AI conversation feel tangible and mechanical.

## v1.0 Requirements (Complete)

All v1.0 requirements shipped and verified.

### Claude Integration

- [x] **CLDE-01**: User can send prompts to Claude Code via CLI wrapper using `--output-format stream-json --verbose --include-partial-messages`
- [x] **CLDE-02**: Tool parses NDJSON stream and extracts `text_delta` events for character-by-character output
- [x] **CLDE-03**: Tool shows a thinking indicator while waiting for Claude's first token

### Character Output

- [x] **CHAR-01**: Characters appear one at a time with configurable delay (50-100ms default range)
- [x] **CHAR-02**: All output is mirrored to both terminal screen and printer simultaneously
- [x] **CHAR-03**: Character pacing varies by context (punctuation 1.5x slower, newlines 3x pause, spaces 0.5x faster)

### Printer Hardware

- [x] **PRNT-01**: Tool auto-discovers USB-LPT adapters on startup via CUPS scan and USB device enumeration
- [x] **PRNT-02**: User can manually specify a printer device via `--device` CLI flag
- [x] **PRNT-03**: Tool gracefully falls back to simulator mode if printer disconnects mid-session without crashing

### Terminal Simulator

- [x] **SIML-01**: Split-screen TUI launches as default mode when no printer hardware is found (Textual-based, top=output, bottom=input)
- [x] **SIML-02**: Simulator renders characters with same typewriter pacing as physical printer output

### Audio

- [x] **AUDI-01**: Carriage return / line break triggers a bell/ding sound effect via sounddevice

### Persistence

- [x] **PERS-01**: Conversations are saved to timestamped plain text transcript files on disk

## v1.1 Requirements

Requirements for multi-turn conversation milestone. Each maps to roadmap phases.

### Multi-Turn Conversation

- [ ] **CONV-01**: User can have a multi-turn conversation in the TUI (prompt → response → prompt loop with full context)
- [ ] **CONV-02**: Claude remembers all previous turns within a session via `--resume <session_id>`
- [ ] **CONV-03**: User sees visual separators between conversation turns in TUI and on printer
- [ ] **CONV-04**: User sees context usage indicator (turn count, context %) in TUI header or footer
- [ ] **CONV-05**: User input is disabled while Claude's response is streaming to prevent race conditions

### Word Wrap

- [ ] **WRAP-01**: Long lines in TUI output wrap at word boundaries instead of extending off-screen
- [ ] **WRAP-02**: Long lines on printer wrap at word boundaries instead of breaking mid-word
- [ ] **WRAP-03**: TUI wrap width updates when the terminal is resized

### Error Handling

- [ ] **ERR-01**: User sees a clear message when Claude Code CLI is not installed, with install URL
- [ ] **ERR-02**: User sees categorized error messages (network, auth, rate limit, context exhausted) instead of raw exceptions
- [ ] **ERR-03**: Subprocess timeouts prevent the app from hanging when Claude Code stops responding
- [ ] **ERR-04**: Zombie/orphaned Claude Code processes are cleaned up with kill-with-timeout pattern
- [ ] **ERR-05**: Rate limit and overload errors trigger automatic retry with exponential backoff and user notification
- [ ] **ERR-06**: Corrupted session recovery — on `--resume` failure, fall back to new session and inform user

## v1.2 Requirements (Deferred)

### CLI Multi-Turn

- **CLI-01**: User can have multi-turn conversation in `--no-tui` mode via interactive REPL
- **CLI-02**: Session persistence works in `--no-tui` REPL mode

### Settings & Configuration

- **SET-01**: User can access settings screen in TUI
- **SET-02**: User can select AI model (Claude or OpenAI/ChatGPT)
- **SET-03**: User can select paper format (A4, A3, etc.)

### Printer Architecture

- **PRINT-01**: Printer-specific settings stored in per-printer config files
- **PRINT-02**: User can select printer model in direct mode
- **PRINT-03**: Juki 6100 specific commands separated into dedicated printer profile

### Polish (Deferred from v1.0)

- **CHAR-04**: User can adjust character pacing mid-session with keyboard shortcuts (+/-)
- **PRNT-04**: Tool sends form feed on exit for clean paper tearoff
- **PRNT-05**: Tool detects printer status (paper out, error) via USB status query
- **SIML-03**: Simulator renders with dot-matrix visual aesthetic (faded ink, mono font)
- **AUDI-02**: Typewriter key-click sound plays on each character output
- **AUDI-03**: Distinct sounds differentiate user input from Claude output
- **PRES-01**: ASCII art session headers printed at start of each conversation

## Out of Scope

| Feature | Reason |
|---------|--------|
| Direct Anthropic API integration | Wraps Claude Code CLI to preserve auth, tools, context, MCP |
| Client-side conversation history | Claude Code manages sessions internally via `--resume` |
| Client-side context truncation | Claude Code's auto-compact handles this better than manual truncation |
| Markdown rendering in TUI | Typewriter aesthetic is plain text; rendering breaks character pacing model |
| `/compact` and `/clear` passthrough | These are interactive REPL commands, not `-p` print mode flags |
| Custom system prompts UI | Feature creep; users can pass `--append-system-prompt` through Claude Code |
| Streaming input format | `--input-format stream-json` is for SDK use, not human-paced conversation |
| Network/remote printer support | Network printers buffer pages, destroying character-by-character streaming |
| GUI interface | Terminal tool for terminal people; GUI adds massive dependency |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

### v1.0 (Complete)

| Requirement | Phase | Status |
|-------------|-------|--------|
| CLDE-01 | Phase 1 | Complete |
| CLDE-02 | Phase 1 | Complete |
| CLDE-03 | Phase 1 | Complete |
| CHAR-01 | Phase 1 | Complete |
| CHAR-02 | Phase 2 | Complete |
| CHAR-03 | Phase 1 | Complete |
| PRNT-01 | Phase 3 | Complete |
| PRNT-02 | Phase 3 | Complete |
| PRNT-03 | Phase 3 | Complete |
| SIML-01 | Phase 2 | Complete |
| SIML-02 | Phase 2 | Complete |
| AUDI-01 | Phase 4 | Complete |
| PERS-01 | Phase 4 | Complete |

### v1.1

| Requirement | Phase | Status |
|-------------|-------|--------|
| CONV-01 | — | Pending |
| CONV-02 | — | Pending |
| CONV-03 | — | Pending |
| CONV-04 | — | Pending |
| CONV-05 | — | Pending |
| WRAP-01 | — | Pending |
| WRAP-02 | — | Pending |
| WRAP-03 | — | Pending |
| ERR-01 | — | Pending |
| ERR-02 | — | Pending |
| ERR-03 | — | Pending |
| ERR-04 | — | Pending |
| ERR-05 | — | Pending |
| ERR-06 | — | Pending |

**Coverage:**
- v1.0 requirements: 13 total, 13 complete ✓
- v1.1 requirements: 14 total
- Mapped to phases: 0
- Unmapped: 14 ⚠️

---
*Requirements defined: 2026-02-14*
*Last updated: 2026-02-16 after v1.1 milestone requirements definition*
