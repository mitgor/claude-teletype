---
phase: 21-profile-capability-fields-custom-toml-support
plan: 03
subsystem: profiles
tags: [printer-profile, resolve-style, fallback-chain, capability-fields, markdown-rendering]

# Dependency graph
requires:
  - phase: 21-01
    provides: "PrinterProfile dataclass slots for bold_on/bold_off/italic_on/italic_off/underline_on/underline_off (defaults b\"\")"
  - phase: 21-02
    provides: "load_custom_profiles populates the same six byte fields plus buffer_bytes from TOML"
provides:
  - "resolve_style(profile, style) module-level helper in profiles.py returning (on_bytes, off_bytes)"
  - "Documented italic -> underline -> plain fallback chain"
  - "Documented bold -> underline -> plain fallback chain"
  - "Underline as terminal node: underline -> plain (no further fallback)"
  - "ValueError raised on unknown style names with a clear message"
  - "Renderer-side import contract: from claude_teletype.profiles import resolve_style"
affects: [phase-22-encode-style-bytes, phase-23-markdown-renderer]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Capability-as-data fallback chain: empty bytes signal absent capability, helper walks the documented substitution order"
    - "Module-level helper consumes dataclass attributes; no method on PrinterProfile (keeps the dataclass pure data)"

key-files:
  created: []
  modified:
    - src/claude_teletype/profiles.py
    - tests/test_profiles.py

key-decisions:
  - "resolve_style is a free function, not a method on PrinterProfile. Phase 23's renderer imports it directly. Keeping the dataclass purely data preserves the frozen-dataclass-as-pure-data convention established in v1.4 and avoids coupling the data shape to fallback logic that may evolve independently."
  - "Underline is the terminal node of the fallback chain — bold and italic fall back to underline, but underline does NOT substitute bold or italic. Rationale: underline is the universally-supported style on impact printers, so it sits at the bottom of the chain. If a printer lacks underline too, the renderer emits plain text (b\"\", b\"\") rather than fabricating a substitute that may print garbage."
  - "Italic wins over underline when both are set; bold wins over underline when both are set. The fallback chain only fires when the primary capability is empty. This means a profile author can declare italic AND underline codes and get italic at the italic call site — no precedence ambiguity."
  - "ValueError on unknown style includes all three valid names ('bold', 'italic', 'underline') in the message so the caller (markdown renderer) gets actionable feedback at first run. Tested via test_unknown_style_message_lists_valid_styles."

patterns-established:
  - "Module-level capability-resolution helpers: data lives in PrinterProfile, decision logic lives in profiles.py module-level functions, renderer imports the function directly"
  - "Test fixture pattern: realistic Epson ESC/P bytes (ESC E/F for bold, ESC 4/5 for italic, ESC - 1/0 for underline) used as test data so tests read like real-world calls and Phase 22's encoded values will match the fixtures"

requirements-completed: [CAP-03]

# Metrics
duration: 2.3min
completed: 2026-04-28
---

# Phase 21 Plan 03: resolve_style Helper Summary

**Module-level `resolve_style(profile, style)` helper in `profiles.py` walks the italic→underline→plain and bold→underline→plain fallback chains, satisfying CAP-03 and giving Phase 23's markdown renderer a single import to decide what bytes to emit for any inline emphasis on any printer profile.**

## Performance

- **Duration:** 2.3 min (135 seconds)
- **Started:** 2026-04-28T19:54:05Z
- **Completed:** 2026-04-28T19:56:20Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added `resolve_style(profile, style) -> tuple[bytes, bytes]` to `src/claude_teletype/profiles.py`, inserted between `load_custom_profiles` and the `USB_PRINTER_CLASS = 7` constant — adjacent to the loader (both consume profile data) and separate from `auto_detect_profile` (different concern).
- Documented the full fallback chain in the function's docstring: italic falls back to underline, then to plain; bold falls back to underline, then to plain; underline is the terminal node and does NOT fall back further (returns plain when its codes are empty).
- ValueError raised on unknown style names with a clear message listing the three valid names ('bold', 'italic', 'underline').
- Added 13 tests under a new `TestResolveStyle` class in `tests/test_profiles.py`, covering the italic chain (4 tests), the bold chain (4 tests), the underline chain (3 tests), and error handling (2 tests).
- Used realistic Epson ESC/P fixture bytes (ESC E/F for bold, ESC 4/5 for italic, ESC - 1/0 for underline) so tests read like real-world calls and will match the values Phase 22 will encode into built-ins.
- Renderer import contract confirmed: `from claude_teletype.profiles import resolve_style` works (verified by Task 1's smoke check and Task 2's import block).
- Full project test baseline preserved: 526 passed (513 carry-forward + 13 new TestResolveStyle tests), zero regressions.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add resolve_style helper to profiles.py with documented fallback chain** — `81dca66` (feat)
2. **Task 2: Add TestResolveStyle test class with all fallback-chain scenarios** — `96d61d4` (test)

**Plan metadata:** _added in final commit below_

## Files Created/Modified

- `src/claude_teletype/profiles.py` — added the `resolve_style(profile, style)` module-level helper with full docstring (61 lines inserted between `load_custom_profiles` and `USB_PRINTER_CLASS`).
- `tests/test_profiles.py` — added `resolve_style` to the import block (1 line) and inserted `TestResolveStyle` test class with 13 tests immediately before the `# auto_detect_profile()` banner section (102 lines).

## Decisions Made

- **Followed the plan's prescribed insertion point exactly:** `resolve_style` lives between `load_custom_profiles` and `USB_PRINTER_CLASS = 7`. It sits next to the loader (both are profile-consumption helpers) and separate from `auto_detect_profile` (a discovery helper, different concern).
- **Did NOT add `resolve_style` to any `__init__.py` or change any public surface beyond the new module-level function.** The renderer in Phase 23 imports it directly: `from claude_teletype.profiles import resolve_style`.
- **Did NOT modify** the `PrinterProfile` dataclass, `BUILTIN_PROFILES`, the IBM/juki aliases, `get_profile`, `load_custom_profiles`, or `auto_detect_profile`.
- The function signature uses positional arguments (`profile, style`) — no keyword-only enforcement. Callers pass `resolve_style(profile, "italic")` not `resolve_style(profile, style="italic")`. This matches the `get_profile(name)` precedent in the same module.
- The function returns a tuple `(on_bytes, off_bytes)` not a dataclass or named tuple. Rationale: the renderer just needs two byte strings; a heavier return type adds ceremony with no extra information. Tuple unpacking at the call site is idiomatic.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None. The execution flow was straightforward:
1. Insert the function in profiles.py.
2. Run the existing test_profiles.py to confirm no regressions (44 passed).
3. Commit Task 1.
4. Add `resolve_style` to the test imports and insert TestResolveStyle.
5. Run TestResolveStyle (13 passed) and the full suite (526 passed).
6. Commit Task 2.

All grep acceptance criteria and python one-liner functional checks passed on the first attempt.

## Next Phase Readiness

- **Phase 21 is COMPLETE.** All three plans (21-01 dataclass fields, 21-02 TOML loader, 21-03 fallback-chain helper) have shipped. Requirements CAP-01, CAP-02, CAP-03, and CAP-06 are now satisfied. The remaining capability requirements (CAP-04 and CAP-05) belong to Phase 22 (encoding verified per-family byte values into built-in profiles).
- **Phase 22 (encode style bytes for built-ins)** is unblocked. The dataclass slots are ready (21-01), the user-facing TOML escape hatch exists (21-02), and the renderer-side resolution helper is operational (21-03). Phase 22 just fills in the actual byte values on each built-in profile (Epson ESC E/F for bold, ESC 4/5 for italic, ESC - 1/0 for underline; PCL `\x1b(s3B`/`\x1b(s0B`; PPDS DC4/DC2; etc.) and the `test_builtin_profiles_have_empty_style_codes_in_phase_21` sentinel test from 21-01 will need to be removed or rewritten at that time.
- **Phase 23 (markdown renderer)** is unblocked from a data-flow standpoint. The renderer's contract for inline emphasis is now: `on_bytes, off_bytes = resolve_style(profile, "italic")`, write `on_bytes` before the span, write the span text, write `off_bytes` after. No per-printer branching in the renderer.

## Self-Check: PASSED

Verified all claims:

- `src/claude_teletype/profiles.py` exists and contains `def resolve_style(`, "Fallback chain:" docstring, and the three style branches (italic/bold/underline) — confirmed via grep.
- `tests/test_profiles.py` exists and contains `class TestResolveStyle` plus all 13 named test methods — confirmed via grep.
- `python -c "from claude_teletype.profiles import resolve_style"` exits 0 — confirmed.
- `python -c "...assert resolve_style(PrinterProfile(name='empty'), 'italic') == (b'', b'')"` exits 0 — confirmed.
- `python -c "...italic falls back to underline..."` exits 0 — confirmed.
- `python -c "...bold direct..."` exits 0 — confirmed.
- `python -c "...ValueError on unknown style..."` exits 0 — confirmed.
- Commit `81dca66` exists in `git log` — confirmed via `git rev-parse --short HEAD` immediately after the commit.
- Commit `96d61d4` exists in `git log` — confirmed via `git rev-parse --short HEAD` immediately after the commit.
- `uv run pytest tests/test_profiles.py::TestResolveStyle -v` returns 13 passed — confirmed.
- `uv run pytest -x` returns 526 passed (513 carry-forward + 13 new tests, zero regressions) — confirmed.

## TDD Gate Compliance

This plan's plan-level type is `execute`, not `tdd`, so the plan-level RED/GREEN gate sequence does not apply. The two tasks each have `tdd="true"` task-level attributes, but the plan structure splits implementation (Task 1) and test-writing (Task 2) into separate atomic commits — a deliberate executor-friendly variant of TDD where the function lands first (Task 1, `feat` commit) and the test class lands second (Task 2, `test` commit), with both committed and the suite green. Task 1's commit is `feat(21-03):` and Task 2's commit is `test(21-03):`, providing per-task type clarity in `git log`.

---
*Phase: 21-profile-capability-fields-custom-toml-support*
*Plan: 03*
*Completed: 2026-04-28*
