# Phase 27: Refactor — Package Split, Registry & Detection Seam - Context

**Gathered:** 2026-06-12
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous) — infrastructure phase, minimal context

<domain>
## Phase Boundary

A reorganized, lower-debt codebase whose registry and detection seams are ready to absorb the printer fleet, with the untracked codepage work now first-class and tested. Covers REF-01..06 (package split via move-with-shim, ProfileRegistry, device-by-identity selection, discovery sentinel split, cli.py dedup, code-review pass), DET-02 (Classification model), and DIR-01 (codepage formalization). NO new printer profiles, NO new detection data, NO packaging — those are Phases 28-30.

</domain>

<decisions>
## Implementation Decisions

### Multi-Printer Selection Scope (open question from roadmap)
- REF-03 fixes the device-index bug via select-by-identity (VID:PID + bus/address or serial when available) — `create_driver_for_selection()` must reconnect to the SAME device the user picked, not first-of-class.
- Full multi-printer selection UX (choosing among several simultaneously-connected printers in the setup screen) is DEFERRED — the setup screen already lists devices; this phase only guarantees the selected one is the one driven.

### Refactor Discipline (from research, locked)
- Move-with-shim, three separately-green steps: (1) move modules + leave re-export shims at old paths, (2) repoint internal imports, (3) migrate test imports mechanically. Full suite green after EACH step.
- Refactor stays isolated from behavior changes — no feature work in this phase beyond DIR-01 test/TOML formalization of already-shipped codepage code.
- Test patch targets: tests patch at source-module paths; when modules move, patch strings must move in the same commit as the test-import migration step.

### Claude's Discretion
All remaining implementation choices (exact sub-package boundaries, shim style, registry API shape, Classification enum vs dataclass, review-finding triage) are at Claude's discretion — pure infrastructure phase. Use ROADMAP success criteria, research/ARCHITECTURE.md recommendations, and codebase conventions.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `profiles.py` — frozen PrinterProfile dataclass, BUILTIN_PROFILES dict, resolve_style, load_custom_profiles (three TOML decoding conventions), USB auto-detect; codepage_command/text_codec/text_fallback fields already exist (untracked work, commits d70aded/7ccdff5)
- `printer.py` — 5 drivers on PrinterDriver Protocol (write/write_bytes), discovery dataclasses, create_driver_for_selection factory, chunk_writes
- 700-test suite, 29 test files, all absolute imports `from claude_teletype.X import Y`

### Established Patterns
- Import-locally + patch-at-source-module test convention for cli.py helpers
- dataclasses.replace for profile aliasing; empty bytes sentinel for absent capability
- CR+LF+reinit atomic USB transfer must not be disturbed

### Integration Points
- Target layout (research/ARCHITECTURE.md): `printing/` (drivers, discovery, profiles, catalog/), `rendering/` (markdown, wordwrap), `screens/` (5 screen modules); cli.py/tui.py stay top-level
- ProfileRegistry consumed by Phase 28 detection and Phase 29 catalog
- Classification (NATIVE_PRINTER/BRIDGE/UNKNOWN) seam consumed by Phase 28

</code_context>

<specifics>
## Specific Ideas

- `discovery=None` sentinel: replace with explicit types (e.g. a SetupDecision enum or distinct sentinel objects) so saved-match skip and device-override skip are distinguishable.
- REF-06 code review: run gsd-code-review across changed surface; fix findings inline where safe, file the rest as todos.

</specifics>

<deferred>
## Deferred Ideas

- Full multi-printer selection UX (multiple simultaneously-connected printers as first-class flow) — revisit after v1.6 fleet detection lands.

</deferred>
