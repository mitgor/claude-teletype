---
phase: 17-claude-cli-warnings
plan: 01
subsystem: ui
tags: [textual, warnings, backend, claude-cli, settings]

requires:
  - phase: 11-multi-llm-backends
    provides: LLMBackend ABC, create_backend factory, backend/system_prompt config
  - phase: 13-settings-panel
    provides: SettingsScreen modal, _apply_settings callback
  - phase: 15-fix-system-prompt-hot-swap
    provides: _system_prompt tracking attribute on TeletypeApp
provides:
  - warnings.py module with check_system_prompt_warning() and should_warn_startup()
  - CLI startup warning when system_prompt configured with claude-cli backend
  - TUI notification toast for same startup warning condition
  - ConfirmSwapScreen modal for backend hot-swap away from claude-cli
  - Once-per-config suppression for startup warnings
affects: []

tech-stack:
  added: []
  patterns:
    - "Warning module pattern: pure functions returning message strings, caller handles display"
    - "Module-level set for per-process suppression of repeated warnings"
    - "ConfirmSwapScreen(ModalScreen[bool]) for blocking confirmation dialogs"
    - "Deferred backend swap via _pending_swap_result + callback pattern"

key-files:
  created:
    - src/claude_teletype/warnings.py
    - tests/test_warnings.py
  modified:
    - src/claude_teletype/cli.py
    - src/claude_teletype/tui.py
    - tests/test_settings_screen.py

key-decisions:
  - "Per-process suppression (module-level set) sufficient for once-per-config -- no file persistence needed"
  - "ConfirmSwapScreen only triggers when switching AWAY FROM claude-cli -- API backends don't maintain persistent sessions"
  - "Startup warning shown in both CLI (console.print) and TUI (notify toast) since CLI output scrolls away when TUI starts"
  - "Backend swap logic extracted to _do_backend_swap() method for reuse by both direct and confirmed paths"

patterns-established:
  - "Warning module with pure check functions: check_X_warning(args) -> str | None"
  - "ConfirmSwapScreen pattern: ModalScreen[bool] with callback for gated operations"

requirements-completed: [WARN-01, WARN-02]

duration: 4min
completed: 2026-02-20
---

# Phase 17-01: Claude-CLI Warnings Summary

**Startup system_prompt warning and backend hot-swap confirmation dialog for claude-cli backend limitations**

## Performance

- **Duration:** 4 min
- **Completed:** 2026-02-20
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Created warnings module with check_system_prompt_warning() detecting system_prompt + claude-cli conflict
- Integrated startup warning in both CLI (Rich console) and TUI (Textual notification toast) with once-per-config suppression
- Added ConfirmSwapScreen blocking confirmation when switching away from claude-cli in settings modal
- 15 new tests (11 warning tests + 4 confirmation screen tests) all passing, 430 total suite

## Task Commits

Each task was committed atomically:

1. **Task 1: Create warnings module and integrate startup warning** - `7279b22` (feat)
2. **Task 2: Add hot-swap confirmation warning in settings modal** - `a7e0c19` (feat)

## Files Created/Modified
- `src/claude_teletype/warnings.py` - Warning logic: check_system_prompt_warning(), should_warn_startup(), once-per-config suppression
- `src/claude_teletype/cli.py` - Added startup warning check after backend validation
- `src/claude_teletype/tui.py` - Added ConfirmSwapScreen class, on_mount warning toast, _apply_settings confirmation gate
- `tests/test_warnings.py` - 11 tests for warning detection and suppression logic
- `tests/test_settings_screen.py` - 4 new tests for ConfirmSwapScreen compose, confirm, cancel, escape

## Decisions Made
- Per-process suppression via module-level set -- no file persistence needed since config changes restart code paths
- Only warn when switching AWAY FROM claude-cli (not between API backends) -- API backends don't have persistent sessions
- Warning shown in both CLI console output and TUI toast notification for visibility
- Backend swap logic extracted to _do_backend_swap() for clean reuse between direct and confirmed code paths

## Deviations from Plan

None - plan executed as written.

## Issues Encountered
- Textual 7.x Static widget has no `.renderable` attribute -- used `str(message.render())` instead in tests

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 17 is the final phase of v1.3 Tech Debt Cleanup milestone
- All v1.3 requirements (PROF-01, CONF-01, WARN-01, WARN-02) now addressed

---
*Phase: 17-claude-cli-warnings*
*Completed: 2026-02-20*
