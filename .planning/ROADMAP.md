# Roadmap: Claude Teletype

## Milestones

- ✅ **v1.0 MVP** - Phases 1-4 (shipped 2026-02-15)
- 🚧 **v1.1 Conversation Mode** - Phases 5-7 (in progress)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-4) - SHIPPED 2026-02-15</summary>

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
- [x] 04-01-PLAN.md — Audio bell module + transcript writer module with tests (TDD) ✓
- [x] 04-02-PLAN.md — Wire audio + transcript into CLI/TUI with --no-audio and --transcript-dir flags ✓

</details>

### 🚧 v1.1 Conversation Mode (In Progress)

**Milestone Goal:** Turn the one-shot prompt/response tool into a real multi-turn conversation experience with proper error handling and text wrapping.

#### Phase 5: Multi-Turn Conversation Foundation
**Goal**: Enable session-persistent multi-turn conversation in TUI with proper subprocess lifecycle management
**Depends on**: Phase 4
**Requirements**: CONV-01, CONV-02, CONV-03, CONV-04, CONV-05
**Success Criteria** (what must be TRUE):
  1. User can submit multiple prompts in TUI, and each response includes context from all previous turns
  2. User sees visual separators between conversation turns in TUI and on printer
  3. User sees session metadata (turn count, context usage) in TUI status area
  4. User cannot submit new prompts while Claude's response is streaming
  5. TUI session resumes correctly after restart using same session_id
**Plans**: 3 plans

Plans:
- [ ] 05-01-PLAN.md — Bridge multi-turn session support: StreamResult, parse_session_id, parse_result, --resume flag (TDD)
- [ ] 05-02-PLAN.md — TUI multi-turn loop, turn formatting, status bar, input blocking, escape cancel
- [ ] 05-03-PLAN.md — CLI --resume flag, session lifecycle, end-to-end verification

#### Phase 6: Error Handling and Recovery
**Goal**: Provide clear, actionable error messages for common failure modes
**Depends on**: Phase 5
**Requirements**: ERR-01, ERR-02, ERR-03, ERR-04, ERR-05, ERR-06
**Success Criteria** (what must be TRUE):
  1. User who hasn't installed Claude Code sees clear message with install URL, not subprocess errors
  2. User sees categorized error messages (network, auth, rate limit, context exhausted) instead of raw stack traces
  3. User sees automatic retry with backoff when rate limit or overload errors occur
  4. Sessions that become corrupted automatically fall back to new session with clear notification to user
**Plans**: TBD

Plans:
- [ ] 06-01: TBD
- [ ] 06-02: TBD

#### Phase 7: Word Wrap for TUI and Printer
**Goal**: Wrap long lines at word boundaries in both TUI output and printer output
**Depends on**: Phase 5 (soft dependency - benefits from multi-turn but can be built in parallel)
**Requirements**: WRAP-01, WRAP-02, WRAP-03
**Success Criteria** (what must be TRUE):
  1. Long lines in TUI wrap at word boundaries without breaking mid-word or extending off-screen
  2. Long lines on printer wrap at word boundaries instead of hard-breaking at 80 columns
  3. TUI wrap width updates automatically when terminal is resized
**Plans**: TBD

Plans:
- [ ] 07-01: TBD
- [ ] 07-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Streaming Pipeline | v1.0 | 2/2 | ✓ Complete | 2026-02-15 |
| 2. Terminal Simulator | v1.0 | 2/2 | ✓ Complete | 2026-02-15 |
| 3. Printer Hardware | v1.0 | 2/2 | ✓ Complete | 2026-02-15 |
| 4. Audio and Persistence | v1.0 | 2/2 | ✓ Complete | 2026-02-15 |
| 5. Multi-Turn Foundation | v1.1 | Complete    | 2026-02-16 | - |
| 6. Error Handling | v1.1 | 0/2 | Not started | - |
| 7. Word Wrap | v1.1 | 0/2 | Not started | - |
