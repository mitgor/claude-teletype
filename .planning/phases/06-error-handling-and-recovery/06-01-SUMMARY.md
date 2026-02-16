---
phase: 06-error-handling-and-recovery
plan: 01
subsystem: bridge
tags: [error-classification, subprocess-timeout, asyncio, kill-with-timeout, enum]

# Dependency graph
requires:
  - phase: 05-multi-turn-conversation-foundation
    provides: "StreamResult dataclass, stream_claude_response async generator, kill-with-timeout in TUI"
provides:
  - "ErrorCategory enum with 7 categories for Claude Code error classification"
  - "classify_error() function mapping error strings to categories"
  - "is_retryable() function for retry eligibility"
  - "ERROR_MESSAGES dict with user-friendly guidance per category"
  - "Readline timeout protection (300s default, 30s post-result)"
  - "Kill-with-timeout on timeout error path (SIGTERM -> 5s -> SIGKILL)"
affects: [06-02, tui-retry-logic, session-recovery]

# Tech tracking
tech-stack:
  added: []
  patterns: [error-classification-via-substring-matching, readline-timeout-with-wait_for, kill-with-timeout-on-all-error-paths]

key-files:
  created:
    - src/claude_teletype/errors.py
    - tests/test_errors.py
  modified:
    - src/claude_teletype/bridge.py
    - tests/test_bridge.py

key-decisions:
  - "Substring matching (not regex) for error classification -- simpler, maintainable, sufficient for known patterns"
  - "300s readline timeout as generous default for long tool operations, 30s after result message"
  - "ErrorCategory as str+Enum for JSON serialization compatibility"

patterns-established:
  - "Error classification via ordered pattern list with first-match-wins"
  - "Dual-timeout strategy: generous during streaming, short after result to catch hang bug"
  - "Kill-with-timeout in bridge exception handler mirrors TUI pattern from Phase 5"

requirements-completed: [ERR-02, ERR-03, ERR-04]

# Metrics
duration: 3min
completed: 2026-02-17
---

# Phase 6 Plan 01: Error Classification and Bridge Timeout Summary

**ErrorCategory enum with 7 categories, classify_error() substring matcher, readline timeout (300s/30s dual), and kill-with-timeout on timeout error path**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-16T23:08:43Z
- **Completed:** 2026-02-16T23:12:07Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Error classification module with 7 categories mapping Claude Code error strings to actionable user messages
- Readline timeout protection preventing indefinite subprocess hangs (known issue #25629)
- Kill-with-timeout pattern on timeout error path ensuring zombie process cleanup (ERR-04)
- Dual-timeout strategy: 300s during active streaming, 30s after result message received

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing tests (RED)** - `cdf11ec` (test)
2. **Task 2: Implement errors.py and bridge timeout (GREEN)** - `36f519d` (feat)

_Note: TDD plan with RED -> GREEN phases. No separate refactor needed._

## Files Created/Modified
- `src/claude_teletype/errors.py` - ErrorCategory enum, classify_error(), is_retryable(), ERROR_MESSAGES dict
- `src/claude_teletype/bridge.py` - READ_TIMEOUT_SECONDS/POST_RESULT_TIMEOUT_SECONDS constants, asyncio.wait_for readline wrapping, TimeoutError handler with kill-with-timeout
- `tests/test_errors.py` - 20 tests covering all 7 categories, retryability, and message completeness
- `tests/test_bridge.py` - 3 new timeout tests verifying error yield, subprocess kill, and post-result timeout switch

## Decisions Made
- Used substring matching (not regex) for error classification -- simpler and sufficient for known Claude Code error patterns
- 300 seconds readline timeout to avoid false positives during legitimate long tool operations
- 30 seconds post-result timeout to quickly catch the stream-json hang bug (#25629) after all content delivered
- ErrorCategory extends both str and Enum for future JSON serialization compatibility

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed kill-with-timeout test mock for proc.wait side effects**
- **Found during:** Task 2 (GREEN phase test verification)
- **Issue:** Mock proc.wait with single TimeoutError side_effect failed on the second await proc.wait() after proc.kill(). Need side_effect list: [TimeoutError, 0] for first wait (times out) and second wait (succeeds after kill).
- **Fix:** Changed `side_effect=asyncio.TimeoutError` to `side_effect=[asyncio.TimeoutError, 0]`
- **Files modified:** tests/test_bridge.py
- **Verification:** All 3 timeout tests pass
- **Committed in:** 36f519d (Task 2 commit)

**2. [Rule 1 - Bug] Fixed shorter-timeout test assertion checking wrong wait_for call**
- **Found during:** Task 2 (GREEN phase test verification)
- **Issue:** Test checked last wait_for call for POST_RESULT_TIMEOUT, but last call was the cleanup handler's wait_for(proc.wait(), timeout=5.0). Needed to check that POST_RESULT_TIMEOUT_SECONDS appeared anywhere in the wait_for call history.
- **Fix:** Changed assertion to check `POST_RESULT_TIMEOUT_SECONDS in timeout_values` across all wait_for calls
- **Files modified:** tests/test_bridge.py
- **Verification:** Test correctly validates the dual-timeout behavior
- **Committed in:** 36f519d (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 bugs in test mocks)
**Impact on plan:** Both fixes were necessary for correct test behavior. No scope creep.

## Issues Encountered
None beyond the test mock issues documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- errors.py module ready for consumption by Plan 02 (TUI retry logic and session recovery)
- classify_error() and is_retryable() provide the classification layer that retry logic needs
- ERROR_MESSAGES dict provides user-facing strings for TUI display
- Bridge timeout protection is active and will yield error StreamResult on hang

## Self-Check: PASSED

- All 4 key files verified present on disk
- Both task commits verified in git log (cdf11ec, 36f519d)
- 243/243 tests passing

---
*Phase: 06-error-handling-and-recovery*
*Completed: 2026-02-17*
