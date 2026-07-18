---
phase: 15-fix-system-prompt-hot-swap
plan: 01
subsystem: tui
tags: [system-prompt, backend-hot-swap, settings-modal, tdd]

# Dependency graph
requires:
  - phase: 13-settings-panel
    provides: SettingsScreen modal with backend/model switching via _apply_settings
  - phase: 09-configuration-system
    provides: config.system_prompt TOML field
provides:
  - _system_prompt tracking attribute on TeletypeApp preserving system_prompt across backend hot-swaps
  - system_prompt passthrough from cli.py config to TeletypeApp constructor
  - system_prompt forwarded to create_backend in _apply_settings
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_system_prompt tracking attribute follows existing _backend_name/_model_config pattern"
    - "empty string or None normalization via `or None` matching cli.py convention"

key-files:
  created: []
  modified:
    - src/claude_teletype/tui.py
    - src/claude_teletype/cli.py
    - tests/test_tui.py

key-decisions:
  - "_system_prompt stored as str (empty string default), converted to None via `or None` at create_backend call site -- matches cli.py pattern"

patterns-established:
  - "Tracking attributes on TeletypeApp follow naming convention: _system_prompt, _backend_name, _model_config"

requirements-completed: [SET-01, LLM-02]

# Metrics
duration: 2min
completed: 2026-02-17
---

# Phase 15 Plan 01: Fix System Prompt Hot-Swap Summary

**system_prompt tracking attribute on TeletypeApp preserves TOML-configured system_prompt through backend/model hot-swap via settings modal**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-17T21:27:17Z
- **Completed:** 2026-02-17T21:29:11Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- TDD RED: test proves system_prompt was silently dropped on backend hot-swap
- TDD GREEN: three surgical edits wire system_prompt from config through cli.py to TeletypeApp to create_backend
- Full test suite (401 tests) passes with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: RED -- failing test for system_prompt preservation** - `27ac056` (test)
2. **Task 2: GREEN -- wire system_prompt through TeletypeApp and cli.py** - `56a313e` (feat)

_TDD plan: RED commit proves the bug, GREEN commit fixes it._

## Files Created/Modified
- `src/claude_teletype/tui.py` - Added system_prompt parameter to __init__, _system_prompt tracking attribute, system_prompt passthrough in _apply_settings create_backend call
- `src/claude_teletype/cli.py` - Added system_prompt=config.system_prompt to TeletypeApp constructor call
- `tests/test_tui.py` - Added test_system_prompt_preserved_on_backend_swap verifying system_prompt survives backend hot-swap

## Decisions Made
- _system_prompt stored as str with empty string default, converted to None via `or None` at create_backend call site -- matches existing cli.py pattern where empty string is treated as None

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test patch target for create_backend**
- **Found during:** Task 2 (GREEN phase)
- **Issue:** Plan specified patching `claude_teletype.tui.create_backend` but create_backend is imported locally inside _apply_settings, not at module level
- **Fix:** Changed patch target to `claude_teletype.backends.create_backend` (the source module)
- **Files modified:** tests/test_tui.py
- **Verification:** Test passes with correct patch target
- **Committed in:** 56a313e (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Corrected test mock target for local import pattern. No scope creep.

## Issues Encountered
None beyond the patch target deviation noted above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- This was the final v1.2 gap closure -- all requirements now verified
- system_prompt flows end-to-end: TOML config -> cli.py -> TeletypeApp -> create_backend on hot-swap

## Self-Check: PASSED

- All 3 modified files exist on disk
- Commit `27ac056` (RED test) verified in git log
- Commit `56a313e` (GREEN implementation) verified in git log
- 15-01-SUMMARY.md exists at expected path

---
*Phase: 15-fix-system-prompt-hot-swap*
*Completed: 2026-02-17*
