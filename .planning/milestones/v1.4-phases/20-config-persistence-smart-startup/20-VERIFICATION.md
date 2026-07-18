---
phase: 20-config-persistence-smart-startup
verified: 2026-04-02T00:00:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
---

# Phase 20: Config Persistence & Smart Startup Verification Report

**Phase Goal:** Users configure their printer once and the app remembers -- setup is skipped on subsequent launches when the saved printer is still connected
**Verified:** 2026-04-02
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | After completing printer setup, printer type, device ID, and profile are saved to TOML config | VERIFIED | `_handle_setup_result` calls `_save_printer_selection` (tui.py:257); saves `saved_printer_type`, `saved_printer_id`, `saved_printer_profile` into `[printer.saved]` TOML section (config.py:226-231) |
| 2 | Config writes are atomic -- a crash mid-write cannot produce a corrupt 0-byte config | VERIFIED | `save_config` uses `tempfile.mkstemp` + `os.replace` with fd-level tracking and cleanup on `BaseException` (config.py:262-280) |
| 3 | On launch, if saved USB printer is still connected (matched by VID:PID), setup screen is skipped | VERIFIED | cli.py:488-505 calls `match_saved_printer`, sets `discovery=None` (setup-skip signal) when USB VID:PID matches; 6 USB tests pass |
| 4 | On launch, if saved CUPS printer queue still exists, setup screen is skipped | VERIFIED | `match_saved_printer` matches by queue name equality (printer.py:619-626); cli.py:488-505 applies same skip logic; CUPS tests pass |
| 5 | On launch, if saved printer is NOT connected, setup screen reappears | VERIFIED | When `match_saved_printer` returns None, `discovery` stays set (cli.py:506 comment); TUI `_needs_printer_setup` returns True when discovery is set and driver is None |

**Score:** 5/5 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/claude_teletype/config.py` | TeletypeConfig with saved_printer_type/id/profile; atomic save_config | VERIFIED | Fields at lines 112-114; atomic write via mkstemp+os.replace at lines 262-280; [printer.saved] section written at lines 226-231; load_config maps sub-table at lines 153-157 |
| `tests/test_config_persistence.py` | Round-trip and atomic-write tests | VERIFIED | 10 tests, all passing: field defaults, TOML round-trip, no section when empty, os.replace usage, original unchanged on failure, template comment, env skip |
| `src/claude_teletype/tui.py` | `_needs_printer_setup` updated; `_save_printer_selection` and `_clear_saved_printer` methods | VERIFIED | `_save_printer_selection` at line 266; `_clear_saved_printer` at line 294; wired into `_handle_setup_result` at lines 241 (skip path) and 257 (selection path) |
| `src/claude_teletype/cli.py` | Startup flow creates driver from saved config when printer is present | VERIFIED | Smart startup block at lines 488-506; imports `create_driver_for_selection`; CFG-02 comment at line 488 |
| `tests/test_smart_startup.py` | Tests for skip-when-connected and show-when-disconnected | VERIFIED | 13 tests, all passing: USB VID:PID match/no-match, CUPS queue match/no-match, edge cases (empty type, skip type, empty id), `_needs_printer_setup` integration |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/claude_teletype/tui.py` | `src/claude_teletype/config.py` | `_handle_setup_result` calls `_save_printer_selection` which calls `save_config` with saved printer fields | WIRED | tui.py:256-257 calls `_save_printer_selection(result)`; method at line 266 loads config, sets `saved_printer_type/id/profile`, calls `save_config` |
| `src/claude_teletype/cli.py` | `src/claude_teletype/printer.py` | `create_driver_for_selection` with saved `PrinterSelection` | WIRED | cli.py:472 imports `create_driver_for_selection`; cli.py:499-501 calls it with `saved_match` from `match_saved_printer` |
| `src/claude_teletype/tui.py` | `src/claude_teletype/config.py` | `_needs_printer_setup` reads `saved_printer_type/id` from config | WIRED | Pattern present in tui.py; `discovery=None` signal from cli.py used by `_needs_printer_setup` to skip setup |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `tui.py _save_printer_selection` | `selection.connection_type`, `selection.cups_printer_name`, `usb_dev.vendor_id/product_id` | `PrinterSelection` from setup screen; `self._discovery.usb_devices` | Yes — real device data from discovery, real user selection | FLOWING |
| `cli.py smart startup block` | `config.saved_printer_type`, `config.saved_printer_id` | Loaded from TOML via `load_config()` (calls `saved_section.get(...)`) | Yes — reads from persisted TOML file | FLOWING |
| `printer.py match_saved_printer` | `discovery.usb_devices`, `discovery.cups_printers` | `DiscoveryResult` from `discover_all()` — real USB/CUPS enumeration | Yes — real hardware discovery at startup | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| TeletypeConfig saved fields have correct defaults | `python -c "from claude_teletype.config import TeletypeConfig; c = TeletypeConfig(); assert c.saved_printer_type == ''"` | OK | PASS |
| `match_saved_printer` importable from printer module | `python -c "from claude_teletype.printer import match_saved_printer; print('OK')"` | OK | PASS |
| TUI has `_save_printer_selection` and `_clear_saved_printer` methods | `python -c "from claude_teletype.tui import TeletypeApp; assert hasattr(TeletypeApp, '_save_printer_selection')"` | OK | PASS |
| All 10 config persistence tests pass | `python -m pytest tests/test_config_persistence.py -x -v` | 10 passed | PASS |
| All 13 smart startup tests pass | `python -m pytest tests/test_smart_startup.py -x -v` | 13 passed | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| CFG-01 | 20-01-PLAN.md | User's printer+profile selection is saved to TOML config file | SATISFIED | `[printer.saved]` section written by `save_config` when `saved_printer_type` is non-empty; `_save_printer_selection` called in `_handle_setup_result` after user selects printer; CFG-01 comment at tui.py:256 |
| CFG-02 | 20-02-PLAN.md | Setup screen is skipped on next launch if saved printer is still connected (USB by VID:PID, CUPS by queue name) | SATISFIED | `match_saved_printer` in printer.py matches USB by VID:PID hex and CUPS by queue name; cli.py smart startup block sets `discovery=None` (skip signal) when match found; CFG-02 comment at cli.py:488 |

No orphaned requirements — both CFG-01 and CFG-02 from REQUIREMENTS.md are claimed by plans and verified in code.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| tui.py | 177, 200, 638, 778 | `placeholder=` | Info | Textual `Input` widget UI placeholder text — not a code stub. No impact. |

No blockers. No warnings. The four `placeholder` hits are Textual framework Input widget attributes for display text, not implementation gaps.

---

### Human Verification Required

#### 1. End-to-end setup-then-restart flow

**Test:** Run the TUI, complete the printer setup screen selecting a USB or CUPS printer. Exit the app. Check that `~/.config/claude-teletype/config.toml` now contains a `[printer.saved]` section with correct type, id, and profile. Relaunch the app with the same printer connected and verify setup screen does not appear.

**Expected:** Config file gains `[printer.saved]` section after first launch. Second launch goes directly to chat without showing setup screen.

**Why human:** Requires a real connected printer and a live TUI session; cannot be verified without hardware or a full TUI test harness.

#### 2. Disconnected-printer fallback

**Test:** After saving a printer config, unplug the USB printer (or remove the CUPS queue). Relaunch the app.

**Expected:** Setup screen reappears because `match_saved_printer` returns None for the missing device.

**Why human:** Requires hardware manipulation (physical disconnect or CUPS queue removal) at test time.

---

### Gaps Summary

No gaps found. All 5 observable truths are fully verified at all four levels (existence, substantive, wired, data-flowing). Both requirement IDs (CFG-01, CFG-02) are satisfied. All 23 tests pass. No blocker or warning anti-patterns.

---

_Verified: 2026-04-02_
_Verifier: Claude (gsd-verifier)_
