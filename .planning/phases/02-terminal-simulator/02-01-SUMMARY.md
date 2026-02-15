---
phase: 02-terminal-simulator
plan: 01
subsystem: tui
tags: [textual, tui, split-screen, multiplexed-output, typewriter-pacing]

# Dependency graph
requires:
  - phase: 01-streaming-pipeline
    provides: "Pacer with output_fn injection, Bridge with async streaming"
provides:
  - "Multiplexed output_fn factory (make_output_fn) for character fan-out to N destinations"
  - "TeletypeApp Textual split-screen TUI with Log + Input + Header + Footer"
  - "Background worker with @work(exclusive=True) for Claude streaming"
  - "15 new tests (6 output, 9 TUI) -- 86 total passing"
affects: [02-02, 03-printer, 04-polish]

# Tech tracking
tech-stack:
  added: [textual-7.5.0]
  patterns: [multiplexed-output-fn-factory, textual-split-screen-layout, exclusive-worker-streaming, on-mount-auto-focus]

key-files:
  created:
    - src/claude_teletype/output.py
    - src/claude_teletype/tui.py
    - tests/test_output.py
    - tests/test_tui.py
  modified:
    - pyproject.toml

key-decisions:
  - "make_output_fn returns destination directly for single-dest case (zero wrapper overhead)"
  - "Added on_mount to auto-focus Input widget (required for both UX and testability)"
  - "Worker uses lazy imports for bridge/pacer/output to keep TUI testable without mocking"
  - "Import work from textual (not textual.work) for Textual 7.x compatibility"

patterns-established:
  - "Multiplexed output_fn: make_output_fn(*destinations) creates a single callable that fans to all destinations"
  - "Textual on_mount focus: auto-focus Input widget so users can type immediately"
  - "Lazy imports in @work: keep optional dependencies out of module-level scope for test isolation"
  - "Thinking indicator: change Input placeholder to 'Thinking...' during response streaming"

# Metrics
duration: 3min
completed: 2026-02-15
---

# Phase 02 Plan 01: Output Multiplexer + TUI Application Summary

**Textual 7.x split-screen TUI with Log/Input layout, multiplexed output_fn factory for character fan-out, and @work(exclusive=True) streaming worker**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-15T21:39:14Z
- **Completed:** 2026-02-15T21:42:40Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Created make_output_fn factory with optimized paths: no-op for zero destinations, pass-through for one, fan-out closure for multiple
- Built TeletypeApp with split-screen layout (Log top, Input bottom, Header/Footer), on_mount auto-focus, input submission with prompt echo, and background streaming worker
- Textual 7.5.0 installed as project dependency; all 86 tests passing across 4 test modules with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Add textual dependency and create multiplexed output module with tests** - `70145c5` (feat)
2. **Task 2: Create Textual split-screen TUI application with tests** - `05868c6` (feat)

## Files Created/Modified
- `pyproject.toml` - Added textual>=7.0.0 dependency
- `src/claude_teletype/output.py` - Multiplexed output function factory (make_output_fn)
- `src/claude_teletype/tui.py` - Textual split-screen TUI application (TeletypeApp)
- `tests/test_output.py` - 6 tests for output multiplexer including pacer integration
- `tests/test_tui.py` - 9 tests for TUI layout, title, input handling, prompt echo, delay config

## Decisions Made
- make_output_fn returns the destination callable directly when given a single destination (avoids unnecessary wrapper overhead)
- Added on_mount handler to auto-focus Input widget -- required for immediate typing in both real app and headless tests
- Worker method uses lazy imports (bridge, pacer, output inside method body) to keep TUI module testable without mocking subprocess dependencies
- Corrected import path: `from textual import work` instead of `from textual.work import work` for Textual 7.x

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed textual.work import path for Textual 7.x**
- **Found during:** Task 2 (TUI application creation)
- **Issue:** `from textual.work import work` raises ModuleNotFoundError in Textual 7.5.0
- **Fix:** Changed to `from textual import work` which is the correct import location
- **Files modified:** src/claude_teletype/tui.py
- **Verification:** Import succeeds, all tests pass
- **Committed in:** 05868c6 (Task 2 commit)

**2. [Rule 1 - Bug] Added on_mount to auto-focus Input widget**
- **Found during:** Task 2 (TUI test validation)
- **Issue:** Input widget not focused by default in headless test mode, causing pilot.press() keystrokes to not reach the Input -- test_prompt_echoed_to_log failed
- **Fix:** Added `on_mount` handler that calls `self.query_one("#prompt", Input).focus()` -- also improves real app UX
- **Files modified:** src/claude_teletype/tui.py
- **Verification:** All 9 TUI tests pass including prompt echo test
- **Committed in:** 05868c6 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both fixes necessary for correct operation. No scope creep.

## Issues Encountered

None beyond the auto-fixed deviations above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- output.py and tui.py are complete and tested, ready to be wired into cli.py in Plan 02-02
- TeletypeApp.stream_response uses lazy imports so bridge/pacer integration is deferred until runtime
- The existing cli.py entry point needs updating to offer TUI mode (default) vs --no-tui fallback

## Self-Check: PASSED

- All 4 created files verified on disk (output.py, tui.py, test_output.py, test_tui.py)
- Both task commits verified in git log (70145c5, 05868c6)
- pyproject.toml modified with textual dependency verified

---
*Phase: 02-terminal-simulator*
*Completed: 2026-02-15*
