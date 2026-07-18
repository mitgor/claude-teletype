# Requirements: Claude Teletype

**Defined:** 2026-07-18
**Core Value:** The physical typewriter experience — characters appearing on paper one at a time with authentic pacing and sound, making AI conversation feel tangible and mechanical.

## v1.7 Requirements

Requirements for the **Review Hardening** milestone. Every requirement traces to a finding in `.planning/v1.6-REVIEW.md` (CR/WR/IN) or `.planning/v1.6-ARCHITECTURE-REVIEW.md` (ARCH). Each maps to roadmap phases.

### Byte Integrity

- [x] **BYTE-01**: User printing with any high-byte profile sequence (codepage commands, cp437/cp866 text) gets those bytes delivered verbatim to USB hardware — `ProfilePrinterDriver._send_raw` no longer round-trips through ASCII (CR-01)
- [x] **BYTE-02**: User printing over CUPS gets non-ASCII bytes delivered intact — `CupsPrinterDriver.write_bytes` no longer destroys bytes ≥ 0x80 (CR-02)
- [x] **BYTE-03**: A byte-integrity regression test round-trips a 0xb5-bearing sequence through ProfilePrinterDriver and CupsPrinterDriver, failing if any byte is altered (CR-01/CR-02 companion)
- [x] **BYTE-04**: User in typewriter mode can type non-ASCII characters without a crash, reset sequences stay atomic per the driver contract, and Ctrl-C exits cleanly (WR-02)

### Setup & Detection Flow

- [x] **FLOW-01**: User whose native-USB printer is kernel-claimed and who accepts the recommended CUPS path gets a working CUPS driver with the queue name set — never a silent NullPrinterDriver, and the broken state is never persisted to config (CR-03)
- [x] **FLOW-02**: User with an uppercase-named custom profile can select it — `ProfileRegistry` lookups are case-insensitive against case-preserved keys (WR-03)
- [x] **FLOW-03**: User running the frozen `.app` never triggers `uv sync` against an arbitrary working directory — in-app pyusb install is guarded or disabled when frozen (WR-05)
- [x] **FLOW-04**: Smart startup restores the saved profile through an explicit parameter or constructor path — no caller-side mutation of a returned dataclass carrying the hardware contract (ARCH-04)

### Print Pipeline

- [x] **PIPE-01**: One shared print-pipeline implementation serves both the CLI `print` subcommand and the TUI file-print path, with identical cancel-safety (`finally: renderer.close()`) in both (ARCH-01)
- [x] **PIPE-02**: User can actually cancel an in-TUI print with escape — pacing no longer blocks the Textual event loop with synchronous `time.sleep` (WR-01)
- [x] **PIPE-03**: Picker-mode printing never invokes a blocking `input()` prompt while a Textual app is running (WR-04)

### Architecture Cleanup

- [ ] **ARCH-CLEAN-01**: `ProfileRegistry` is passed as the registry seam through cli, setup screen, and driver selection — no flatten-to-dict-and-rebuild round trips, and unknown profile names fail loudly instead of silently skipping profile wrapping (ARCH-02)
- [ ] **ARCH-CLEAN-02**: Adding a printer family touches exactly one catalog module — `_load_catalog` discovers catalog modules without hand-edited import tuples, and remaining inline families move to catalog modules (ARCH-03)
- [ ] **ARCH-CLEAN-03**: Dead code removed: unused `all_profiles` parameter, unused 91-line `printing/__init__` facade (trim or adopt), stale shim-era docstrings, redundant juki compat paths beyond the alias profile (ARCH-07, ARCH-08, IN-01)
- [ ] **ARCH-CLEAN-04**: `tui.py` no longer reaches into `ProfilePrinterDriver._inner`; the needed capability is exposed on the driver Protocol (ARCH-06)

## Future Requirements

Deferred to v1.8+. Tracked but not in current roadmap.

### From reviews (accepted, not scheduled)

- **ARCH-05**: decompose `cli.main()` god function / extract `--teletype` sub-app — high churn, low user-visible value; revisit when cli.py next changes substantially
- **ARCH-09**: dedupe CUPS entry population in PrinterSetupScreen
- **IN-02**: `.app` launcher quoting hardening; **IN-03** vendor_name misnomer; **IN-04** markdown emphasis escapes; **IN-05** serial-aware saved-printer matching; **IN-06** smoke-script temp HOME cleanup

### Carried from earlier milestones

- **PKG-03** (v1.6): frozen `.app` verified on a true clean machine — `human_needed`
- **PKG-05/06/07**: Linux binary, universal2, signing/notarization
- **PREV-01**, **FMT-01**, **PICK-06**, **PICK-07**, **CAP-07**, **CAP-08** (v1.5 carry-overs)
- Real-hardware verification sweep: style ESC sequences, `buffer_bytes`, CH341 interface class, Juki 9100 codes — `human_needed`

## Out of Scope

| Feature | Reason |
|---------|--------|
| cli.main() decomposition (ARCH-05) | Pure churn with no user-visible behavior change; sequence it with the next feature that touches cli.py |
| New printer families or detection expansion | v1.7 hardens what v1.6 shipped; no new surface |
| Markdown emphasis escape syntax (IN-04) | Behavior matches documented v1.5 contract; revisit with real user friction |

## Traceability

Which phases cover which requirements. Filled in by `gsd-roadmapper` during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| BYTE-01 | Phase 31 | Complete |
| BYTE-02 | Phase 31 | Complete |
| BYTE-03 | Phase 31 | Complete |
| BYTE-04 | Phase 31 | Complete |
| FLOW-01 | Phase 32 | Complete |
| FLOW-02 | Phase 32 | Complete |
| FLOW-03 | Phase 32 | Complete |
| FLOW-04 | Phase 32 | Complete |
| PIPE-01 | Phase 33 | Complete |
| PIPE-02 | Phase 33 | Complete |
| PIPE-03 | Phase 33 | Complete |
| ARCH-CLEAN-01 | Phase 34 | Pending |
| ARCH-CLEAN-02 | Phase 34 | Pending |
| ARCH-CLEAN-03 | Phase 34 | Pending |
| ARCH-CLEAN-04 | Phase 34 | Pending |

**Coverage:** 15/15 requirements mapped. No orphans.

---
*Requirements defined: 2026-07-18*
*Traceability mapped: 2026-07-18 (roadmap creation)*
