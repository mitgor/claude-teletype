---
phase: 03-printer-hardware
plan: 01
subsystem: printer
tags: [cups, subprocess, protocol, printer-driver, usb, device-io]

# Dependency graph
requires:
  - phase: 01-streaming-pipeline
    provides: make_output_fn multiplexer for character-by-character output
provides:
  - PrinterDriver protocol with is_connected, write, close
  - NullPrinterDriver (no-op for simulator-only mode)
  - FilePrinterDriver (direct device file I/O with disconnect detection)
  - CupsPrinterDriver (line-buffered raw printing via lp subprocess)
  - discover_printer() tiered auto-discovery function
  - make_printer_output() resilient wrapper with graceful degradation
affects: [03-02, 04-audio-effects]

# Tech tracking
tech-stack:
  added: []
  patterns: [Strategy pattern for printer backends, circuit-breaker disconnect via boolean flag, resilient closure wrapper]

key-files:
  created:
    - src/claude_teletype/printer.py
    - tests/test_printer.py
  modified: []

key-decisions:
  - "Catch ValueError in addition to OSError for closed file handle writes"
  - "Per-line buffering in CupsPrinterDriver (lp invoked per newline, not per character)"
  - "make_printer_output uses closure-local disconnected flag, not driver.is_connected"

patterns-established:
  - "PrinterDriver Protocol: all printer backends implement is_connected, write(char), close()"
  - "Tiered discovery: device override > CUPS USB > Linux /dev/usb/lp* > NullPrinterDriver"
  - "Resilient wrapper: make_printer_output catches errors and degrades to no-op silently"

# Metrics
duration: 2min
completed: 2026-02-15
---

# Phase 3 Plan 1: Printer Driver Protocol Summary

**PrinterDriver strategy pattern with CUPS/File/Null backends, tiered USB discovery via lpstat, and resilient make_printer_output wrapper for graceful disconnect**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-15T22:19:38Z
- **Completed:** 2026-02-15T22:21:47Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- PrinterDriver protocol defined with runtime_checkable for duck-typing verification
- Three backends: NullPrinterDriver (silent no-op), FilePrinterDriver (direct device file I/O), CupsPrinterDriver (CUPS lp subprocess per-line)
- Tiered discovery: --device flag > CUPS USB printers via lpstat > Linux /dev/usb/lp* > NullPrinterDriver fallback
- make_printer_output() wraps any driver with IOError/OSError catch for graceful degradation (PRNT-03)
- 21 new tests covering all drivers, discovery tiers, and resilient wrapper; 107 total tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing printer tests** - `e5c2e32` (test)
2. **Task 1 (GREEN): Implement printer module** - `2bcf5f2` (feat)

_TDD task: RED commit for failing tests, GREEN commit for passing implementation._

## Files Created/Modified
- `src/claude_teletype/printer.py` - PrinterDriver protocol, three backends, discovery, resilient wrapper
- `tests/test_printer.py` - 21 tests covering all drivers, discovery, and make_printer_output

## Decisions Made
- Catch `ValueError` in addition to `OSError` in FilePrinterDriver.write() because writing to a closed file descriptor raises ValueError (not OSError) in Python
- Per-line buffering in CupsPrinterDriver: `lp` is invoked once per newline, not per character, to avoid catastrophic subprocess overhead
- make_printer_output uses its own closure-local `disconnected` flag rather than checking `driver.is_connected`, providing an additional layer of resilience

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] FilePrinterDriver.write() did not catch ValueError for closed file handles**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** Writing to a closed file descriptor raises `ValueError: I/O operation on closed file` in Python, not `IOError` or `OSError`. The plan's exception handler only caught `IOError, OSError`.
- **Fix:** Added `ValueError` to the except clause: `except (OSError, ValueError)`
- **Files modified:** `src/claude_teletype/printer.py`
- **Verification:** `test_file_driver_disconnect_on_write_error` passes
- **Committed in:** `2bcf5f2` (GREEN phase commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Essential for correctness -- without this fix, a printer disconnect would crash the application instead of degrading gracefully.

## Issues Encountered
- Ruff flagged `IOError` as an alias for `OSError` (UP024) and unused `pytest` import (F401) -- both auto-fixed by `ruff check --fix`

## User Setup Required
None - no external service configuration required. Printer hardware is auto-discovered at runtime.

## Next Phase Readiness
- PrinterDriver protocol and all backends ready for integration with CLI and TUI
- 03-02 can wire discover_printer() into CLI --device flag and TUI worker
- make_printer_output() is compatible with existing make_output_fn() multiplexer

---
*Phase: 03-printer-hardware*
*Completed: 2026-02-15*

## Self-Check: PASSED
- All created files exist on disk
- All commit hashes verified in git log
- 107/107 tests passing, lint clean
