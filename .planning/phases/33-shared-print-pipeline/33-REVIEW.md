---
phase: 33-shared-print-pipeline
reviewed: 2026-07-19T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - src/claude_teletype/printing/pipeline.py
  - src/claude_teletype/cli.py
  - src/claude_teletype/tui.py
  - tests/test_pipeline.py
  - tests/test_cli_print.py
  - tests/test_tui.py
findings:
  critical: 2
  warning: 2
  info: 3
  total: 7
status: issues_found
---

# Phase 33: Code Review Report

**Reviewed:** 2026-07-19
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

The shared pipeline (`render_document`) itself is solid: speed-mode validation before any driver call, LIFO style-off via `finally: renderer.close()`, transcript fan-out taps only the text channel, driver never closed, MD-08 newline routing preserved. The CLI adapters are correct thin wrappers and the WR-04 picker driver pre-resolution is properly implemented and well tested.

The defects are all concentrated in the TUI thread-worker adapter's mutual-exclusion model. The T-33-07 guards (`_print_active`, `_driver_busy`) are built on `Worker.is_finished`, and for Textual **thread** workers that is a lie after cancel: `Worker.cancel()` cancels the wrapping asyncio task awaiting `loop.run_in_executor(...)`, which transitions the worker to `CANCELLED` **immediately while the executor thread keeps running** (the thread only stops at its next `cancel_check` poll, which in typewriter mode may be a full char-sleep away, plus the `finally` style-off writes after that). Every guard, plus `on_unmount`'s `printer.close()`, trusts this state. Two concrete broken paths fall out of that single root cause (CR-01, CR-02). A third unguarded driver mutator (Settings profile swap) was missed by the guard sweep (WR-01).

## Critical Issues

### CR-01: Cancelled print thread keeps writing to the driver while every T-33-07 guard reports idle

**File:** `src/claude_teletype/tui.py:528-541, 543-556, 607-633` (root cause: guards built on `worker.is_finished`)
**Issue:** `_print_worker` is `@work(thread=True)`. On Escape, `action_cancel_stream` → `Worker.cancel()` → `self._task.cancel()` (textual/worker.py:416-421). The wrapping task is awaiting `loop.run_in_executor(...)` (textual/worker.py:326); cancelling it raises `CancelledError` at the await point and `_run` sets `state = CANCELLED` **immediately** — but the executor thread cannot be cancelled and continues running `render_document` until its next between-characters `cancel_check` poll. In typewriter mode that poll is behind a blocking `time.sleep(base_delay * multiplier)` (pipeline.py:119-123), so the thread keeps writing for up to a full char-delay, then emits the style-off bytes from `finally: renderer.close()`. During that whole window `_print_active()` and `_driver_busy()` return False (worker is "finished"), so:

- `on_input_submitted` accepts a chat submit (the user's prompt was deliberately preserved in the input, making Escape-then-Enter the natural gesture) and writes turn separators / "Claude: " label to the driver (tui.py:858-886),
- a new print can be dispatched (`_run_print_pipeline` guards pass),
- `action_enter_typewriter` / live keystroke echo (`on_input_changed`, gated only on `_print_active()`) resume writing,

all interleaving with the dying print thread's final text bytes and its style-off ESC bytes — violating the single-writer contract T-33-07 exists to enforce and the Phase 31 byte-ordering locks (MD-08) on the physical device. `test_chat_refused_while_print_active` does not catch this because its `_wait_workers` helper also polls `is_finished`, then only presses Enter afterwards — the race window is precisely between cancel and real thread exit.

**Fix:** Track actual thread completion, not worker state. Set an event from inside the thread itself:

```python
# dispatch (in _run_print_pipeline, just before self._print_worker(...)):
self._print_thread_done = threading.Event()

# _print_worker body:
try:
    render_document(...)
except PrintCancelled: ...
finally:
    self._print_thread_done.set()   # runs IN the worker thread, after renderer.close()

# guards:
def _print_active(self) -> bool:
    ev = getattr(self, "_print_thread_done", None)
    if ev is not None and not ev.is_set():
        return True
    return any(w.group == "print" and not w.is_finished for w in self.workers)
```

`_driver_busy()` needs no change (it guards the opposite direction), but `on_input_changed`, `on_input_submitted`, `action_enter_typewriter`, `action_open_markdown`, and `_run_print_pipeline` all route through the fixed `_print_active()` automatically.

### CR-02: Quit during print: `on_unmount` closes the driver while the print thread is still writing; style-off bytes hit a closed handle (T-33-02 violated on the quit path)

**File:** `src/claude_teletype/tui.py:322-328` (`on_unmount`), interacting with `_print_worker` (607-645)
**Issue:** Same root cause as CR-01, different broken path. On Ctrl+D during a print, Textual's message loop exits → `self.workers.cancel_all()` (textual/app.py:3335) flags the thread but does not wait for it → `_shutdown()` dispatches `Unmount` → `on_unmount` runs `self.printer.close()`. With an API backend (or no live subprocess), `_kill_process()` returns immediately, so `printer.close()` executes while the print thread is typically still inside a char sleep. The thread then wakes, `cancel_check` raises `PrintCancelled`, and `finally: renderer.close()` writes the style-off ESC bytes to a **closed** driver:

1. The write raises → the `except Exception` arm calls `self.call_from_thread(self.notify, ...)` on an app that is no longer running → `RuntimeError` out of the worker thread (an unhandled second failure masking the first).
2. The style-off bytes never reach the printer → the physical device is left with bold/italic engaged, which is exactly the leaked-state outcome T-33-02 ("style-off on EVERY exit path") is locked against.

**Fix:** In `on_unmount`, wait for real thread completion before closing the driver (pairs with the CR-01 event):

```python
async def on_unmount(self) -> None:
    await self._kill_process()
    ev = getattr(self, "_print_thread_done", None)
    if ev is not None:
        # Cancelled worker exits within one char-delay; 5s is a generous cap.
        await asyncio.get_running_loop().run_in_executor(None, ev.wait, 5.0)
    if self.printer is not None:
        self.printer.close()
    ...
```

Also make `_print_worker`'s `call_from_thread` calls tolerant of a stopped app (`try/except RuntimeError`), so shutdown-time notifies cannot turn a clean cancel into a worker error.

## Warnings

### WR-01: Settings screen is an unguarded driver mutator — profile hot-swap during an active print corrupts output and rebinds `self.printer` under the worker

**File:** `src/claude_teletype/tui.py:439-457` (`action_open_settings`), `647-695` (`_apply_settings`), `731-773` (`_apply_printer_profile`)
**Issue:** The T-33-07 guard sweep covered chat submit, live echo, the picker, and typewriter mode — but not Settings (Ctrl+, is reachable mid-print). If the user changes the printer profile while a print is in flight:

- `ProfilePrinterDriver.swap_profile()` (drivers.py:357-366) replaces `self._profile` and clears `_initialized`/`_codepage_sent` from the event-loop thread while the print thread is writing through the same wrapper — the **next print character re-fires the new profile's init sequence mid-document**, and the new profile's ESC codes no longer match the style-on bytes already emitted (the eventual style-off close uses the new profile's sequences).
- In the wrap/re-discover arms, `self.printer` is rebound to a brand-new driver while the worker keeps writing to the old object; `_printer_write` now targets a different device than the in-flight print, and the old driver is never closed.

This is a data race between the event loop and the worker thread on shared driver state, not just interleaved output.

**Fix:** Refuse (or defer) the profile-swap arm while a print is active — mirror the existing guards:

```python
def action_open_settings(self) -> None:
    if self._print_active():
        self.notify("Print in progress — Escape to cancel", severity="warning")
        return
    ...
```

(Guarding only `_apply_printer_profile` would also work and keeps delay/audio edits available, but the whole-screen guard is simpler and consistent with the other T-33-07 refusals.)

### WR-02: Pipeline docstring promises a TUI-injected cancellable sleep that the TUI never injects; cancel latency is a full uninterruptible char-sleep

**File:** `src/claude_teletype/printing/pipeline.py:27-29`; `src/claude_teletype/tui.py:623-633`
**Issue:** The module docstring states the seam contract: "the TUI's thread-worker consumer in Plan 33-02 injects a cancellable sleep." `_print_worker` passes no `sleep_fn`, so the worker thread blocks in plain `time.sleep(base_delay * CHAR_DELAYS[...])` between characters. Consequences: (a) the documented contract is false — the next maintainer reading pipeline.py will assume Escape interrupts a sleep; (b) Escape response in typewriter mode is delayed by up to one full per-char sleep (newline-class multipliers make this the worst case), which also widens the CR-01 race window.

**Fix:** Either inject a cancellable sleep in `_print_worker`:

```python
def _cancellable_sleep(seconds: float) -> None:
    worker.cancelled_event.wait(seconds)   # returns early on cancel

render_document(..., sleep_fn=_cancellable_sleep, cancel_check=lambda: worker.is_cancelled)
```

(`Worker.cancel()` sets `cancelled_event`, so `wait()` doubles as an interruptible sleep) — or correct the docstring to state that the TUI accepts one-char cancel latency by design. The injection is three lines and matches the documented contract; prefer it.

## Info

### IN-01: Picker-mode CLI print never writes a transcript entry, unlike the explicit-path print

**File:** `src/claude_teletype/cli.py:570-616` (`_print_command_impl_picker`), `547-565` (`_on_pick`)
**Issue:** `_print_command_impl` builds a transcript writer from `config.transcript_dir` and passes it to the render adapter (TXN-01); the picker path passes nothing, so `claude-teletype print` (no path) silently skips the transcript entry even when `transcript_dir` is configured. Pre-existing asymmetry (present at diff base), but Phase 33 restructured this exact code path and preserved the gap.
**Fix:** Build the same `make_transcript_output` pair in `_print_command_impl_picker` when `config.transcript_dir` is set, pass `transcript_write` through the factory closure into `_on_pick`, close in the launcher's `finally`.

### IN-02: Keystrokes typed during a print are permanently dropped from the printer echo, producing a fragmented prompt on paper

**File:** `src/claude_teletype/tui.py:814-836` (`on_input_changed`)
**Issue:** The guard updates `_prev_input_value` then returns while a print is active — deliberate, and it does prevent stale-diff mis-echo. But the characters typed during the print (including the `"\nYou: "` prefix, which fires only when `old_val` is empty) are never echoed; once the print finishes, echo resumes mid-string. The paper record shows a prompt fragment with no label and no leading characters. The transcript still gets the full prompt at submit, so this is cosmetic hardware output only.
**Fix:** On the first `on_input_changed` after a print finishes, echo the full `new_val` (with prefix) instead of the diff — e.g., set a `self._echo_resync = True` flag when the guard fires and handle it on the next change event.

### IN-03: `render_document` documents `source_path` as required with `transcript_write` but never validates it; `None` fails at the end of an otherwise-successful render

**File:** `src/claude_teletype/printing/pipeline.py:80-82, 168-171`
**Issue:** With `transcript_write` set and `source_path=None`, the whole document prints, then `write_printed_file(..., None, ...)` hits `Path(None).resolve()` → `TypeError` after the fact — the adapter surfaces "Print failed" for a print that physically completed. Both current adapters pass it correctly; this is a contract-hardening gap in the shared core.
**Fix:** Validate up front with the speed-mode check: `if transcript_write is not None and source_path is None: raise ValueError("source_path required when transcript_write is provided")`.

---

_Reviewed: 2026-07-19_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
