# Phase 22: Encoded Style Sequences for Built-In Profiles - Context

**Gathered:** 2026-04-28
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss=true; autonomous run)

<domain>
## Phase Boundary

Each built-in profile ships with the bold/italic/underline byte sequences that real hardware actually accepts, so users on Epson, IBM PPDS, HP PCL, Juki, OKI, and Citizen printers see styled output without writing custom-TOML.

Covers: CAP-04 (verified bold and italic for Epson ESC/P, IBM PPDS, HP PCL) and CAP-05 (Juki, OKI, Citizen — encode where documented, leave empty where unverified).

</domain>

<decisions>
## Implementation Decisions

### Code targets
- All edits land in `src/claude_teletype/profiles.py` BUILTIN_PROFILES dict — no new files, no new functions
- Each profile gets bold_on/bold_off/italic_on/italic_off/underline_on/underline_off bytes filled with verified ESC sequences from the printer's manual / family standard
- Where a printer family does NOT support a capability (e.g. Juki daisywheel italic), leave the field as the dataclass default `b""` — the resolve_style helper from Phase 21 will fall back to underline → plain
- Tests in `tests/test_profiles.py` add a per-profile assertion for each newly-encoded capability (e.g. `test_escp_has_bold_codes`, `test_juki_lacks_italic`) plus the regression sentinel `test_builtin_profiles_have_empty_style_codes_in_phase_21` MUST be REMOVED or REPLACED in this phase

### Encoding sources (canonical references)
- **Epson ESC/P** (profile name `escp`): Bold = `ESC E` (\x1bE) / Bold off = `ESC F` (\x1bF). Italic = `ESC 4` (\x1b4) / Italic off = `ESC 5` (\x1b5). Underline = `ESC -1` (\x1b-\x01) / Underline off = `ESC -0` (\x1b-\x00). Source: Epson ESC/P Reference Manual.
- **IBM PPDS** (profile name `ppds`, alias `ibm`): Bold = `ESC E` (\x1bE) / Bold off = `ESC F` (\x1bF). Italic = `ESC %G` (\x1b%G) / Italic off = `ESC %H` (\x1b%H). Underline = `ESC -1` (\x1b-\x01) / Underline off = `ESC -0` (\x1b-\x00). Source: IBM Personal Printer Data Stream documentation.
- **HP PCL** (profile name `pcl`): Bold = `ESC(s3B` (\x1b(s3B) / Bold off = `ESC(s0B` (\x1b(s0B). Italic = `ESC(s1S` (\x1b(s1S) / Italic off = `ESC(s0S` (\x1b(s0S). Underline = `ESC&dD` (\x1b&dD) / Underline off = `ESC&d@` (\x1b&d@). Source: HP PCL 5 Comparison Guide.
- **Juki 6100/9100** (profile names `juki-6100`, alias `juki`): Daisywheel impact — Bold via overstrike is not a one-shot ESC sequence (it requires duplicate-strike per char and breaks the streaming pipeline), so leave bold_on/off empty. Underline = `ESC -1` (\x1b-\x01) / Underline off = `ESC -0` (\x1b-\x00). Italic = NOT SUPPORTED (no italic daisywheel installed) — leave empty. Source: Juki 6100 Programmer's Reference; daisywheel mechanical limitations.
- **Juki 2200** (profile name `juki-2200`): Same as 6100 — underline only.
- **OKI Microline 3390** (profile name `oki-3390`): Microline command set is a superset of Epson ESC/P. Bold = `ESC E` (\x1bE) / Bold off = `ESC F` (\x1bF). Italic = `ESC !` with mode bit (variable; conservative path is to leave italic empty). Underline = `ESC -1` (\x1b-\x01) / Underline off = `ESC -0` (\x1b-\x00). Source: OKI Programmer's Reference Manual.
- **Citizen CTS-2000** (profile name `citizen-cts2000`): Thermal receipt printer using ESC/POS subset. Bold = `ESC E1` (\x1b\x451) / Bold off = `ESC E0` (\x1b\x450). Italic = NOT SUPPORTED on thermal receipt. Underline = `ESC -1` (\x1b-\x01) / Underline off = `ESC -0` (\x1b-\x00). Source: ESC/POS specification.
- **Generic** (`generic`): No ESC sequences. Leave all style fields empty — generic profile is the "no styling" baseline.

### Conservative default rule
When unsure about a sequence, leave it empty rather than fabricate. The fallback chain handles missing capabilities gracefully (italic → underline → plain). The 21-REVIEW IN-05 finding (style_on without style_off would leak modes) becomes ESPECIALLY important here — every encoded *_on field MUST be paired with a non-empty *_off field.

### Test strategy
- Per-profile assertions: confirm exact byte sequences encoded for each verified capability
- Negative assertions: confirm intentionally-unsupported capabilities (Juki italic, Citizen italic, generic everything) ARE empty bytes — these are not "missing" tests, they document the CAP-05 deferral pattern
- Round-trip: confirm resolve_style returns the encoded bytes for the right capability and falls back correctly when capability is empty
- Regression-removal: the sentinel `test_builtin_profiles_have_empty_style_codes_in_phase_21` from Phase 21 is REMOVED in this phase (its job was to prevent encoding before Phase 22 — that gate is now lifted)

### Claude's Discretion
- Exact test class layout (one TestStyleCodesPerProfile vs one test per family)
- Whether to verify by hardcoded byte literals or by parametrized table
- Plan count (1 plan vs split per-family) — recommend single plan since BUILTIN_PROFILES edits are small and tightly coupled

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project files
- `src/claude_teletype/profiles.py` — BUILTIN_PROFILES dict at line ~63 onward; PrinterProfile fields landed in Phase 21
- `tests/test_profiles.py` — TestStyleCodes patterns from Phase 21 to mirror; the regression sentinel to remove
- `.planning/REQUIREMENTS.md` — CAP-04, CAP-05 definitions
- `.planning/PROJECT.md` — frozen-dataclass decision, ProfilePrinterDriver standalone constraint
- `.planning/phases/21-profile-capability-fields-custom-toml-support/21-01-SUMMARY.md` — fields landed in Phase 21
- `.planning/phases/21-profile-capability-fields-custom-toml-support/21-03-SUMMARY.md` — resolve_style helper landed in Phase 21

</canonical_refs>

<specifics>
## Specific Ideas

The encoding table above (under "Encoding sources") is the contract. Every cell of that table that has a non-empty value MUST be encoded; every cell explicitly marked "NOT SUPPORTED" or "leave empty" MUST stay empty. Plans should include a parametrized test that walks the table cell-by-cell.

</specifics>

<deferred>
## Deferred Ideas

- ESC! mode-bit composite styling for OKI (italic): too vendor-specific to verify without hardware; revisit if user reports italic missing on OKI
- Bold-via-overstrike for Juki daisywheel: would require pipeline changes (duplicate writes per char) — outside Phase 22's profile-data scope
- Verifying every sequence on real hardware: this phase encodes documented codes from manuals; hardware verification is a separate concern (see PROJECT.md "Juki 9100 control codes extrapolated from 6100 (need hardware verification)")

</deferred>

---

*Phase: 22-encoded-style-sequences-for-built-in-profiles*
*Context auto-generated 2026-04-28 (autonomous run, skip_discuss=true)*
