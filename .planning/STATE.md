# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-14)

**Core value:** The physical typewriter experience -- characters appearing on paper one at a time with authentic pacing and sound, making AI conversation feel tangible and mechanical.
**Current focus:** Phase 3 in progress (Printer Hardware)

## Current Position

Phase: 3 of 4 (Printer Hardware)
Plan: 1 of 2 in current phase
Status: In Progress
Last activity: 2026-02-15 -- Completed 03-01 (Printer Driver Protocol)

Progress: [█████░░░░░] 50%

## Performance Metrics

**Velocity:**
- Total plans completed: 5
- Average duration: 3min
- Total execution time: 0.25 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-streaming-pipeline | 2 | 5min | 2.5min |
| 02-terminal-simulator | 2 | 8min | 4min |
| 03-printer-hardware | 1 | 2min | 2min |

**Recent Trend:**
- Last 5 plans: 2min, 3min, 5min, 2min
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
- Catch ValueError in FilePrinterDriver.write() for closed file handles (Python raises ValueError not OSError)
- Per-line buffering in CupsPrinterDriver: lp invoked per newline, not per character
- make_printer_output uses closure-local disconnected flag for resilient degradation

### Pending Todos

None yet.

### Blockers/Concerns

- USB-LPT adapter communication on macOS has LOW confidence from research. Phase 3 may need hardware-specific investigation. Product must work simulation-first.
- NDJSON message format from Claude Code CLI needs live validation in Phase 1 -- research was based on community docs, not live testing. UPDATE: Human-verified working end-to-end in 01-02.

## Session Continuity

Last session: 2026-02-15
Stopped at: Completed 03-01-PLAN.md (Printer Driver Protocol)
Resume file: .planning/phases/03-printer-hardware/03-01-SUMMARY.md
