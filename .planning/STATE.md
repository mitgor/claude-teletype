# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-14)

**Core value:** The physical typewriter experience -- characters appearing on paper one at a time with authentic pacing and sound, making AI conversation feel tangible and mechanical.
**Current focus:** Phase 3 complete (Printer Hardware). Ready for Phase 4 (Audio Effects).

## Current Position

Phase: 3 of 4 (Printer Hardware) -- COMPLETE
Plan: 2 of 2 in current phase
Status: Phase Complete
Last activity: 2026-02-15 -- Completed 03-02 (CLI --device + TUI Printer Integration)

Progress: [███████░░░] 75%

## Performance Metrics

**Velocity:**
- Total plans completed: 6
- Average duration: 3min
- Total execution time: 0.30 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-streaming-pipeline | 2 | 5min | 2.5min |
| 02-terminal-simulator | 2 | 8min | 4min |
| 03-printer-hardware | 2 | 5min | 2.5min |

**Recent Trend:**
- Last 5 plans: 3min, 5min, 2min, 3min
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
- Printer cleanup on TUI unmount via on_unmount lifecycle hook
- No-TUI branch uses make_output_fn with both sys.stdout.write and make_printer_output

### Pending Todos

None yet.

### Blockers/Concerns

- USB-LPT adapter communication on macOS has LOW confidence from research. Phase 3 may need hardware-specific investigation. Product must work simulation-first.
- NDJSON message format from Claude Code CLI needs live validation in Phase 1 -- research was based on community docs, not live testing. UPDATE: Human-verified working end-to-end in 01-02.

## Session Continuity

Last session: 2026-02-15
Stopped at: Completed 03-02-PLAN.md (CLI --device + TUI Printer Integration) -- Phase 3 complete
Resume file: .planning/phases/03-printer-hardware/03-02-SUMMARY.md
