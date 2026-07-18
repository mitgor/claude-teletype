---
phase: 11-multi-llm-backends
plan: 02
subsystem: cli
tags: [config, cli-flags, tui-refactor, backend-wiring, integration-tests]

# Dependency graph
requires:
  - phase: 11-multi-llm-backends
    plan: 01
    provides: "LLMBackend ABC, create_backend factory, ClaudeCliBackend, OpenAIBackend, OpenRouterBackend"
  - phase: 09-configuration-system
    provides: "TeletypeConfig dataclass, load_config, apply_env_overrides, merge_cli_flags"
provides:
  - "TeletypeConfig with backend, model, system_prompt fields"
  - "--backend and --model CLI flags with config merge"
  - "Backend factory wiring at startup with validation"
  - "TUI streaming via LLMBackend instead of direct bridge calls"
  - "Status bar model name from any backend (model_usage or item.model)"
  - "Integration tests for full config-to-backend pipeline"
affects: [future-backends, tui-features]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Backend-polymorphic streaming in CLI and TUI", "Config merge chain extended with backend/model fields"]

key-files:
  created:
    - "tests/test_integration_llm.py"
  modified:
    - "src/claude_teletype/config.py"
    - "src/claude_teletype/cli.py"
    - "src/claude_teletype/tui.py"
    - "tests/test_cli.py"

key-decisions:
  - "check_claude_installed() replaced by create_backend + validate() for all backends"
  - "TUI _kill_process uses backend.proc_holder (no-op for API backends)"
  - "Model name fallback: extract_model_name(model_usage) or item.model for API backends"
  - "Session ID updated from backend.session_id property instead of StreamResult directly"
  - "Existing _chat_async tests refactored to mock at backend level instead of subprocess level"

patterns-established:
  - "Backend polymorphism: CLI/TUI create backend at startup, pass it down, stream via backend.stream()"
  - "Config [llm] section: backend, model, system_prompt flattened automatically by existing config loader"

requirements-completed: [LLM-01, LLM-02, LLM-03, LLM-04]

# Metrics
duration: 7min
completed: 2026-02-17
---

# Phase 11 Plan 02: Backend Integration Summary

**Config/CLI/TUI wired to use LLMBackend polymorphically with --backend/--model flags, startup validation, and backend-driven streaming**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-17T18:21:22Z
- **Completed:** 2026-02-17T18:28:33Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Config extended with backend/model/system_prompt fields in [llm] TOML section
- CLI --backend and --model flags with full config merge chain
- Backend created and validated at startup, replacing check_claude_installed()
- TUI refactored to stream via self._backend.stream() instead of direct bridge calls
- Status bar shows model name from any backend (Claude CLI via model_usage, API via item.model)
- 9 integration tests covering full config-to-backend wiring pipeline
- Existing CLI tests refactored to mock at backend level instead of subprocess level

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend config and CLI with backend/model/system_prompt fields and flags** - `402fd3f` (feat)
2. **Task 2: Refactor TUI to use LLMBackend and add integration tests** - `db85952` (feat)

## Files Created/Modified
- `src/claude_teletype/config.py` - Added backend, model, system_prompt fields to TeletypeConfig; added [llm] section to DEFAULT_CONFIG_TEMPLATE
- `src/claude_teletype/cli.py` - Added --backend/--model flags; replaced check_claude_installed with backend validation; wired backend to _chat_async and TUI
- `src/claude_teletype/tui.py` - Added backend parameter; replaced stream_claude_response with backend.stream(); updated _kill_process and model name extraction
- `tests/test_cli.py` - Refactored _chat_async tests to use mock backend; updated CLI tests to mock create_backend instead of check_claude_installed
- `tests/test_integration_llm.py` - 9 new integration tests for config defaults, TOML loading, env overrides, factory wiring, TUI storage, _chat_async usage, validation errors, config show

## Decisions Made
- Replaced check_claude_installed() with create_backend() + validate() -- a single validation path for all backends instead of a Claude-specific check
- TUI _kill_process uses backend.proc_holder attribute (only present on ClaudeCliBackend) -- API backends have no subprocess to kill, so it's a clean no-op
- Model name display uses fallback chain: extract_model_name(model_usage) -> item.model -> "--", supporting both Claude CLI (which provides model_usage dict) and API backends (which set model directly)
- Session ID updated from backend.session_id property rather than StreamResult.session_id directly -- backend owns session state
- Refactored existing _chat_async tests to mock at the backend.stream() level rather than subprocess level -- cleaner and backend-agnostic

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing _chat_async tests to provide backend parameter**
- **Found during:** Task 1 (config and CLI changes)
- **Issue:** Three existing _chat_async tests called the function without the new `backend` parameter, causing `AttributeError: 'NoneType' object has no attribute 'stream'`
- **Fix:** Refactored tests to create mock backend objects and pass them to _chat_async
- **Files modified:** tests/test_cli.py
- **Verification:** All 354 non-backend tests pass
- **Committed in:** 402fd3f (Task 1 commit)

**2. [Rule 1 - Bug] Updated CLI tests patching check_claude_installed to patch create_backend**
- **Found during:** Task 1 (config and CLI changes)
- **Issue:** Seven existing CLI integration tests patched check_claude_installed which no longer exists in the main() code path
- **Fix:** Created _mock_create_backend helper; replaced all check_claude_installed patches with create_backend patches
- **Files modified:** tests/test_cli.py
- **Verification:** All CLI tests pass
- **Committed in:** 402fd3f (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both fixes necessary to keep existing tests passing after the refactor. No scope creep.

## Issues Encountered
None beyond the deviations documented above.

## User Setup Required
None - no external service configuration required. Users set OPENAI_API_KEY or OPENROUTER_API_KEY environment variables when they choose to use those backends.

## Next Phase Readiness
- Phase 11 complete: full multi-LLM backend support from config through TUI
- All backends produce identical streaming behavior (AsyncIterator[str | StreamResult])
- Ready for Phase 12 (Settings TUI) and Phase 13 (Testing and Documentation)

---
## Self-Check: PASSED

All files verified present. All commits verified in git log.

---
*Phase: 11-multi-llm-backends*
*Completed: 2026-02-17*
