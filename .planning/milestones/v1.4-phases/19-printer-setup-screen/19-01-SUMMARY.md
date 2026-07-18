---
phase: 19-printer-setup-screen
plan: 01
subsystem: printer
tags: [dataclass, factory-pattern, printer-driver, tdd]

requires:
  - phase: 18-printer-discovery
    provides: DiscoveryResult, CupsPrinterDriver, UsbPrinterDriver, NullPrinterDriver, ProfilePrinterDriver
provides:
  - PrinterSelection dataclass capturing user printer choice
  - create_driver_for_selection() factory converting selection to driver
affects: [19-02 setup screen TUI, 19-03 TUI integration]

tech-stack:
  added: []
  patterns: [selection-to-driver factory pattern]

key-files:
  created: [tests/test_printer_setup.py]
  modified: [src/claude_teletype/printer.py]

key-decisions:
  - "Factory uses lazy import of BUILTIN_PROFILES to avoid circular import"
  - "USB path delegates to existing _find_usb_printer() rather than duplicating discovery"
  - "Graceful fallback to NullPrinterDriver when USB discovery fails"

patterns-established:
  - "PrinterSelection as typed data contract between setup screen and driver creation"
  - "create_driver_for_selection as single entry point for selection-to-driver conversion"

requirements-completed: [SETUP-02, SETUP-04]

duration: 1min
completed: 2026-04-03
---

# Phase 19 Plan 01: Printer Selection Data Contract Summary

**PrinterSelection dataclass and create_driver_for_selection() factory for typed setup-screen-to-driver conversion**

## Performance

- **Duration:** 1 min
- **Started:** 2026-04-03T08:19:20Z
- **Completed:** 2026-04-03T08:20:39Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- PrinterSelection dataclass with connection_type, device_index, cups_printer_name, profile_name fields
- create_driver_for_selection() factory handling skip, cups, usb paths with profile wrapping
- 6 tests covering all selection paths: skip, cups, cups+profile, usb-fallback, usb-generic, usb+profile
- Full test suite (448 tests) passes with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests** - `d91f6d9` (test)
2. **Task 1 (GREEN): Implementation** - `b9d8228` (feat)

_TDD task: test-first then implementation._

## Files Created/Modified
- `src/claude_teletype/printer.py` - Added PrinterSelection dataclass and create_driver_for_selection() factory
- `tests/test_printer_setup.py` - 6 tests for selection-to-driver conversion

## Decisions Made
- Factory uses lazy import of BUILTIN_PROFILES (from claude_teletype.profiles) to avoid circular import at module level
- USB path delegates to existing _find_usb_printer() rather than duplicating discovery logic
- Graceful NullPrinterDriver fallback when USB device not found (no crash on missing hardware)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- PrinterSelection and create_driver_for_selection() are importable and tested
- Ready for 19-02 (setup screen TUI) to use PrinterSelection as its return type
- Ready for 19-03 (TUI integration) to call create_driver_for_selection() with screen results

---
*Phase: 19-printer-setup-screen*
*Completed: 2026-04-03*
