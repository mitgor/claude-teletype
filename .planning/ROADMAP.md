# Roadmap: Claude Teletype

## Overview

Claude Teletype delivers a character-by-character typewriter experience for Claude Code conversations, streaming AI responses to both a physical dot-matrix printer and a terminal simulator. The roadmap builds the streaming pipeline first (the entire product hinges on character-by-character flow), then the terminal simulator (what 90% of users will actually use), then printer hardware (the differentiator), and finally audio and persistence (independent consumers that complete the experience).

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Streaming Pipeline** - Claude Code bridge with character-by-character flow and typewriter pacing ✓ 2026-02-15
- [x] **Phase 2: Terminal Simulator** - Split-screen TUI with mirrored typewriter output ✓ 2026-02-15
- [x] **Phase 3: Printer Hardware** - USB-LPT auto-discovery, manual selection, and graceful disconnect ✓ 2026-02-15
- [ ] **Phase 4: Audio and Persistence** - Carriage return sound effects and conversation transcripts

## Phase Details

### Phase 1: Streaming Pipeline
**Goal**: User can send a prompt and watch Claude's response appear character by character with typewriter pacing in a basic terminal output
**Depends on**: Nothing (first phase)
**Requirements**: CLDE-01, CLDE-02, CLDE-03, CHAR-01, CHAR-03
**Success Criteria** (what must be TRUE):
  1. User can type a prompt and it is sent to Claude Code via the CLI wrapper
  2. Claude's response appears one character at a time in the terminal (not dumped all at once)
  3. Character output has visible typewriter pacing with ~50-100ms delay between characters
  4. Punctuation pauses feel noticeably longer than regular characters, and spaces feel faster
  5. A thinking indicator is visible while waiting for Claude's first response token
**Plans**: 2 plans

Plans:
- [x] 01-01-PLAN.md — Project scaffold, pacer module, and bridge module with tests ✓
- [x] 01-02-PLAN.md — CLI integration with thinking indicator + end-to-end verification ✓

### Phase 2: Terminal Simulator
**Goal**: User without printer hardware gets a polished split-screen terminal experience with the full typewriter feel
**Depends on**: Phase 1
**Requirements**: SIML-01, SIML-02, CHAR-02
**Success Criteria** (what must be TRUE):
  1. Tool launches a split-screen TUI (top=output, bottom=input) when no printer is connected
  2. User can type input in the bottom pane and see Claude's response render in the top pane
  3. Character pacing in the simulator matches the same typewriter timing as the streaming pipeline
  4. When a printer is later connected, output appears on both terminal and printer simultaneously
**Plans**: 2 plans

Plans:
- [x] 02-01-PLAN.md — Output multiplexer + Textual split-screen TUI app with tests ✓
- [x] 02-02-PLAN.md — CLI integration (TUI as default) + end-to-end verification ✓

### Phase 3: Printer Hardware
**Goal**: User can plug in a USB-LPT printer and have it discovered automatically, or specify a device manually, with graceful recovery if the printer disconnects
**Depends on**: Phase 2
**Requirements**: PRNT-01, PRNT-02, PRNT-03
**Success Criteria** (what must be TRUE):
  1. Tool auto-discovers a USB-LPT printer on startup without user configuration
  2. User can override auto-discovery by passing `--device /path/to/printer` on the command line
  3. If the printer disconnects mid-session, the tool continues running in simulator mode without crashing
**Plans**: 2 plans

Plans:
- [x] 03-01-PLAN.md — PrinterDriver protocol, CUPS/File/Null backends, discovery, resilient wrapper (TDD) ✓
- [x] 03-02-PLAN.md — CLI --device flag + TUI printer wiring + end-to-end verification ✓

### Phase 4: Audio and Persistence
**Goal**: Conversations have audible carriage return sounds and are saved to disk as plain text transcripts
**Depends on**: Phase 1 (audio and transcript are independent consumers of the character flow; Phase 2/3 not required)
**Requirements**: AUDI-01, PERS-01
**Success Criteria** (what must be TRUE):
  1. A bell/ding sound plays on every line break during Claude's output
  2. After a conversation ends, a timestamped plain text transcript file exists on disk containing the full exchange
**Plans**: 2 plans

Plans:
- [ ] 04-01-PLAN.md — Audio bell module + transcript writer module with tests (TDD)
- [ ] 04-02-PLAN.md — Wire audio + transcript into CLI/TUI with --no-audio and --transcript-dir flags

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Streaming Pipeline | 2/2 | ✓ Complete | 2026-02-15 |
| 2. Terminal Simulator | 2/2 | ✓ Complete | 2026-02-15 |
| 3. Printer Hardware | 2/2 | ✓ Complete | 2026-02-15 |
| 4. Audio and Persistence | 0/TBD | Not started | - |
