---
phase: 03-printer-hardware
plan: 02
subsystem: printer
tags: [cli, tui, device-flag, output-multiplexer, printer-integration]

# Dependency graph
requires:
  - phase: 03-printer-hardware
    provides: PrinterDriver protocol, discover_printer(), make_printer_output()
  - phase: 02-terminal-simulator
    provides: TeletypeApp TUI with Log widget and worker-based streaming
  - phase: 01-streaming-pipeline
    provides: make_output_fn multiplexer for character-by-character output
provides:
  - "--device CLI flag for printer device path override"
  - "TUI multiplexes output to Log widget + printer via make_output_fn"
  - "No-TUI branch also supports printer output"
  - "Printer cleanup on app exit (unmount and finally block)"
  - "Simulator-only mode when no printer (NullPrinterDriver fallback)"
affects: [04-audio-effects]

# Tech tracking
tech-stack:
  added: []
  patterns: [Lazy import of printer module in CLI branches, printer parameter injection into TeletypeApp]

key-files:
  created: []
  modified:
    - src/claude_teletype/cli.py
    - src/claude_teletype/tui.py

key-decisions:
  - "Lazy import of TeletypeApp inside TUI branch so Textual is not loaded in --no-tui mode"
  - "Printer cleanup on TUI unmount via on_unmount lifecycle hook"
  - "No-TUI branch uses make_output_fn with both sys.stdout.write and make_printer_output"

patterns-established:
  - "Device flag pattern: --device overrides auto-discovery, None triggers full discovery chain"
  - "Printer parameter injection: TeletypeApp accepts optional printer kwarg, wires into worker"

# Metrics
duration: 3min
completed: 2026-02-15
---

# Phase 3 Plan 2: CLI --device + TUI Printer Integration Summary

**--device CLI flag wired to discover_printer(), TUI multiplexes output to Log widget + printer via make_output_fn, graceful NullPrinterDriver fallback when no printer connected**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-15T22:23:00Z
- **Completed:** 2026-02-15T22:25:03Z
- **Tasks:** 2 (1 auto + 1 human-verify)
- **Files modified:** 2

## Accomplishments
- CLI `--device` flag accepts printer device path (e.g., /dev/usb/lp0) and overrides auto-discovery
- TUI wires printer into stream_response worker via make_output_fn multiplexer
- No-TUI branch also supports printer output through the same multiplexer pattern
- Printer cleanup on TUI unmount and _chat_async finally block
- All 107 tests passing with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Add --device flag to CLI and wire printer into TUI** - `5e4bf44` (feat)
2. **Task 2: Verify printer integration end-to-end** - checkpoint:human-verify (approved)

## Files Created/Modified
- `src/claude_teletype/cli.py` - Added --device flag, discover_printer() at startup, printer passed to TUI and _chat_async
- `src/claude_teletype/tui.py` - TeletypeApp accepts printer parameter, multiplexes output to Log + printer, cleanup on unmount

## Decisions Made
- Lazy import of printer module in both TUI and no-TUI CLI branches to keep imports lightweight
- Printer cleanup via on_unmount lifecycle hook in TUI, and finally block in _chat_async
- No-TUI branch uses make_output_fn with both sys.stdout.write and make_printer_output for consistent multiplexing

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required. Printer hardware is auto-discovered at runtime; --device flag available for manual override.

## Next Phase Readiness
- Phase 3 (Printer Hardware) is complete: driver protocol (03-01) + CLI/TUI integration (03-02)
- Phase 4 (Audio Effects) can proceed -- printer subsystem provides make_printer_output() compatible with make_output_fn()
- Full end-to-end flow: Claude response -> streaming bridge -> pacer -> output_fn -> [Log widget + printer]

---
*Phase: 03-printer-hardware*
*Completed: 2026-02-15*

## Self-Check: PASSED
- All modified files exist on disk (cli.py, tui.py)
- Commit 5e4bf44 verified in git log
- 107/107 tests passing, lint clean
- SUMMARY.md created at .planning/phases/03-printer-hardware/03-02-SUMMARY.md
