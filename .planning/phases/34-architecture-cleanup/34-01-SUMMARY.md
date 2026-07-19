---
phase: 34-architecture-cleanup
plan: 01
subsystem: printing
tags: [profile-registry, driver-selection, diagnostics, case-insensitive-lookup]

# Dependency graph
requires:
  - phase: 31-printing-refactor
    provides: ProfileRegistry (REF-02) and the selection.py driver-factory seam
  - phase: 32-setup-detection-flow-fixes
    provides: 32-REVIEW.md findings WR-01, WR-02, WR-04 closed here
provides:
  - create_driver_for_selection with registry= and diagnostics= keyword params
  - Registry-backed, case-insensitive profile resolution in driver creation (WR-01)
  - Case-fold name collision warning in ProfileRegistry._by_lower (WR-02)
  - _emit diagnostics channel — caller-capturable list or stderr (WR-04 plumbing)
affects: [34-02 (all_profiles shim removal), 34-04 (get_profile retirement), tui, cli]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_emit(diagnostics, msg): append to caller list when given, else stderr"
    - "unknown profile name = loud diagnostic + explicit unwrapped fallback, never silent"

key-files:
  created: []
  modified:
    - src/claude_teletype/printing/registry.py
    - src/claude_teletype/printing/selection.py
    - tests/test_registry.py
    - tests/test_smart_startup.py

key-decisions:
  - "effective registry precedence: registry= arg > ProfileRegistry(all_profiles) if non-empty dict > ProfileRegistry(BUILTIN_PROFILES)"
  - "all_profiles kept as deprecated positional shim until 34-02 removes it (tui.py/cli.py still pass dicts)"

patterns-established:
  - "Collision policy symmetry: case-fold name collisions mirror the VID-collision diagnostic (last-wins + warning naming both keys)"

requirements-completed: [ARCH-CLEAN-01]

# Metrics
duration: 9min
completed: 2026-07-19
---

# Phase 34 Plan 01: Registry-Backed Driver Selection Summary

**ProfileRegistry is now the lookup authority in create_driver_for_selection: case-insensitive resolution (WR-01), loud unknown-name fallback via a caller-capturable diagnostics channel (WR-04), and case-fold collision warnings in the registry (WR-02)**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-07-19T00:05:57Z
- **Completed:** 2026-07-19T00:14:30Z
- **Tasks:** 2 (both TDD)
- **Files modified:** 4

## Accomplishments
- `ProfileRegistry._by_lower` construction now detects case-fold key collisions and logs a warning naming both keys and the lowered lookup key — last-wins resolution unchanged and test-pinned
- `create_driver_for_selection` gained keyword-only `registry=` and `diagnostics=` params; profile lookup goes through `registry.get()` in try/except ValueError instead of a plain dict `.get()`
- Unknown profile names now emit "Unknown printer profile ... printing without profile wrapping" instead of silently producing an unwrapped generic driver
- Both CR-03 fallback messages (USB→CUPS, empty-cups-name) route through `_emit` — appended to a caller's list when passed, stderr otherwise

## Task Commits

Each task was committed atomically (TDD: test → feat):

1. **Task 1: WR-02 case-fold collision warning** - `0c9ff85` (test), `0657ca2` (feat)
2. **Task 2: WR-01 + diagnostics plumbing** - `be8fb55` (test), `75ff0f1` (feat)

## Files Created/Modified
- `src/claude_teletype/printing/registry.py` - explicit `_by_lower` loop with case-collision warning; docstring policy bullet
- `src/claude_teletype/printing/selection.py` - `_emit` helper; registry-backed lookup with deprecated `all_profiles` shim; updated docstring
- `tests/test_registry.py` - 2 new caplog tests (collision warns + last-wins, no-collision silence)
- `tests/test_smart_startup.py` - 5 new tests (case-insensitive wrap, unknown-name list diagnostic, unknown-name stderr, CR-03 routing both ways, bare-call builtin default)

## Decisions Made
- None - followed plan as specified

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Worktree test runs initially imported the main repo's editable-install package (`/Users/mit/Documents/claude-teletype/src/...`), masking worktree edits. Resolved by running pytest with `PYTHONPATH=$PWD/src`; no code change needed.
- Known worktree artifact: `tests/test_usb_backend.py` fails 2 tests with `ModuleNotFoundError: No module named 'usb'` (pyusb not installed in this environment). Pre-existing, unrelated to this plan; recorded per orchestrator instruction, not chased. Full suite otherwise green: 970 passed (baseline >= 965 collected met).

## Known Stubs
- `all_profiles` positional parameter in `create_driver_for_selection` is a deliberate transitional shim (deprecated, documented in signature comment and docstring). Plan 34-02 removes it once tui.py/cli.py pass `registry=` instead.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- 34-02 can delete the `all_profiles` shim and migrate tui.py/cli.py call sites to `registry=`
- 34-04 can retire the module-top `get_profile` import once `discover_printer` migrates
- No changes made to profiles.py or catalog/* (34-03's territory) — no conflicts observed

---
*Phase: 34-architecture-cleanup*
*Completed: 2026-07-19*

## Self-Check: PASSED

All 4 modified files exist; all 4 task commits (0c9ff85, 0657ca2, be8fb55, 75ff0f1) verified in git log.
