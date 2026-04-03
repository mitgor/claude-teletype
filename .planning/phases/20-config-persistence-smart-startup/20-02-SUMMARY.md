---
phase: 20-config-persistence-smart-startup
plan: 02
subsystem: startup
tags: [printer-discovery, config-persistence, smart-startup, vid-pid]

requires:
  - phase: 20-config-persistence-smart-startup/01
    provides: saved_printer_type/id/profile fields in TeletypeConfig, save_config atomic writes
provides:
  - match_saved_printer function matching USB by VID:PID and CUPS by queue name
  - Smart startup flow in cli.py that skips setup screen when saved printer is connected
affects: [printer-setup-screen, tui]

tech-stack:
  added: []
  patterns: [saved-printer-matching-by-vid-pid, discovery-none-signals-skip-setup]

key-files:
  created:
    - tests/test_smart_startup.py
  modified:
    - src/claude_teletype/printer.py
    - src/claude_teletype/cli.py

key-decisions:
  - "match_saved_printer returns PrinterSelection|None rather than bool, enabling direct use with create_driver_for_selection"
  - "discovery=None used as signal to TUI that setup should be skipped (existing convention from --device path)"

patterns-established:
  - "VID:PID matching: parse hex string '04b8:0005' to int pair, compare against DiscoveryResult.usb_devices"
  - "CUPS matching: direct string equality on queue name against DiscoveryResult.cups_printers"

requirements-completed: [CFG-02]

duration: 2min
completed: 2026-04-03
---

# Phase 20 Plan 02: Smart Startup Summary

**Skip printer setup screen on launch when saved USB/CUPS printer is still connected, via VID:PID and queue-name matching against discovery results**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-03T12:18:15Z
- **Completed:** 2026-04-03T12:20:00Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 3

## Accomplishments
- match_saved_printer() matches USB devices by VID:PID hex string and CUPS printers by queue name
- cli.py TUI startup checks saved config against discovery before showing setup screen
- When saved printer is connected: driver created directly, setup skipped entirely
- When saved printer is disconnected: setup screen shown as before
- 13 tests covering all match paths, edge cases, and _needs_printer_setup integration

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests for smart startup** - `208ca65` (test)
2. **Task 1 (GREEN): Implement match_saved_printer and cli.py smart startup** - `59d9d09` (feat)

**Plan metadata:** TBD (docs: complete plan)

## Files Created/Modified
- `src/claude_teletype/printer.py` - Added match_saved_printer() function before create_driver_for_selection
- `src/claude_teletype/cli.py` - Added smart startup logic in TUI mode branch, imports create_driver_for_selection
- `tests/test_smart_startup.py` - 13 tests: USB VID:PID matching, CUPS queue matching, edge cases, _needs_printer_setup

## Decisions Made
- match_saved_printer returns PrinterSelection|None (not bool) so it can be passed directly to create_driver_for_selection
- Reused existing discovery=None convention to signal "skip setup" (same as --device path)
- Profile name set on returned PrinterSelection from saved config, then resolved in cli.py for status bar display

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all data paths are wired.

## Next Phase Readiness
- Config persistence and smart startup complete (CFG-01 from plan 01, CFG-02 from plan 02)
- Phase 20 fully complete: printer selection saved to TOML, subsequent launches skip setup when printer connected

## Self-Check: PASSED

All files exist, all commits verified.

---
*Phase: 20-config-persistence-smart-startup*
*Completed: 2026-04-03*
