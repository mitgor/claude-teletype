---
phase: 06-error-handling-and-recovery
plan: 02
subsystem: tui
tags: [pre-flight-check, retry-backoff, error-classification, session-recovery, cli-validation]

# Dependency graph
requires:
  - phase: 06-error-handling-and-recovery
    plan: 01
    provides: "ErrorCategory enum, classify_error(), is_retryable(), ERROR_MESSAGES dict"
  - phase: 05-multi-turn-conversation-foundation
    provides: "StreamResult with is_error/error_message, session_id resume, kill-with-timeout"
provides:
  - "CLI pre-flight check for claude binary with install instructions"
  - "TUI retry loop with exponential backoff (MAX_RETRIES=3, jitter) for rate_limit/overloaded"
  - "Classified error messages in TUI for all ErrorCategory types"
  - "Session recovery resets session_id before retry to prevent reuse of corrupted sessions"
  - "No-retry-after-text guard to prevent response duplication"
affects: [07-ux-polish, tui-error-handling]

# Tech tracking
tech-stack:
  added: []
  patterns: [exponential-backoff-with-jitter, pre-flight-cli-validation, classified-exception-handler]

key-files:
  created: []
  modified:
    - src/claude_teletype/cli.py
    - src/claude_teletype/tui.py
    - tests/test_tui.py

key-decisions:
  - "Pre-flight check at chat() entry point catches missing CLI before TUI launch"
  - "Only retry when no text has been streamed yet to prevent response duplication (Pitfall 4)"
  - "Session ID reset happens BEFORE retry decision to ensure fresh session on retry"
  - "Exception handler classifies error string before displaying (not just raw exception)"

patterns-established:
  - "Pre-flight validation pattern: check external dependencies at CLI entry before deep logic"
  - "Retry with exponential backoff + jitter: BASE_DELAY * 2^(retries-1) + random(0,1)"
  - "has_text flag tracking to prevent retry after partial response delivery"

requirements-completed: [ERR-01, ERR-05, ERR-06]

# Metrics
duration: 2min
completed: 2026-02-17
---

# Phase 6 Plan 02: CLI Pre-flight, TUI Retry with Backoff, and Session Recovery Summary

**CLI pre-flight check_claude_installed() with install URL, TUI exponential backoff retry for transient errors, and classified error messages with session recovery reset**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-16T23:14:30Z
- **Completed:** 2026-02-16T23:16:44Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments
- CLI exits with install URL and docs link when `claude` binary not found via shutil.which()
- TUI retries rate_limit and overloaded errors up to 3 times with exponential backoff and jitter
- All error paths show classified user-friendly messages from ERROR_MESSAGES dict
- Session recovery resets session_id before retry to prevent corrupted session reuse
- No-retry guard when text already streamed prevents response duplication (research Pitfall 4)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add CLI pre-flight check and TUI retry loop with classified errors** - `656d718` (feat)

## Files Created/Modified
- `src/claude_teletype/cli.py` - Added check_claude_installed() with shutil.which, CLAUDE_INSTALL_URL/CLAUDE_DOCS_URL constants, called at start of chat()
- `src/claude_teletype/tui.py` - Added MAX_RETRIES/BASE_DELAY constants, retry while loop with exponential backoff, classify_error integration, session_id reset, has_text guard, classified exception handler
- `tests/test_tui.py` - Added test_check_claude_installed_missing (typer.Exit on missing binary) and test_check_claude_installed_found (success path)

## Decisions Made
- Pre-flight check placed at chat() entry point, before teletype branch -- catches missing CLI as early as possible
- Only retry when no text has been streamed yet (has_text flag) to avoid response duplication per research Pitfall 4
- Session ID reset happens unconditionally on any error when session_id is set, BEFORE retry decision
- Exception handler attempts classify_error on str(exc) before falling back to raw error display

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test catching wrong exception type for typer.Exit**
- **Found during:** Task 1 (test verification)
- **Issue:** Test used `pytest.raises(SystemExit)` but `typer.Exit` extends `click.exceptions.Exit`, not `SystemExit`. Exit code accessed via `.exit_code` not `.code`.
- **Fix:** Changed to `pytest.raises(typer.Exit)` and `exc_info.value.exit_code == 1`
- **Files modified:** tests/test_tui.py
- **Verification:** All 245 tests pass
- **Committed in:** 656d718 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug in test assertion)
**Impact on plan:** Minor test fix, no scope creep.

## Issues Encountered
None beyond the test exception type issue documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All Phase 6 error handling requirements complete (ERR-01 through ERR-06)
- CLI validates claude binary before launch
- TUI handles transient errors with automatic retry
- All error categories have user-friendly messages
- Session recovery prevents corrupted session reuse
- Ready for Phase 7 (UX polish and word wrapping)

## Self-Check: PASSED

- All 3 key files verified present on disk
- Task commit verified in git log (656d718)
- 245/245 tests passing

---
*Phase: 06-error-handling-and-recovery*
*Completed: 2026-02-17*
