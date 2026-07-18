---
phase: 10-printer-profiles
plan: 02
subsystem: printer
tags: [profiles, esc-sequences, cli, config, teletype, backward-compat]

# Dependency graph
requires:
  - phase: 10-printer-profiles
    plan: 01
    provides: PrinterProfile dataclass, BUILTIN_PROFILES registry, get_profile(), load_custom_profiles(), auto_detect_profile()
  - phase: 09-configuration-system
    provides: TeletypeConfig, TOML loading, env overrides, CLI flags
provides:
  - ProfilePrinterDriver wrapping any inner driver with profile ESC sequences
  - JukiPrinterDriver as deprecated alias (thin subclass)
  - discover_printer() profile parameter for profile-driven discovery
  - --printer/-p CLI flag for named profile selection
  - --juki deprecated flag with warning
  - config.printer_profile field and custom TOML profile loading
  - Profile-aware teletype mode (replaces juki boolean)
  - make_printer_output() configurable columns parameter
affects: [cli, teletype, printer, config]

# Tech tracking
tech-stack:
  added: []
  patterns: [profile-driven-printer-wrapping, deprecated-flag-with-warning, profile-resolution-chain]

key-files:
  created: []
  modified:
    - src/claude_teletype/printer.py
    - src/claude_teletype/config.py
    - src/claude_teletype/cli.py
    - src/claude_teletype/teletype.py
    - tests/test_printer.py
    - tests/test_cli.py
    - tests/test_config.py
    - tests/test_teletype.py

key-decisions:
  - "ProfilePrinterDriver as standalone class, JukiPrinterDriver as thin deprecated subclass -- preserves backward compat while enabling generic profile support"
  - "Profile resolution chain: --printer > --juki (deprecated) > config.printer_profile > config.juki > auto_detect_profile() > generic"
  - "Instance-based type dispatch in apply_env_overrides -- avoids __future__ annotations breaking f.type identity checks"

patterns-established:
  - "Deprecated flag pattern: --juki still works but emits typer.echo warning to stderr, resolves to same profile"
  - "Profile resolution chain: CLI flag > deprecated flag > config > old config compat > USB auto-detect > generic fallback"
  - "Non-TOML field on dataclass: custom_profiles dict loaded separately from TOML flattening, skipped by env override"

requirements-completed: [PRNT-01, PRNT-03]

# Metrics
duration: 8min
completed: 2026-02-17
---

# Phase 10 Plan 02: Profile Integration Summary

**ProfilePrinterDriver replacing JukiPrinterDriver with full CLI/config/teletype integration via --printer flag, TOML custom profiles, and profile-aware teletype mode**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-17T17:25:24Z
- **Completed:** 2026-02-17T17:33:28Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments
- ProfilePrinterDriver wraps any inner driver with profile ESC sequences (init, newline, close behavior)
- JukiPrinterDriver preserved as thin deprecated subclass for backward compatibility
- --printer/-p CLI flag with full resolution chain (CLI > config > auto-detect > generic)
- config.printer_profile field with TOML [printer.profiles.*] custom profile loading
- Profile-aware teletype mode replacing juki boolean parameter
- 22 new tests (12 ProfilePrinterDriver, 6 config, 4 CLI) bringing total to 354 passing

## Task Commits

Each task was committed atomically:

1. **Task 1: ProfilePrinterDriver and discover_printer()** - `fe25c3c` (feat) - ProfilePrinterDriver class, JukiPrinterDriver deprecated alias, discover_printer() profile parameter
2. **Task 2: Config, CLI, and teletype integration** - `e14c76a` (feat) - --printer flag, printer_profile field, profile-aware teletype, apply_env_overrides fix
3. **Task 3: Integration tests** - `a974970` (test) - 22 new tests for ProfilePrinterDriver, config, CLI, and profile behavior

## Files Created/Modified
- `src/claude_teletype/printer.py` - ProfilePrinterDriver class, JukiPrinterDriver deprecated alias, discover_printer() profile parameter, make_printer_output columns param
- `src/claude_teletype/config.py` - printer_profile field, custom_profiles dict, updated template, apply_env_overrides fix for __future__ annotations
- `src/claude_teletype/cli.py` - --printer/-p flag, profile resolution chain, config show printer_profile, teletype profile passthrough
- `src/claude_teletype/teletype.py` - profile parameter replacing juki boolean, profile-driven init/newline/close
- `tests/test_printer.py` - TestProfilePrinterDriver class (12 tests), updated discover_printer type checks
- `tests/test_cli.py` - TestPrinterFlag class (4 tests), updated config show assertion
- `tests/test_config.py` - TestPrinterProfileConfig class (6 tests)
- `tests/test_teletype.py` - Updated juki tests to use profile parameter, updated CLI integration tests

## Decisions Made
- ProfilePrinterDriver as standalone class with JukiPrinterDriver as thin deprecated subclass -- cleanest path for generic profile support while preserving backward compat
- Profile resolution chain with 6 levels of fallback -- ensures every use case works (CLI flag, deprecated flag, config file, old config compat, USB auto-detection, generic default)
- Instance-based type dispatch in apply_env_overrides (isinstance check on default value) -- avoids the issue where `from __future__ import annotations` makes `f.type` a string instead of the actual type

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed apply_env_overrides broken by __future__ annotations**
- **Found during:** Task 2
- **Issue:** Adding `from __future__ import annotations` to config.py made all type annotations lazy strings. The existing `f.type is bool` identity check failed, causing env var overrides to set booleans as raw strings ("true" instead of True).
- **Fix:** Changed type dispatch to use `isinstance(default_val, bool)` on the current field value plus explicit field name set for known booleans, instead of `f.type is bool`.
- **Files modified:** src/claude_teletype/config.py
- **Verification:** All 5 previously-failing env override tests pass
- **Committed in:** e14c76a (Task 2 commit)

**2. [Rule 1 - Bug] Updated existing tests for new return types**
- **Found during:** Task 1
- **Issue:** discover_printer(juki=True) now returns ProfilePrinterDriver (not JukiPrinterDriver subclass) since it uses the generic wrapping path. 4 existing tests checked `isinstance(driver, JukiPrinterDriver)`.
- **Fix:** Updated test assertions to check for ProfilePrinterDriver instead.
- **Files modified:** tests/test_printer.py
- **Verification:** All 68 printer tests pass
- **Committed in:** fe25c3c (Task 1 commit)

**3. [Rule 1 - Bug] Updated teletype tests for profile-based API**
- **Found during:** Task 2
- **Issue:** 5 teletype tests used `juki=True/False` keyword arg which no longer exists on run_teletype(). Also test assertions checked for `juki=True` calls instead of `profile=...`.
- **Fix:** Updated tests to use `profile=get_profile("juki")` and check profile name in assertions.
- **Files modified:** tests/test_teletype.py
- **Verification:** All teletype tests pass
- **Committed in:** e14c76a (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (3 bugs from API changes during refactor)
**Impact on plan:** All fixes necessary for correctness after the juki-to-profile migration. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviations documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 10 (Printer Profiles) is fully complete
- ProfilePrinterDriver and profile system integrated across printer, config, CLI, and teletype
- Ready for next phase (11-multi-llm or as defined in ROADMAP)
- All 354 tests passing

## Self-Check: PASSED

_Verified below._

---
*Phase: 10-printer-profiles*
*Completed: 2026-02-17*
