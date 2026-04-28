---
phase: 21-profile-capability-fields-custom-toml-support
verified: 2026-04-28T00:00:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
requirements_covered: [CAP-01, CAP-02, CAP-03, CAP-06]
test_baseline:
  total: 526
  passed: 526
  failed: 0
  new_tests: 22  # 5 (21-01) + 4 (21-02) + 13 (21-03)
---

# Phase 21: Profile Capability Fields & Custom-TOML Support Verification Report

**Phase Goal:** PrinterProfile exposes style byte fields and a buffer-size knob so the renderer (Phase 23) and instant-mode chunker (Phase 26) can consume them as data — and custom-TOML profiles can declare the same fields.

**Verified:** 2026-04-28
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

The phase goal is achieved. PrinterProfile carries six style-byte fields plus `buffer_bytes`, the TOML loader reads all seven new keys with correct decoding (hex→bytes for style fields, plain int for buffer_bytes), and a `resolve_style` helper implements the documented italic→underline→plain and bold→underline→plain fallback chain. Phase 22 will populate built-in style codes; Phase 23/26 will consume the fields. No work in this phase requires hardware verification.

### Observable Truths (from PLAN must_haves)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | PrinterProfile exposes bold_on/off, italic_on/off, underline_on/off, buffer_bytes fields | VERIFIED | profiles.py:41-46 (style fields), profiles.py:84 (buffer_bytes); test_profiles.py:86-94, 97-100 |
| 2 | All seven new fields default to empty bytes / int 256 | VERIFIED | Dataclass declarations show `= b""` and `= 256`; tests test_printer_profile_capability_fields_default_to_empty + test_printer_profile_buffer_bytes_default_256 PASS |
| 3 | All existing v1.4 PrinterProfile tests pass with no regressions | VERIFIED | 57/57 in test_profiles.py PASS; 526/526 full suite PASS |
| 4 | Built-in profiles still resolve correctly via get_profile() with no behavioral change | VERIFIED | test_get_profile_by_name + 5 sibling get_profile tests PASS; test_juki_profile_esc_sequences, test_escp_profile_esc_sequences, test_ppds_profile_esc_sequences, test_pcl_profile_esc_sequences, test_oki_3390_profile_epson_fx2_defaults, test_citizen_cts2000_profile_escpos_defaults, test_juki_2200_profile_typewriter_defaults all PASS |
| 5 | Custom-TOML profile with hex-encoded style + integer buffer_bytes populates fields | VERIFIED | profiles.py:260-265 (style fromhex), profiles.py:285 (buffer_bytes int); test_load_custom_profiles_style_hex_round_trip + test_load_custom_profiles_buffer_bytes_int + extended test_load_custom_profiles_all_fields PASS; behavioral spot-check confirms `bold_on='1b45'` → `b'\x1bE'` and `buffer_bytes=128` → 128 |
| 6 | Missing optional style keys default to b""; missing buffer_bytes defaults to 256 | VERIFIED | profiles.py:260-265 (`bytes.fromhex(data.get(KEY, ""))`), profiles.py:285 (`data.get("buffer_bytes", 256)`); test_load_custom_profiles_style_keys_default_empty_when_absent + test_load_custom_profiles_buffer_bytes_default_256_when_absent PASS |
| 7 | All v1.4 custom-TOML loading tests continue to pass | VERIFIED | test_load_custom_profiles_valid_hex, _usb_vid_hex, _empty_dict, _no_profiles_section, _missing_optional_fields, _all_fields all PASS |
| 8 | resolve_style returns italic codes when italic set, falls back to underline, then plain | VERIFIED | profiles.py:330-335; TestResolveStyle::test_italic_returns_italic_codes_when_set + test_italic_falls_back_to_underline_when_italic_empty + test_italic_returns_plain_when_italic_and_underline_both_empty + test_italic_wins_over_underline_when_both_set PASS (4 tests) |
| 9 | resolve_style returns bold codes when bold set, falls back to underline, then plain | VERIFIED | profiles.py:336-341; 4 TestResolveStyle bold tests PASS |
| 10 | resolve_style underline returns underline codes if present, plain if absent (terminal node) | VERIFIED | profiles.py:342-345; test_underline_returns_underline_codes_when_set + test_underline_returns_plain_when_underline_empty + test_underline_does_not_fall_back_to_bold_or_italic PASS |
| 11 | Fallback chain documented in resolve_style docstring AND module docstring | VERIFIED | Module docstring lines 7-10; resolve_style docstring lines 301-311 ("Fallback chain:" + three documented branches) |
| 12 | resolve_style importable as `from claude_teletype.profiles import resolve_style` | VERIFIED | tests/test_profiles.py:14 imports resolve_style and tests pass; behavioral spot-check confirms direct import works |
| 13 | Unknown style raises ValueError with clear message listing valid styles | VERIFIED | profiles.py:346-348; test_unknown_style_raises_valueerror + test_unknown_style_message_lists_valid_styles PASS |

**Score:** 13/13 truths verified.

### Required Artifacts (Levels 1-4)

| Artifact | Expected | Exists | Substantive | Wired | Data | Status |
|----------|----------|--------|-------------|-------|------|--------|
| `src/claude_teletype/profiles.py` PrinterProfile dataclass | 6 style byte fields + buffer_bytes int with documented defaults | YES (lines 41-46, 84) | YES (frozen=True, type-annotated, commented) | YES (consumed by load_custom_profiles + resolve_style + tests) | YES (BUILTIN_PROFILES: juki-6100=64, juki-2200=64, citizen=128, oki=256, others=256; six style fields = b"" sentinel awaiting Phase 22) | VERIFIED |
| `src/claude_teletype/profiles.py` module docstring | Fallback chain documented | YES (lines 7-10) | YES (mentions italic→underline, bold→underline, plain fallback, references resolve_style) | N/A (documentation) | N/A | VERIFIED |
| `src/claude_teletype/profiles.py` load_custom_profiles | Reads 7 new TOML keys | YES (lines 260-265, 285) | YES (six bytes.fromhex calls + one data.get for int, docstring updated lines 240-244) | YES (test coverage exercises the path) | YES (round-trip test confirms `1b45` → `b'\x1bE'`, int 128 → 128, defaults preserved) | VERIFIED |
| `src/claude_teletype/profiles.py` resolve_style | Module-level helper with documented chain | YES (lines 290-348) | YES (full docstring, three branches, ValueError with message listing valid styles) | YES (imported by tests; documented as Phase 23 renderer entry point) | YES (returns real `(on,off)` tuples; behavioral spot-check confirms italic+underline fallback returns underline tuple) | VERIFIED |
| `tests/test_profiles.py` capability fields tests | 5 tests for new fields + frozen-ness + builtin sentinels | YES (test_printer_profile_capability_fields_default_to_empty, test_printer_profile_buffer_bytes_default_256, test_printer_profile_capability_fields_are_frozen, test_builtin_profiles_have_empty_style_codes_in_phase_21, test_builtin_profiles_have_positive_buffer_bytes) | YES (real assertions, not stubs) | YES (run by pytest, all 5 PASS) | N/A | VERIFIED |
| `tests/test_profiles.py` TOML-loader tests | 4 new + 1 extended | YES (test_load_custom_profiles_style_hex_round_trip, _buffer_bytes_int, _buffer_bytes_default_256_when_absent, _style_keys_default_empty_when_absent + extended test_load_custom_profiles_all_fields) | YES (full hex round-trip assertions including ESC E/F, ESC 4/5, ESC - 1/0) | YES (5 tests PASS) | N/A | VERIFIED |
| `tests/test_profiles.py` TestResolveStyle class | 13 tests covering chain | YES (lines 525-617, class with 13 test methods) | YES (Epson ESC/P fixture bytes, full chain coverage, error handling) | YES (13 tests PASS) | N/A | VERIFIED |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `tests/test_profiles.py::test_printer_profile_capability_fields_default_to_empty` | PrinterProfile defaults | field-by-field assertion | WIRED | Asserts all 6 fields equal `b""` against bare `PrinterProfile(name="minimal")` |
| `src/claude_teletype/profiles.py::PrinterProfile` | frozen dataclass field decl | `@dataclass(frozen=True)` | WIRED | profiles.py:19 `@dataclass(frozen=True)` + line 84 `buffer_bytes: int = 256` |
| `src/claude_teletype/profiles.py::load_custom_profiles` | PrinterProfile constructor | `bytes.fromhex()` for byte fields, `int` for buffer_bytes | WIRED | Six `bytes.fromhex(data.get(KEY, ""))` lines + one `data.get("buffer_bytes", 256)` line in PrinterProfile(...) call |
| `tests/test_profiles.py::test_load_custom_profiles_style_hex_round_trip` | load_custom_profiles | TOML dict assertion | WIRED | Asserts `bold_on='1b45'` → `b'\x1bE'` after round-trip |
| `src/claude_teletype/profiles.py::resolve_style` | PrinterProfile capability fields | attribute access | WIRED | Reads `profile.italic_on`, `profile.bold_on`, `profile.underline_on` (and corresponding `_off` companions) |
| `tests/test_profiles.py::TestResolveStyle` | resolve_style | tuple-return assertion | WIRED | 13 tests assert `resolve_style(p, "italic"/"bold"/"underline")` returns expected tuples |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|----|
| BUILTIN_PROFILES style fields | bold_on/off, italic_on/off, underline_on/off | Hardcoded `b""` defaults via dataclass field | Empty by design (Phase 22 fills) | FLOWING (sentinel intended) |
| BUILTIN_PROFILES buffer_bytes | int values | Per-profile literals (juki=64, citizen=128, others=256) | YES — 4 distinct real values | FLOWING |
| load_custom_profiles output | bold_on, ..., buffer_bytes | TOML dict via `bytes.fromhex` / `data.get` | YES — round-trip verified by test | FLOWING |
| resolve_style return | (on_bytes, off_bytes) tuple | profile attribute reads | YES — 13 tests cover all branches | FLOWING |

Note: built-in style fields are intentionally empty in Phase 21 — this is the documented contract (sentinel for Phase 22). The test `test_builtin_profiles_have_empty_style_codes_in_phase_21` asserts this and is documented in 21-01-SUMMARY as a Phase 22 rewrite point.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| PrinterProfile defaults match contract | `python -c "from claude_teletype.profiles import PrinterProfile; p = PrinterProfile(name='x'); assert p.bold_on==b'' and p.italic_on==b'' and p.underline_on==b'' and p.buffer_bytes==256"` | exits 0 | PASS |
| Per-profile buffer_bytes overrides applied | `python -c "...juki-6100.buffer_bytes==64; juki-2200==64; juki==64; citizen-cts2000==128; oki-3390==256"` | all assertions pass | PASS |
| TOML round-trip for all 7 keys | `load_custom_profiles({...all 7 keys...})` then assert decoded values | bold_on=b'\x1bE', italic_on=b'\x1b4', underline_on=b'\x1b-\x01', buffer_bytes=128 | PASS |
| TOML defaults preserved for absent keys | `load_custom_profiles({'printer':{'profiles':{'bare':{}}}})` | All style fields b"", buffer_bytes=256 | PASS |
| resolve_style italic→italic when set | `resolve_style(p_italic_only, 'italic')` | returns italic tuple | PASS |
| resolve_style italic→underline fallback | `resolve_style(p_underline_only, 'italic')` | returns underline tuple | PASS |
| resolve_style bold→underline fallback | `resolve_style(p_underline_only, 'bold')` | returns underline tuple | PASS |
| resolve_style underline terminal node | `resolve_style(p_bold_and_italic_set, 'underline')` | returns (b"", b"") — does NOT fall back | PASS |
| resolve_style ValueError on unknown style | `resolve_style(p, 'strikethrough')` | raises ValueError with bold/italic/underline mentioned | PASS |
| Full pytest suite | `uv run pytest` | 526 passed in 10.30s | PASS |
| Profile-only suite | `uv run pytest tests/test_profiles.py -v` | 57 passed in 0.02s | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| CAP-01 | 21-01-PLAN | PrinterProfile exposes bold_on/off, italic_on/off, underline_on/off byte fields (empty bytes = capability not supported) | SATISFIED | profiles.py:41-46; test_printer_profile_capability_fields_default_to_empty PASS; test_builtin_profiles_have_empty_style_codes_in_phase_21 PASS (sentinel documented for Phase 22 rewrite) |
| CAP-02 | 21-01-PLAN | PrinterProfile exposes a buffer_bytes integer field (default chosen per profile family) used to chunk writes in instant mode | SATISFIED | profiles.py:84 (`buffer_bytes: int = 256`); per-profile overrides juki=64 (CH341 byte-fragility), citizen=128 (thermal); test_printer_profile_buffer_bytes_default_256 + test_builtin_profiles_have_positive_buffer_bytes PASS |
| CAP-03 | 21-03-PLAN | Renderer applies a documented fallback chain: italic → underline → plain when italic codes are absent; bold → underline → plain when bold codes are absent | SATISFIED | profiles.py:290-348 (resolve_style helper with documented chain in docstring); module docstring lines 7-10; 13 TestResolveStyle tests PASS covering all six required scenarios + underline-terminal + ValueError |
| CAP-06 | 21-02-PLAN | Custom TOML profiles can declare bold/italic/underline byte sequences and buffer_bytes using the same field names | SATISFIED | profiles.py:260-265 (six `bytes.fromhex(data.get(KEY, ""))` lines), profiles.py:285 (`buffer_bytes=data.get("buffer_bytes", 256)`); test_load_custom_profiles_style_hex_round_trip + test_load_custom_profiles_buffer_bytes_int + test_load_custom_profiles_buffer_bytes_default_256_when_absent + test_load_custom_profiles_style_keys_default_empty_when_absent PASS; behavioral round-trip confirmed |

CAP-04 and CAP-05 (mapped to Phase 22 in REQUIREMENTS.md table at line 115-116) are NOT in this phase's scope and not expected to be delivered here.

### Anti-Patterns Found

None. Scanned `src/claude_teletype/profiles.py` and `tests/test_profiles.py` for TODO/FIXME/XXX/HACK/PLACEHOLDER patterns and forward-references to "Phase 22"/"Phase 23"/"Phase 26" are intentional documentation of upcoming consumers (allowed by 21-01-PLAN and explicitly approved in summaries).

### Human Verification Required

None for Phase 21.

Per the verification context: "style codes get encoded in Phase 22, so if the verifier expects styled output the answer is 'deferred to Phase 22'." This phase delivers fields + loader + helper only; no styled printer output is expected. The buffer_bytes per-profile values (juki=64, citizen=128) carry hardware-tuning intent that is itself a STATE.md concern but does not block goal achievement here.

### Gaps Summary

No gaps. All four phase requirements (CAP-01, CAP-02, CAP-03, CAP-06) are satisfied with code, tests, and behavioral spot-checks. The full project test suite (526 tests) passes with zero regressions. The phase delivers the data shape Phase 22 (style encoding), Phase 23 (renderer), and Phase 26 (instant-mode chunker) need to consume.

---
*Verified: 2026-04-28*
*Verifier: Claude (gsd-verifier)*
