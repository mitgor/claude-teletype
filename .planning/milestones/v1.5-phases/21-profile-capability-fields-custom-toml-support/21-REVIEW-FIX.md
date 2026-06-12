---
phase: 21-profile-capability-fields-custom-toml-support
fixed_at: 2026-04-28T00:00:00Z
review_path: .planning/phases/21-profile-capability-fields-custom-toml-support/21-REVIEW.md
iteration: 1
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
---

# Phase 21: Code Review Fix Report

**Fixed at:** 2026-04-28
**Source review:** .planning/phases/21-profile-capability-fields-custom-toml-support/21-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 1 (Critical + Warning)
- Fixed: 1
- Skipped: 0

Info findings (IN-01..IN-05) were deferred per default `critical_warning` scope.
None of them were trivially adjacent to the WR-01 fix path, so none were
addressed incidentally.

## Fixed Issues

### WR-01: `load_custom_profiles` accepts non-int / zero / negative `buffer_bytes` without validation

**Files modified:** `src/claude_teletype/profiles.py`, `tests/test_profiles.py`
**Commit:** 615e45c
**Applied fix:** Added a guard at the top of the per-profile loop in
`load_custom_profiles` that reads `buffer_bytes` (default 256) and validates
it is a positive `int` that is NOT a `bool`. Invalid values (str, bool, 0,
negative) now raise `ValueError` with the offending profile name and the
bad value embedded in the message — e.g. `Profile 'bad': buffer_bytes must
be a positive integer, got '256'`. The validated `buf` value is then passed
to the `PrinterProfile(...)` constructor.

The fix matches the review's suggested code shape exactly and uses the same
"must be a positive int" invariant already enforced for built-in profiles
by `test_builtin_profiles_have_positive_buffer_bytes`.

Added 4 regression tests in `tests/test_profiles.py` (the 3 the review
called for, plus a `bool`-rejection test since the validator explicitly
filters `bool` — `True`/`False` are technically `int` subclasses in Python,
so without the `isinstance(buf, bool)` guard `True` would slip through as
`buffer_bytes=1`):

- `test_load_custom_profiles_buffer_bytes_rejects_zero`
- `test_load_custom_profiles_buffer_bytes_rejects_negative`
- `test_load_custom_profiles_buffer_bytes_rejects_non_int`
- `test_load_custom_profiles_buffer_bytes_rejects_bool`

All 4 new tests pass; full `tests/test_profiles.py` suite (61 tests) green.

---

_Fixed: 2026-04-28_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
