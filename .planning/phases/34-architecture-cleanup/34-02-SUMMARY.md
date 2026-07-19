---
phase: 34-architecture-cleanup
plan: 02
subsystem: printing
tags: [profile-registry, tui, cli, setup-screen, diagnostics, arch-02, arch-06]

# Dependency graph
requires:
  - phase: 34-architecture-cleanup
    provides: "34-01: create_driver_for_selection registry=/diagnostics= params and _emit channel"
provides:
  - ProfileRegistry object threaded end-to-end (cli -> TeletypeApp -> PrinterSetupScreen -> create_driver_for_selection)
  - all_profiles dict currency extinct in src (ARCH-02 closed)
  - Public read-only ProfilePrinterDriver.inner property (ARCH-06 closed)
  - Selection diagnostics surfaced in-TUI via notify() (WR-04 closed)
  - Unresolvable saved profile -> resolved_profile=None so status bar matches actual driver (IN-03 closed)
  - Kernel-owns CUPS recommendation gated on enabled queues (IN-01 closed)
affects: [34-04 (get_profile retirement), tui, cli, printer-setup-screen]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TeletypeApp._lookup_profile: case-insensitive registry lookup, None on no-registry/unknown"
    - "registry object as the one profile currency — no flatten/rebuild round trips"

key-files:
  created: []
  modified:
    - src/claude_teletype/cli.py
    - src/claude_teletype/tui.py
    - src/claude_teletype/screens/printer_setup.py
    - src/claude_teletype/printing/drivers.py
    - src/claude_teletype/printing/selection.py
    - tests/test_tui.py
    - tests/test_printer.py
    - tests/test_printer_setup_screen.py
    - tests/test_tui_file_picker_keybinding.py

key-decisions:
  - "TeletypeApp stores the registry as _profile_registry, not _registry — Textual's App already owns self._registry (its internal widget registry); clobbering it crashes push_screen"

patterns-established:
  - "Screens/apps receive the ProfileRegistry object; dict catalogs never cross a constructor boundary"

requirements-completed: [ARCH-CLEAN-01, ARCH-CLEAN-04]

# Metrics
duration: 7min
completed: 2026-07-19
---

# Phase 34 Plan 02: Registry Threading End-to-End Summary

**ProfileRegistry now flows cli -> TeletypeApp -> PrinterSetupScreen -> create_driver_for_selection as one object; the all_profiles dict currency and the 34-01 shim are deleted, driver internals are reached via a public `.inner` property, and setup-flow diagnostics surface as Textual notifications**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-07-19T00:13:37Z
- **Completed:** 2026-07-19T00:20:46Z
- **Tasks:** 3 (Task 1 TDD)
- **Files modified:** 9

## Accomplishments
- ARCH-06: `ProfilePrinterDriver.inner` read-only property; tui.py has zero `_inner` reach-ins
- ARCH-02: `_resolve_print_context` returns the registry object; `main()` passes `registry=` to smart-startup and TeletypeApp; PrinterSetupScreen consumes the registry directly — the flatten-to-dict and second-registry rebuild are gone; `all_profiles` no longer exists anywhere in src
- WR-04: `_handle_setup_result` captures `diagnostics=` and surfaces each message via `self.notify(severity="warning")` — pinned by a new test
- IN-03: an unresolvable `saved_printer_profile` yields `resolved_profile = None` so the status bar never claims a profile the driver doesn't wear
- IN-01: kernel-owns CUPS recommendation now requires `any(q.enabled ...)` — never recommends a method Connect will refuse (new test)
- `create_driver_for_selection` shim deleted: signature is `(selection, discovery, *, registry=None, diagnostics=None)`

## Task Commits

1. **Task 1: public inner property (TDD)** - `b724ce5` (test), `04a457d` (feat)
2. **Task 2: registry through cli/tui + notify diagnostics** - `c9d96d7`
3. **Task 3: setup screen registry + IN-01 + shim removal** - `dc15028`

## Files Created/Modified
- `src/claude_teletype/printing/drivers.py` - `inner` property beside `is_connected` (only drivers.py change; byte path untouched)
- `src/claude_teletype/cli.py` - registry object returned/threaded; IN-03 saved-profile resolution
- `src/claude_teletype/tui.py` - `registry=` kwarg (TYPE_CHECKING import), `_lookup_profile` helper replacing 4 dict sites, notify-surfaced diagnostics, `driver.inner`
- `src/claude_teletype/screens/printer_setup.py` - registry constructor, rebuild deleted, registry-based Select/suggestion, IN-01 enabled-queue gate
- `src/claude_teletype/printing/selection.py` - `all_profiles` shim deleted; docstring updated
- tests: migrated all `all_profiles=` constructions to `registry=ProfileRegistry({...})`; new WR-04 notify test, new IN-01 disabled-queues test, 2 new `.inner` property tests

## Decisions Made
- Stored the registry on TeletypeApp as `self._profile_registry` instead of the plan's implied `self._registry`: Textual's `App` base class uses `self._registry` internally as its widget registry, and shadowing it breaks `push_screen` with `TypeError: argument of type 'ProfileRegistry' is not iterable`. The constructor kwarg stays `registry=` per the plan contract.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Attribute name collision with Textual App internals**
- **Found during:** Task 2 (42 test failures in run_test-based tests)
- **Issue:** `self._registry = registry` on TeletypeApp clobbered Textual's internal widget registry attribute of the same name
- **Fix:** renamed the instance attribute to `self._profile_registry` (public kwarg unchanged)
- **Files modified:** src/claude_teletype/tui.py
- **Commit:** c9d96d7

## Issues Encountered
- Known worktree artifact: `tests/test_usb_backend.py` fails 2 frozen-backend tests (`ModuleNotFoundError: No module named 'usb'` — pyusb not installed in this environment). Pre-existing, recorded per orchestrator instruction. Full suite otherwise green: 976 passed (baseline >= 965 collected met). Verification run with `PYTHONPATH=$PWD/src` per 34-01 precedent.

## Known Stubs
- None. The 34-01 `all_profiles` shim this plan was tracked to remove is now deleted.

## User Setup Required

None.

## Next Phase Readiness
- 34-04 can retire `get_profile` — the registry is the only profile currency across cli/tui/screens/selection
- No changes to profiles.py or catalog/* (34-03's territory)

---
*Phase: 34-architecture-cleanup*
*Completed: 2026-07-19*

## Self-Check: PASSED

All 9 modified files exist; all 4 task commits (b724ce5, 04a457d, c9d96d7, dc15028) verified in git log; no file deletions in any commit.
