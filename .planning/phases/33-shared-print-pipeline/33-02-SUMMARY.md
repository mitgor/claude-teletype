---
phase: 33-shared-print-pipeline
plan: 02
subsystem: tui
tags: [pipeline, wr-01, t-33-07, thread-worker, mutual-exclusion, tdd]
requires:
  - "33-01 (printing/pipeline.py::render_document + PrintCancelled)"
provides:
  - "tui.py::_print_worker — @work(thread=True, exclusive=True, group='print') adapter over render_document (PIPE-01 TUI half)"
  - "Escape cancels an in-flight paced print via worker.cancel() → is_cancelled → PrintCancelled (WR-01 / PIPE-02)"
  - "_print_active/_driver_busy printer mutual-exclusion guards — single-writer driver access (T-33-07)"
affects:
  - "34 (any further pipeline edits are now one-place in printing/pipeline.py)"
tech-stack:
  added: []
  patterns:
    - "Thread-worker print with per-char cancel_check; UI calls via call_from_thread"
    - "Worker-group discriminator for driver exclusivity (group='print' vs everything else)"
key-files:
  created: []
  modified:
    - src/claude_teletype/tui.py
    - tests/test_tui.py
decisions:
  - "Mutual exclusion implemented purely from self.workers state (group + is_finished) — no new flags"
  - "on_input_changed live keystroke echo also guarded (Rule 2): it was an unguarded driver writer the plan's guard list missed"
metrics:
  duration: "~25m"
  completed: "2026-07-19"
---

# Phase 33 Plan 02: TUI Print Thread-Worker Adapter Summary

**One-liner:** Replaced tui.py's ~90-line duplicated print pipeline with a `@work(thread=True, group="print")` adapter over the shared `render_document` (escape now cancels mid-print with clean style state, WR-01), and added worker-based printer mutual exclusion so chat, typewriter mode, live input echo, and printing never interleave driver bytes (T-33-07).

## What Was Built

- **`tui.py::_run_print_pipeline`** (sync entry, same name/callers): printer-connected guard → `_driver_busy()` refusal ("Printer busy") → `_print_active()` double-print refusal → file read (OSError → notify) → profile lookup → "Printing..." notify → dispatches `_print_worker`.
- **`tui.py::_print_worker`**: `@work(thread=True, exclusive=True, group="print")`; calls `render_document` with `cancel_check=lambda: worker.is_cancelled` (via `get_current_worker()`); `PrintCancelled` → "Print cancelled" warning, `Exception` → "Print failed" error, else "Printed" — all notifies through `call_from_thread`. Never closes `self.printer`. Default sleep_fn sleeps the worker thread, not the event loop.
- **Mutual exclusion (T-33-07)**: `_print_active()` (any unfinished group="print" worker) guards `on_input_submitted` (before any `_printer_write`), `action_open_markdown`, `action_enter_typewriter`, and `on_input_changed` (live echo — see deviations). `_driver_busy()` (any unfinished non-"print" worker — covers chat stream AND TypewriterScreen's `_process_keys`) guards `_run_print_pipeline`.
- **Deleted**: the duplicated pacer/WordWrapper/chunk_writes/MarkdownRenderer/transcript-collector body — tui.py now has exactly one `render_document(` call; zero rendering internals in the print path.
- **Tests** (8 new in tests/test_tui.py, TDD): worker dispatch (kwargs + cancel_check non-None), escape-cancel (binding → worker.cancel() → cancel_check flip), style-clean-on-cancel (real pipeline, bold-heavy doc, ESC F asserted after mid-render cancel), failure-survives, no-printer guard, and three mutual-exclusion tests (chat-refused-during-print incl. guard-clears-after-cancel, print-refused-during-stream, print-refused-during-typewriter).

## Verification

- `uv run pytest -q` → 958 passed, 2 failed — both `tests/test_usb_backend.py` `ModuleNotFoundError: 'usb'`, the pre-declared worktree-env artifact (960 on-main equivalent vs 952 baseline; gate ≥932 satisfied)
- `grep -v '^#' tui.py | grep -c 'render_document('` == 1; `time.sleep` in the print-path section == 0; `_print_active|_driver_busy` refs == 8 (2 defs + 6 call sites, one more than planned due to the on_input_changed guard)
- RED-discipline verified by temporary reversion (each restored before commit):
  - cancel_check dropped from `_print_worker` → escape-cancel test FAILED
  - `_print_active()` guard removed from `on_input_submitted` → chat-refused test FAILED
  - `_driver_busy()` guard removed from `_run_print_pipeline` → both stream and typewriter refusal tests FAILED
  - `_driver_busy()` narrowed to stream-only → typewriter refusal test FAILED
  - `finally: renderer.close()` removed from pipeline.py (temporary, file restored, never committed) → style-clean test FAILED

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 3c4c363 | refactor(33-02): thread-worker adapter over render_document + guards |
| 2 (RED) | 13c2519 | test(33-02): cancel/dispatch/mutual-exclusion tests (RED on live-echo hole) |
| 2 (GREEN) | 60075a6 | fix(33-02): guard live input echo during print (T-33-07) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] on_input_changed live keystroke echo guarded**
- **Found during:** Task 2 (the chat-refused test's "no chat bytes reached the driver" assertion failed RED with `['\n', 'You:']`)
- **Issue:** The plan guarded on_input_submitted / action_open_markdown / action_enter_typewriter, but `on_input_changed` echoes every typed character to the printer live — an unguarded driver writer that interleaves bytes mid-print, violating the plan's own single-writer truth (T-33-07).
- **Fix:** `_print_active()` early-return in `on_input_changed` after `_prev_input_value` tracking is updated (so post-print typing doesn't mis-echo a stale diff). Covered by the RED→GREEN chat-refused test.
- **Files modified:** src/claude_teletype/tui.py
- **Commit:** 60075a6

**2. [Rule 1 - Bug in test design] Style-clean test doc reshaped for real pacing granularity**
- **Found during:** Task 2
- **Issue:** WordWrapper batches output per word/line chunk, so a single 600-char bold word paces only ~16 sleeps and rendered in <0.1s — the cancel landed after completion.
- **Fix:** Doc changed to one bold span of 500 short words (one paced chunk per word, ~1s+ uncancelled), cancel at 0.05s. Test asserts both "cancelled" notify (render did not complete) and ESC F bold_off (finally ran).
- **Files modified:** tests/test_tui.py
- **Commit:** 13c2519

## TDD Gate Compliance

RED commit 13c2519 (`test(...)`) precedes GREEN commit 60075a6 (`fix(...)`); Task 1's `refactor(...)` commit predates the test commit but the plan's RED discipline (guard reversions) was executed and is documented above.

## Known Stubs

None — no placeholder values, empty-data wirings, or TODO markers introduced.

## Threat Flags

None — no new surface beyond the plan's threat model. T-33-04/05/06/07 mitigations implemented and test-asserted (T-33-07 additionally hardened via the on_input_changed guard).

## Notes for Verifier

- `tests/test_usb_backend.py` 2 failures are the pre-declared worktree-env `ModuleNotFoundError: 'usb'` artifact; both pass on main.
- No modifications to STATE.md, ROADMAP.md, cli.py, or printing/pipeline.py (pipeline.py was temporarily edited for one RED check and restored via `git checkout --` before any commit; `git log` touches only tui.py and test_tui.py).

## Self-Check: PASSED

- src/claude_teletype/tui.py `_print_worker` — FOUND
- tests/test_tui.py mutual-exclusion tests — FOUND
- Commits 3c4c363, 13c2519, 60075a6 — FOUND in git log
