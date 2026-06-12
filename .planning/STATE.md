---
gsd_state_version: 1.0
milestone: v1.6
milestone_name: Printer Fleet & Standalone
status: executing
stopped_at: v1.6 roadmap created (Phases 27-30)
last_updated: "2026-06-12T18:39:58.821Z"
last_activity: 2026-06-12 -- Phase 27 execution started
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 6
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-12)

**Core value:** The physical typewriter experience -- characters appearing on paper one at a time with authentic pacing and sound, making AI conversation feel tangible and mechanical.
**Current focus:** Phase 27 — Refactor — Package Split, Registry & Detection Seam

## Current Position

Phase: 27 (Refactor — Package Split, Registry & Detection Seam) — EXECUTING
Plan: 1 of 6
Status: Executing Phase 27
Last activity: 2026-06-12 -- Phase 27 execution started

## Performance Metrics

**Velocity:**

- Total plans completed: 42
- Average duration: 3.4min
- Total execution time: 2.5 hours

**By Milestone:**

| Milestone | Phases | Plans | Duration | Timeline |
|-----------|--------|-------|----------|----------|
| v1.0 MVP | 4 | 8 | 22min | 2026-02-15 |
| v1.1 Conversation Mode | 3 | 7 | 20min | 2026-02-16 → 2026-02-17 |
| v1.2 Config/Profiles/LLM/Settings | 8 | 13 | 57min | 2026-02-14 → 2026-02-17 |
| v1.3 Tech Debt Cleanup | 2 | 2 | 8min | 2026-02-20 |
| v1.4 Printer Setup TUI | 3 | 6 | 15min | 2026-04-03 |
| v1.5 Markdown File Printing | 6 | 14 | ~3hr | 2026-04-28 (shipped) |

## Accumulated Context

### Decisions

All decisions logged in PROJECT.md Key Decisions table.
v1.5 plan-level decisions archived in phase SUMMARY.md files (`.planning/phases/21-*` … `26-*`) and MILESTONES.md.

Carry-forward still in force:

- CR+LF+reinit must remain a single atomic USB transfer for newlines (Juki/CH341 drops fragmented LF). Any renderer/output path must compose with `ProfilePrinterDriver.write` for `\n` rather than re-implementing the newline path.
- `dataclasses.replace` is the supported way to alias profiles (preserves frozen immutability of `PrinterProfile`).
- Three TOML decoding conventions coexist in `load_custom_profiles`: `bytes.fromhex()` for byte fields, `int(x, 16)` for VID/PID, plain values for ints/bools/strings. Do not unify.
- Empty bytes (b"") is the sentinel for absent style capability; `resolve_style` fallback chain is italic→underline→plain, bold→underline→plain; underline is the terminal node.
- `write_bytes` is the style channel — newlines must go through `write('\n')` (MD-08 boundary).
- Paired `action_<name>` + `_handle_<name>_result` convention for push_screen+callback flows; full-screen gates subclass `Screen`, not `ModalScreen`.
- `_make_*_app()` closure-factory pattern for one-shot Textual launchers; `App._exit_code` attribute idiom for return-code propagation.
- Import-locally + patch-at-source-module test convention for cli.py helpers.

### v1.6 Roadmap Notes

- **Strict phase ordering** (research-backed): Refactor (27) → Fleet detection (28) → Profile catalog (29) → Packaging (30). Refactor must stay isolated from feature/behavior changes so failures stay diagnosable. PyInstaller freezes last — only after the module graph is stable.
- **DIR-01 (codepage formalization) lands in Phase 27**, not later — other families extend it, so it must become tracked + tested before being extended nine times.
- **Package refactor uses move-with-shim** (three separately-green steps): move-with-re-export → repoint internals → migrate tests. Big-bang moves break ~700 tests via stale mock patch targets.
- **Bridge VIDs live in a separate `BRIDGE_CHIP_VIDS` set, never in the ProfileRegistry** — CH340/FTDI VID:PIDs collide with Arduinos/GPS dongles; never auto-select or auto-skip a bridge match.
- **Leave-empty-when-unsure rule** extends to all nine new families; every non-empty byte field cites manual + page + assumed emulation mode; unverified families tagged `human_needed`.

### Hardware-Verification Flags (human_needed expected during v1.6)

- **Phase 28 — bridge-chip interface-class behavior:** Does a CH341 USB-LPT adapter in parallel mode enumerate as class 7 or CDC/vendor-specific? Determines whether the class-7 fast path survives or must become advisory. Needs a real CH341 + `lsusb -v`. MEDIUM confidence until verified.
- **Phase 28/29 — native-USB PIDs beyond Epson LX-350 (0x0046) / LQ-350 (0x0047):** All other model-level PIDs are LOW confidence. Registry VID-only fallback is the safe default; per-model PIDs fill in via `diagnose`-on-real-device over time.
- **Phase 30 — libusb bundling + macOS clean-machine run:** Exact dylib path varies by arch; ad-hoc vs notarized signing is a project decision (Apple Developer account $99/yr). Needs a real build iteration on Intel + Apple Silicon. PortAudio bundling also requires clean-machine verification.

### Deferred Items

Items acknowledged and deferred at milestone close on 2026-06-12:

| Category | Item | Status |
|----------|------|--------|
| verification_gap | Phase 22: 22-VERIFICATION.md | human_needed |

Detail: real-hardware verification of bold/italic/underline ESC sequences on physical printers (Epson FX/LQ/LX, IBM PPDS, HP PCL, OKI ML 3390 in FX-2 mode, Citizen CT-S2000, Juki 6100/2200 underline). All automated spec checks pass (10/10); only physical hardware can confirm acceptance.

### Pending Todos

None.

### Blockers/Concerns

Carried into v1.6:

- Real-hardware verification of style ESC sequences (see Deferred Items above) — includes Juki underline ESC -1/-0 on the physical 6100/2200.
- Per-profile `buffer_bytes` defaults need real-hardware validation for at least Juki and Epson before instant mode is fully trusted.
- Juki 9100 control codes still extrapolated from 6100 (carried since v1.4).
- Post-v1.5 codepage/transliteration work (commits d70aded, 7ccdff5) — now formalized as DIR-01 in Phase 27.
- Multiple-printer selection scope (TBD): the REF-03 device-index fix enables selecting among several USB printers; clarify during Phase 27 planning whether full multi-printer selection is in v1.6 scope or just the index-bug fix.

## Session Continuity

Last session: 2026-06-12
Stopped at: v1.6 roadmap created (Phases 27-30)
Resume file: None
Next action: Plan Phase 27 with /gsd:plan-phase 27

## Operator Next Steps

- Plan the first phase with `/gsd:plan-phase 27`
