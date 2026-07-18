---
phase: 11-multi-llm-backends
plan: 01
subsystem: api
tags: [openai, openrouter, async-streaming, abc, factory-pattern]

# Dependency graph
requires:
  - phase: 01-streaming-pipeline
    provides: "bridge.py StreamResult and stream_claude_response"
  - phase: 06-error-handling-and-recovery
    provides: "ERROR_PATTERNS for error classification"
provides:
  - "LLMBackend ABC with stream/validate/add_to_history interface"
  - "ClaudeCliBackend wrapping bridge.py"
  - "OpenAIBackend streaming via AsyncOpenAI with history management"
  - "OpenRouterBackend as thin OpenAIBackend wrapper"
  - "create_backend factory function"
  - "BackendError exception"
affects: [11-02-integration, tui, cli]

# Tech tracking
tech-stack:
  added: ["openai>=2.21.0"]
  patterns: ["ABC-based backend abstraction", "factory function for backend creation", "SDK exception to StreamResult error mapping"]

key-files:
  created:
    - "src/claude_teletype/backends/__init__.py"
    - "src/claude_teletype/backends/claude_cli.py"
    - "src/claude_teletype/backends/openai_backend.py"
    - "tests/test_backends.py"
  modified:
    - "pyproject.toml"

key-decisions:
  - "Placeholder API key ('not-set') in constructor to avoid OpenAI SDK raising on None api_key"
  - "max_retries=0 on AsyncOpenAI to let TUI retry loop handle consistently across backends"
  - "Error messages match existing ERROR_PATTERNS substrings for seamless classification"

patterns-established:
  - "LLMBackend ABC: all backends implement stream(), validate(), add_to_history()"
  - "Factory pattern: create_backend() with lazy imports for backend implementations"
  - "SDK error -> StreamResult(is_error=True) mapping with ERROR_PATTERNS-compatible messages"

requirements-completed: [LLM-01, LLM-02, LLM-04]

# Metrics
duration: 4min
completed: 2026-02-17
---

# Phase 11 Plan 01: Backend Abstraction Summary

**LLMBackend ABC with factory, Claude CLI wrapper, OpenAI/OpenRouter streaming backends using openai SDK v2.21.0**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-17T18:14:33Z
- **Completed:** 2026-02-17T18:18:46Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- LLMBackend ABC defining stream/validate/add_to_history interface for all backends
- ClaudeCliBackend wrapping existing bridge.py stream_claude_response with session ID tracking
- OpenAIBackend streaming chat completions with conversation history and SDK error handling
- OpenRouterBackend as thin wrapper over OpenAI with different base_url
- create_backend factory creating correct backend for "claude-cli", "openai", "openrouter"
- 21 comprehensive tests covering factory, validation, streaming, errors, history, system prompts

## Task Commits

Each task was committed atomically:

1. **Task 1: Create backends subpackage with ABC, factory, and Claude CLI backend** - `3d8d1a7` (feat)
2. **Task 2: Create OpenAI and OpenRouter backends with streaming and tests** - `ad57f8b` (feat)

## Files Created/Modified
- `src/claude_teletype/backends/__init__.py` - LLMBackend ABC, BackendError, create_backend factory
- `src/claude_teletype/backends/claude_cli.py` - ClaudeCliBackend wrapping bridge.py
- `src/claude_teletype/backends/openai_backend.py` - OpenAIBackend and OpenRouterBackend streaming implementations
- `tests/test_backends.py` - 21 tests covering all backend functionality
- `pyproject.toml` - Added openai>=2.21.0 dependency
- `uv.lock` - Updated lockfile

## Decisions Made
- Used placeholder API key ("not-set") in AsyncOpenAI constructor to avoid SDK raising on None. Validation happens in validate() method at startup, not during construction.
- Set max_retries=0 on AsyncOpenAI to disable SDK-level retries, letting the TUI retry loop handle consistently across all backends (per research recommendation).
- Error messages from SDK exceptions include keywords matching existing ERROR_PATTERNS ("authentication", "rate limit", "network") so the TUI error classification works unchanged.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] OpenAI SDK raises on None api_key in constructor**
- **Found during:** Task 2 (OpenAI backend tests)
- **Issue:** OpenAI SDK v2.21.0 raises OpenAIError in AsyncOpenAI constructor when api_key=None and OPENAI_API_KEY env var is unset. Plan assumed key could be passed as None with validation deferred.
- **Fix:** Pass "not-set" placeholder when api_key is None, track with _api_key_provided bool, validate in validate() method.
- **Files modified:** src/claude_teletype/backends/openai_backend.py
- **Verification:** test_openai_validate_no_key and test_openrouter_validate_no_key both pass
- **Committed in:** ad57f8b (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Fix necessary for correctness. No scope creep.

## Issues Encountered
None beyond the deviation documented above.

## User Setup Required
None - no external service configuration required. Users will set OPENAI_API_KEY or OPENROUTER_API_KEY environment variables when they choose to use those backends.

## Next Phase Readiness
- Backend abstraction complete; ready for Plan 02 integration with CLI flags and TUI
- All backends produce identical AsyncIterator[str | StreamResult] output
- create_backend factory ready for CLI/TUI to call at startup

---
## Self-Check: PASSED

All files verified present. All commits verified in git log.

---
*Phase: 11-multi-llm-backends*
*Completed: 2026-02-17*
