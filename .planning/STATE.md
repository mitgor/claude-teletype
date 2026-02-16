# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-16)

**Core value:** The physical typewriter experience -- characters appearing on paper one at a time with authentic pacing and sound, making AI conversation feel tangible and mechanical.
**Current focus:** v1.1 Conversation Mode

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-02-16 — Milestone v1.1 started

## Performance Metrics

**Velocity:**
- Total plans completed: 8
- Average duration: 3min
- Total execution time: 0.37 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-streaming-pipeline | 2 | 5min | 2.5min |
| 02-terminal-simulator | 2 | 8min | 4min |
| 03-printer-hardware | 2 | 5min | 2.5min |
| 04-audio-and-persistence | 2 | 4min | 2min |

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
- Lazy import sounddevice/numpy inside make_bell_output for graceful degradation without PortAudio
- Transcript returns (write_fn, close_fn) tuple instead of single callable to enable cleanup
- Flush-on-newline semantics for transcript real-time persistence
- Session-scoped transcript in TUI: init in on_mount, close in on_unmount for single file per session
- User prompt written to transcript before streaming so full exchange is captured
- Lazy imports of audio/transcript in both TUI worker and CLI async path

### Pending Todos

None yet.

### Blockers/Concerns

- Claude Code CLI conversation context: need to determine whether to use `--resume` flag or manage message history in-process
- Auto-truncation strategy needs research: token counting vs message counting vs character limit

## Session Continuity

Last session: 2026-02-16
Stopped at: Milestone v1.1 initialization — defining requirements
Resume file: —
