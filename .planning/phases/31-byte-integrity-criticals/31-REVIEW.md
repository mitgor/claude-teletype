---
phase: 31-byte-integrity-criticals
reviewed: 2026-07-18T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - src/claude_teletype/printing/drivers.py
  - src/claude_teletype/teletype.py
  - tests/test_byte_integrity.py
  - tests/test_printer.py
  - tests/test_teletype.py
  - tests/test_codepage.py
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 31: Code Review Report

**Reviewed:** 2026-07-18
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Narrative Findings (AI reviewer)

## Summary

Reviewed the Phase 31 byte-integrity fixes against the original findings and the diff range `42946d8..HEAD`. Verdict on the three targeted findings:

- **CR-01 closed.** `ProfilePrinterDriver._send_raw` (drivers.py:246-257) now routes through `inner.write_bytes` — no ASCII round-trip. Verified all four inner drivers (Null/File/Usb/Cups) implement `write_bytes`, and the ppds sentinel byte 0xb5 survives in `test_byte_integrity.py` (BYTE-01).
- **CR-02 closed.** `CupsPrinterDriver` buffers `list[bytes]` end to end (drivers.py:108, 117, 122, 144-151); `write_bytes` no longer decodes. `lp` receives the exact byte stream (BYTE-02 verified, including the composed ppds-over-CUPS round trip).
- **WR-02 closed.** teletype.py:45 sends init via `write_bytes` (strict `decode("ascii")` crash gone), teletype.py:80 sends `reset_sequence` as one atomic `write_bytes` call (per-byte `chr()` loop gone), and teletype.py:71-72 catches `KeyboardInterrupt` around the read loop with cleanup ordered correctly in `finally` (tcsetattr first, then printer teardown, then close). Locked constraints hold: CR+LF+reinit remains one transfer (drivers.py:288-299, locked by test_codepage.py:259-279), `write_bytes` remains the raw channel, newlines stay on `write("\n")` (WordWrapper emits newlines as separate calls — verified in wordwrap.py:59-63, 88, 104).

CUPS flush semantics were traced for the composed paths: newline via `_send_raw(b"\r\n"...)` hits `write_bytes`, which flushes on `b"\n" in data`; ESC-only sequences (cut/reset) are picked up by `end_response`'s `inner.flush()` hook (drivers.py:385-387) or by `CupsPrinterDriver.close()`. Partial-line handling on close is correct: `close()` flushes any residual buffer, and `_flush_line` clears the buffer *before* the subprocess call, so a failed flush cannot be double-sent.

No critical issues found. Two warnings and three informational items below.

## Warnings

### WR-01: CupsPrinterDriver never detects lp submission failure (silent output loss)

**File:** `src/claude_teletype/printing/drivers.py:124-132`
**Issue:** `_flush_line` only flips `_connected` on `SubprocessError`/`OSError` (lp binary missing, timeout). When `lp` runs but exits non-zero — wrong queue name, queue disabled, CUPS daemon rejecting the job — `subprocess.run(..., capture_output=True)` returns normally, the returncode is discarded, and every subsequent line is silently dropped into a failing queue while `is_connected` stays `True`. The buffer is cleared before the call, so the data is unrecoverable. This is a data-loss-adjacent gap in the exact channel Phase 31 hardened; pre-existing, but it sits in the reviewed byte path.
**Fix:**
```python
result = subprocess.run(
    ["lp", "-o", "raw", "-d", self._name],
    input=line,
    capture_output=True,
    timeout=30,
)
if result.returncode != 0:
    self._connected = False
```

### WR-02: Second Ctrl-C during teletype teardown skips printer reset and driver.close()

**File:** `src/claude_teletype/teletype.py:71-81`
**Issue:** The `except KeyboardInterrupt` only wraps the read loop. The `finally` teardown then performs real printer I/O — form feed (a physical page eject that takes seconds on a Juki daisywheel) followed by `reset_sequence` and `driver.close()`. cbreak leaves ISIG on, so a second Ctrl-C (a common user habit when a printer appears hung) raises `KeyboardInterrupt` *inside* the `finally`: terminal restore has already run (good ordering), but the reset sequence and `close()` (including `usb.util.dispose_resources`) are skipped, leaving the printer un-reset and the USB interface claimed. The exception then propagates out of `run_teletype`; the `--teletype` CLI path (cli.py:896-947) has no `KeyboardInterrupt` handler, so the user gets a raw traceback.
**Fix:** Make the teardown interrupt-tolerant, e.g.:
```python
finally:
    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    try:
        if profile is not None and profile.formfeed_on_close:
            driver.write("\f")
        elif profile is None:
            driver.write("\f")
        if profile is not None and profile.reset_sequence:
            driver.write_bytes(profile.reset_sequence)
    except KeyboardInterrupt:
        pass  # still reach close()
    finally:
        driver.close()
```

## Info

### IN-01: CupsPrinterDriver.close() bypasses the _connected guard that flush() enforces

**File:** `src/claude_teletype/printing/drivers.py:153-155`
**Issue:** `flush()` checks `self._line_buffer and self._connected`; `close()` checks only `self._line_buffer`. In practice the buffer is always empty after a disconnect (`_flush_line` clears before attempting, and writes early-return once disconnected), so this cannot currently double-send — but the asymmetry is a trap for future edits that reorder `_flush_line`.
**Fix:** `if self._line_buffer and self._connected: self._flush_line()` in `close()`, matching `flush()`.

### IN-02: write_bytes flushes on any 0x0A byte, including binary ESC parameters

**File:** `src/claude_teletype/printing/drivers.py:150-151`
**Issue:** `if b"\n" in data` treats a 0x0A *parameter* byte (e.g. ESC/POS `b"\x1bd\x0a"` — feed 10 lines — or a chunk_writes slice landing mid-sequence) as a line terminator, splitting one ESC sequence across two `lp` jobs. Bytes and ordering are preserved on a raw queue, so this is a granularity quirk, not corruption — but it contradicts the "callers must not pass newline bytes through write_bytes" contract being only advisory.
**Fix:** Acceptable as-is given the documented contract; optionally flush only on trailing `data.endswith(b"\n")` to reduce mid-sequence splits.

### IN-03: Teletype forwards typed non-ASCII characters as '?'

**File:** `src/claude_teletype/teletype.py:68` (via `drivers.py:80, 199`)
**Issue:** WR-02 fixed the strict-decode *crash*, but typed non-ASCII input still reaches `driver.write`, where File/Usb drivers apply `encode("ascii", errors="replace")` — a typed "ц" prints as "?". No codepage path exists in teletype mode even when the profile defines `text_codec`. Deliberate scope limit, recording so it isn't mistaken for a regression.
**Fix:** If ever needed: encode via `profile.text_codec` (after `_ensure_codepage`-style command) instead of routing through `write`.

## Test Assessment

- `tests/test_byte_integrity.py` — sound contract lock; the 0xb5 sentinel and the `b"\x3f" not in sent` assertions would catch any reintroduced ASCII round-trip. Interleaved `mock_calls` reconstruction preserves ordering correctly.
- `tests/test_teletype.py` — new WR-02 tests correctly pin: one `write_bytes` call for init with 0xb5 intact (line 149-165), exactly one atomic reset call with explicit no-fragment assertion on the text channel (line 171-189), and full cleanup ordering on `KeyboardInterrupt` (line 195-208). The strict `encode("ascii")` in `_written_bytes` is intentionally fail-loud.
- `tests/test_printer.py` `_collect_raw` rewrite (line 512-525) correctly interleaves both channels via `mock_calls`, keeping `startswith(init)` ordering assertions valid.
- `tests/test_codepage.py` — atomicity assertions correctly migrated to the `write_bytes` channel.
- Verified: `test_byte_integrity.py`, `test_teletype.py`, `test_codepage.py` — 41 passed.

---

_Reviewed: 2026-07-18_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
