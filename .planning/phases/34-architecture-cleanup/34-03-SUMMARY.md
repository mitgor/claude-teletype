---
phase: 34-architecture-cleanup
plan: 03
subsystem: printing-catalog
tags: [pkgutil, catalog, profiles, arch-03]
requires: []
provides:
  - "pkgutil auto-discovery in profiles._load_catalog — adding a family is one new catalog/<family>.py file"
  - "catalog/juki.py, ibm.py, hp.py, citizen.py, panasonic.py, tally.py (new); escp in epson.py; oki-3390 + oki-ml-* in oki.py"
  - "profile-name snapshot test pinning all 21 names (no-profile-lost gate)"
affects: [packaging]
tech-stack:
  added: []
  patterns:
    - "pkgutil.iter_modules discovery, sorted for deterministic merge order"
    - "cross-family aliases via explicit sibling imports (from ...catalog import epson as _epson)"
key-files:
  created:
    - src/claude_teletype/printing/catalog/juki.py
    - src/claude_teletype/printing/catalog/ibm.py
    - src/claude_teletype/printing/catalog/hp.py
    - src/claude_teletype/printing/catalog/citizen.py
    - src/claude_teletype/printing/catalog/panasonic.py
    - src/claude_teletype/printing/catalog/tally.py
  modified:
    - src/claude_teletype/printing/profiles.py
    - src/claude_teletype/printing/catalog/__init__.py
    - src/claude_teletype/printing/catalog/epson.py
    - src/claude_teletype/printing/catalog/oki.py
    - tests/test_profiles.py
    - packaging/claude-teletype.spec
decisions:
  - "Alias blocks live with the family they derive from (same-family) or the brand (cross-family), per plan destination map"
  - "R021 rationale comment for the Panasonic/Tally alias group lives in panasonic.py; tally.py docstring points at it"
metrics:
  duration: "~20 min"
  completed: 2026-07-19
---

# Phase 34 Plan 03: Catalog Migration (ARCH-03) Summary

pkgutil auto-discovery in _load_catalog plus all seven inline families and nine alias blocks moved into per-family catalog modules — profiles.py now holds only the dataclass, "generic", loaders, and resolve_style.

## What was done

- **Task 1** (b7b2138 test, f4abb50 refactor): `test_catalog_discovery_covers_all_modules` (does its own pkgutil discovery) and `test_builtin_profile_names_snapshot` (pins all 21 pre-migration names) written first and passing against the inline code; then `_load_catalog` rewritten to `pkgutil.iter_modules(catalog.__path__)` sorted by name, function-local imports and the cycle-break docstring preserved. Hand-edited import tuple gone.
- **Task 2** (7b7f404): juki/ibm/hp/citizen/panasonic/tally modules created; escp added to epson.py; oki-3390 + oki-ml-ibm/oki-ml-epson added to oki.py with explicit sibling imports (`_epson.PROFILES["escp"]`, `_ibm.PROFILES["ppds"]`). BUILTIN_PROFILES literal reduced to "generic"; all alias blocks and the "AFTER the literal, BEFORE the aliases" ordering comment deleted (replaced with a one-line note). catalog/__init__.py docstring documents auto-discovery and sibling-import aliasing. Every usb_vendor_id=None nulling and D007 comment preserved.

## Byte fidelity verification (T-34-05)

Beyond the unmodified byte-pinning tests, a full field-level diff was run: `dataclasses.asdict` of every profile in BUILTIN_PROFILES at base commit 491fcdf vs post-migration — **all 21 profiles byte-for-byte identical**. Snapshot test passed unmodified from Task 1.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] PyInstaller spec loses catalog modules under pkgutil discovery**
- **Found during:** Task 1 frozen-build note check
- **Issue:** The pkgutil rewrite removed the only *static* imports of catalog modules; PyInstaller's static analysis would no longer bundle them, so the frozen app would silently ship with only the "generic" profile.
- **Fix:** `hiddenimports += collect_submodules("claude_teletype.printing.catalog")` in packaging/claude-teletype.spec with a comment explaining why it is mandatory. PyInstaller's FrozenImporter implements pkgutil.iter_modules, so discovery works once modules are collected.
- **Files modified:** packaging/claude-teletype.spec
- **Commit:** 3f4ac44

## Notes

- **Frozen smoke check not run locally:** packaging/smoke_frozen.sh requires a full PyInstaller build (`uv sync --extra usb --group packaging`); this worktree's venv lacks the usb extra (see below), so the build was not run. The smoke script's existing star-line diagnose-row check will catch a missing catalog on the next frozen build. No module list was hardcoded as a fallback (per plan).
- **Known worktree artifact:** tests/test_usb_backend.py — 2 failures with `ModuleNotFoundError: No module named 'usb'`, pre-existing in this worktree and unrelated to this plan. Full suite otherwise: **965 passed** (matches main baseline), 967 collected.
- **TDD note:** Task 1 was tdd="true" but the plan explicitly specifies the tests pass against the *current* (pre-rewrite) code — they are characterization/no-loss gates, not red/green. Commit sequence: test(34-03) then refactor(34-03).
- No issues found in registry.py/selection.py (34-01 territory); neither file touched.

## Known Stubs

None.

## Threat Flags

None — catalog discovery imports only first-party package modules; no new trust boundary.

## Commits

| Task | Commit | Description |
| ---- | ------ | ----------- |
| 1 (tests) | b7b2138 | discovery + snapshot regression gates |
| 1 (impl) | f4abb50 | pkgutil auto-discovery in _load_catalog |
| 2 | 7b7f404 | families + aliases into catalog modules |
| deviation | 3f4ac44 | PyInstaller collect_submodules for catalog |

## Self-Check: PASSED

All six created catalog modules exist on disk; all four task commits present in git log; full suite 965 passed / 967 collected; profile count 21 unchanged.
