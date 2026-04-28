---
gsd_state_version: 1.0
milestone: v1.5
milestone_name: Markdown File Printing
status: in-progress
stopped_at: Completed 23-03-PLAN.md (Inline emphasis state machine; MD-01 + MD-07 closed; Phase 23 complete — MD-01..MD-08 all green)
last_updated: "2026-04-28T20:59:56Z"
last_activity: 2026-04-28 -- 23-03 landed (inline emphasis bold/italic state machine; 17 new tests; MD-01 closed; Phase 23 complete)
progress:
  total_phases: 9
  completed_phases: 3
  total_plans: 9
  completed_plans: 8
  percent: 89
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-28)

**Core value:** The physical typewriter experience -- characters appearing on paper one at a time with authentic pacing and sound, making AI conversation feel tangible and mechanical.
**Current focus:** Phase 23 — Streaming Markdown Renderer — **COMPLETE** (3/3 plans)

## Current Position

Phase: 23 — Streaming Markdown Renderer — **COMPLETE** (3/3 plans)
Plan: Phase 24 next (TUI file picker — markdown renderer is now ready as a downstream consumer)
Status: Phase 23 closed. MD-01..MD-08 all satisfied. MarkdownRenderer fully tested through real WordWrapper(80) + real escp profile (39 markdown tests, 605 project tests, all green).
Last activity: 2026-04-28 -- 23-03 landed (inline emphasis bold/italic state machine; 17 new tests; MD-01 closed; Phase 23 complete)

## Performance Metrics

**Velocity:**

- Total plans completed: 38
- Average duration: 3.3min
- Total execution time: 2.2 hours

**Recent plan metrics:**

| Plan | Duration | Tasks | Files | Completed |
|------|----------|-------|-------|-----------|
| 21-03 | 2.3min | 2 | 2 | 2026-04-28 |
| 22-01 | 4.0min | 3 | 2 | 2026-04-28 |
| 23-01 | 2.5min | 2 | 2 | 2026-04-28 |
| 23-02 | 5.1min | 2 | 2 | 2026-04-28 |
| 23-03 | 4.1min | 2 | 2 | 2026-04-28 |

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

Decisions added in 23-01:

- write_bytes is a public Protocol method (not an adapter wrapper). Keeps the dual-channel seam visible at the type-checker layer so renderer code accepts any `PrinterDriver` and the Protocol enforces the contract. Adapter approach would have hidden the seam behind a wrapper class and complicated downstream injection.
- ProfilePrinterDriver.write_bytes empty-bytes guard fires BEFORE _ensure_init(). `write_bytes(b"")` is a true no-op that does not initialize the printer — protects against the renderer's `resolve_style` returning `(b"", b"")` and accidentally booting hardware on every plain-text run.
- MD-08 boundary held in two places: (1) docstring on ProfilePrinterDriver.write_bytes telling renderer to use write('\n') for newlines, (2) `test_write_bytes_does_not_handle_newlines_specially` asserting `b'\n'` passes through verbatim (no CR+LF, no reinit). The contract is owned by the caller — write_bytes will not silently rescue a misuse.
- CupsPrinterDriver.write_bytes appends the decoded chunk as a single list element (not character-by-character). Preserves the atomicity hint and matches `_flush_line()`'s `"".join()` pattern. Verified by `test_cups_driver_write_bytes_buffers_until_newline` asserting `b"\x1bEhi\x1bF\n"` reaches `lp` as a single subprocess call.

Decisions added in 23-02:

- Trailing empty line from `text.split("\n")` is dropped at `render()` entry. A document ending with `\n` (POSIX convention) splits to `[..., ""]`; the trailing newline is structural delimitation, not a blank-line paragraph. Without the drop, `# Hello\n` would render `\nHello\n\n\n` instead of the spec `\nHello\n\n`. Discovered while writing Task 2's hand-checkable expected strings — landed as a Rule-1 fix commit between Task 1 (feat) and Task 2 (test).
- Tables render eagerly in `render()` via 2-line look-ahead (header `|` + delimiter `|---|`). Clearer than the alternative flush-time validation; keeps `_dispatch_block_line` free of table state. `_flush_table` kept as a no-op stub for a future streaming-mode renderer that can't peek.
- Code-block 4-space leading indent is intentionally NOT preserved through WordWrapper. WordWrapper's canonical leading-space-at-column-0 rule (`test_leading_space_dropped`) strips them. Code content survives, but visual indent is lost in the wrap stage. This is documented in the MD-07 integration test rather than fixed in WordWrapper (changing WordWrapper would break its existing contract).
- `_render_inline` is a separate method emitting chars verbatim through `text_output_fn`. Plan 23-03 swaps just the method body; the 5 call sites (heading text, ulist content, olist content, blockquote content, paragraph content) inherit the inline-emphasis upgrade automatically. `_handle_code_line` deliberately bypasses `_render_inline` (MD-04: literal pass-through inside fences).
- `style_output_fn` defaults to a no-op lambda. Lets the renderer be unit-tested without a profile/driver — every block test in TestHeadings/TestLists/etc passes only `text_output_fn`. The MD-08 negative test exercises the style channel explicitly to assert no newline byte ever leaks into it.

Decisions added in 23-03:

- Heading wraps inline span in an OUTER bold pair via direct `_emit_style_on/off("bold")` calls — independent of inline `_bold_open` state. `_close_open_styles` closes inner spans BEFORE the outer `_emit_style_off("bold")` so the LIFO order is natural. `# **Inner**` produces 2 bold-on / 2 bold-off pairs (outer + inner) — symmetry verified by `test_emphasis_in_heading_pairs_correctly`.
- Greedy two-then-one tokenization for emphasis markers in `_render_inline`: `**`/`__` checked before `*`/`_`. `***foo***` parses as bold-on, italic-on, foo, italic-off, bold-off (4 emits); no special-cased triple-marker token needed.
- Markdown emphasis markers are state-machine tokens, NOT text. The `*`/`_` characters are consumed by the toggle path and never reach `text_output_fn`. Pure-paragraph tests assert `text.count('*') == 0 and text.count('_') == 0` after rendering.
- `_close_open_styles()` invoked from 7 sites: heading (close-before-outer-bold-off), ulist, olist, blockquote, paragraph, code-block-enter (defensive — emphasis is suppressed inside code fences per MD-04), end-of-render (defensive close for unclosed `**hello`). Italic closes BEFORE bold to mirror the natural LIFO open order for nested `**outer *inner* outer**` spans.
- `resolve_style` consulted at every emit; `(b"", b"")` returns silently no-op via `if on:` / `if off:` guards — text falls back to plain without renderer-side branching. `_profile is None` short-circuit makes the renderer unit-testable without a profile.

### Pending Todos

None — phase planning starts at Phase 21.

### Blockers/Concerns

- Juki 9100 control codes still extrapolated from 6100 (carried over from v1.4) — Phase 22 left Juki bold/italic intentionally empty (CAP-05 conservative-default rule), so the carry-forward concern shrinks to "underline ESC -1/-0 should be exercised on real hardware before claiming Juki underline works end-to-end". 23-03 wires the fallback chain end-to-end (juki bold/italic → underline ESC -1/-0 verified by TestStyleFallback) — the on-hardware verification of underline itself remains the open item.
- Phase 22 left intentionally-empty cells for OKI italic (ESC! mode-bit composite varies by firmware revision) and all three Citizen italics (thermal receipt does not support italic). Documented in 22-CONTEXT.md Deferred Ideas.
- Phase 23 narrow-columns: 23-02's `test_table_fits_within_columns` proves the renderer won't crash on Citizen 42-col thermal — but cells get truncated rather than wrapped. Acceptable for v1; in-cell wrap is in `<deferred>`. Closed.
- Phase 23 code-block visual indent: WordWrapper strips the renderer's 4-space leading indent on code-block lines. Content survives, indent doesn't. Out of scope for v1.5; a renderer-aware tab/non-space prefix could fix it later. 23-03's TestIntegration documents this nuance via the `code with *no italic*` substring assertion (no leading-space prefix asserted).
- Phase 26: per-profile `buffer_bytes` defaults need real-hardware validation for at least Juki and Epson before instant mode can be trusted.

## Session Continuity

Last session: 2026-04-28T20:59:56Z
Stopped at: Completed 23-03-PLAN.md (Inline emphasis state machine; MD-01 + MD-07 closed; Phase 23 complete — MD-01..MD-08 all green)
Resume file: None
Next action: Execute Phase 24 (TUI file picker — markdown renderer is now ready as a downstream consumer; integrates with WordWrapper(80) + ProfilePrinterDriver via the dual-channel `text_output_fn`/`style_output_fn` interface)
