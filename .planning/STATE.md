---
gsd_state_version: 1.0
milestone: v1.5
milestone_name: Markdown File Printing
status: executing
stopped_at: Completed 21-02-PLAN.md (custom-TOML loader for new fields)
last_updated: "2026-04-28T19:51:00Z"
last_activity: 2026-04-28 -- Phase 21 Plan 02 complete (custom-TOML loader extended)
progress:
  total_phases: 9
  completed_phases: 0
  total_plans: 3
  completed_plans: 2
  percent: 67
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-28)

**Core value:** The physical typewriter experience -- characters appearing on paper one at a time with authentic pacing and sound, making AI conversation feel tangible and mechanical.
**Current focus:** Phase 21 — Profile Capability Fields & Custom-TOML Support

## Current Position

Phase: 21 — Profile Capability Fields & Custom-TOML Support
Plan: 21-03 (next — resolve_style helper for fallback chain)
Status: 21-02 complete; ready to execute 21-03
Last activity: 2026-04-28 -- Phase 21 Plan 02 complete (custom-TOML loader extended)

## Performance Metrics

**Velocity:**

- Total plans completed: 33
- Average duration: 3.3min
- Total execution time: 1.9 hours

**Recent plan metrics:**

| Plan | Duration | Tasks | Files | Completed |
|------|----------|-------|-------|-----------|
| 21-01 | 2.8min | 2 | 2 | 2026-04-28 |
| 21-02 | 1.8min | 2 | 2 | 2026-04-28 |

**By Milestone:**

| Milestone | Phases | Plans | Duration | Timeline |
|-----------|--------|-------|----------|----------|
| v1.0 MVP | 4 | 8 | 22min | 2026-02-15 |
| v1.1 Conversation Mode | 3 | 7 | 20min | 2026-02-16 → 2026-02-17 |
| v1.2 Config/Profiles/LLM/Settings | 8 | 13 | 57min | 2026-02-14 → 2026-02-17 |
| v1.3 Tech Debt Cleanup | 2 | 2 | 8min | 2026-02-20 |
| v1.4 Printer Setup TUI | 3 | 6 | 15min | 2026-04-03 |
| v1.5 Markdown File Printing | 6 | TBD | — | In progress |

## Accumulated Context

### Decisions

All decisions logged in PROJECT.md Key Decisions table (24 entries).
v1.3 decisions archived in MILESTONES.md.

Carry-forward from v1.4 still in force for v1.5:

- CR+LF+reinit must remain a single atomic USB transfer for newlines (Juki/CH341 drops fragmented LF). The markdown renderer must compose with `ProfilePrinterDriver.write` for `\n` rather than re-implementing the newline path.
- `dataclasses.replace` is the supported way to alias profiles (preserves frozen immutability of `PrinterProfile`).
- Custom-TOML profiles use `bytes.fromhex()` decoding for byte fields and `int(..., 16)` for VID/PID — Phase 21 must mirror this convention for the new `bold_on`/`italic_on`/`underline_on` and integer `buffer_bytes` fields.

Decisions added in 21-01:

- Empty bytes (b"") is the sentinel for absent style capability — the markdown renderer's fallback chain (italic→underline→plain, bold→underline→plain, lands in 21-03) reads that state to decide whether to substitute underline or plain text.
- buffer_bytes default 256 is conservative for unknown hardware; per-profile overrides apply real-world tuning (CH341 byte-fragility=64, thermal=128) without scattering hardware knowledge in conditional code. Applied values: juki-6100=64, juki-2200=64, juki alias inherits 64, citizen-cts2000=128, others=256.
- Style codes (bold/italic/underline) intentionally LEFT EMPTY on every built-in profile in Plan 21-01; Phase 22 encodes verified per-family sequences. Sentinel test `test_builtin_profiles_have_empty_style_codes_in_phase_21` enforces this and will be updated/removed in Phase 22.

Decisions added in 21-02:

- buffer_bytes is a plain int in TOML, NOT a hex string — distinct from usb_vendor_id/usb_product_id which use int(x, 16) because they are USB identifiers. buffer_bytes is a count of bytes, so plain int is the natural type. The loader docstring documents this distinction explicitly so future contributors don't unify the three TOML decoding patterns into one.
- Three TOML decoding conventions coexist cleanly in load_custom_profiles: (1) bytes.fromhex(data.get(KEY, "")) for raw byte sequences with empty default, (2) int(data[KEY], 16) if KEY in data else None for hex-encoded USB IDs with None sentinel, (3) data.get(KEY, default) for plain ints/bools/strings.

### Pending Todos

None — phase planning starts at Phase 21.

### Blockers/Concerns

- Juki 9100 control codes still extrapolated from 6100 (carried over from v1.4) — relevant when Phase 22 fills in Juki style codes.
- Phase 22: bold/italic byte sequences for OKI 3390 (Epson FX-2 mode) and Citizen CT-S2000 (ESC/POS) need verification against published references; sequences left empty if unverified rather than fabricated (CAP-05 explicitly allows this).
- Phase 23: ASCII table layout under narrow `profile.columns` (e.g. Citizen 42-col thermal) needs a graceful fallback strategy — degenerate wide tables should not crash the renderer.
- Phase 26: per-profile `buffer_bytes` defaults need real-hardware validation for at least Juki and Epson before instant mode can be trusted.

## Session Continuity

Last session: 2026-04-28T19:51:00Z
Stopped at: Completed 21-02-PLAN.md (custom-TOML loader for new fields)
Resume file: None
Next action: Execute 21-03-PLAN.md (resolve_style helper for fallback chain)
