---
phase: 19
slug: printer-setup-screen
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-03
---

# Phase 19 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] asyncio_mode = "auto" |
| **Quick run command** | `uv run pytest tests/test_printer_setup_screen.py -x` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~12 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_printer_setup_screen.py -x`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 19-01-01 | 01 | 1 | SETUP-02, SETUP-04 | unit | `uv run pytest tests/test_printer_setup.py -x` | ❌ W0 | ⬜ pending |
| 19-02-01 | 02 | 2 | SETUP-01..05, DEP-02 | unit | `python -c "from claude_teletype.printer_setup_screen import PrinterSetupScreen"` | ❌ W0 | ⬜ pending |
| 19-02-02 | 02 | 2 | SETUP-01..05, DEP-02 | unit | `uv run pytest tests/test_printer_setup_screen.py -x` | ❌ W0 | ⬜ pending |
| 19-03-01 | 03 | 3 | SETUP-01..05 | integration | `python -c "from claude_teletype.tui import TeletypeApp; ..."` | ✅ | ⬜ pending |
| 19-03-02 | 03 | 3 | all | integration | `uv run pytest tests/ -x --timeout=30 -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_printer_setup.py` — stubs for PrinterSelection, create_driver_for_selection
- [ ] `tests/test_printer_setup_screen.py` — stubs for SETUP-01 through SETUP-05, DEP-02
- [ ] Test app harness: follow `SettingsTestApp` pattern from `test_settings_screen.py`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Visual layout matches UI-SPEC | all | CSS layout + widget rendering needs visual inspection | Launch app, verify device list, radio buttons, profile select, buttons visible |
| Async pyusb install progress | DEP-02 | Requires actual `uv sync` execution | Uninstall pyusb, launch, click install, verify progress indicator |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
