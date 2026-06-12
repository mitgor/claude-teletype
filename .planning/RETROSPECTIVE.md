# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.5 — Markdown File Printing

**Shipped:** 2026-04-28 (archived 2026-06-12)
**Phases:** 6 (21–26) | **Plans:** 14 | **Tasks:** 28

### What Was Built
- Streaming markdown renderer (headings, lists, fenced code, blockquotes, GFM tables, inline emphasis) with a dual text/style channel composing with `WordWrapper` and the atomic CR+LF+reinit newline path
- `PrinterProfile` style capability fields + `resolve_style` fallback chain, with verified ESC sequences for all six built-in profile families and custom-TOML support
- TUI file picker (`ctrl+o`) and `claude-teletype print [path]` CLI subcommand (explicit path or picker mode)
- Per-print speed dialog, `buffer_bytes` instant-mode chunking, cancel-safe `renderer.close()`, transcript integration

### What Worked
- Data-first phase ordering (21 fields → 22 encodings → 23 renderer → 24/25 entries → 26 integration) meant every phase consumed locked contracts from the previous one — zero rework across 14 plans
- "Encoding-table-as-contract" for Phase 22: byte literals copied verbatim from published manuals with a conservative leave-empty rule prevented fabricated codes
- Locked-contract handoffs between plans (e.g. Phase 24's `notify()` stub explicitly designed for Phase 26 to replace only the method body) kept phases independently mergeable
- TDD RED→GREEN gates proven explicitly in Phase 26 (failing-import / failing-kwarg evidence before implementation)
- Hand-checkable expected-string tests for the renderer caught the trailing-newline paragraph bug during test authoring

### What Was Inefficient
- Milestone closed 6 weeks after the work shipped (2026-04-28 work, 2026-06-12 archive) — STATE.md and MILESTONES.md lagged reality
- Post-v1.5 codepage/transliteration work (4 commits) landed entirely outside GSD tracking — no requirements, no phase artifacts, now needs back-filling
- Phase 22's `human_needed` verification (real-hardware style testing) has no owner or schedule — deferred without a closing mechanism

### Patterns Established
- Dual-channel driver API: `write()` for text/newlines (CR+LF+reinit), `write_bytes()` for style ESC codes (verbatim pass-through) — MD-08 boundary
- `resolve_style` free-function fallback chain with empty-bytes capability sentinel; underline as terminal fallback node
- `_make_*_app()` closure factory + `App._exit_code` idiom for one-shot Textual launchers
- Paired `action_<name>` + `_handle_<name>_result` for all push_screen+callback flows
- Import-locally + patch-at-source-module test convention for cli.py helpers
- Promote-private-helper-to-public-API via thin 1:1 delegation (`close()` → `_close_open_styles`)

### Key Lessons
1. Lock the downstream contract in the upstream plan (method name, argument shape, refocus pattern) — Phase 26 replaced Phase 24's stub body without touching a single test from Phase 24
2. When encoding hardware byte sequences, "verbatim from the manual or empty" beats interpolation — empty bytes degrade gracefully through the fallback chain; wrong bytes print garbage
3. Close milestones promptly — the 6-week gap let untracked work accumulate and stale state mislead tooling
4. Hardware-dependent verification items need an explicit owner/next-step at close, or they silently roll forward forever

### Cost Observations
- Execution: ~3hr wall-clock for 14 plans (avg ~5min/plan, up from 3.4min project average — TDD gates and Pilot tests add overhead)
- Tests: 479 → 700 (+221) with zero regressions across the milestone

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0–v1.2 | 15 | 28 | Rapid greenfield; conventions forming |
| v1.3 | 2 | 2 | First dedicated debt-cleanup milestone |
| v1.4 | 3 | 6 | Full-screen gate pattern (Screen over ModalScreen) locked |
| v1.5 | 6 | 14 | Locked-contract plan handoffs; explicit TDD RED→GREEN evidence |

### Cumulative Quality

| Milestone | Tests | Source LOC | Test LOC |
|-----------|-------|-----------|----------|
| v1.3 | 430 | 3,381 | 5,709 |
| v1.4 | 479 | 4,646 | 6,510 |
| v1.5 | 700 | 6,647 | 10,201 |

### Top Lessons (Verified Across Milestones)

1. Hardware quirks (CH341 atomic CR+LF, byte-fragility) must be encoded as data/contracts, not conditional code — held since v1.0, extended cleanly in v1.5
2. Frozen-dataclass + `dataclasses.replace` profile aliasing scales: new capability fields in v1.5 propagated to aliases with zero extra encoding
3. Tech-debt items only close when given a dedicated phase (v1.3) or explicit deferral record — untracked debt rolls forward indefinitely
