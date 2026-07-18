---
phase: 33-shared-print-pipeline
plan: 01
subsystem: printing
tags: [pipeline, arch-01, wr-04, refactor, tdd]
requires: []
provides:
  - "printing/pipeline.py::render_document — the ONE shared print pipeline (PIPE-01)"
  - "printing/pipeline.py::PrintCancelled — cancel exception adapters catch"
  - "CLI explicit-path + picker adapters as thin consumers of render_document"
  - "Picker driver pre-resolution before Textual owns the terminal (WR-04 / PIPE-03)"
affects:
  - "33-02 (TUI adapter consumes render_document with injected sleep_fn + cancel_check)"
  - "34 (all_profiles dead-param removal overlaps ARCH-CLEAN-03)"
tech-stack:
  added: []
  patterns:
    - "Injectable seams: sleep_fn (None sentinel, late-resolved time.sleep) + cancel_check"
    - "Single-owner driver close: close_driver kwarg; picker launcher owns close"
key-files:
  created:
    - src/claude_teletype/printing/pipeline.py
    - tests/test_pipeline.py
  modified:
    - src/claude_teletype/cli.py
    - tests/test_cli_print.py
decisions:
  - "sleep_fn default is a None sentinel resolved to time.sleep inside the typewriter branch (not an early-bound default) so patch('time.sleep') in existing tests still intercepts sync pacing"
  - "finally: renderer.close() (TUI semantics) + adapter-owned driver.close() (CLI semantics) merged as the shared contract"
  - "WR-04 fixed via pre-resolution (review option 2): interactive multi-queue selection stays available on the real terminal before picker_app.run()"
metrics:
  duration: "16m"
  completed: "2026-07-18"
---

# Phase 33 Plan 01: Shared Print Pipeline Summary

**One-liner:** Extracted the ~90-line duplicated print pipeline into `printing/pipeline.py::render_document` (cancel-safe `finally: renderer.close()`, injectable sleep_fn/cancel_check), rewired both CLI paths as thin adapters, and fixed WR-04 by resolving the picker's driver before Textual takes the terminal.

## What Was Built

- **`printing/pipeline.py`** (new, 176 lines): `render_document(driver, profile, text, *, speed_mode, base_delay_ms, no_audio, transcript_write, source_path, sleep_fn, cancel_check)` + `PrintCancelled`. Merges the cli/tui copies with semantics decided once:
  - speed_mode validated first → `ValueError` before any driver call
  - typewriter: per-char `sleep_fn(base_delay * CHAR_DELAYS[classify_char])`, bell unless no_audio, style bytes straight to `write_bytes`
  - instant: unpaced text, style chunked via `chunk_writes` at `buffer_bytes` (getattr-guarded, falsy → 256)
  - cancel_check polled between characters (both modes) → `PrintCancelled`
  - `finally: renderer.close()` on every exit path (T-33-02); `end_response` + transcript write only on success
  - transcript collector taps ONLY the text channel (TXN-02); never closes the driver
- **`cli.py` explicit-path adapter**: `_render_markdown_to_driver(path, config, resolved_profile, driver, speed_mode, transcript_write, close_driver=True)` — file read + error surfacing + close-in-finally only; pipeline body deleted (zero `MarkdownRenderer`/`WordWrapper`/`chunk_writes`/`CHAR_DELAYS` references remain). `_print_command_impl` acquires the driver itself. Dead `all_profiles` param dropped (IN-01).
- **`cli.py` picker path (WR-04)**: `_print_command_impl_picker` resolves the driver via `discover_printer` BEFORE `picker_app.run()`; the factory closure captures the pre-resolved driver; `_on_pick` renders with `close_driver=False`; the launcher closes the driver in `finally` on cancel/success/error.
- **Tests**: `tests/test_pipeline.py` (18 tests, TDD RED→GREEN) covering both modes, chunking boundaries (64→64+36, falsy→256+44), cancel-safety with style-off assertion, driver-error propagation, transcript byte-cleanliness, epilogue ordering, driver-ownership. `tests/test_cli_print.py` updated to the new signatures + 5 new WR-04 regression tests (discover→factory→run ordering, multi-queue prompt guard, close-exactly-once on cancel/failure, no discovery reachable in-app).

## Verification

- `uv run pytest tests/test_pipeline.py tests/test_cli_print.py tests/test_cli.py tests/test_markdown.py tests/test_byte_integrity.py -q` → 129 passed (Phase 31 byte contracts intact, MD-08 unchanged)
- Full suite: 939 passed, 2 failed — both `tests/test_usb_backend.py` `ModuleNotFoundError: 'usb'`, the pre-declared worktree-env artifact, unrelated to this plan
- `grep -v '^#' cli.py | grep -c 'render_document('` == 1; pipeline-internal identifiers in cli.py == 0
- No `discover_printer`/`select_printer` reference inside the picker app factory body
- tui.py untouched (`git diff --name-only` vs base: cli.py, pipeline.py, test_cli_print.py, test_pipeline.py only)

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 (RED) | 612aa11 | test(33-01): failing test suite for render_document |
| 1 (GREEN) | db5dd99 | feat(33-01): implement render_document shared pipeline core |
| 2 | 87c9348 | refactor(33-01): rewire cli.py explicit-path adapter |
| 3 | 320a940 | fix(33-01): resolve picker driver before picker_app.run() (WR-04) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] sleep_fn default changed from `time.sleep` to None sentinel**
- **Found during:** Task 2
- **Issue:** An early-bound `sleep_fn=time.sleep` default captures the function object at module import, so existing tests patching `time.sleep` could no longer intercept pacing (they would sleep for real and fail).
- **Fix:** `sleep_fn=None` default, resolved to `time.sleep` inside the typewriter branch at call time. Behavior identical (locked v1.5 sync pacing preserved); testability restored.
- **Files modified:** src/claude_teletype/printing/pipeline.py
- **Commit:** 87c9348

**2. [Rule 1 - Bug] Picker dispatch tests hung on real CUPS discovery**
- **Found during:** Task 3
- **Issue:** After the WR-04 hoist, `test_print_no_path_invokes_picker_app` (and sibling) reached the real `discover_printer`; with >= 2 real CUPS queues and CliRunner's empty stdin, `select_printer` loops forever on EOFError (test timeout).
- **Fix:** Patched `discover_printer` in the two dispatch tests (the WR-04 fix legitimately moved discovery into the dispatch path); also patched `discover_usb_device` in the multi-queue regression test so it cannot touch real hardware.
- **Files modified:** tests/test_cli_print.py
- **Commit:** 320a940

**Note (acceptance-grep nuance):** the plan's check `grep -c 'time\.sleep(' pipeline.py == 1` is satisfied by the single docstring mention; there is no bare `time.sleep(` call site — all pacing routes through `sleep_fn`, which is the criterion's intent.

## Known Stubs

None — no placeholder values, empty-data wirings, or TODO markers introduced.

## Threat Flags

None — no new network endpoints, auth paths, or trust-boundary changes beyond the plan's threat model. T-33-02 (style-state on abort) and T-33-03 (transcript ESC leakage) mitigations are implemented and test-asserted.

## Next Plan Contract (33-02)

`render_document(driver, profile, text, *, speed_mode, base_delay_ms, no_audio, transcript_write, source_path, sleep_fn, cancel_check)` raises `PrintCancelled`; never closes the driver; `finally: renderer.close()` guaranteed. The TUI adapter injects its own `sleep_fn` and `cancel_check`.

## Self-Check: PASSED

- src/claude_teletype/printing/pipeline.py — FOUND
- tests/test_pipeline.py — FOUND
- .planning/phases/33-shared-print-pipeline/33-01-SUMMARY.md — FOUND
- Commits 612aa11, db5dd99, 87c9348, 320a940 — FOUND in git log
