# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-16)

**Core value:** The physical typewriter experience -- characters appearing on paper one at a time with authentic pacing and sound, making AI conversation feel tangible and mechanical.
**Current focus:** Phase 5 - Multi-Turn Conversation Foundation

## Current Position

Phase: 5 of 7 (Multi-Turn Conversation Foundation)
Plan: 2 of 3 in current phase
Status: Executing phase
Last activity: 2026-02-16 — Completed 05-02 TUI multi-turn conversation

Progress: [████████░░] 57% (4 of 7 phases complete)

## Performance Metrics

**Velocity:**
- Total plans completed: 10
- Average duration: 3min
- Total execution time: 0.47 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-streaming-pipeline | 2 | 5min | 2.5min |
| 02-terminal-simulator | 2 | 8min | 4min |
| 03-printer-hardware | 2 | 5min | 2.5min |
| 04-audio-and-persistence | 2 | 4min | 2min |
| 05-multi-turn-conversation-foundation | 2 | 6min | 3min |

**Recent Trend:**
- Last 5 plans: [2.5min, 2.5min, 2min, 2min, 3min, 3min]
- Trend: Stable (average ~3min per plan)

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Wrap Claude Code CLI rather than use API directly — preserves auth, context, tool use
- output_fn injection pattern — enables testing without real stdout, flexible destination fan-out
- Textual Log widget for TUI output — handles character streaming with proper newline semantics
- Use write() not write_line() for character streaming in Textual Log widget
- Session-scoped transcript in TUI: init in on_mount, close in on_unmount for single file per session
- StreamResult yielded as final item from async generator for session metadata propagation
- proc_holder mutable list pattern for subprocess reference propagation from bridge to TUI
- Real NDJSON modelUsage data for context % calculation (not turn count proxy)
- Turn formatting: "You: " / "Claude: " labels with blank-line separation between turns
- Static widget for status bar (not Footer) — Footer only shows keybindings, Static supports custom text
- Input disabled + 70% opacity CSS during streaming — prevents race conditions on rapid submission
- Escape cancel writes " [interrupted]" with space prefix for readability after partial response

### Pending Todos

None yet.

### Blockers/Concerns

**From research (Phase 5 critical):**
- Session corruption: If Claude Code process killed mid-response, session file becomes invalid. Need exit code checking and graceful fallback to new session.
- ~~Subprocess zombies: Multi-turn spawns many subprocesses. Interruptions leave 200-500MB processes. Need kill-with-timeout pattern (SIGTERM -> wait 5s -> SIGKILL).~~ RESOLVED in 05-02: _kill_process() implemented in TUI with SIGTERM -> wait_for(5s) -> SIGKILL, called in finally block and on_unmount.
- Word wrap via CSS breaks streaming: Must implement as pipeline filter before Log.write(), not as widget property (Phase 7).

**Resolution approach:**
- Phase 5 implements kill-with-timeout and session_id capture from NDJSON
- Phase 6 adds stderr parsing and session recovery
- Phase 7 adds WordWrapper pipeline filter

## Session Continuity

Last session: 2026-02-16
Stopped at: Completed 05-02-PLAN.md (TUI multi-turn conversation)
Resume file: None
