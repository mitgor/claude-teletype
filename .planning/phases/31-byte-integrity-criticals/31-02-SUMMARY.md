---
phase: 31-byte-integrity-criticals
plan: 02
subsystem: teletype
tags: [byte-integrity, teletype, keyboard-interrupt, tdd]
requires:
  - PrinterDriver.write_bytes single-transfer contract (31-01)
provides:
  - byte-clean teletype init/reset delivery via write_bytes
  - KeyboardInterrupt-safe teletype read loop (clean Ctrl-C exit)
affects: [teletype-mode, custom-toml-profiles]
tech-stack:
  added: []
  patterns:
    - "raw ESC/init/reset sequences always travel the write_bytes channel"
    - "_written_bytes interleaves write/write_bytes via driver.mock_calls"
key-files:
  created: []
  modified:
    - src/claude_teletype/teletype.py
    - tests/test_teletype.py
decisions:
  - "Kept the ch == '\\x03' break check alongside except KeyboardInterrupt — harmless if cbreak ever delivers Ctrl-C raw"
metrics:
  duration: "~8 minutes"
  completed: "2026-07-18"
  tasks: 2
  commits: 2
---

# Phase 31 Plan 02: Teletype Byte Delivery and Ctrl-C Summary

Fixed the three WR-02 teletype defects: init now goes out via one write_bytes transfer (high-byte custom profiles no longer crash with UnicodeDecodeError), reset_sequence leaves as ONE atomic write_bytes call instead of per-byte chr() writes, and Ctrl-C exits cleanly through the finally restore/formfeed/reset path.

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 (RED) | Failing teletype byte/Ctrl-C tests | 0fa8e2d | tests/test_teletype.py |
| 1 (GREEN) | write_bytes init/reset + KeyboardInterrupt-safe loop | dd6268d | src/claude_teletype/teletype.py, tests/test_teletype.py |
| 2 | Phase gate — full suite | (verification only) | — |

## What Changed

- `run_teletype` init: `driver.write(init_data.decode("ascii"))` → `driver.write_bytes(init_data)` — single transfer, byte-verbatim, no decode.
- `run_teletype` reset (finally block): per-byte `for b in reset_sequence: driver.write(chr(b))` loop → `driver.write_bytes(profile.reset_sequence)` — one atomic transfer.
- Read loop wrapped in `try/except KeyboardInterrupt: pass` inside the existing try; finally still restores termios, sends formfeed/reset, closes driver (T-31-03 mitigation).
- `tests/test_teletype.py`: `_written_bytes` now walks `driver.mock_calls` in order merging both channels; 3 new tests (high-byte init verbatim with 0xb5 sentinel, single-transfer reset, KeyboardInterrupt clean exit). Test count 19 → 22.
- Unchanged per plan: use_crlf newline strategy on the text channel, `\f` formfeed via write, stderr echo, termios restore ordering.

## TDD Gate Compliance

RED: 0fa8e2d — 2 tests failed, KeyboardInterrupt test aborted the pytest run (the exact uncaught-propagation defect). GREEN: dd6268d — 22 passed. REFACTOR: not needed.

## Deviations from Plan

None - plan executed exactly as written. (One assertion in my own new test was corrected before GREEN commit: the 0xb5 sentinel is the last byte of init_sequence, not of the full init payload.)

## Verification

- `uv run pytest tests/test_teletype.py -q` — 22 passed
- Acceptance greps: `driver.write_bytes(` == 2, `chr(b)` == 0, `decode("ascii")` == 0, `KeyboardInterrupt` == 1 in teletype.py
- Phase gate `uv run pytest -q` — 912 collected, 910 passed, 2 failed: both pre-existing `tests/test_usb_backend.py` failures (`ModuleNotFoundError: No module named 'usb'`, pyusb absent in this worktree env — known artifact, orchestrator re-runs on main)
- `uv run pytest tests/test_byte_integrity.py tests/test_teletype.py tests/test_printer.py -q` — 162 passed
- No existing test deleted; count went from 19 to 22 (+3)

## Known Stubs

None.

## Threat Flags

None — no new surface; T-31-03 mitigated (termios always restored), T-31-04 accepted per plan (verbatim local profile bytes are the requirement).

## Deferred Issues

- tests/test_usb_backend.py: 2 worktree-env failures from missing `usb` module (pre-existing, also recorded in 31-01).

## Self-Check: PASSED

Commits 0fa8e2d and dd6268d verified present; SUMMARY and modified files exist on disk.
