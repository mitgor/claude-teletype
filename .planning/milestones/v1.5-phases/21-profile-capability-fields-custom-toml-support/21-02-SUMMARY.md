---
phase: 21-profile-capability-fields-custom-toml-support
plan: 02
subsystem: profiles
tags: [printer-profile, custom-toml, capability-fields, buffer-bytes, hex-decode, loader]

# Dependency graph
requires:
  - phase: 21-01
    provides: "PrinterProfile dataclass slots for bold_on/bold_off/italic_on/italic_off/underline_on/underline_off (defaults b\"\") and buffer_bytes (default 256, with per-profile overrides on Juki/Citizen built-ins)"
provides:
  - "load_custom_profiles reads bold_on/bold_off/italic_on/italic_off/underline_on/underline_off as hex strings via bytes.fromhex(), defaulting to b\"\" when absent"
  - "load_custom_profiles reads buffer_bytes as a plain int (NOT a hex string), defaulting to 256 when absent"
  - "Loader docstring documents the byte-vs-int distinction (bytes.fromhex for raw bytes, int(x, 16) for USB IDs, plain int for byte counts)"
  - "Test coverage: 4 new tests + 1 extended test for the seven new TOML keys"
affects: [21-03-resolve-style-helper, phase-22-encode-style-bytes, phase-23-markdown-renderer, phase-26-instant-mode-chunker]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TOML decoding convention: bytes.fromhex() for raw byte fields, int(x, 16) for USB VID/PID, plain int for byte counts (buffer_bytes)"
    - "Loader extension preserves existing field order and the for-loop's early-return for missing profiles section"

key-files:
  created: []
  modified:
    - src/claude_teletype/profiles.py
    - tests/test_profiles.py

key-decisions:
  - "buffer_bytes is a plain int in TOML, NOT a hex string. This is distinct from usb_vendor_id and usb_product_id which use int(x, 16) because they are USB identifiers (typically expressed in hex by hardware vendors). buffer_bytes is a count of bytes, so plain int is the natural type and matches Python's standard convention."
  - "Style hex fields (bold_on/off, italic_on/off, underline_on/off) follow the existing init/reset/line_spacing/char_pitch/reinit_sequence/end_of_response_sequence convention: hex string in TOML, decoded via bytes.fromhex() to bytes in the dataclass. Empty string default produces b\"\" — matching the dataclass default and the capability-absent sentinel established in 21-01."
  - "Did NOT add resolve_style helper (plan 21-03's scope) and did NOT modify the PrinterProfile dataclass (plan 21-01 already shipped the fields)."

patterns-established:
  - "Three TOML decoding conventions coexist cleanly: (1) bytes.fromhex(data.get(KEY, '')) for raw byte sequences with empty default, (2) int(data[KEY], 16) if KEY in data else None for hex-encoded USB IDs with None sentinel, (3) data.get(KEY, default) for plain ints/bools/strings"
  - "Extending an existing TOML loader = inserting new lines into the PrinterProfile constructor call without disturbing existing argument lines or the function signature"

requirements-completed: [CAP-06]

# Metrics
duration: 1.8min
completed: 2026-04-28
---

# Phase 21 Plan 02: Custom-TOML Loader Extension Summary

**`load_custom_profiles` now reads the seven new style and buffer_bytes TOML keys, satisfying CAP-06 and giving users a no-code path to declare per-printer style capabilities and chunk size in their `config.toml`.**

## Performance

- **Duration:** 1.8 min (110 seconds)
- **Started:** 2026-04-28T19:48:54Z
- **Completed:** 2026-04-28T19:50:44Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Extended `load_custom_profiles` in `src/claude_teletype/profiles.py` to decode six style hex keys (`bold_on`, `bold_off`, `italic_on`, `italic_off`, `underline_on`, `underline_off`) via `bytes.fromhex()` with empty-string defaults, and `buffer_bytes` as a plain int with default 256.
- Updated the loader docstring to explicitly call out the byte-vs-int distinction: style keys use `bytes.fromhex()` like other byte fields, but `buffer_bytes` is a plain int (count of bytes) — distinct from `usb_vendor_id`/`usb_product_id` which use `int(x, 16)` because they are USB identifiers, not byte counts.
- Added 4 new tests in `tests/test_profiles.py` proving round-trip and default behaviour for the seven new keys: `test_load_custom_profiles_style_hex_round_trip`, `test_load_custom_profiles_buffer_bytes_int`, `test_load_custom_profiles_buffer_bytes_default_256_when_absent`, `test_load_custom_profiles_style_keys_default_empty_when_absent`.
- Extended the existing `test_load_custom_profiles_all_fields` test with the seven new keys and corresponding assertions, preserving all pre-existing assertions.
- Full project baseline confirmed clean: 513 passed (509 carry-forward + 4 new tests), zero regressions.

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend load_custom_profiles to read the seven new TOML keys** — `0bfbdb0` (feat)
2. **Task 2: Add tests covering the seven new TOML keys (round-trip and defaults)** — `d013f6b` (test)

**Plan metadata:** _added in final commit below_

## Files Created/Modified

- `src/claude_teletype/profiles.py` — added 7 lines to the `PrinterProfile(...)` constructor call inside `load_custom_profiles` (six `bytes.fromhex()` lines for style keys, one `data.get` line for `buffer_bytes`), and 6 lines to the function docstring documenting the byte-vs-int distinction.
- `tests/test_profiles.py` — added 4 new tests after `test_load_custom_profiles_all_fields`, plus extended that existing test with 7 new fields and 7 new assertions.

## Decisions Made

- **Followed the plan's prescribed insertion order strictly:** the six style keys go between `char_pitch` and `crlf` in the constructor call (grouped with byte-sequence fields), and `buffer_bytes` goes at the end after `columns` (matching the dataclass ordering established by plan 21-01).
- **Did NOT touch the `resolve_style` helper** — that is plan 21-03's scope. The loader simply populates the fields; the renderer's fallback chain consumes them.
- **Did NOT modify the `PrinterProfile` dataclass** — plan 21-01 already added the fields.
- **Did NOT alter any existing constructor argument lines** — only inserted new lines as instructed.
- **Did NOT change the function signature, return type, or the early-return for an empty `profiles` section.**
- The docstring addition matches the plan's prescribed text exactly; no embellishments.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None. The execution flow was straightforward: edit loader, run tests, commit; edit tests, run tests, commit. All grep acceptance criteria and python one-liner functional checks passed on the first attempt.

## Next Phase Readiness

- **Plan 21-03 (resolve_style helper)** is unblocked. The full data path is now in place: built-in profiles ship the dataclass shape with empty defaults (21-01), custom TOML profiles can populate the fields via the loader (21-02), and 21-03 adds the consumer helper that walks the italic→underline→plain and bold→underline→plain fallback chain. The contract documented in the `profiles.py` module docstring (added in 21-01) is the spec.
- **Phase 22 (encode style bytes for built-ins)** is unblocked. Both the dataclass slots and the user-facing TOML escape hatch exist; Phase 22 fills in verified per-family sequences (Epson FX `\x1b4`/`\x1b5` for italic, etc.) on the built-in profiles. Users with niche printers don't need to wait for Phase 22 — they can declare their codes in `config.toml` today via the seven new keys this plan landed.
- **Phase 23 (markdown renderer)** is unblocked from a data-flow standpoint: the renderer reads `profile.bold_on` etc. directly (populated either by built-ins in Phase 22 or by user TOML now). The fallback chain helper (21-03) is the renderer's actual consumer.
- **Phase 26 (instant-mode chunker)** is unblocked from a data-flow standpoint: the chunker reads `profile.buffer_bytes` directly (populated either by built-ins in 21-01 or by user TOML now).

## Self-Check: PASSED

Verified all claims:

- `src/claude_teletype/profiles.py` exists and contains `bold_on=bytes.fromhex(data.get("bold_on", ""))`, all five other style keys, `buffer_bytes=data.get("buffer_bytes", 256)`, and the byte-vs-int docstring paragraph — confirmed via grep.
- `tests/test_profiles.py` exists and contains all 4 new test names plus the extended `test_load_custom_profiles_all_fields` (with `"bold_on": "1b45"` appearing in 2 places: the new style-round-trip test and the extended _all_fields test) — confirmed via grep.
- Commit `0bfbdb0` exists in `git log` — confirmed via `git rev-parse --short HEAD` immediately after the commit.
- Commit `d013f6b` exists in `git log` — confirmed via `git rev-parse --short HEAD` immediately after the commit.
- `uv run pytest tests/test_profiles.py -x` returns 44 passed (40 carry-forward + 4 new tests) — confirmed.
- `uv run pytest -x` returns 513 passed (509 carry-forward + 4 new tests) — confirmed, baseline preserved.

---
*Phase: 21-profile-capability-fields-custom-toml-support*
*Plan: 02*
*Completed: 2026-04-28*
