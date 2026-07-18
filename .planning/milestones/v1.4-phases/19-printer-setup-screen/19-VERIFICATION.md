---
phase: 19-printer-setup-screen
verified: 2026-04-02T10:00:00Z
status: passed
score: 10/10 must-haves verified
re_verification: false
---

# Phase 19: Printer Setup Screen Verification Report

**Phase Goal:** Users see an interactive setup screen on startup where they can browse discovered devices, pick a connection method, assign a printer profile, install pyusb if missing, or skip to simulator mode
**Verified:** 2026-04-02T10:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

All truths are derived from the must_haves sections across Plans 01, 02, and 03.

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | PrinterSelection dataclass captures user choice from setup screen | VERIFIED | `class PrinterSelection` at printer.py:78 with connection_type, device_index, cups_printer_name, profile_name fields |
| 2  | create_driver_for_selection() converts a PrinterSelection into a working PrinterDriver | VERIFIED | `def create_driver_for_selection` at printer.py:588, handles skip/cups/usb paths with NullPrinterDriver fallback |
| 3  | Skip selection returns NullPrinterDriver | VERIFIED | printer.py:605 `if selection.connection_type == "skip": return NullPrinterDriver()` — test confirmed |
| 4  | Setup screen shows discovered USB devices and CUPS printers in a selectable list | VERIFIED | OptionList populated in on_mount() at printer_setup_screen.py:141-166 from self._discovery.usb_devices and cups_printers |
| 5  | User can select a printer profile from a dropdown, with auto-suggestion for known VID:PID | VERIFIED | Select widget populated in compose() with all_profiles keys; VID:PID matching in on_option_list_option_selected() |
| 6  | User sees diagnostic messages in a log area | VERIFIED | Log widget at id="diagnostics-log"; on_mount() writes self._discovery.diagnostics at printer_setup_screen.py:169 |
| 7  | User can trigger pyusb install from within the screen with async progress | VERIFIED | `@work(exclusive=True, thread=False) async def _install_pyusb` at printer_setup_screen.py:312 with spinner, subprocess, and reimport |
| 8  | Screen dismisses with PrinterSelection or None | VERIFIED | self.dismiss(selection) at line 293, self.dismiss(None) at lines 297 and 301 |
| 9  | Setup screen appears on TUI startup when printer is not pre-configured | VERIFIED | _needs_printer_setup() at tui.py:162 guards the push; call_after_refresh(self._show_setup_screen) at tui.py:216 |
| 10 | cli.py runs discover_all() for TUI mode and passes DiscoveryResult to TeletypeApp | VERIFIED | cli.py:485 `discovery = discover_all()`, cli.py:519 `discovery=discovery` passed to TeletypeApp |

**Score:** 10/10 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/claude_teletype/printer.py` | PrinterSelection dataclass, create_driver_for_selection() factory | VERIFIED | PrinterSelection at line 78, factory at line 588; file is 620+ lines |
| `tests/test_printer_setup.py` | 6 tests for selection-to-driver conversion | VERIFIED | 91 lines, 6 tests all passing |
| `src/claude_teletype/printer_setup_screen.py` | PrinterSetupScreen(Screen[PrinterSelection | None]) | VERIFIED | 422 lines (exceeds 150 min); class at line 36 |
| `tests/test_printer_setup_screen.py` | 8 async tests for setup screen | VERIFIED | 153 lines (exceeds 60 min); 8 tests all passing |
| `src/claude_teletype/tui.py` | discovery parameter, conditional setup screen push, _show_setup_screen | VERIFIED | discovery=None param at line 130, _needs_printer_setup at 162, _show_setup_screen at 221, _handle_setup_result at 233 |
| `src/claude_teletype/cli.py` | discover_all() call before TUI launch, discovery passed to TeletypeApp | VERIFIED | discover_all at line 485, discovery= at line 519 |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `create_driver_for_selection` | CupsPrinterDriver, UsbPrinterDriver, NullPrinterDriver, ProfilePrinterDriver | conditional construction based on selection.connection_type | WIRED | printer.py:605-625 — all four driver types constructed depending on connection_type and profile_name |
| `PrinterSetupScreen.__init__` | DiscoveryResult | constructor parameter | WIRED | printer_setup_screen.py:88 `def __init__(self, discovery: DiscoveryResult, ...)` |
| `PrinterSetupScreen` | PrinterSelection | dismiss() call | WIRED | printer_setup_screen.py:293 `self.dismiss(selection)` where selection is a PrinterSelection instance |
| `PrinterSetupScreen._install_pyusb` | uv sync --extra usb | asyncio.create_subprocess_exec in @work worker | WIRED | printer_setup_screen.py:329 `proc = await asyncio.create_subprocess_exec(uv_path, "sync", "--extra", "usb", ...)` |
| `src/claude_teletype/cli.py` | `src/claude_teletype/tui.py` | TeletypeApp constructor receives discovery=DiscoveryResult | WIRED | cli.py:519 `discovery=discovery` passed when not effective_no_tui and not config.device |
| `src/claude_teletype/tui.py` | `src/claude_teletype/printer_setup_screen.py` | push_screen(PrinterSetupScreen(...), callback=...) | WIRED | tui.py:226-231 `PrinterSetupScreen(discovery=self._discovery, all_profiles=self._all_profiles)` |
| `src/claude_teletype/tui.py` | `src/claude_teletype/printer.py` | create_driver_for_selection in callback | WIRED | tui.py:244-247 `from claude_teletype.printer import create_driver_for_selection` used in _handle_setup_result |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `printer_setup_screen.py` OptionList | self._discovery.usb_devices, cups_printers | DiscoveryResult passed via constructor | Yes — DiscoveryResult is produced by discover_all() which queries libusb/CUPS | FLOWING |
| `printer_setup_screen.py` Log widget | self._discovery.diagnostics | DiscoveryResult.diagnostics populated during discover_all() | Yes — diagnostics appended during USB/CUPS discovery | FLOWING |
| `printer_setup_screen.py` Select widget | self._all_profiles keys | all_profiles dict passed via constructor from BUILTIN_PROFILES | Yes — BUILTIN_PROFILES contains 6 real profile entries | FLOWING |
| `tui.py` _handle_setup_result | result (PrinterSelection or None) | screen dismiss from user interaction | Yes — user selects device/profile and clicks Connect, or skips | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| PrinterSelection importable | `python3 -c "from claude_teletype.printer import PrinterSelection, create_driver_for_selection; print('OK')"` | OK | PASS |
| PrinterSetupScreen importable | `python3 -c "from claude_teletype.printer_setup_screen import PrinterSetupScreen; print('OK')"` | OK | PASS |
| TeletypeApp accepts discovery=None | `python3 -c "from claude_teletype.tui import TeletypeApp; TeletypeApp(discovery=None)"` | No error | PASS |
| cli.py importable | `python3 -c "from claude_teletype.cli import main; print('OK')"` | OK | PASS |
| 6 factory tests pass | `uv run pytest tests/test_printer_setup.py -v` | 6 passed | PASS |
| 8 screen tests pass | `uv run pytest tests/test_printer_setup_screen.py -v` | 8 passed | PASS |
| Full suite (456 tests) | `uv run pytest tests/ -q` | 456 passed in 10.31s | PASS |

---

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|---------------|-------------|--------|----------|
| SETUP-01 | 19-02, 19-03 | User sees a list of all discovered USB devices and CUPS printers on startup | SATISFIED | OptionList populated from DiscoveryResult in on_mount(); test_device_list_populated verifies 2 items for mixed discovery; test_connect_disabled_when_no_devices verifies empty state |
| SETUP-02 | 19-01, 19-03 | User can choose between USB Direct and CUPS Queue connection methods | SATISFIED | RadioSet with RadioButton("USB Direct") and RadioButton("CUPS Queue") in compose(); radio auto-selection in on_option_list_option_selected(); selection captured in _on_connect() |
| SETUP-03 | 19-02, 19-03 | User must select a printer profile (juki/escp/ppds/pcl/generic), with VID:PID auto-suggestion | SATISFIED | Select widget with all_profiles keys; VID:PID matching loop in on_option_list_option_selected(); test_profile_select_populated verifies all BUILTIN_PROFILES present |
| SETUP-04 | 19-01, 19-02, 19-03 | User can skip printer setup and run in simulator-only mode | SATISFIED | Skip button dismisses with None; Escape binding also dismisses with None; _handle_setup_result in tui.py preserves NullPrinterDriver on None result; test_skip_returns_none and test_escape_dismisses_with_none verify |
| SETUP-05 | 19-02, 19-03 | User sees discovery progress and connection status messages inline in the setup screen | SATISFIED | Log widget at id="diagnostics-log"; diagnostics written from DiscoveryResult.diagnostics and summary counts; test_diagnostics_displayed verifies log contains expected text |
| DEP-02 | 19-02, 19-03 | User can install pyusb from within the app via async `uv sync --extra usb` with progress indicator | SATISFIED | _install_pyusb @work(exclusive=True, thread=False) at printer_setup_screen.py:312; shows spinner, runs subprocess, calls _reimport_pyusb and _refresh_discovery; test_install_button_hidden_when_pyusb_available and test_install_button_visible_when_pyusb_missing verify visibility |

**Orphaned requirements check:** REQUIREMENTS.md maps SETUP-01 through SETUP-05 and DEP-02 to Phase 19. All six are claimed by plans. No orphaned requirements.

Note: SETUP-06 (refresh device list without restarting) and SETUP-07 (test print from setup screen) are listed as "planned" in REQUIREMENTS.md but not assigned to Phase 19 — correctly out of scope.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `printer_setup_screen.py` | 202 | Comment says `# "no printers found" placeholder` | Info | The string "placeholder" appears in a comment explaining a guard condition, not a stub implementation. The early return guards against clicking the static "No printers found" list entry that has no _device_entries counterpart. Legitimate guard, not a stub. |

No blocker or warning anti-patterns found.

---

### Human Verification Required

#### 1. Full Startup Flow — Real Hardware

**Test:** Launch the app normally (`uv run teletype`) with no USB printer connected and no CUPS queue configured.
**Expected:** PrinterSetupScreen appears immediately after TUI loads. Device list shows "No printers found." Install button is visible. Skip button dismisses to simulator mode.
**Why human:** Requires running the Textual TUI; cannot verify interactive screen rendering programmatically.

#### 2. pyusb Install Worker

**Test:** On a machine where pyusb is not installed, open the setup screen and click "Install USB Support."
**Expected:** Spinner appears, log shows install progress messages, and either "pyusb installed successfully" + re-scan (if uv succeeds) or an error message (if uv fails).
**Why human:** Requires a machine without pyusb and the ability to run `uv sync --extra usb`.

#### 3. Profile Auto-Suggestion on USB Selection

**Test:** With a Juki 6100 USB printer connected, open the setup screen and click the USB device entry.
**Expected:** Profile Select auto-selects "juki" (VID 0x1a86 / PID 0x7584 match). On macOS, radio defaults to CUPS Queue.
**Why human:** Requires physical USB hardware and cannot be tested in unit tests.

#### 4. Connect Produces Working Printer Driver

**Test:** Select a CUPS printer, choose "escp" profile, click Connect.
**Expected:** Setup screen dismisses, TUI is usable, subsequent prints use the escp profile.
**Why human:** Requires real CUPS queue and end-to-end print verification.

---

### Gaps Summary

No gaps. All 10 observable truths are verified, all 6 artifacts pass all four levels (exists, substantive, wired, data flowing), all 7 key links are confirmed wired in the actual code, all 6 requirements are satisfied with evidence, and all 14 tests pass in the full 456-test suite with no regressions.

The phase goal is achieved: users encounter the interactive PrinterSetupScreen on TUI startup, can browse devices, pick connection method and profile, install pyusb if missing, or skip to simulator mode.

---

_Verified: 2026-04-02T10:00:00Z_
_Verifier: Claude (gsd-verifier)_
