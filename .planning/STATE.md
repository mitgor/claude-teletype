# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-14)

**Core value:** The physical typewriter experience -- characters appearing on paper one at a time with authentic pacing and sound, making AI conversation feel tangible and mechanical.
**Current focus:** Phase 2 complete. Next: Phase 3 (Printer Integration)

## Current Position

Phase: 2 of 4 (Terminal Simulator) -- COMPLETE
Plan: 2 of 2 in current phase
Status: Phase Complete
Last activity: 2026-02-15 -- Completed 02-02 (CLI Integration + TUI Verification)

Progress: [████░░░░░░] 40%

## Performance Metrics

**Velocity:**
- Total plans completed: 4
- Average duration: 3.3min
- Total execution time: 0.22 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-streaming-pipeline | 2 | 5min | 2.5min |
| 02-terminal-simulator | 2 | 8min | 4min |

**Recent Trend:**
- Last 5 plans: 3min, 2min, 3min, 5min
- Trend: stable

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Used hatchling build backend (plan spec) instead of uv_build (uv init default)
- Pacer uses output_fn injection pattern for testability without real stdout
- Bridge separates parse_text_delta helper for unit testing NDJSON without subprocess
- CLI uses asyncio.run() bridge from sync Typer to async streaming pipeline
- Rich Console.status spinner stops on first token for thinking -> streaming transition
- make_output_fn returns destination directly for single-dest case (zero wrapper overhead)
- Added on_mount to auto-focus Input widget (required for UX and testability)
- Worker uses lazy imports for bridge/pacer/output to keep TUI testable without mocking
- Import work from textual (not textual.work) for Textual 7.x compatibility
- Log.write() handles \n correctly via line_split(); write_line("") does NOT create newlines because "".splitlines() returns []
- Use write() not write_line() for character streaming and newline handling in Textual Log widget
- Lazy import of TeletypeApp inside TUI branch so Textual is not loaded in --no-tui mode

### Pending Todos

None yet.

### Blockers/Concerns

- USB-LPT adapter communication on macOS has LOW confidence from research. Phase 3 may need hardware-specific investigation. Product must work simulation-first.
- NDJSON message format from Claude Code CLI needs live validation in Phase 1 -- research was based on community docs, not live testing. UPDATE: Human-verified working end-to-end in 01-02.

## Session Continuity

Last session: 2026-02-15
Stopped at: Completed 02-02-PLAN.md (CLI Integration + TUI Verification) -- Phase 2 complete
Resume file: .planning/phases/02-terminal-simulator/02-02-SUMMARY.md
