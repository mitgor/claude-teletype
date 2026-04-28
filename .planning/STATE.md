---
gsd_state_version: 1.0
milestone: v1.5
milestone_name: Markdown File Printing
status: planning
stopped_at: Completed 22-01-PLAN.md (built-in profiles encoded; Phase 22 complete; CAP-04 + CAP-05 satisfied)
last_updated: "2026-04-28T20:19:27Z"
last_activity: 2026-04-28 -- Phase 22 complete (style sequences encoded on built-ins; CAP-04 + CAP-05 satisfied)
progress:
  total_phases: 9
  completed_phases: 3
  total_plans: 5
  completed_plans: 5
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-28)

**Core value:** The physical typewriter experience -- characters appearing on paper one at a time with authentic pacing and sound, making AI conversation feel tangible and mechanical.
**Current focus:** Phase 22 — Encoded Style Sequences for Built-In Profiles — **COMPLETE**

## Current Position

Phase: 22 — Encoded Style Sequences for Built-In Profiles — **COMPLETE**
Plan: Phase 23 next (markdown renderer consuming resolve_style on the now-encoded built-ins)
Status: Phase 22 complete (CAP-04 + CAP-05 satisfied); CAP-01..06 all satisfied; ready for Phase 23 planning
Last activity: 2026-04-28 -- Phase 22 complete (style sequences encoded on built-ins; CAP-04 + CAP-05 satisfied)

## Performance Metrics

**Velocity:**

- Total plans completed: 35
- Average duration: 3.3min
- Total execution time: 2.0 hours

**Recent plan metrics:**

| Plan | Duration | Tasks | Files | Completed |
|------|----------|-------|-------|-----------|
| 21-01 | 2.8min | 2 | 2 | 2026-04-28 |
| 21-02 | 1.8min | 2 | 2 | 2026-04-28 |
| 21-03 | 2.3min | 2 | 2 | 2026-04-28 |
| 22-01 | 4.0min | 3 | 2 | 2026-04-28 |

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

Decisions added in 21-03:

- resolve_style is a free function in profiles.py (not a method on PrinterProfile) — keeps the dataclass purely data and avoids coupling the data shape to fallback logic that may evolve independently. Renderer imports it via `from claude_teletype.profiles import resolve_style`.
- Underline is the terminal node of the fallback chain — bold and italic fall back to underline, but underline does NOT substitute bold or italic. Rationale: underline is universally supported on impact printers; if a printer lacks underline too, the renderer emits plain text rather than fabricating a substitute that may print garbage.
- Italic wins over underline when both are set; bold wins over underline when both are set. The fallback chain only fires when the primary capability is empty — no precedence ambiguity for profile authors who declare both.

Decisions added in 22-01:

- Encoding-table-as-contract: 22-CONTEXT.md's "Encoding sources" table was the authoritative spec. Every byte literal in the planner's action blocks was copied character-for-character into profiles.py — no interpretation, no creative substitution. Fabricated codes would print garbage on real hardware; the conservative-default rule (when unsure, leave empty) was already baked into the table.
- Citizen ESC/POS bold uses BINARY 1/0 in the third byte (`\x1b\x45\x01`/`\x1b\x45\x00`), NOT ASCII '1'/'0'. The `test_citizen_cts2000_bold_codes` docstring flags this gotcha explicitly so future contributors don't "correct" it back to `\x1b\x45\x31`/`\x1b\x45\x30`.
- Removed the Phase 21 sentinel `test_builtin_profiles_have_empty_style_codes_in_phase_21` rather than rewriting it — its stated purpose explicitly anticipated removal once Phase 22 landed. Replacement is strictly stronger: TestStyleCodesPerProfile asserts exact byte literals per cell + paired-symmetry sentinel asserts the structural invariant (non-empty `*_on` implies non-empty `*_off`) closing Phase 21 REVIEW IN-05 carry-forward.
- Aliases (ibm, juki) are NOT separately encoded — they pick up codes through the existing `dataclasses.replace` pattern. Two explicit alias-inheritance tests verify this works after the encoding edit.

### Pending Todos

None — phase planning starts at Phase 21.

### Blockers/Concerns

- Juki 9100 control codes still extrapolated from 6100 (carried over from v1.4) — Phase 22 left Juki bold/italic intentionally empty (CAP-05 conservative-default rule), so the carry-forward concern shrinks to "underline ESC -1/-0 should be exercised on real hardware before claiming Juki underline works end-to-end".
- Phase 22 left intentionally-empty cells for OKI italic (ESC! mode-bit composite varies by firmware revision) and all three Citizen italics (thermal receipt does not support italic). Documented in 22-CONTEXT.md Deferred Ideas.
- Phase 23: ASCII table layout under narrow `profile.columns` (e.g. Citizen 42-col thermal) needs a graceful fallback strategy — degenerate wide tables should not crash the renderer.
- Phase 26: per-profile `buffer_bytes` defaults need real-hardware validation for at least Juki and Epson before instant mode can be trusted.

## Session Continuity

Last session: 2026-04-28T20:19:27Z
Stopped at: Completed 22-01-PLAN.md (built-in profiles encoded; Phase 22 complete; CAP-04 + CAP-05 satisfied)
Resume file: None
Next action: Plan Phase 23 (markdown renderer consuming resolve_style on the now-encoded built-ins)
