---
phase: 15-fix-system-prompt-hot-swap
verified: 2026-02-17T21:45:00Z
status: passed
score: 3/3 must-haves verified
re_verification: false
---

# Phase 15: Fix system_prompt Backend Hot-Swap Verification Report

**Phase Goal:** Preserve system_prompt when switching backends via settings modal so users don't lose their custom prompt
**Verified:** 2026-02-17T21:45:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                          | Status     | Evidence                                                                                       |
|----|------------------------------------------------------------------------------------------------|------------|-----------------------------------------------------------------------------------------------|
| 1  | system_prompt configured in TOML is preserved when user switches backends via settings modal   | VERIFIED   | `_apply_settings` passes `system_prompt=self._system_prompt or None` to `create_backend`     |
| 2  | system_prompt configured in TOML is preserved when user switches models (same backend) via settings modal | VERIFIED | Same `create_backend` call fires on any backend OR model change (line 197-208 of tui.py)    |
| 3  | TeletypeApp stores system_prompt as a tracking attribute accessible throughout its lifecycle   | VERIFIED   | `self._system_prompt = system_prompt` at tui.py:83; `system_prompt: str = ""` in `__init__` |

**Score:** 3/3 truths verified

### Required Artifacts

| Artifact                        | Expected                                          | Status     | Details                                                                                            |
|---------------------------------|---------------------------------------------------|------------|----------------------------------------------------------------------------------------------------|
| `src/claude_teletype/tui.py`    | `_system_prompt` tracking attribute and create_backend passthrough | VERIFIED | `self._system_prompt = system_prompt` at line 83; `system_prompt=self._system_prompt or None` at line 207 |
| `src/claude_teletype/cli.py`    | `system_prompt` kwarg passed to TeletypeApp constructor            | VERIFIED | `system_prompt=config.system_prompt` at line 446 inside `TeletypeApp(...)` call                   |
| `tests/test_tui.py`             | Test verifying system_prompt survives backend hot-swap             | VERIFIED   | `test_system_prompt_preserved_on_backend_swap` at line 263; passes (confirmed via test run)        |

### Key Link Verification

| From                          | To                                           | Via                                     | Status   | Details                                                                                      |
|-------------------------------|----------------------------------------------|-----------------------------------------|----------|----------------------------------------------------------------------------------------------|
| `src/claude_teletype/cli.py`  | `src/claude_teletype/tui.py`                 | `system_prompt` constructor kwarg       | WIRED    | `system_prompt=config.system_prompt` at cli.py:446 in `TeletypeApp(...)` constructor call    |
| `src/claude_teletype/tui.py`  | `src/claude_teletype/backends/__init__.py`   | `system_prompt` passed to `create_backend` in `_apply_settings` | WIRED | `system_prompt=self._system_prompt or None` at tui.py:207; local import of `create_backend` inside `_apply_settings` at line 201 |

### Requirements Coverage

| Requirement | Source Plan | Description                                                                                              | Status    | Evidence                                                                                                        |
|-------------|-------------|----------------------------------------------------------------------------------------------------------|-----------|-----------------------------------------------------------------------------------------------------------------|
| SET-01      | 15-01-PLAN  | User can open a settings modal in the TUI via keyboard shortcut to change printer, LLM, delay, and audio | SATISFIED | Phase 13 originally satisfied. Phase 15 extends it: system_prompt now survives the backend/model change applied via that modal |
| LLM-02      | 15-01-PLAN  | User can chat with OpenAI or OpenRouter models via direct API using the `openai` library                  | SATISFIED | Phase 11 originally satisfied. Phase 15 integration fix ensures system_prompt flows to `create_backend` during hot-swap, preserving correct behavior for all backends |

**Note on requirement ownership:** Both SET-01 and LLM-02 were first satisfied in earlier phases (13 and 11 respectively). Phase 15 is an integration gap-closure: it fixes a bug where the existing SET-01 settings modal and LLM-02 backend creation silently dropped `system_prompt` on hot-swap. The requirements are not re-opened; they are reinforced.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/claude_teletype/tui.py` | 96, 119, 310, 443 | `placeholder=` | None | These are Textual `Input` widget `placeholder` text attributes, not stub indicators — false positive |

No genuine anti-patterns detected.

### Human Verification Required

None. All critical behaviors are mechanically verifiable:

- `system_prompt` passthrough is a deterministic code path (not UI-dependent)
- Test `test_system_prompt_preserved_on_backend_swap` asserts both the `create_backend` call arguments and the `app._system_prompt` attribute directly
- Full test suite (401 tests) passes with zero regressions

### Test Execution Results

```
tests/test_tui.py::test_system_prompt_preserved_on_backend_swap PASSED   [100%]
1 passed in 0.08s

Full suite: 401 passed, 2 warnings in 8.80s
```

The 2 warnings are pre-existing `RuntimeWarning: coroutine '_chat_async' was never awaited` from unrelated tests in test_cli.py and test_printer.py.

### Commit Verification

| Commit    | Message                                                             | Status  |
|-----------|---------------------------------------------------------------------|---------|
| `27ac056` | `test(15-01): add failing test for system_prompt backend hot-swap preservation` | Verified in git log |
| `56a313e` | `feat(15-01): preserve system_prompt during backend hot-swap`       | Verified in git log |

### Key Implementation Details Verified

1. **`_system_prompt` tracking attribute** — `TeletypeApp.__init__` accepts `system_prompt: str = ""` (tui.py:61) and stores it as `self._system_prompt = system_prompt` (tui.py:83). Follows established `_backend_name` / `_model_config` pattern.

2. **create_backend passthrough** — `_apply_settings` (tui.py:182-224) calls `create_backend(backend=..., model=..., system_prompt=self._system_prompt or None)` at line 204-208. The `or None` normalizes empty string to None, matching the cli.py convention.

3. **cli.py wiring** — `TeletypeApp(...)` at cli.py:437-449 includes `system_prompt=config.system_prompt` at line 446. This means TOML-configured system_prompt flows end-to-end: TOML -> `config.system_prompt` -> `TeletypeApp._system_prompt` -> `create_backend(system_prompt=...)` on every hot-swap.

4. **Patch target deviation from plan** — Test patches `claude_teletype.backends.create_backend` (the source module) rather than `claude_teletype.tui.create_backend`, because `create_backend` is imported locally inside `_apply_settings`, not at module level. This is the correct approach and documented in the SUMMARY as an auto-fixed deviation.

### Gaps Summary

None. All must-haves pass at all three verification levels (exists, substantive, wired). Both requirement IDs (SET-01, LLM-02) are accounted for. The phase goal is achieved.

---

_Verified: 2026-02-17T21:45:00Z_
_Verifier: Claude (gsd-verifier)_
