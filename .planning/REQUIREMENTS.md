# Requirements: Claude Teletype

**Defined:** 2026-04-03
**Core Value:** The physical typewriter experience -- characters appearing on paper one at a time with authentic pacing and sound, making AI conversation feel tangible and mechanical.

## v1.4 Requirements

Requirements for the Printer Setup TUI milestone. Each maps to roadmap phases.

### Printer Setup Screen

- [ ] **SETUP-01**: User sees a list of all discovered USB devices and CUPS printers on startup
- [ ] **SETUP-02**: User can choose between USB Direct and CUPS Queue connection methods
- [ ] **SETUP-03**: User must select a printer profile (juki/escp/ppds/pcl/generic) for USB devices, with VID:PID auto-suggestion
- [ ] **SETUP-04**: User can skip printer setup and run in simulator-only mode
- [ ] **SETUP-05**: User sees discovery progress and connection status messages inline in the setup screen

### Dependency Management

- [x] **DEP-01**: App handles missing pyusb gracefully -- shows CUPS printers only, no crashes
- [ ] **DEP-02**: User can install pyusb from within the app via async `uv sync --extra usb` with progress indicator

### Config Persistence

- [ ] **CFG-01**: User's printer+profile selection is saved to TOML config file
- [ ] **CFG-02**: Setup screen is skipped on next launch if saved printer is still connected (USB by VID:PID, CUPS by queue name)

### Diagnostics

- [x] **DIAG-01**: User can run `claude-teletype diagnose` for structured troubleshooting output (USB devices, CUPS queues, pyusb status, libusb backend)

## Future Requirements

Deferred to v1.5+. Tracked but not in current roadmap.

### Setup Enhancements

- **SETUP-06**: User can refresh device list without restarting the app
- **SETUP-07**: User can send a test print from the setup screen

## Out of Scope

| Feature | Reason |
|---------|--------|
| Network/remote printer setup | Local USB-LPT only -- network printers buffer pages, destroying character streaming |
| Automatic driver installation (libusb) | OS-level package management is out of scope; `brew install libusb` stays manual |
| Multi-printer simultaneous output | Single printer at a time; complexity not justified |
| Printer setup in --no-tui mode | Setup screen requires TUI; --no-tui uses CLI flags/config only |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SETUP-01 | Phase 19 | Pending |
| SETUP-02 | Phase 19 | Pending |
| SETUP-03 | Phase 19 | Pending |
| SETUP-04 | Phase 19 | Pending |
| SETUP-05 | Phase 19 | Pending |
| DEP-01 | Phase 18 | Complete |
| DEP-02 | Phase 19 | Pending |
| CFG-01 | Phase 20 | Pending |
| CFG-02 | Phase 20 | Pending |
| DIAG-01 | Phase 18 | Complete |

**Coverage:**
- v1.4 requirements: 10 total
- Mapped to phases: 10
- Unmapped: 0

---
*Requirements defined: 2026-04-03*
*Last updated: 2026-04-02 after roadmap creation*
