---
phase: 34-architecture-cleanup
verified: 2026-07-19T00:00:00Z
status: passed
score: 7/7 must-haves verified
overrides_applied: 0
---

# Phase 34: Architecture Cleanup Verification Report

**Phase Goal:** ProfileRegistry is the single profile seam end-to-end, the catalog is the single home for family data, and shim-era dead code is gone
**Verified:** 2026-07-19
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | ProfileRegistry flows cli → TeletypeApp → PrinterSetupScreen → create_driver_for_selection, no flatten-to-dict-and-rebuild; unknown profile fails loudly (ARCH-02) | ✓ VERIFIED | cli.py:350 builds the one registry; :951 `registry=registry` into TeletypeApp; tui.py:267 passes it to PrinterSetupScreen, :292 into `create_driver_for_selection(..., registry=..., diagnostics=...)`; selection.py:216-224 emits "Unknown printer profile ... Check saved_printer_profile in config." and returns unwrapped driver. `grep 'dict(BUILTIN_PROFILES)'` in src: only a historical docstring in registry.py describing the pattern it replaced. printer_setup.py:118 default registry is a tests-only generic fallback, not a rebuild. |
| 2 | Adding a family = one catalog/<family>.py; _load_catalog auto-discovers; inline families + aliases moved (ARCH-03) | ✓ VERIFIED | profiles.py:154 `pkgutil.iter_modules(catalog.__path__)` with function-local import (cycle-break preserved); BUILTIN_PROFILES literal holds only "generic" (line 127); 10 catalog modules (citizen, epson, hp, ibm, juki, oki, panasonic, star, tally); all 9 replace-aliases present and living in family modules. Byte fidelity spot-checked live against `git show 491fcdf`: **ppds, citizen-cts2000, juki-6100, pcl all field-for-field identical** (dataclasses.asdict compare, zero mismatches). |
| 3 | Dead code gone: all_profiles param, 91-line facade trimmed, stale shim docstrings, juki compat paths beyond alias (ARCH-07/08/IN-01) | ✓ VERIFIED | `grep all_profiles src/` — zero hits (one test docstring only); printing/__init__.py is 6 lines, docstring-only; screens/__init__.py has no shim claim, `grep shim src/` clean; JukiPrinterDriver / honor_config_juki / --juki — zero src hits; "juki" alias profile resolves via catalog/juki.py. Full suite green. |
| 4 | tui.py uses public driver property, no _inner reach-in (ARCH-06) | ✓ VERIFIED | drivers.py:275 `def inner` property; tui.py:388 `inner = driver.inner`; `grep _inner tui.py` — zero hits. |
| 5 | 32-review WR-01 closed: case-sensitive dict lookups gone | ✓ VERIFIED | selection.py resolves via `effective_registry.get()`; registry.py:119 `self._by_lower.get(name.lower().strip())` — case-insensitive everywhere; cli/tui lookups also route through registry.get. |
| 6 | 32-review WR-02 closed: case-collision diagnostic | ✓ VERIFIED | registry.py:67-75 logger.warning("Profile name case collision: %r shadows %r ..."); pinned by test_registry.py:232. |
| 7 | 32-review WR-04 closed: diagnostics visible under Textual | ✓ VERIFIED | selection diags → `notify()` at tui.py:294-296 (setup path) and tui.py:251-252 (mount, startup path); tests test_tui.py:993 (notified on mount) and :1006 (no spurious notify). |

**Score:** 7/7 truths verified

### Post-Review Fix Verification (34-REVIEW warnings, all 5 fixed)

| Fix | Commit | Evidence in code |
| --- | ------ | ---------------- |
| WR-01 stale `[printer] juki = true` warned | 32a07fb | config.py:139-146 detects retired key, warns once (`_warned_retired_keys`) |
| WR-02 unknown config printer_profile → warning + auto-detect continues | 5500485 | cli.py:365-374: `typer.echo("Warning: unknown printer_profile ... using auto-detect", err=True)` then `detect_native_profile(registry)` |
| WR-03 saved-match diagnostics → TUI notify | f6b5ff9 | cli.py:871/909/956 `startup_diagnostics` collected and passed to TeletypeApp; tui.py:251-252 notifies on mount; test_smart_startup.py:654 pins the threading |
| WR-04 simulator-fallback diagnostic | 20ebea5 | selection.py:203-210: `_emit(..., "no printer available — running in simulator mode")` before `return NullPrinterDriver()` |
| WR-05 resolvable ProfileRegistry annotation | 1ac9353 | selection.py:27 runtime import; verified live: `typing.get_type_hints(create_driver_for_selection)` resolves without NameError |

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/claude_teletype/printing/selection.py` | registry= and diagnostics= params, loud unknown-name | ✓ VERIFIED | Both params (lines 115-116); registry.get in try/except ValueError with _emit |
| `src/claude_teletype/printing/registry.py` | case-fold collision diagnostic | ✓ VERIFIED | Lines 64-75, "case collision" warning |
| `src/claude_teletype/printing/drivers.py` | public `inner` property | ✓ VERIFIED | Line 275 |
| `src/claude_teletype/screens/printer_setup.py` | registry accepted directly, no second-registry rebuild | ✓ VERIFIED | Line 110 param; comment + code confirm no flatten-rebuild |
| `src/claude_teletype/printing/profiles.py` | pkgutil _load_catalog; literal holds only "generic" | ✓ VERIFIED | pkgutil at line 154; single literal entry |
| `src/claude_teletype/printing/catalog/juki.py` | juki-6100, juki-2200 + juki alias | ✓ VERIFIED | Present, byte-identical to 491fcdf |
| `src/claude_teletype/printing/catalog/ibm.py` | ppds + ibm/lexmark-forms aliases | ✓ VERIFIED | Present |
| `src/claude_teletype/printing/__init__.py` | docstring-only, ≤15 lines | ✓ VERIFIED | 6 lines |
| `src/claude_teletype/screens/__init__.py` | no false shim claim | ✓ VERIFIED | Docstring rewritten, no "shim" anywhere in src |

### Key Link Verification

| From | To | Via | Status |
| ---- | -- | --- | ------ |
| cli.py | tui.py | `registry=registry` (line 951) | ✓ WIRED |
| tui.py | selection.py | `create_driver_for_selection(..., registry=..., diagnostics=...)` (line 292) | ✓ WIRED |
| tui.py | drivers.py | `driver.inner` (line 388) | ✓ WIRED |
| selection.py | registry.py | `effective_registry.get(selection.profile_name)` in try/except ValueError (line 216) | ✓ WIRED |
| profiles.py | catalog/ | `pkgutil.iter_modules(catalog.__path__)` function-local (line 154) | ✓ WIRED |
| catalog/oki.py | catalog/epson.py | sibling import for oki-ml-epson alias | ✓ WIRED (alias present, bytes verified) |
| tests/test_printer.py | profiles.py | juki byte pins on juki-6100 fields | ✓ WIRED (suite green) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full test suite | `uv run pytest -q` | **992 passed in 22.13s** | ✓ PASS |
| Byte fidelity of moved profiles | asdict compare vs `git show 491fcdf` literal (ppds, citizen-cts2000, juki-6100, pcl) | zero field mismatches; 21 profiles total; all 9 aliases present | ✓ PASS |
| WR-05 annotation resolvable | `typing.get_type_hints(create_driver_for_selection)` | resolves, no NameError | ✓ PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes declared by any Phase 34 plan; not a migration/tooling phase. SKIPPED.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| ARCH-CLEAN-01 | 34-01, 34-02 | Registry seam, no flatten-rebuild, loud unknown names | ✓ SATISFIED | Truths 1, 5-7 |
| ARCH-CLEAN-02 | 34-03 | One catalog module per family, auto-discovery | ✓ SATISFIED | Truth 2 |
| ARCH-CLEAN-03 | 34-04 | Dead code removed, suite green | ✓ SATISFIED | Truth 3 + 992 passed |
| ARCH-CLEAN-04 | 34-02 | Public driver property, no _inner reach-in | ✓ SATISFIED | Truth 4 |

No orphaned requirements — REQUIREMENTS.md maps exactly these four IDs to Phase 34 and every one appears in a plan's `requirements` field.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| src/claude_teletype/printing/catalog/juki.py | 54 | Stale comment: "and the deprecated --juki flag" (flag no longer exists) | ℹ️ Info | Cosmetic; already logged as 34-REVIEW IN-01, IN items explicitly out of phase scope |

No TBD/FIXME/XXX markers in any phase-modified file. No stub patterns.

### Human Verification Required

None. All success criteria are structural/behavioral and were verified via greps, a live byte-fidelity comparison against the pre-move commit, and the full test suite (including Textual pilot tests that pin the notify-visibility paths).

### Gaps Summary

No gaps. All four roadmap success criteria hold in the codebase, all five post-review warning fixes are present in the committed code (32a07fb, 5500485, f6b5ff9, 20ebea5, 1ac9353), the three absorbed 32-review items (WR-01/WR-02/WR-04) are closed with pinning tests, and the full suite is green at 992 tests.

---

_Verified: 2026-07-19_
_Verifier: Claude (gsd-verifier)_
