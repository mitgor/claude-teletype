---
phase: 31-byte-integrity-criticals
plan: 01
subsystem: printing
tags: [byte-integrity, codepage, cups, regression-test, tdd]
requires: []
provides:
  - byte-clean ProfilePrinterDriver._send_raw (delivers via inner.write_bytes)
  - bytes-based CupsPrinterDriver line buffer (b"".join to lp input)
  - tests/test_byte_integrity.py contract lock (BYTE-03)
affects: [printing-drivers, codepage-feature, cups-path]
tech-stack:
  added: []
  patterns:
    - "raw ESC/codepage sequences always travel the write_bytes channel"
    - "interleaved write/write_bytes mock collection via inner.mock_calls"
key-files:
  created:
    - tests/test_byte_integrity.py
  modified:
    - src/claude_teletype/printing/drivers.py
    - tests/test_printer.py
    - tests/test_codepage.py
decisions:
  - "Atomicity invariant (CR+LF+reinit as ONE call) preserved — only the channel moved from write(str) to write_bytes(bytes)"
metrics:
  duration: "~10 minutes"
  completed: "2026-07-18"
  tasks: 3
  commits: 3
---

# Phase 31 Plan 01: Byte-Integrity Criticals Summary

Fixed CR-01/CR-02 ASCII round-trip corruptions so bytes >= 0x80 (ppds codepage 0xb5, cp437/cp866 text) survive verbatim through _send_raw and the CUPS lp path, locked in by a 4-test regression file that was RED before the fix.

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Failing byte-integrity regression tests (RED) | 14fcf93 | tests/test_byte_integrity.py |
| 2 | Fix _send_raw (CR-01) + CupsPrinterDriver byte buffer (CR-02) | 8272b46 | src/claude_teletype/printing/drivers.py |
| 3 | Migrate test helpers to interleaved write/write_bytes collection | 9b0915e | tests/test_printer.py, tests/test_codepage.py |

## What Changed

- `ProfilePrinterDriver._send_raw`: `self._inner.write(data.decode("ascii", errors="replace"))` → `self._inner.write_bytes(data)`. Single-transfer atomicity kept; docstring updated.
- `CupsPrinterDriver`: `_line_buffer` is now `list[bytes]`; `write()` appends ASCII-encoded char, `write_bytes()` appends raw data (flush on `b"\n" in data`), `_flush_line()` passes `b"".join(...)` directly as `input=` to `subprocess.run` — no decode/encode round trip.
- `tests/test_printer.py`: `_collect_raw` walks `inner.mock_calls` in order merging both channels; codepage-once test inspects `byte_calls`.
- `tests/test_byte_integrity.py`: 4 tests covering raw path, codepage text path, CUPS path, and the composed ppds-over-CUPS stack; sentinel byte 0xb5 asserted verbatim.

## TDD Gate Compliance

RED: 14fcf93 (all 4 tests failed with 0xb5 → 0x3f). GREEN: 8272b46 (all 4 pass). REFACTOR: not needed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] tests/test_codepage.py atomicity-lock tests hardcoded the old str channel**
- **Found during:** Task 3 (file was in the verify list but not in files_modified)
- **Issue:** `test_newline_is_single_atomic_write_with_crlf_and_reinit` and `test_newline_atomic_on_codepage_profile` asserted the newline transfer arrived via `("write", str)` — the channel _send_raw no longer uses
- **Fix:** Expectations updated to `("write_bytes", bytes)`; the locked one-call invariant itself is unchanged
- **Files modified:** tests/test_codepage.py
- **Commit:** 9b0915e

## Verification

- `uv run pytest tests/test_byte_integrity.py -q` — 4 passed (was 4 failed pre-fix)
- `uv run pytest tests/test_printer.py tests/test_codepage.py tests/test_output.py tests/test_markdown.py -q` — 209 passed
- Full suite: 907 passed, 2 failed — both pre-existing `tests/test_usb_backend.py` failures (`ModuleNotFoundError: No module named 'usb'`, pyusb absent in this environment; unrelated to this plan)
- `grep 'decode("ascii"' src/claude_teletype/printing/drivers.py` — zero hits
- test_printer.py test count unchanged (136) — nothing deleted to pass

## Known Stubs

None.

## Threat Flags

None — argv to `lp` remains the fixed list `["lp","-o","raw","-d",name]` with payload only via `input=` bytes (T-31-01 mitigation upheld); no new dependencies (T-31-SC).

## Deferred Issues

- tests/test_usb_backend.py: 2 pre-existing failures from missing `usb` module in this environment (see deferred-items.md).

## Self-Check: PASSED

All created files and task commits (14fcf93, 8272b46, 9b0915e) verified present.
