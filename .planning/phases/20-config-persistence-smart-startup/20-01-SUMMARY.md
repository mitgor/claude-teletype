---
phase: 20-config-persistence-smart-startup
plan: 01
subsystem: config
tags: [toml, atomic-write, persistence, printer-setup]

requires:
  - phase: 19-printer-setup-screen
    provides: PrinterSetupScreen with PrinterSelection result, DiscoveryResult with USB/CUPS data
provides:
  - saved_printer_type/id/profile fields on TeletypeConfig
  - Atomic save_config using tempfile + os.replace
  - [printer.saved] TOML section for persisted printer selection
  - _save_printer_selection and _clear_saved_printer methods on TeletypeApp
affects: [20-02, smart-startup, config-system]

tech-stack:
  added: [tempfile (stdlib)]
  patterns: [atomic file write via mkstemp + os.replace, TOML sub-table mapping to flat dataclass fields]

key-files:
  created: [tests/test_config_persistence.py]
  modified: [src/claude_teletype/config.py, src/claude_teletype/tui.py]

key-decisions:
  - "Atomic write uses fd-level os.write + os.replace for crash safety (no intermediate partial state)"
  - "TOML validation (tomllib.loads) before write catches template bugs before they corrupt config"
  - "saved_printer_* fields excluded from env override -- internal state, not user-facing settings"

patterns-established:
  - "Atomic config save: tempfile.mkstemp in same dir + os.replace for crash-safe writes"
  - "TOML sub-table to flat dataclass: extract nested dict, map after construction"

requirements-completed: [CFG-01]

duration: 3min
completed: 2026-04-03
---

# Phase 20 Plan 01: Config Persistence Summary

**Saved printer fields on TeletypeConfig with atomic TOML writes and TUI persistence after setup**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-03T12:13:35Z
- **Completed:** 2026-04-03T12:16:18Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- TeletypeConfig gains saved_printer_type, saved_printer_id, saved_printer_profile fields with empty string defaults
- save_config uses atomic temp file + os.replace -- a crash mid-write cannot produce a corrupt 0-byte config
- [printer.saved] TOML section written when fields are non-empty, round-trips through load_config
- TUI persists printer selection to config after setup screen dismiss; clears on skip

## Task Commits

Each task was committed atomically:

1. **Task 1: Add saved printer fields and atomic save_config** - `8c76296` (test: RED) + `1358208` (feat: GREEN)
2. **Task 2: Save printer selection after setup screen dismiss** - `759dde2` (feat)

## Files Created/Modified
- `src/claude_teletype/config.py` - Added saved_printer_* fields, [printer.saved] TOML section, atomic save via tempfile+os.replace
- `src/claude_teletype/tui.py` - Added _save_printer_selection and _clear_saved_printer methods, wired into _handle_setup_result
- `tests/test_config_persistence.py` - 10 tests: field defaults, TOML round-trip, atomic write, template comment, env skip

## Decisions Made
- Atomic write uses fd-level os.write + os.replace (not write_text) for crash safety
- TOML content validated via tomllib.loads before write to catch template bugs
- saved_printer_* fields excluded from env overrides (internal state, not user settings)
- fd tracking uses sentinel value (-1) after close to avoid double-close in error path

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Config persistence foundation complete for plan 20-02 (smart startup skip logic)
- saved_printer_type/id fields ready for matching against discovered devices at startup

## Self-Check: PASSED

All files exist. All commits verified (8c76296, 1358208, 759dde2).

---
*Phase: 20-config-persistence-smart-startup*
*Completed: 2026-04-03*
