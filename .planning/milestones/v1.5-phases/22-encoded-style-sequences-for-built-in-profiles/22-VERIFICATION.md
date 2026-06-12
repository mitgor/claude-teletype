---
phase: 22-encoded-style-sequences-for-built-in-profiles
verified: 2026-04-28T20:30:00Z
status: human_needed
score: 10/10 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Real-hardware verification of Epson ESC/P bold/italic/underline sequences"
    expected: "Bold prints darker, italic prints slanted, underline prints with line under text on a real Epson FX/LQ/LX printer"
    why_human: "Documented codes from the manual match the spec, but only physical hardware confirms the printer accepts them"
  - test: "Real-hardware verification of IBM PPDS bold/italic/underline sequences"
    expected: "Bold/italic/underline render correctly on a real IBM PPDS-compatible printer"
    why_human: "Spec match verified; real Proprinter behavior cannot be verified programmatically"
  - test: "Real-hardware verification of HP PCL bold/italic/underline sequences"
    expected: "Bold/italic/underline render correctly on a real HP LaserJet/DeskJet/OfficeJet printer"
    why_human: "PCL 5 Comparison Guide codes match the source; real LaserJet behavior needs hardware"
  - test: "Real-hardware verification of OKI Microline 3390 bold + underline (Epson FX-2 mode)"
    expected: "Bold and underline print correctly on a real OKI ML 3390 with the front-panel emulation set to Epson FX-2"
    why_human: "ML 3390 emulation menu must be set to Epson FX-2 — verifying this requires the physical printer"
  - test: "Real-hardware verification of Citizen CT-S2000 ESC/POS bold + underline"
    expected: "Bold (ESC E 1, binary 1) and underline (ESC - 1, binary 1) render correctly on a real Citizen CT-S2000 thermal receipt printer"
    why_human: "ESC/POS bold uses BINARY 1/0 (not ASCII '1'/'0') — only the physical printer confirms the byte interpretation is correct"
  - test: "Real-hardware verification of Juki 6100/2200 underline (ESC -1/-0)"
    expected: "Underline prints correctly on a real Juki 6100 daisywheel; bold and italic correctly absent"
    why_human: "Juki 6100/2200 control codes are extrapolated from the 6100 Programmer's Reference (per PROJECT.md note 'Juki 9100 control codes extrapolated from 6100 (need hardware verification)')"
---

# Phase 22: Encoded Style Sequences for Built-In Profiles Verification Report

**Phase Goal:** Each built-in profile ships with bold/italic/underline byte sequences that real hardware accepts; intentionally-empty cells stay empty.
**Verified:** 2026-04-28T20:30:00Z
**Status:** human_needed (all automated checks pass; real-hardware verification deferred per CONTEXT.md "Deferred Ideas")
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth                                                                                                                              | Status     | Evidence                                                                                                  |
| --- | ---------------------------------------------------------------------------------------------------------------------------------- | ---------- | --------------------------------------------------------------------------------------------------------- |
| 1   | Epson ESC/P profile (escp) emits bold/italic/underline ESC sequences from the Epson manual                                          | ✓ VERIFIED | profiles.py:136-141 — bold ESC E/F, italic ESC 4/5, underline ESC -1/-0 all match table                    |
| 2   | IBM PPDS profile (ppds, alias ibm) emits bold/italic/underline ESC sequences                                                        | ✓ VERIFIED | profiles.py:154-159 — bold ESC E/F, italic ESC %G/%H, underline ESC -1/-0; alias inheritance verified      |
| 3   | HP PCL profile (pcl) emits bold/italic/underline ESC sequences from PCL 5 Comparison Guide                                          | ✓ VERIFIED | profiles.py:171-176 — bold ESC(s3B/0B, italic ESC(s1S/0S, underline ESC&dD/&d@ all match table             |
| 4   | Juki 6100/2200 emit underline only — bold and italic stay empty                                                                    | ✓ VERIFIED | profiles.py:101-102, 122-123 — underline encoded; bold and italic remain at b"" defaults                  |
| 5   | OKI Microline 3390 emits bold and underline; italic stays empty                                                                    | ✓ VERIFIED | profiles.py:197-200 — bold ESC E/F + underline ESC -1/-0; italic_on/off remain at b"" defaults             |
| 6   | Citizen CT-S2000 emits bold and underline ESC/POS sequences with BINARY 1/0 (not ASCII)                                            | ✓ VERIFIED | profiles.py:217-220 — `bold_on=b"\x1bE\x01"` confirms binary byte; underline ESC -1/-0 present             |
| 7   | Generic profile leaves every style field empty                                                                                     | ✓ VERIFIED | profiles.py:88-91 — only name + description constructor args; all 6 style fields stay at b"" default      |
| 8   | Every non-empty *_on has a non-empty *_off (REVIEW IN-05 carry-forward)                                                            | ✓ VERIFIED | test_builtin_profiles_paired_style_symmetry passes; 0 orphaned codes; runtime check exits 0               |
| 9   | juki and ibm aliases inherit newly-encoded codes via dataclasses.replace (no separate encoding)                                    | ✓ VERIFIED | profiles.py:240-252 (replace blocks unchanged); runtime: ibm.bold_on == ppds.bold_on, juki.underline_on == juki-6100.underline_on |
| 10  | All pre-existing tests still pass; Phase 21 sentinel removed                                                                       | ✓ VERIFIED | `uv run pytest -x` → 554 passed, 0 regressions; sentinel grep count = 0                                   |

**Score:** 10/10 truths verified

### Required Artifacts

| Artifact                              | Expected                                                                  | Status     | Details                                                                                                |
| ------------------------------------- | ------------------------------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------ |
| `src/claude_teletype/profiles.py`     | BUILTIN_PROFILES dict with verified style byte sequences encoded          | ✓ VERIFIED | 471 lines; `bold_on=b"\x1bE"` and other plan-specified literals all present; aliases unchanged         |
| `tests/test_profiles.py`              | TestStyleCodesPerProfile + per-profile assertions + paired-symmetry test  | ✓ VERIFIED | TestStyleCodesPerProfile class present (line 655); test_builtin_profiles_paired_style_symmetry (line 819) |

### Key Link Verification

| From                                          | To                                                              | Via                                          | Status   | Details                                                  |
| --------------------------------------------- | --------------------------------------------------------------- | -------------------------------------------- | -------- | -------------------------------------------------------- |
| BUILTIN_PROFILES["escp"]                      | PrinterProfile.bold_on / italic_on / underline_on slots          | constructor keyword arguments                | ✓ WIRED  | `bold_on=b"\x1bE"` literal at profiles.py:136            |
| BUILTIN_PROFILES["juki"]                      | BUILTIN_PROFILES["juki-6100"]                                    | dataclasses.replace alias pattern            | ✓ WIRED  | profiles.py:248-252 unchanged; runtime check confirms inheritance |
| paired-symmetry test                          | every entry in BUILTIN_PROFILES                                  | iterate built-ins, check on→off symmetry      | ✓ WIRED  | tests/test_profiles.py:838 iterates BUILTIN_PROFILES.items(); both directions asserted |
| BUILTIN_PROFILES["ibm"]                       | BUILTIN_PROFILES["ppds"]                                         | dataclasses.replace alias pattern            | ✓ WIRED  | profiles.py:240-244 unchanged; ibm.bold_on == ppds.bold_on at runtime |

### Data-Flow Trace (Level 4)

| Artifact     | Data Variable        | Source                                  | Produces Real Data | Status      |
| ------------ | -------------------- | --------------------------------------- | ------------------ | ----------- |
| profiles.py  | BUILTIN_PROFILES dict | Module-level literal initialization     | Yes — verified per-cell against the encoding table | ✓ FLOWING   |
| resolve_style | profile.bold_on/etc  | Reads frozen-dataclass fields populated above | Yes — `resolve_style(get_profile('escp'), 'italic')` returns `(b'\x1b4', b'\x1b5')` (real codes, not empty) | ✓ FLOWING   |

### Behavioral Spot-Checks

| Behavior                                             | Command                                                                              | Result                            | Status |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------ | --------------------------------- | ------ |
| Encoding table matches profiles.py cell-by-cell      | python loop over expected dict comparing each profile field to literal              | 0 mismatches across 48 cells      | ✓ PASS |
| Phase 21 sentinel removed                            | `grep -c 'test_builtin_profiles_have_empty_style_codes_in_phase_21' tests/test_profiles.py` | 0                              | ✓ PASS |
| Aliases inherit newly-encoded codes                  | runtime assertion ibm.bold_on == ppds.bold_on, juki.underline_on == juki-6100        | both equal                        | ✓ PASS |
| Full pytest suite (554 tests)                        | `uv run pytest -x`                                                                   | 554 passed in 10.42s              | ✓ PASS |
| resolve_style returns real codes for escp italic     | `resolve_style(get_profile('escp'), 'italic')`                                       | `(b'\x1b4', b'\x1b5')`            | ✓ PASS |
| resolve_style fallback works for juki-6100 bold      | `resolve_style(get_profile('juki-6100'), 'bold')`                                    | `(b'\x1b-\x01', b'\x1b-\x00')` (underline fallback) | ✓ PASS |
| resolve_style returns plain for generic              | `resolve_style(get_profile('generic'), 'bold')`                                      | `(b'', b'')`                      | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description                                                                                                  | Status      | Evidence                                                                                          |
| ----------- | ----------- | ------------------------------------------------------------------------------------------------------------ | ----------- | ------------------------------------------------------------------------------------------------- |
| CAP-04      | 22-01       | Built-in Epson ESC/P, IBM PPDS, HP PCL profiles ship with verified bold and italic sequences encoded         | ✓ SATISFIED | escp/ppds/pcl bold + italic encoded per spec; per-profile + alias-inheritance tests pass          |
| CAP-05      | 22-01       | Built-in Juki, OKI, Citizen profiles ship documented bold sequences; absent capabilities left as empty bytes | ✓ SATISFIED | juki = none (overstrike not streamable, no italic daisywheel); oki = ESC E/F; citizen = ESC E 1/0; intentionally-empty cells documented by negative assertions |

### Anti-Patterns Found

None. Files modified:
- `src/claude_teletype/profiles.py` — only data-value populations on existing keyword arguments; no TODO/FIXME/placeholder/stub patterns; no hardcoded empty values flowing to rendering (the b"" cells are intentional CAP-05 deferrals documented by negative tests).
- `tests/test_profiles.py` — only test additions and one removal; no skipped tests, no `pytest.skip`, no console.log patterns.

### Human Verification Required

The phase implementation is complete and all programmatic checks pass. The remaining concerns are real-hardware verification of the documented ESC sequences. Per 22-CONTEXT.md "Deferred Ideas", hardware verification is explicitly out of scope for this phase ("this phase encodes documented codes from manuals; hardware verification is a separate concern"). These are documented for future hardware-access opportunities and do NOT block phase completion.

1. **Real-hardware Epson ESC/P** — Print `**bold**`, `*italic*`, `__underline__` markdown via Phase 23 renderer to a real Epson FX/LQ/LX printer; expect bold/italic/underline glyphs.
2. **Real-hardware IBM PPDS** — Same test on a real Proprinter-compatible printer.
3. **Real-hardware HP PCL** — Same test on a real HP LaserJet.
4. **Real-hardware OKI ML 3390** — Set front-panel emulation to Epson FX-2; verify bold + underline render; italic correctly falls back to underline (not plain).
5. **Real-hardware Citizen CT-S2000** — Verify ESC E 1/0 (binary) bold and ESC - 1/0 underline on thermal receipt; italic correctly falls back to underline.
6. **Real-hardware Juki 6100 + Juki 2200** — Verify underline renders; bold and italic correctly fall back to underline (italic→underline→plain chain).

### Gaps Summary

No gaps. Every cell of the 22-CONTEXT.md "Encoding sources" table is reflected byte-for-byte in BUILTIN_PROFILES (48/48 cells verified — 8 profiles × 6 style fields). Every "leave empty" / "NOT SUPPORTED" cell is `b""` per the conservative-default rule. Aliases inherit through the unchanged `dataclasses.replace` blocks. The Phase 21 regression sentinel `test_builtin_profiles_have_empty_style_codes_in_phase_21` is gone (grep count = 0). The new TestStyleCodesPerProfile class adds 24 cell-level assertions, and `test_builtin_profiles_paired_style_symmetry` enforces the REVIEW IN-05 carry-forward invariant in both directions. Full pytest suite is green at 554 passed, zero regressions.

The only outstanding work is real-hardware verification of the documented ESC sequences, which 22-CONTEXT.md explicitly defers as a separate concern outside Phase 22's profile-data scope.

---

_Verified: 2026-04-28T20:30:00Z_
_Verifier: Claude (gsd-verifier)_
