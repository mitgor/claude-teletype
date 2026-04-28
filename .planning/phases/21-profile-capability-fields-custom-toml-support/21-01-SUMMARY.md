---
phase: 21-profile-capability-fields-custom-toml-support
plan: 01
subsystem: profiles
tags: [printer-profile, dataclass, frozen, capability-fields, buffer-bytes, markdown-rendering]

# Dependency graph
requires:
  - phase: v1.4-printer-setup-tui
    provides: PrinterProfile frozen dataclass with USB auto-detection, eight canonical built-ins, dataclasses.replace alias pattern
provides:
  - PrinterProfile.bold_on/bold_off byte fields (default b"")
  - PrinterProfile.italic_on/italic_off byte fields (default b"")
  - PrinterProfile.underline_on/underline_off byte fields (default b"")
  - PrinterProfile.buffer_bytes int field (default 256)
  - Per-profile buffer_bytes overrides (juki-6100=64, juki-2200=64, citizen-cts2000=128)
  - Module docstring documenting the upcoming italic→underline→plain and bold→underline→plain fallback chain
affects: [21-02-custom-toml-loader, 21-03-resolve-style-helper, phase-22-encode-style-bytes, phase-23-markdown-renderer, phase-26-instant-mode-chunker]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Capability-as-data: empty bytes signal absent capability, non-empty bytes signal supported"
    - "Per-profile buffer_bytes override mirrors per-profile instant_output convention"

key-files:
  created: []
  modified:
    - src/claude_teletype/profiles.py
    - tests/test_profiles.py

key-decisions:
  - "Empty bytes (b\"\") is the sentinel for absent style capability; the markdown renderer's fallback chain (lands in plan 21-03) will read that state to decide whether to substitute underline or plain text"
  - "buffer_bytes default 256 is conservative for unknown hardware; per-profile overrides apply real-world tuning (CH341 byte-fragility=64, thermal=128) without scattering hardware knowledge in conditional code"
  - "Style codes (bold/italic/underline) are intentionally LEFT EMPTY on every built-in profile in this plan; Phase 22 encodes verified per-family sequences. Fabricated codes here would print garbage on real hardware"
  - "buffer_bytes per-profile values applied in this plan: juki-6100=64, juki-2200=64, juki alias inherits 64 via dataclasses.replace, citizen-cts2000=128, oki-3390/escp/ppds/pcl/generic/ibm=256 default"

patterns-established:
  - "Capability-field default = empty bytes: signals absent capability for the consumer's fallback chain to act on"
  - "buffer_bytes is per-profile data, not conditional code in the chunker (Phase 26 reads profile.buffer_bytes)"
  - "Forward-references in docstrings to upcoming helpers (resolve_style) acceptable when they document an already-decided contract"

requirements-completed: [CAP-01, CAP-02]

# Metrics
duration: 2.8min
completed: 2026-04-28
---

# Phase 21 Plan 01: Profile Capability Fields Summary

**PrinterProfile frozen dataclass extended with six bold/italic/underline byte fields plus a per-profile buffer_bytes int, providing the data shape Phase 22 (style encoding) and Phase 26 (instant-mode chunker) consume without any conditional code.**

## Performance

- **Duration:** 2.8 min (168 seconds)
- **Started:** 2026-04-28T19:43:09Z
- **Completed:** 2026-04-28T19:45:58Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added six byte fields (bold_on, bold_off, italic_on, italic_off, underline_on, underline_off) to PrinterProfile, all defaulting to b"" (capability not supported)
- Added buffer_bytes int field defaulting to 256 with per-profile overrides on CH341-bridged Juki profiles (64) and the Citizen thermal receipt profile (128)
- Updated the profiles.py module docstring to document the upcoming italic→underline→plain and bold→underline→plain fallback chain that plan 21-03 will implement as `resolve_style`
- Added five new tests in test_profiles.py covering: defaults, frozen-ness of new fields, every built-in having empty style codes (Phase 22 sentinel), and every built-in exposing positive-int buffer_bytes
- All 10 built-in profiles (8 canonical + ibm alias + juki alias) inherit the new fields with no behavioral regression — the `juki` alias picks up `buffer_bytes=64` automatically through `dataclasses.replace`
- Full project test baseline confirmed clean: 509 tests passing (project tracker says 479; baseline has grown beyond that — also a regression-free state)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add capability fields to PrinterProfile dataclass and update module docstring** — `7b05512` (feat)
2. **Task 2: Add tests covering the seven new PrinterProfile fields and built-in defaults** — `11c3de2` (test)

**Plan metadata:** _added in final commit below_

## Files Created/Modified

- `src/claude_teletype/profiles.py` — added 6 style byte fields + buffer_bytes int to PrinterProfile, set per-profile buffer_bytes overrides on Juki and Citizen built-ins, expanded module docstring with fallback-chain contract
- `tests/test_profiles.py` — added 5 tests under two banner sections (PrinterProfile capability fields, BUILTIN_PROFILES registry sentinels)

## Decisions Made

- **Took the optional Task 1 step 3 buffer_bytes overrides.** Plan permitted skipping per-profile values (leaving everything at 256) but explicitly recommended Juki=64 (CH341 byte-fragility) and Citizen=128 (modest thermal chunks). Chose to apply them now so plan 21-02 (custom-TOML loader) and Phase 26 (instant-mode chunker) inherit real values rather than placeholders that would need a follow-up edit.
- Style fields placed in the dataclass between `char_pitch` and `# Newline strategy` to group with other byte-sequence ESC fields, matching the plan's prescribed ordering.
- `buffer_bytes` placed at the end of the dataclass (after `columns`) per plan instruction — keeps it grouped with instant-mode-related concerns even though it sits below the byte fields.
- No bold/italic/underline byte values added to any built-in profile (plan explicitly forbids this; Phase 22 owns it). Sentinel test `test_builtin_profiles_have_empty_style_codes_in_phase_21` asserts this and is documented as a regression sentinel that Phase 22 will update or remove.
- Did not edit `load_custom_profiles` (plan 21-02's scope) or add `resolve_style` (plan 21-03's scope). The docstring's forward-reference to `resolve_style` is intentional — plan 21-03 lands the helper.

## Deviations from Plan

None - plan executed exactly as written.

The optional Task 1 step 3 (per-profile buffer_bytes overrides) was applied with the exact values listed in the plan (Juki=64, Citizen=128, others=256). This is plan-permitted, not a deviation.

## Issues Encountered

None.

## Next Phase Readiness

- **Plan 21-02 (custom-TOML loader)** is unblocked. The `load_custom_profiles` function in profiles.py now needs to learn the new field names (`bold_on`, `bold_off`, `italic_on`, `italic_off`, `underline_on`, `underline_off` as hex strings → bytes via `bytes.fromhex`, and `buffer_bytes` as int → int with default 256). Existing CR+LF and end_of_response_sequence patterns are the model.
- **Plan 21-03 (resolve_style helper)** is unblocked. The dataclass shape and the documented fallback chain in the module docstring are the contract; the helper just operationalises it.
- **Phase 22 (encode style bytes for built-ins)** is unblocked. The dataclass slots are ready; Phase 22 fills in `init_sequence`-style byte values per family (Epson ESC E/F for italic, ESC E/F for bold; PCL `\x1b(s3B`/`\x1b(s0B`; PPDS DC4/DC2; Juki/OKI/Citizen left empty unless documented). The `test_builtin_profiles_have_empty_style_codes_in_phase_21` sentinel will need to be removed or rewritten in Phase 22.
- **Phase 26 (instant-mode chunker)** is unblocked. The chunker reads `profile.buffer_bytes` directly (data-driven, no conditional code per printer family). Real-hardware validation of the chosen values (Juki=64, Citizen=128, others=256) is still flagged as a STATE.md concern.

## Self-Check: PASSED

Verified all claims:

- `src/claude_teletype/profiles.py` exists and contains all 6 style fields, buffer_bytes default 256, and "fallback chain" docstring text — confirmed via grep
- `tests/test_profiles.py` exists and contains all 5 new test names — confirmed via grep
- Commit `7b05512` exists in `git log` — confirmed
- Commit `11c3de2` exists in `git log` — confirmed
- `uv run pytest -x` returns 509 passed (baseline preserved, 5 new tests included)

---
*Phase: 21-profile-capability-fields-custom-toml-support*
*Plan: 01*
*Completed: 2026-04-28*
