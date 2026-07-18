---
phase: 10-printer-profiles
plan: 01
subsystem: printer
tags: [dataclass, esc-sequences, usb, pyusb, toml, profiles]

# Dependency graph
requires:
  - phase: 09-configuration-system
    provides: TOML config loading, TeletypeConfig dataclass
provides:
  - PrinterProfile frozen dataclass with ESC sequence fields
  - BUILTIN_PROFILES registry with 5 printer families
  - get_profile() case-insensitive lookup
  - load_custom_profiles() TOML hex-to-bytes parser
  - auto_detect_profile() USB VID:PID matching
affects: [10-02-printer-profiles, cli, config]

# Tech tracking
tech-stack:
  added: []
  patterns: [data-driven-profiles, frozen-dataclass-registry, hex-encoded-toml-bytes, usb-printer-class-filter]

key-files:
  created:
    - src/claude_teletype/profiles.py
    - tests/test_profiles.py
  modified: []

key-decisions:
  - "Data-driven profiles via frozen dataclass -- all printer behavior encoded as data, not conditional code"
  - "USB printer class 7 filter before VID:PID matching -- prevents matching non-printer devices (scanners, cameras)"
  - "Separate exact VID+PID and VID-only lookup maps -- exact match takes priority over vendor-only match"

patterns-established:
  - "PrinterProfile frozen dataclass: immutable named bundle of ESC sequences and behavior"
  - "Hex-encoded byte strings in TOML config: bytes.fromhex() for custom profile ESC sequences"
  - "USB auto-detection with graceful fallback: ImportError and NoBackendError handled silently"

requirements-completed: [PRNT-02, PRNT-04]

# Metrics
duration: 5min
completed: 2026-02-17
---

# Phase 10 Plan 01: PrinterProfile Dataclass and Registry Summary

**Frozen PrinterProfile dataclass with 5 built-in profiles (Juki/ESC-P/PPDS/PCL/generic), hex-encoded TOML custom profile loading, and USB VID:PID auto-detection**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-17T17:16:58Z
- **Completed:** 2026-02-17T17:22:40Z
- **Tasks:** 2 (TDD RED + GREEN)
- **Files created:** 2

## Accomplishments
- PrinterProfile frozen dataclass with 13 fields covering ESC sequences, newline strategy, USB IDs, and paper width
- 5 built-in profiles with verified ESC sequences from 10-RESEARCH.md: generic, juki, escp, ppds, pcl
- Case-insensitive get_profile() with helpful ValueError listing available names
- load_custom_profiles() parsing hex-encoded TOML byte strings into PrinterProfile instances
- auto_detect_profile() with USB printer class 7 filter, exact VID+PID priority over VID-only match
- 28 tests covering all behaviors, full suite (332 tests) green

## Task Commits

Each task was committed atomically:

1. **TDD RED: Failing tests** - `ba90041` (test) - 28 tests for dataclass, registry, custom loading, auto-detection
2. **TDD GREEN: Implementation** - `9fe3368` (feat) - profiles.py module with all exports, all tests pass

_TDD plan: RED committed failing tests, GREEN committed implementation + test fixes for mock iteration._

## Files Created/Modified
- `src/claude_teletype/profiles.py` - PrinterProfile dataclass, BUILTIN_PROFILES dict, get_profile(), load_custom_profiles(), auto_detect_profile() (225 lines)
- `tests/test_profiles.py` - 28 tests covering frozen immutability, 5 profile ESC sequences, case-insensitive lookup, hex TOML parsing, USB auto-detection with mocked pyusb (393 lines)

## Decisions Made
- Data-driven profiles via frozen dataclass -- all printer-specific differences live in fields, not conditional code
- USB printer class 7 filter before VID:PID matching -- prevents false matches against scanners/cameras sharing a vendor ID
- Separate exact VID+PID and VID-only lookup maps in auto_detect_profile -- exact match takes priority
- `_patch_usb()` test helper to correctly mock Python's `import usb.core` resolution through sys.modules

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed USB mock iteration in tests**
- **Found during:** TDD GREEN phase
- **Issue:** MagicMock `__iter__` set via `MagicMock(return_value=iter(...))` did not work for `for x in mock_device` iteration in Python 3.13. Also, `patch.dict("sys.modules", {"usb": MagicMock(), "usb.core": mock_usb_core})` failed because `import usb.core` resolves via `usb` parent module's `.core` attribute, not directly from sys.modules.
- **Fix:** Created `_make_usb_device()` helper with lambda-based `__iter__` and `_patch_usb()` helper that sets `mock_usb.core = mock_usb_core` explicitly on the parent mock.
- **Files modified:** tests/test_profiles.py
- **Verification:** All 28 tests pass including USB auto-detection tests
- **Committed in:** 9fe3368 (GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug in test mocking approach)
**Impact on plan:** Test infrastructure fix, no scope creep. Implementation matches plan exactly.

## Issues Encountered
None beyond the mock iteration fix documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- PrinterProfile dataclass and registry ready for Plan 02 (ProfilePrinterDriver + CLI integration)
- BUILTIN_PROFILES dict ready to replace JukiPrinterDriver hard-coded constants
- auto_detect_profile() ready for CLI fallback chain integration
- load_custom_profiles() ready for config module integration

## Self-Check: PASSED

- All 3 files exist (profiles.py, test_profiles.py, 10-01-SUMMARY.md)
- Both commits found (ba90041 RED, 9fe3368 GREEN)
- 28 tests collected and passing

---
*Phase: 10-printer-profiles*
*Completed: 2026-02-17*
