---
phase: 32-setup-detection-flow-fixes
plan: 01
subsystem: tui-setup
tags: [textual, cups, usb, setup-screen, security]
requires:
  - phase: 31
    provides: write_bytes contract (untouched — no driver code modified)
provides:
  - CR-03 fix: kernel-claimed USB + CUPS recommendation dismisses with a resolved queue name
  - CR-03 fix: _save_printer_selection never persists saved_printer_id="" for usb/cups
  - WR-05 fix: Install USB Support hidden/inert under sys.frozen; uv sync cwd-pinned to project root
affects: [32-02 (selection.py defensive half of CR-03 lives there)]
tech-stack:
  added: []
  patterns: [serial-match/first-enabled queue fallback mirrored from selection.py:140-155]
key-files:
  created: []
  modified:
    - src/claude_teletype/screens/printer_setup.py
    - src/claude_teletype/tui.py
    - tests/test_printer_setup_screen.py
    - tests/test_tui.py
decisions:
  - "Refusal path (zero enabled CUPS queues) logs to #diagnostics-log and keeps the screen up rather than dismissing with a broken selection"
  - "_save_printer_selection returns silently on empty id (no notify) — keeps the guard testable outside a running app and the broken state never reaches config"
  - "uv-on-PATH check moved after the frozen/root guards so refusals are reported even when uv is absent"
metrics:
  duration: ~10 min
  completed: 2026-07-19
  tasks: 2
  tests-added: 9
---

# Phase 32 Plan 01: Setup-Screen CR-03 / WR-05 Fixes Summary

CUPS-recommended USB setup now dismisses with a real queue name (serial-matched, else first enabled) instead of silently degrading to the simulator, and Install USB Support is frozen-guarded and cwd-pinned to the project's own pyproject.toml.

## Tasks

| Task | Name | Commits |
|------|------|---------|
| 1 | CR-03: queue resolution in _on_connect + empty-ID persist guard | 46d5357 (RED), 68bc857 (GREEN) |
| 2 | WR-05: frozen guard + cwd pinning for Install USB Support | 5d3a715 (RED), e85bd11 (GREEN) |

## What Changed

**printer_setup.py `_on_connect`:** when `connection_type == "cups"` and the entry is USB, filters `self._discovery.cups_printers` to enabled queues, prefers the queue whose `serial` matches the device's (only when truthy), else the first enabled queue — mirroring `create_driver_for_selection` (selection.py:140-155, not modified here). Zero enabled queues → writes "No enabled CUPS queue available — cannot connect via CUPS" to `#diagnostics-log` and returns without dismissing. Plain CUPS entries unchanged.

**tui.py `_save_printer_selection`:** computes the id first; for `connection_type in ("usb", "cups")` with an empty id, returns before `load_config`/`save_config` — the broken state can no longer be persisted. "skip" persists as before.

**printer_setup.py WR-05:** module-level `_project_root()` walks `Path(__file__).resolve().parents` for `pyproject.toml`. `#install-row` hidden under `sys.frozen` in both `on_mount` and `_refresh_discovery` (frozen + pyusb missing logs "USB support not bundled in this build"). `_install_pyusb` refuses under `sys.frozen`, refuses when `_project_root()` is None, and otherwise passes `cwd=str(root)` to `create_subprocess_exec`. Closes T-32-01 (Tampering/EoP) and T-32-02 (Tampering) per the threat register.

## Verification

- `uv run pytest tests/test_printer_setup_screen.py tests/test_tui.py -q`: 58 passed.
- Full suite: 921 passed, 2 failed — both `tests/test_usb_backend.py` `ModuleNotFoundError: 'usb'`, the known worktree-env artifact (orchestrator re-runs on main). 921 ≥ 912 baseline; no regressions in this plan's scope.
- Source assertions: `sys, "frozen"` guards at printer_setup.py:233, 389, 487; `cwd=` at :419; resolved-queue `cups_printer_name` assignment at :339-353.
- TDD gates: RED commit precedes GREEN commit for both tasks.

## Deviations from Plan

**1. [Minor] Skipped the optional `self.notify` warning in `_save_printer_selection`**
- Plan said "optionally self.notify a warning"; omitted because `notify` outside a running app raises, which would make the guard untestable in the existing sync-test convention. The refusal is silent but the state is never persisted.

**2. [Minor] Moved the `shutil.which("uv")` check after the frozen/root guards**
- Guards must fire "before spawning anything" per the plan; ordering them first also means refusals are reported even on machines without uv.

Otherwise executed as written. No auth gates.

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, or trust-boundary surface introduced; this plan only closes existing ones (T-32-01, T-32-02).

## Notes for Orchestrator

- selection.py read-only constraint honored (no edits; owned by 32-02). No issues found in the mirrored fallback lines.
- STATE.md / ROADMAP.md untouched per instructions.

## Self-Check: PASSED

- src/claude_teletype/screens/printer_setup.py, src/claude_teletype/tui.py, tests modified and committed.
- Commits 46d5357, 68bc857, 5d3a715, e85bd11 present on worktree-agent-a470641fae5e66a12.
