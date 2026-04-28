---
phase: 26-speed-dialog-buffer-transcript
plan: 01
subsystem: tui
tags: [tui, modal-screen, pacer, buffer-chunking, speed-dialog, instant-mode, radioset, time-sleep]

# Dependency graph
requires:
  - phase: 21-printer-profile-data-model
    provides: PrinterProfile.instant_output (FLOW-02 default selector) and PrinterProfile.buffer_bytes (FLOW-04 chunk size)
  - phase: 23-markdown-renderer
    provides: MarkdownRenderer with text_output_fn / style_output_fn channels (renderer never emits '\n' on style channel)
  - phase: 25-claude-teletype-print-cli-subcommand
    provides: _render_markdown_to_driver function with locked sync 4-arg shape; preserved as backcompat default speed_mode="instant"
provides:
  - SpeedModeScreen ModalScreen[str | None] dismissing with "typewriter" / "instant" / None
  - chunk_writes(driver, data, chunk_size) free function in printer.py (FLOW-04 buffer chunking)
  - _render_markdown_to_driver speed_mode parameter (default "instant" for Phase 25 backcompat)
  - Dual-mode rendering pipeline: typewriter (per-char time.sleep + bell) vs instant (chunked style writes)
affects: [26-02, 26-03, tui.py file picker integration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - RadioSet with two RadioButtons + Print/Cancel button row inside Vertical(id="speed-dialog") modal
    - Synchronous time.sleep for per-character pacing in sync-only render helpers (reuses pacer.classify_char + CHAR_DELAYS, bypasses async pace_characters)
    - Closure-captured style_dest function wrapping chunk_writes(driver, data, profile.buffer_bytes)
    - Backward-compatible default arg pattern (speed_mode: str = "instant") preserves existing callsites without modification

key-files:
  created:
    - src/claude_teletype/speed_mode_screen.py
    - tests/test_speed_mode_screen.py
  modified:
    - src/claude_teletype/printer.py (added chunk_writes free function)
    - src/claude_teletype/cli.py (extended _render_markdown_to_driver with speed_mode param + dual-mode pipeline)
    - tests/test_printer.py (added TestChunkWrites class + import pytest)
    - tests/test_cli_print.py (added TestPrintCli26SpeedMode class)

key-decisions:
  - "chunk_writes is a free function in printer.py (not a method on ProfilePrinterDriver) — driver-agnostic, pure, trivially testable, accepts any PrinterDriver Protocol"
  - "Sync time.sleep used for typewriter pacing instead of converting _render_markdown_to_driver to async — preserves Plan 25-02's sync MarkdownPickerApp._on_pick callback shape; pacer.pace_characters async function is bypassed but its CHAR_DELAYS dict + classify_char function are reused for parity with the chat path"
  - "speed_mode defaults to 'instant' (not 'typewriter') so the two existing Phase 25 callers (_print_command_impl, MarkdownPickerApp._on_pick) keep working without modification — they passed 4 positional args before Phase 26 and inherit the no-pacer behaviour matching their pre-26 contract"
  - "Style-channel chunking lives only on the instant path (not typewriter) because typewriter mode interleaves 1-char text writes with 3–6 byte ESC bursts that are always under any realistic profile.buffer_bytes; the no-op chunking would only add overhead"
  - "Instant-mode generic-profile fallback uses buffer_bytes=256 (defensive default) — but resolve_style returns (b'', b'') for None profile so style_dest is effectively unreachable; belt-and-suspenders"
  - "chunk_writes patch target is claude_teletype.printer.chunk_writes (source module) because cli.py imports it locally inside the function body — matches the patch-target convention documented at the top of tests/test_cli_print.py"
  - "SpeedModeScreen __init__ defensively coerces unknown default_mode values to 'typewriter' rather than raising — Phase 26-02/26-03 callers will pass 'typewriter' or 'instant' derived from profile.instant_output, but a junk value (e.g. user-edited config) shouldn't crash the dialog"

patterns-established:
  - "ModalScreen with RadioSet + button row: SpeedModeScreen mirrors SettingsScreen's compose() shape (Vertical wrapper, BINDINGS escape→cancel, on_button_pressed dispatch by button.id, action_cancel→dismiss(None))"
  - "Buffer-aware byte chunking: chunk_writes(driver, data, chunk_size) splits payload into ceil(L/N) write_bytes calls; raises ValueError on chunk_size<=0; no-op on empty data"
  - "Dual-mode render pipeline: speed_mode branch builds different (text_dest, style_dest) closures, then both feed into the same MarkdownRenderer + WordWrapper.flush + driver.end_response sequence — the rendering plumbing stays identical, only the per-char/per-burst destination differs"

requirements-completed: [FLOW-01, FLOW-02, FLOW-03, FLOW-04]

# Metrics
duration: 5min 52s
completed: 2026-04-28
---

# Phase 26 Plan 01: Speed Dialog + Buffer Chunking + Dual-Mode Pipeline Summary

**Per-print speed selection (typewriter vs instant) wired end-to-end through SpeedModeScreen modal, buffer-aware chunk_writes helper for impact-printer byte-fragility, and a backwards-compatible speed_mode parameter on `_render_markdown_to_driver` that keeps Phase 25 callers untouched.**

## Performance

- **Duration:** 5min 52s
- **Started:** 2026-04-28T22:20:24Z
- **Completed:** 2026-04-28T22:26:16Z
- **Tasks:** 2
- **Files modified:** 6 (2 new, 4 modified)

## Accomplishments

- **SpeedModeScreen ModalScreen** (FLOW-01, FLOW-02): New `src/claude_teletype/speed_mode_screen.py` implements `ModalScreen[str | None]` with two-radio compose + Print/Cancel buttons. Dismisses with `"typewriter"`, `"instant"`, or `None` (cancel/escape). `default_mode` parameter accepts `"typewriter"` or `"instant"` — caller derives from `profile.instant_output` per FLOW-02 (juki/oki → typewriter; citizen-cts2000 → instant). Defensive fallback to `"typewriter"` on unknown values.
- **chunk_writes helper** (FLOW-04): New free function in `src/claude_teletype/printer.py` splits a bytes payload into `chunk_size`-byte slices via repeated `driver.write_bytes` calls. `ValueError` on `chunk_size <= 0`; no-op on empty data. Designed to prevent CH341 USB-LPT byte-fragility on impact printers (Juki/OKI buffer_bytes=64).
- **Dual-mode render pipeline** (FLOW-03 + FLOW-04): `_render_markdown_to_driver` gains optional fifth parameter `speed_mode: str = "instant"`. Typewriter mode wraps the WordWrapper output_fn with synchronous per-char `time.sleep` (using `pacer.classify_char` + `CHAR_DELAYS` multipliers) plus bell on `'\n'` (unless `config.no_audio`). Instant mode wraps the style-channel output with `chunk_writes(driver, data, profile.buffer_bytes)`. Default `"instant"` preserves Phase 25 callsites verbatim — the 27 existing tests still pass.
- **22 new tests, 0 regressions:** Test count 653 → 675 (9 SpeedModeScreen Pilot tests + 7 chunk_writes unit tests + 6 speed_mode wiring tests). Phase 25 regression sentinel passing (all 27 prior `test_cli_print.py` tests still green).

## Task Commits

Each task was committed atomically per the executor protocol:

1. **Task 1: SpeedModeScreen + chunk_writes helper** — `76faf95` (feat)
2. **Task 2: speed_mode parameter wiring** — `f9616c8` (feat)

## Files Created/Modified

### Created

- `src/claude_teletype/speed_mode_screen.py` (98 lines) — `SpeedModeScreen(ModalScreen[str | None])` with compose, on_button_pressed, action_cancel, BINDINGS, CSS
- `tests/test_speed_mode_screen.py` (115 lines) — 9 tests covering MRO, defensive default_mode, compose contents, default selection per mode, dismiss values for typewriter/instant/cancel/escape

### Modified

- `src/claude_teletype/printer.py` — added `chunk_writes(driver, data, chunk_size)` free function (~36 lines) at module bottom
- `src/claude_teletype/cli.py` — extended `_render_markdown_to_driver` with `speed_mode: str = "instant"` parameter + dual-mode rendering body (~80 lines added/changed)
- `tests/test_printer.py` — added `import pytest`, `_RecorderDriver` test helper, and `TestChunkWrites` class with 7 tests (~85 lines)
- `tests/test_cli_print.py` — added `TestPrintCli26SpeedMode` class with 6 tests (~165 lines)

## Locked Contracts (for Plan 26-02 and 26-03)

These signatures are LOCKED for downstream waves and must not change without coordination:

### `SpeedModeScreen` public interface

```python
class SpeedModeScreen(ModalScreen[str | None]):
    def __init__(self, default_mode: str = "typewriter", **kwargs) -> None: ...
    # dismisses with "typewriter" | "instant" | None
```

**Caller pattern (Plan 26-02 in tui.py, Plan 26-03 in cli.py picker callback):**

```python
default = "instant" if (profile and profile.instant_output) else "typewriter"
self.push_screen(
    SpeedModeScreen(default_mode=default),
    callback=lambda choice: ...,  # choice is "typewriter" | "instant" | None
)
```

### `chunk_writes` signature

```python
def chunk_writes(driver: PrinterDriver, data: bytes, chunk_size: int) -> None: ...
```

- Raises `ValueError` on `chunk_size <= 0`
- No-op on empty data
- Calls `driver.write_bytes(slice)` once per chunk; never calls `driver.write` (text channel)
- Synchronous; no inter-chunk sleeps (sleeps reserved for call-site if needed)

### `_render_markdown_to_driver` extended signature

```python
def _render_markdown_to_driver(
    path: Path,
    config,
    all_profiles: dict,
    resolved_profile,
    speed_mode: str = "instant",  # NEW in Plan 26-01 — default = Phase 25 behaviour
) -> int: ...
```

- `speed_mode in {"typewriter", "instant"}` — invalid values return 1 with stderr message before driver discovery
- `speed_mode="instant"` (default): style channel routed through `chunk_writes(driver, data, profile.buffer_bytes)`; text channel goes straight to `driver.write` (no pacing). Matches Phase 25 observable behaviour for any profile (instant was the Phase 25 implicit mode).
- `speed_mode="typewriter"`: text channel applies `time.sleep(base_delay * CHAR_DELAYS[classify_char(c)])` per char + bell on `'\n'` via `audio.make_bell_output()` (skipped if `config.no_audio`). Style channel goes straight to `driver.write_bytes` (no chunking — style bursts are tiny ESC seqs).

**Plan 26-03 will update both Phase 25 callsites** (`_print_command_impl`, `MarkdownPickerApp._on_pick`) to pass `speed_mode` explicitly after the SpeedModeScreen has resolved the user's choice.

## Verification Gates

All plan-required gates passed:

| Gate | Result |
|------|--------|
| `uv run pytest -q` | **675 passed** (target: ≥674; baseline 653 + 22 new) |
| `uv run pytest tests/test_cli_print.py -v` | **33 passed** (Phase 25 regression sentinel — 27 prior + 6 new) |
| `uv run pytest tests/test_tui_file_picker_keybinding.py -v` | **10 passed** (no Phase 24 regression) |
| Symbol existence smoke | `from claude_teletype.speed_mode_screen import SpeedModeScreen; from claude_teletype.printer import chunk_writes; from claude_teletype.cli import _render_markdown_to_driver` → OK |
| `inspect.signature(_render_markdown_to_driver).parameters['speed_mode'].default` | `'instant'` |
| `SpeedModeScreen.__mro__[:3]` | `(SpeedModeScreen, ModalScreen, Screen)` |
| ruff check (new files) | Clean (existing F841 `pilot` warnings in test pattern match `tests/test_settings_screen.py`; no new categories introduced) |
| Two atomic `feat(26-01):` commits | `76faf95` + `f9616c8` |

## Deviations from Plan

**None — plan executed exactly as written.**

The single test-mechanic adjustment (patching `claude_teletype.printer.chunk_writes` rather than `claude_teletype.cli.chunk_writes`) was anticipated by the patch-target convention documented at the top of `tests/test_cli_print.py`: "patches must therefore target the SOURCE modules ... NOT `claude_teletype.cli.discover_printer`". `chunk_writes` is imported locally inside `_render_markdown_to_driver`, so the same convention applies. This is consistent with the existing `discover_printer` patch pattern and is not a deviation from the plan's intent.

## Threat Model — Mitigations Verified

Per the plan's `<threat_model>` section:

| Threat ID | Mitigation | Test Coverage |
|-----------|-----------|---------------|
| T-26-01 | `chunk_writes` raises `ValueError` on `chunk_size <= 0` | `test_zero_chunk_size_raises`, `test_negative_chunk_size_raises` |
| T-26-02 | `_render_markdown_to_driver` validates `speed_mode in {"typewriter", "instant"}` at function entry; returns 1 with stderr message | `test_invalid_speed_mode_returns_1` (also asserts `discover_printer.assert_not_called()` — short-circuits before driver work) |
| T-26-03 | (accepted) Error messages echo path + OSError text only — same risk profile as Phase 25 | n/a |
| T-26-04 | (accepted) Phase 25 already streams char-by-char through WordWrapper; typewriter path adds `time.sleep` but doesn't buffer | n/a |

No new threat surface introduced beyond what the plan declared.

## Self-Check: PASSED

**Files verified to exist:**
- `src/claude_teletype/speed_mode_screen.py` — FOUND
- `tests/test_speed_mode_screen.py` — FOUND
- `src/claude_teletype/printer.py` — FOUND (modified, contains `chunk_writes`)
- `src/claude_teletype/cli.py` — FOUND (modified, contains `speed_mode`)
- `tests/test_printer.py` — FOUND (modified, contains `TestChunkWrites`)
- `tests/test_cli_print.py` — FOUND (modified, contains `TestPrintCli26SpeedMode`)

**Commits verified:**
- `76faf95` — FOUND in `git log`
- `f9616c8` — FOUND in `git log`

**Test count verified:** 675 passing (≥674 plan target)

## Next: Plan 26-02 + 26-03

- **Plan 26-02 (Wave 2):** `MarkdownRenderer.close()` for safe-cancel mid-render (FLOW-05). Will need to flush any open style_off bytes before driver shutdown.
- **Plan 26-03 (Wave 3):** Wire `SpeedModeScreen` into `tui.py::_handle_picker_result` (replacing Phase 24's `notify()` stub) and `cli.py::MarkdownPickerApp._on_pick`. Both callsites push `SpeedModeScreen(default_mode=...)`, await the dismiss, then call `_render_markdown_to_driver(..., speed_mode=choice)` or abort on `None`. Also wires `transcript.write_printed_file(path, body)` per TXN-01..TXN-03.

The dual-mode pipeline shipped in 26-01 is the foundation both downstream plans build on; SpeedModeScreen + chunk_writes are ready to be exercised end-to-end by Plan 26-03's integration test.
