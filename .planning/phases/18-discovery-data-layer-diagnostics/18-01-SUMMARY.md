---
phase: 18-discovery-data-layer-diagnostics
plan: 01
subsystem: printer
tags: [pyusb, libusb, cups, rich, dataclass, diagnostics]

requires:
  - phase: 10-printer-profiles
    provides: PrinterProfile dataclass, CUPS discovery, USB auto-detection

provides:
  - DiscoveryResult, UsbDeviceInfo, CupsPrinterInfo dataclasses in printer.py
  - discover_all() aggregator function returning structured discovery results
  - diagnose.py module with Rich-formatted diagnostic output
  - claude-teletype diagnose CLI subcommand

affects: [19-setup-tui, printer-setup-screen]

tech-stack:
  added: []
  patterns: [structured discovery result dataclass, never-raise aggregator pattern]

key-files:
  created:
    - src/claude_teletype/diagnose.py
    - tests/test_diagnose.py
  modified:
    - src/claude_teletype/printer.py
    - src/claude_teletype/cli.py

key-decisions:
  - "discover_all() uses importlib.util.find_spec to check pyusb without importing -- avoids caching failed imports"
  - "DiscoveryResult captures diagnostics as list[str] for flexible display in both CLI and future TUI"
  - "CUPS discovery always runs regardless of pyusb state -- mixed setups get full visibility"

patterns-established:
  - "Never-raise discovery: discover_all() catches all exceptions internally, records in diagnostics list"
  - "Structured discovery result: single DiscoveryResult dataclass replaces ad-hoc tuples and dicts"

requirements-completed: [DEP-01, DIAG-01]

duration: 4min
completed: 2026-04-03
---

# Phase 18 Plan 01: Discovery Data Layer & Diagnostics Summary

**Structured DiscoveryResult dataclass with discover_all() aggregator and Rich-formatted `claude-teletype diagnose` CLI command**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-03T07:23:15Z
- **Completed:** 2026-04-03T07:27:24Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Three dataclasses (UsbDeviceInfo, CupsPrinterInfo, DiscoveryResult) providing structured printer discovery primitives
- discover_all() function that never raises exceptions, aggregating pyusb, libusb, USB devices, and CUPS printers
- `claude-teletype diagnose` command with Rich tables showing dependencies, USB devices, CUPS queues, and system info
- 12 tests covering all discovery scenarios and CLI integration

## Task Commits

Each task was committed atomically:

1. **Task 1: Add discovery dataclasses and discover_all()** - `c7295f9` (test) -> `f397a90` (feat)
2. **Task 2: Create diagnose module and wire CLI subcommand** - `d88e3e5` (test) -> `c4f1c35` (feat)

_TDD tasks: RED (failing test) then GREEN (implementation) commits._

## Files Created/Modified
- `src/claude_teletype/printer.py` - Added UsbDeviceInfo, CupsPrinterInfo, DiscoveryResult dataclasses and discover_all() function
- `src/claude_teletype/diagnose.py` - New module with run_diagnose() producing Rich console output
- `src/claude_teletype/cli.py` - Wired diagnose subcommand via @app.command()
- `tests/test_diagnose.py` - 12 tests for discovery and CLI integration

## Decisions Made
- Used importlib.util.find_spec to check pyusb availability without importing (avoids caching failed imports)
- DiscoveryResult captures diagnostics as list[str] for flexible display in both CLI and future TUI
- CUPS discovery always runs regardless of pyusb state for full visibility in mixed setups

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed mock hierarchy in pyusb tests**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** MagicMock parent `usb` auto-generated `.core` attribute differed from explicitly mocked `usb.core`, causing `import usb.core` inside discover_all() to use wrong mock
- **Fix:** Built parent mock with `mock_usb.core = mock_usb_core` so sys.modules and attribute access resolve consistently
- **Files modified:** tests/test_diagnose.py
- **Verification:** All 8 discovery tests pass
- **Committed in:** f397a90 (Task 1 feat commit)

---

**Total deviations:** 1 auto-fixed (1 bug in test setup)
**Impact on plan:** Test mock fix only, no production code impact. No scope creep.

## Issues Encountered
- Pre-existing test failure in test_cli.py::TestChatAsyncStreamResult (not caused by our changes, verified by running on clean HEAD)

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all data flows are wired end-to-end.

## Next Phase Readiness
- DiscoveryResult and discover_all() are ready for Phase 19 setup TUI screen to consume
- diagnose.py provides a working CLI diagnostic tool for immediate troubleshooting
- CupsPrinterInfo captures vendor/model/serial for profile matching in setup flow

---
*Phase: 18-discovery-data-layer-diagnostics*
*Completed: 2026-04-03*
