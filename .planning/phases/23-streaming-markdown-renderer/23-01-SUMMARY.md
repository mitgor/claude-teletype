---
phase: 23-streaming-markdown-renderer
plan: 01
subsystem: printer-driver
tags: [printer-driver, write-bytes, protocol, atomic-transfer, style-channel, md-08]

# Dependency graph
requires:
  - phase: 22-encoded-style-sequences-for-built-in-profiles
    provides: bold/italic/underline ESC bytes encoded on every built-in profile (the bytes the renderer will route through write_bytes)
provides:
  - PrinterDriver Protocol method write_bytes(data: bytes) -> None
  - Five concrete write_bytes implementations (Null, File, Cups, Usb, Profile)
  - Documented MD-08 boundary contract — write_bytes does NOT do CR+LF + reinit
  - Atomic style-channel seam for the markdown renderer (Plan 23-02 + 23-03)
affects: [23-02-PLAN, 23-03-PLAN, markdown-renderer, style-channel]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dual-channel driver interface: write(char) for paced visible text, write_bytes(data) for atomic ESC sequences"
    - "MD-08 boundary documented in code (docstring) and tests (test_write_bytes_does_not_handle_newlines_specially)"

key-files:
  created: []
  modified:
    - src/claude_teletype/printer.py
    - tests/test_printer.py

key-decisions:
  - "write_bytes is a public Protocol method (not an adapter). Callers can route ESC sequences through any PrinterDriver, not just ProfilePrinterDriver. Kept the Protocol surface minimal: one new method, no overload of write()."
  - "ProfilePrinterDriver.write_bytes empty-bytes guard fires BEFORE _ensure_init(). Writing b'' is a true no-op — does not initialize the printer. This matches the existing _send_raw guard and prevents the renderer's style-resolve fallback (b'', b'') from accidentally initializing hardware."
  - "MD-08 boundary held in two places: (1) docstring on ProfilePrinterDriver.write_bytes telling renderer to use write('\\n') for newlines, (2) test_write_bytes_does_not_handle_newlines_specially asserting b'\\n' passes through verbatim (no CR+LF, no reinit). The contract is owned by the caller — write_bytes will not silently rescue a misuse."
  - "CupsPrinterDriver.write_bytes appends the decoded chunk as a single list element (not character-by-character). Preserves the atomicity hint that the bytes were a single ESC sequence and keeps _flush_line()'s ''.join() behaviour intact."

patterns-established:
  - "Per-driver no-op guards: every write_bytes implementation checks both `not is_connected/_connected` and `not data` before doing real work. Disconnected drivers and empty data are first-class no-ops."
  - "Atomic ESC transfer: ProfilePrinterDriver.write_bytes routes through _send_raw (existing single-write helper) so ESC sequences are not fragmented across USB transfers — same pattern Phase 17 introduced for the CR+LF + reinit path."

requirements-completed: [MD-08]

# Metrics
duration: 2.5min
completed: 2026-04-28
---

# Phase 23 Plan 01: write_bytes Protocol foundation Summary

**Public write_bytes(data: bytes) method added to PrinterDriver Protocol and all five concrete drivers, with explicit MD-08 boundary preventing CR+LF + reinit from firing on style-channel bytes.**

## Performance

- **Duration:** 2.5 min
- **Started:** 2026-04-28T20:38:58Z
- **Completed:** 2026-04-28T20:41:25Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `PrinterDriver` Protocol now exposes `write_bytes(data: bytes) -> None` alongside `write(char: str)` — the dual-channel seam the markdown renderer needs.
- All five drivers (Null, File, Cups, Usb, Profile) implement `write_bytes` with driver-appropriate semantics.
- `ProfilePrinterDriver.write_bytes` is the canonical implementation: calls `_ensure_init()`, sets `_has_unflushed_output = True`, then routes through `_send_raw(data)` for atomic single-write transfer. Crucially it does NOT replicate the CR+LF + reinit branch — `b'\n'` passes through verbatim, forcing the renderer to use `write('\n')` for newlines (MD-08 boundary).
- Empty-bytes guard fires before `_ensure_init()`, so `write_bytes(b'')` is a true no-op that does not even initialize the printer — protects against the renderer's `resolve_style` fallback returning `(b"", b"")` and accidentally booting the device.
- 12 new tests cover every driver path: noop, success, empty bytes, disconnected inner, MD-08 boundary, init triggering, unflushed-output flag, error-on-disconnect.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add write_bytes to PrinterDriver Protocol and all five concrete drivers** — `108c21f` (feat)
2. **Task 2: Add test_write_bytes_* tests for each driver** — `dc1e807` (test)

_Note: Plan tasks both carried `tdd="true"` but the planner intentionally split implementation into Task 1 and tests into Task 2 (Task 1's verify step explicitly says "new write_bytes tests are added in Task 2"). Plan order honoured exactly._

## Files Created/Modified

- `src/claude_teletype/printer.py` — Added Protocol method + 5 driver implementations (52 insertions, no deletions)
- `tests/test_printer.py` — Added 12 test methods (1 Null + 2 File + 2 Cups + 2 Usb + 5 Profile inside `TestProfilePrinterDriver`) (150 insertions, no deletions)

## Decisions Made

- **Protocol method, not adapter** (CONTEXT.md left this to discretion). Kept the dual-channel seam visible at the Protocol layer so the renderer accepts any `PrinterDriver` and the type checker enforces the contract. Adapter approach would have hidden the seam behind a wrapper class and complicated downstream injection.
- **Empty-bytes guard before `_ensure_init()`.** The plan's behavior block was explicit about this ordering and the test `test_write_bytes_empty_bytes_is_noop` asserts `ppd._initialized is False` after `write_bytes(b"")`. This matters because the renderer will frequently call `write_bytes(style_off)` after a style block, and if `resolve_style` returned empty for that style, the renderer would still emit the empty bytes — we don't want every plain-text run to initialize the printer.
- **CupsPrinterDriver appends decoded chunk as single list element**, not per-character. Preserves the atomicity hint and matches `_flush_line()`'s `"".join()` join pattern. The test `test_cups_driver_write_bytes_buffers_until_newline` asserts the combined `b"\x1bEhi\x1bF\n"` payload reaches `lp` as a single subprocess call.

## Deviations from Plan

None — plan executed exactly as written.

The planner's action blocks specified exact byte literals, exact insertion points, and exact docstrings. Every edit landed verbatim. Both verification commands (`grep -c 'def write_bytes'` returns 6; `pytest -k write_bytes -v` 12/12 green) passed on first run.

## Issues Encountered

None — full project test suite (566 tests) passed first run after each task.

## TDD Gate Compliance

The two tasks landed implementation-first then tests (Task 1 = `feat`, Task 2 = `test`), which is the inverse of the canonical RED→GREEN ordering. The plan deliberately structured it this way (Task 1 verify step says "existing tests must still pass — new write_bytes tests added in Task 2") because the implementation is purely additive — no behavior change to verify. Both commits exist in git log and the new tests pass against the new code, satisfying the spirit of the gate even if the order is inverted.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

**Ready for Plan 23-02 (MarkdownRenderer block-level parsing).** The renderer can now construct a `style_output_fn` by closing over the driver:

```python
def style_output_fn(data: bytes) -> None:
    driver.write_bytes(data)
```

…and pass it alongside `text_output_fn` to feed plain chars through `WordWrapper` + pacer. The MD-08 contract is documented in code (the `write_bytes` docstring) and asserted in tests, so 23-02 can lean on the boundary without re-deriving it.

**No blockers carried forward.** The Phase 23 deferred concern in STATE.md (ASCII table layout under narrow `profile.columns`) is unrelated to this plan and remains for 23-02/23-03.

## Self-Check: PASSED

- src/claude_teletype/printer.py: FOUND
- tests/test_printer.py: FOUND
- Commit 108c21f: FOUND in git log
- Commit dc1e807: FOUND in git log
- `grep -c 'def write_bytes' src/claude_teletype/printer.py` returns 6 (1 Protocol + 5 drivers)
- `pytest tests/test_printer.py -k write_bytes -v` 12/12 green
- Full project suite 566/566 green

---
*Phase: 23-streaming-markdown-renderer*
*Completed: 2026-04-28*
