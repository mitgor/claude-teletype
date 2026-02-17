# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-17)

**Core value:** The physical typewriter experience -- characters appearing on paper one at a time with authentic pacing and sound, making AI conversation feel tangible and mechanical.
**Current focus:** v1.1 milestone complete. Ready for next milestone.

## Current Position

Milestone: v1.1 Conversation Mode -- SHIPPED 2026-02-17
Status: All phases complete. Milestone archived.
Last activity: 2026-02-17 -- Archived v1.1 milestone

Progress: v1.0 ✓ | v1.1 ✓ | Next: /gsd:new-milestone

## Performance Metrics

**Velocity:**
- Total plans completed: 15
- Average duration: 3min
- Total execution time: 0.70 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-streaming-pipeline | 2 | 5min | 2.5min |
| 02-terminal-simulator | 2 | 8min | 4min |
| 03-printer-hardware | 2 | 5min | 2.5min |
| 04-audio-and-persistence | 2 | 4min | 2min |
| 05-multi-turn-conversation-foundation | 3 | 9min | 3min |
| 06-error-handling-and-recovery | 2 | 5min | 2.5min |
| 07-word-wrap-for-tui-and-printer | 2 | 6min | 3min |

**Recent Trend:**
- Last 5 plans: [3min, 3min, 2min, 2min, 4min]
- Trend: Stable (average ~2.8min per plan)

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
- Session ID printed to stderr (not stdout) — avoids interference with piped output
- Resume failure resets session_id and starts new session with warning (no retry)
- Substring matching (not regex) for error classification -- simpler, maintainable, sufficient for known patterns
- 300s readline timeout as generous default, 30s after result message for hang bug detection
- ErrorCategory as str+Enum for JSON serialization compatibility
- Pre-flight check at chat() entry point catches missing CLI before TUI launch
- Only retry when no text streamed yet to prevent response duplication (Pitfall 4)
- Session ID reset happens BEFORE retry decision to ensure fresh session on retry
- Deferred space pattern in WordWrapper prevents trailing whitespace on wrapped lines
- Hard-break words longer than width (same as textwrap break_long_words=True)
- Width clamped to min 1 via max(1, value) to prevent infinite loops
- TUI wrapper wraps only log.write; printer/audio/transcript receive unwrapped chars via output_fn
- Claude: label routed through TUI wrapper for accurate column tracking
- Printer CR/FF handled as special control chars: flush buffer, pass through, reset column

### Pending Todos

None yet.

### Blockers/Concerns

**From research (Phase 5 critical):**
- Session corruption: If Claude Code process killed mid-response, session file becomes invalid. Need exit code checking and graceful fallback to new session.
- ~~Subprocess zombies: Multi-turn spawns many subprocesses. Interruptions leave 200-500MB processes. Need kill-with-timeout pattern (SIGTERM -> wait 5s -> SIGKILL).~~ RESOLVED in 05-02: _kill_process() implemented in TUI with SIGTERM -> wait_for(5s) -> SIGKILL, called in finally block and on_unmount.
- ~~Word wrap via CSS breaks streaming: Must implement as pipeline filter before Log.write(), not as widget property (Phase 7).~~ RESOLVED in 07-02: WordWrapper wraps log.write in stream_response, on_resize updates width dynamically.

**Resolution approach:**
- Phase 5 implements kill-with-timeout and session_id capture from NDJSON
- Phase 6 adds stderr parsing and session recovery
- Phase 7 adds WordWrapper pipeline filter

## Session Continuity

Last session: 2026-02-17
Stopped at: Completed 07-02-PLAN.md (TUI and Printer WordWrapper integration) -- Phase 7 complete, Milestone v1.0 complete
Resume file: None
