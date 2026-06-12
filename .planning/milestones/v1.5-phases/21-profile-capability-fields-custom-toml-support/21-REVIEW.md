---
phase: 21-profile-capability-fields-custom-toml-support
reviewed: 2026-04-28T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - src/claude_teletype/profiles.py
  - tests/test_profiles.py
findings:
  critical: 0
  warning: 1
  info: 5
  total: 6
status: issues_found
---

# Phase 21: Code Review Report

**Reviewed:** 2026-04-28
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Phase 21 adds six style-capability byte fields (bold/italic/underline on/off) and a
`buffer_bytes` int to `PrinterProfile`, extends `load_custom_profiles` to read those
new TOML keys, and introduces a module-level `resolve_style(profile, style)` helper
implementing the documented italic→underline→plain and bold→underline→plain fallback
chains.

The implementation is correct, well-documented, and well-tested for the happy path.
Forward references to Phases 22/23/26 are appropriate contract documentation. Empty
style codes on built-ins are intentional Phase 21 scope and are explicitly guarded
against regression by `test_builtin_profiles_have_empty_style_codes_in_phase_21`.

The findings below are all about defensive handling of malformed/hostile custom-TOML
input — `load_custom_profiles` is a public ingestion surface for user-authored config,
and currently surfaces low-context `ValueError` from the stdlib for bad input and
silently accepts any value (including non-int, zero, or negative) for `buffer_bytes`.
None of this affects Phase 21 acceptance, but the issues are easy to fix and worth
recording so the loader does not become a usability foot-gun once Phase 22 lands and
encourages more user-authored style codes.

## Warnings

### WR-01: `load_custom_profiles` accepts non-int / zero / negative `buffer_bytes` without validation

**File:** `src/claude_teletype/profiles.py:285`
**Issue:** `buffer_bytes=data.get("buffer_bytes", 256)` performs no type or range
validation. A user-authored TOML file with `buffer_bytes = "256"` (string),
`buffer_bytes = 0`, or `buffer_bytes = -64` will silently produce a `PrinterProfile`
that downstream Phase 26 chunker code will then either crash on (TypeError on string
arithmetic) or loop forever / produce zero-byte writes (on `<= 0`). The corresponding
built-in test `test_builtin_profiles_have_positive_buffer_bytes` already encodes the
"must be a positive int" invariant for built-ins, so the same check should apply to
custom profiles where the failure mode is much worse (foreign input).
**Fix:**
```python
buf = data.get("buffer_bytes", 256)
if not isinstance(buf, int) or isinstance(buf, bool) or buf <= 0:
    raise ValueError(
        f"Profile {name!r}: buffer_bytes must be a positive integer, "
        f"got {buf!r}"
    )
# ... then pass buffer_bytes=buf to PrinterProfile(...)
```
Also add tests: `test_load_custom_profiles_buffer_bytes_rejects_zero`,
`test_load_custom_profiles_buffer_bytes_rejects_negative`,
`test_load_custom_profiles_buffer_bytes_rejects_non_int`.

## Info

### IN-01: Malformed hex in custom-TOML produces low-context `ValueError`

**File:** `src/claude_teletype/profiles.py:256-271`
**Issue:** Every `bytes.fromhex(data.get("…", ""))` call propagates a bare
`ValueError("non-hexadecimal number found in fromhex() arg at position N")` with no
mention of which profile or which field was bad. Same for the
`int(data["usb_vendor_id"], 16)` calls (lines 274-283) — a malformed
`usb_vendor_id = "ZZZZ"` raises `ValueError: invalid literal for int() with base 16:
'ZZZZ'` without naming the offending profile. For a public user-config ingestion path,
this makes diagnosis painful. Wrap the per-profile parse in a try/except and re-raise
with context, e.g. `raise ValueError(f"Profile {name!r}: invalid hex for {field!r}: …")`.
**Fix:** Extract the per-field hex decode into a small helper that includes the
profile name and field name in any raised error — e.g.
```python
def _hex(name: str, field: str, raw: str) -> bytes:
    try:
        return bytes.fromhex(raw)
    except ValueError as e:
        raise ValueError(
            f"Profile {name!r}: invalid hex in {field!r}: {raw!r}"
        ) from e
```
and call it for every bytes field. Same wrapper pattern for the VID/PID `int(..., 16)`.

### IN-02: `load_custom_profiles` silently ignores unknown TOML keys

**File:** `src/claude_teletype/profiles.py:252-286`
**Issue:** A user typo such as `intit = "1b40"` (instead of `init`) is silently
dropped — `data.get("init", "")` returns the default empty string, and the typo'd key
is never inspected. This is a common foot-gun for hand-edited TOML and worth at least
a deferred follow-up. Two reasonable options: (a) compute the set difference between
`data.keys()` and the known field names and emit a warning (`logging.warning(...)`)
listing unknown keys, or (b) raise `ValueError` on unknown keys. Option (a) is more
forgiving and matches the spirit of the rest of the loader.
**Fix:** Add at the top of the loop:
```python
KNOWN = {"description", "init", "reset", "line_spacing", "char_pitch",
         "bold_on", "bold_off", "italic_on", "italic_off",
         "underline_on", "underline_off",
         "crlf", "reinit_on_newline", "reinit_sequence",
         "end_of_response_sequence", "formfeed_on_close", "instant_output",
         "usb_vendor_id", "usb_product_id", "columns", "buffer_bytes"}
unknown = set(data) - KNOWN
if unknown:
    logger.warning("Profile %r: ignoring unknown keys %s", name, sorted(unknown))
```

### IN-03: TOML `name` field is silently overridden by the table key

**File:** `src/claude_teletype/profiles.py:253-254`
**Issue:** The loader hard-codes `name=name` from the dict key (the TOML table name).
If a user writes `[printer.profiles.foo]\nname = "bar"`, the `name = "bar"` line is
silently ignored — `foo` wins. This is probably the intended design (the key is the
canonical identifier), but it is undocumented in the function docstring and could
confuse a user diagnosing why their `name = ...` value has no effect. Either document
the precedence in the docstring or warn (per IN-02).
**Fix:** Add to the docstring of `load_custom_profiles`:
```
The TOML table key (e.g. ``[printer.profiles.my-printer]``) is always
authoritative for the profile name. A ``name = ...`` field inside the
table is silently ignored.
```

### IN-04: No regression sentinel for the per-profile `buffer_bytes` values from phase scope

**File:** `tests/test_profiles.py:160-164`
**Issue:** `test_builtin_profiles_have_positive_buffer_bytes` only asserts
`isinstance(int)` and `> 0`. The phase-scope decisions
(juki-6100=64, juki-2200=64, juki alias=64, citizen-cts2000=128, others=256) are not
encoded as a regression test. A future refactor that flips juki-6100 to 256 would
silently regress the CH341 byte-fragility fix without any test failure.
**Fix:** Add a test:
```python
def test_builtin_profiles_buffer_bytes_per_phase_21_decisions():
    expected = {
        "juki-6100": 64, "juki-2200": 64, "juki": 64,
        "citizen-cts2000": 128,
        "generic": 256, "escp": 256, "ppds": 256,
        "pcl": 256, "ibm": 256, "oki-3390": 256,
    }
    for name, want in expected.items():
        assert BUILTIN_PROFILES[name].buffer_bytes == want, (
            f"{name}: expected buffer_bytes={want}, got {BUILTIN_PROFILES[name].buffer_bytes}"
        )
```

### IN-05: `resolve_style` does not validate `_off` symmetry

**File:** `src/claude_teletype/profiles.py:330-345`
**Issue:** The fallback chain pairs `_on` with its `_off` companion based solely on
whether `_on` is non-empty. If a profile (built-in or custom) sets
`bold_on = b"\x1bE"` but leaves `bold_off = b""`, `resolve_style(p, "bold")` returns
`(b"\x1bE", b"")` — the renderer emits the on-sequence and never closes it, leaving
the printer in bold mode for the rest of the document. The function's docstring
explicitly says "the function does NOT mix-and-match across capabilities", which
correctly rules out borrowing underline_off to close bold, but it does not warn the
user that a missing `_off` will silently leak. This is a profile-authoring concern,
not a bug in `resolve_style` itself, but a defensive validator in
`load_custom_profiles` (and a docstring mention here) would catch it at config-load
time instead of at print time.
**Fix:** In `load_custom_profiles`, after building each profile, check pair symmetry:
```python
for on_field, off_field in [
    ("bold_on", "bold_off"),
    ("italic_on", "italic_off"),
    ("underline_on", "underline_off"),
]:
    on_val = getattr(p, on_field)
    off_val = getattr(p, off_field)
    if bool(on_val) != bool(off_val):
        logger.warning(
            "Profile %r: %s is set but %s is empty (or vice versa); "
            "style will not close correctly",
            name, on_field, off_field,
        )
```
Optionally add a one-line note in the `resolve_style` docstring:
"Callers are responsible for ensuring `_on` and `_off` are both set or both empty;
this function does not enforce pairing."

---

_Reviewed: 2026-04-28_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
