---
phase: 32-setup-detection-flow-fixes
plan: 02
subsystem: printing
tags: [registry, selection, discovery, cli, frozen-dataclass]
requires: []
provides:
  - "Case-insensitive ProfileRegistry.get over case-preserved keys (WR-03/FLOW-02)"
  - "match_saved_printer(profile_name=...) owns profile hand-off (ARCH-04/FLOW-04)"
  - "Frozen PrinterSelection dataclass"
  - "cups-no-name defensive fallback in create_driver_for_selection (CR-03/FLOW-01 factory half)"
affects: [34-status-bar-profile-display]
tech-stack:
  added: []
  patterns: [lowered-key-index, frozen-dataclass, loud-fallback]
key-files:
  created: []
  modified:
    - src/claude_teletype/printing/registry.py
    - src/claude_teletype/printing/selection.py
    - src/claude_teletype/printing/discovery.py
    - src/claude_teletype/cli.py
    - tests/test_registry.py
    - tests/test_smart_startup.py
decisions:
  - "Lowered-key index built once in __init__ with dict-comprehension last-wins on case-fold collision (matches documented merge policy; no extra handling)"
  - "PrinterSelection frozen rather than documenting a no-mutate convention; dataclasses.replace is the derivation path"
  - "cups-no-name fallback mirrors the USB-fallback stderr message style; NullPrinterDriver only when zero enabled queues"
metrics:
  duration: "~10 min"
  completed: 2026-07-18
requirements: [FLOW-02, FLOW-04, FLOW-01]
---

# Phase 32 Plan 02: Registry Case-Insensitivity, Profile Hand-off, CUPS Fallback Summary

Case-insensitive registry.get via a lowered-key index, explicit profile_name parameter on match_saved_printer with frozen PrinterSelection, and a loud first-enabled-queue fallback for cups selections with no queue name.

## Tasks

| Task | Name | Commits |
| ---- | ---- | ------- |
| 1 | WR-03 case-insensitive ProfileRegistry.get | b2e1748 (RED), 7933ee4 (GREEN) |
| 2 | ARCH-04 profile_name param + frozen PrinterSelection + CR-03 cups fallback | 7fb6310 (RED), 68c00e9 (GREEN) |
| 3 | Full-suite gate | (verification only) |

## What Was Done

- **registry.py**: `self._by_lower` index maps `key.lower().strip()` to the case-preserved key; `get()` resolves through it. `names()`/`all()`/`_build_index`/`match_vidpid` untouched. Uppercase custom TOML profiles now reachable via setup screen and `--printer` (FLOW-02) — no cli.py change needed since `_resolve_profile_selection` already routes through `registry.get`.
- **selection.py**: `match_saved_printer(..., profile_name="generic")` stamps both PrinterSelection variants. `create_driver_for_selection` cups branch: no queue name → first enabled queue with stderr note; NullPrinterDriver only when queueless.
- **discovery.py**: `PrinterSelection` is `@dataclass(frozen=True)`.
- **cli.py**: passes `profile_name=config.saved_printer_profile or "generic"` to match_saved_printer; the `saved_match.profile_name = ...` mutation at former line 989 is deleted (grep count 0). Status-bar profile re-resolution left as-is (Phase 34 territory).

## Verification

- `uv run pytest tests/test_registry.py -q` — 19 passed.
- `uv run pytest tests/test_smart_startup.py tests/test_selection_identity.py tests/test_cli.py tests/test_printer_setup.py -q` — 78 passed.
- `uv run pytest -q` — **919 passed** (gate: ≥ 912), 2 failed.
- Grep gates: `saved_match.profile_name =` count 0; `frozen=True` on PrinterSelection; profile_name in signature and both constructors.
- `git diff --stat` touches only the 6 declared files — no drivers.py/teletype.py (Phase 31 write_bytes surface untouched).

## Known Environment Failures (not regressions)

- `tests/test_usb_backend.py::test_frozen_with_bundled_dylib_builds_explicit_backend` and `::test_frozen_get_backend_returning_none_propagates` fail with `ModuleNotFoundError: 'usb'` in the worktree env — pre-declared artifact; orchestrator re-runs on main.

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None — no new surface beyond the plan's threat model; T-32-04 mitigation (frozen dataclass + parameterized hand-off) landed in Task 2.

## TDD Gate Compliance

Both tdd tasks have RED (test) commits preceding GREEN (feat) commits.

## Self-Check: PASSED

All modified files exist; commits b2e1748, 7933ee4, 7fb6310, 68c00e9 verified in git log.
