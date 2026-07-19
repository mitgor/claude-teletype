---
phase: 34-architecture-cleanup
plan: 04
subsystem: printing
tags: [dead-code, facade, juki-compat, arch-07, arch-08]

# Dependency graph
requires:
  - phase: 34-architecture-cleanup
    provides: "34-01/34-02: registry threading end-to-end; 34-03: pkgutil catalog"
provides:
  - printing/__init__.py is a docstring-only namespace (ARCH-07 closed)
  - Single juki compat path — the "juki" alias profile (ARCH-08 closed)
  - JukiPrinterDriver, discover_printer(juki=), --juki, config.juki all deleted
  - Stale `juki = true` TOML keys tolerated (regression test)
  - Stale shim docstrings corrected (printing, screens)
affects: [cli, config, printing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "juki byte contract pinned on BUILTIN_PROFILES['juki-6100'] catalog fields, not driver class constants"

key-files:
  created: []
  modified:
    - src/claude_teletype/printing/__init__.py
    - src/claude_teletype/screens/__init__.py
    - src/claude_teletype/printing/drivers.py
    - src/claude_teletype/printing/selection.py
    - src/claude_teletype/cli.py
    - src/claude_teletype/config.py
    - tests/test_printer.py
    - tests/test_config.py
    - tests/test_cli.py
    - tests/test_teletype.py

key-decisions:
  - "Facade TRIMMED, not adopted: zero consumers verified by grep (all importers use submodule paths); matches rendering/ and screens/ docstring-only pattern"
  - "No explicit unknown-key ignore needed in config.py: load_config already filters flat TOML keys by dataclass fields, so stale juki=true drops silently — pinned by regression test"

patterns-established:
  - "Byte contracts live in the profile catalog; tests pin catalog fields, never driver class constants"

requirements-completed: [ARCH-CLEAN-03]

# Metrics
duration: 5min
completed: 2026-07-19
---

# Phase 34 Plan 04: Shim-Era Dead Code Removal Summary

**91-line zero-consumer printing facade trimmed to a 6-line namespace docstring, both stale shim docstrings fixed, and the three redundant juki compat paths (JukiPrinterDriver, discover_printer(juki=), --juki/config.juki plumbing) deleted — the "juki" alias profile alone carries backward compat, with byte pins re-anchored on the catalog**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-07-19T00:22:40Z
- **Completed:** 2026-07-19T00:27:34Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- ARCH-07: printing/__init__.py is a docstring-only namespace (6 lines, no imports, no __all__), matching rendering/ and screens/; grep confirmed every importer already uses submodule paths
- ARCH-08: exactly one juki compat path remains — `get_profile("juki")` alias resolving to the juki-6100 byte contract; JukiPrinterDriver class, discover_printer's juki= parameter, the --juki typer option, juki_flag/honor_config_juki plumbing, and the config.juki field are all gone
- Stale docstrings fixed: printing/__init__ no longer claims printer.py/profiles.py shims exist; screens/__init__ no longer claims *_screen.py re-export shims remain
- Stale `juki = true` TOML keys load without error (loader filters by dataclass fields) — pinned by new regression test
- cli.py precedence simplified to: --printer > config.printer_profile > auto-detect > generic
- Verified absent: `all_profiles` in cli.py (Phase 33 / 34-02 residue check — clean)

## Task Commits

1. **Task 1: trim facade + fix shim docstrings** - `e9e886b`
2. **Task 2: remove juki compat paths, re-pin tests** - `60a263d`

## Files Created/Modified
- `src/claude_teletype/printing/__init__.py` - 91-line re-export facade → 6-line namespace docstring
- `src/claude_teletype/screens/__init__.py` - false "*_screen.py shims remain" sentence deleted
- `src/claude_teletype/printing/drivers.py` - JukiPrinterDriver class + unused get_profile import deleted (only drivers.py change; byte path untouched per Phase 31 locks)
- `src/claude_teletype/printing/selection.py` - juki= param, compat branch, deprecation note, unused get_profile import removed
- `src/claude_teletype/cli.py` - juki_flag/honor_config_juki params + branches, --juki option, and call-site args removed; docstrings updated
- `src/claude_teletype/config.py` - juki field and "juki" bool-coercion entry deleted
- `tests/test_printer.py` - 9 JukiPrinterDriver tests re-pinned as `ProfilePrinterDriver(inner, BUILTIN_PROFILES["juki-6100"])` with identical byte expectations; 6 discover_printer(juki=) tests converted to profile=get_profile("juki")
- `tests/test_config.py` - juki default/TOML/merge tests converted; stale-key regression test added
- `tests/test_cli.py` - alias test strengthened (asserts juki-6100 byte equality); deprecation-warning test converted to --juki-rejected test
- `tests/test_teletype.py` - test_cli_teletype_passes_juki_profile now invokes `--teletype --printer juki` (surviving alias path), same assertion

## Decisions Made
- Facade trimmed (not adopted) per plan decision: zero consumers, and adoption would create a 28-name surface to maintain
- No explicit unknown-key tolerance code added to config.py: `load_config` already filters flat keys against dataclass field names, so deleting the field is inherently safe — the regression test pins this (T-34-06 mitigated)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Known worktree artifact: tests/test_usb_backend.py fails 2 frozen-backend tests (`ModuleNotFoundError: No module named 'usb'` — pyusb not installed here). Pre-existing, matches 34-02's record. Full suite otherwise green: 977 passed, 979 collected (>= 965 baseline met). Verified with `PYTHONPATH=$PWD/src` per 34-01 precedent.

## Known Stubs
- None.

## User Setup Required

None.

## Next Phase Readiness
- Phase 34 success criterion 3 (ARCH-07, ARCH-08) closed; all three waves complete
- Threat register: T-34-06 (config crash on stale key) and T-34-07 (byte-contract loss) both mitigated with tests

---
*Phase: 34-architecture-cleanup*
*Completed: 2026-07-19*

## Self-Check: PASSED

All 10 modified files + SUMMARY exist; both task commits (e9e886b, 60a263d) verified in git log; no file deletions in either commit.
