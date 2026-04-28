# Phase 26: Speed Dialog, Buffer Chunking, Cancel & Transcript Integration - Context

**Gathered:** 2026-04-28
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous run, skip_discuss=true)

<domain>
## Phase Boundary

Closing phase of v1.5. Wraps the Phase 23 renderer + Phase 24 picker + Phase 25 CLI with:
- a per-print speed dialog (typewriter pacing vs instant)
- buffer-aware chunking in instant mode (using Phase 21's profile.buffer_bytes)
- safe cancel that closes any open style codes
- transcript integration for printed files

Covers FLOW-01..FLOW-05 and TXN-01..TXN-03.

</domain>

<decisions>
## Implementation Decisions

### Speed dialog (FLOW-01, FLOW-02)
- New ModalScreen `SpeedModeScreen(ModalScreen[str | None])` in `src/claude_teletype/speed_mode_screen.py`
- Two options: "Typewriter pacing" (default) and "Instant"
- Default selection follows `profile.instant_output` for the active printer profile (FLOW-02)
- Returns the choice as a string ("typewriter" / "instant") or None on cancel
- Displayed before render begins; on cancel, the print job is aborted cleanly

### Pacing path (FLOW-03)
- Typewriter mode reuses existing `pacer.py` (apply_pacing async function) and audio pipeline (`audio.py`)
- The text channel of MarkdownRenderer is fed through the pacer; style channel bypasses pacer (style codes are control sequences, not user-visible chars)
- This integrates with `tui.py`'s existing chat streaming pattern — same audio handle, same delay

### Buffer chunking (FLOW-04)
- New helper `chunk_writes(driver: PrinterDriver, data: bytes, chunk_size: int)` either as a free function or a method on ProfilePrinterDriver
- Used in instant mode: when emitting accumulated output, split at `profile.buffer_bytes` boundaries; brief inter-chunk pause (`await asyncio.sleep(0.001)` or similar) so impact printers don't overrun
- For typewriter mode, chunking is irrelevant — bytes are emitted one char at a time anyway
- Integration point: instant mode's emit loop wraps `driver.write` and `driver.write_bytes` to honor chunk_size

### Safe cancel (FLOW-05)
- The MarkdownRenderer must expose a way to "abort" mid-render that flushes any open style_off bytes
- Option A: Add `MarkdownRenderer.close()` method that emits style_off for any open emphasis (uses existing `_close_open_styles()` from Phase 23)
- Option B: Wrap render() in try/except so the caller can call `_close_open_styles()` on cancel
- Recommend Option A — public `close()` method or a context-manager pattern
- The TUI cancel keybinding (e.g. `escape` during a print) calls renderer.close() and driver.end_response() to leave the printer in clean state

### Transcript integration (TXN-01..TXN-03)
- Update `transcript.py` to add `write_printed_file(path: Path, body: str)` helper that writes a "Printed file: {path}" header followed by the body
- Wire the call in tui.py's `_handle_picker_result(Path)` after rendering completes (replacing the Phase 24 notify() stub)
- For CLI subcommand (Phase 25): if a transcript file is configured, write the printed-file entry; otherwise no-op
- TXN-02: only the plain-text rendered body goes to transcript — NOT the raw markdown source, NOT the ESC bytes. The renderer's text_output_fn channel is the right source — capture it via a list-collector callback parallel to the printer pipe.
- TXN-03: only write if a transcript writer exists. Both TUI (chat session) and CLI may or may not have one configured.

### Wiring summary

For the TUI chat-session path (tui.py):
1. User presses ctrl+o → FilePickerScreen
2. Picker returns Path → `_handle_picker_result(path)`
3. Push SpeedModeScreen → user picks "typewriter" or "instant"
4. Read file
5. Build text-channel collector (for transcript) + WordWrapper → pacer (if typewriter) → ProfilePrinterDriver.write
6. Build style-channel pipe → ProfilePrinterDriver.write_bytes (chunked if instant)
7. Instantiate MarkdownRenderer with both channels and active profile
8. await renderer.render(text)
9. driver.end_response()
10. transcript.write_printed_file(path, collected_text)
11. Cancel keybinding (e.g. escape) calls renderer.close() and aborts the await

For the CLI path (cli.py):
1. `_render_markdown_to_driver` (Phase 25) gets extended:
   - Accept optional `speed_mode: str = "instant"` parameter
   - In typewriter mode, route through pacer (same async pattern as TUI)
   - In instant mode, chunk_writes for the style channel
   - Optionally write printed-file transcript entry if config has one configured

### Plan layout
Three plans:
- **26-01 (Wave 1):** SpeedModeScreen + pacer integration + buffer chunking helper. Modifies speed_mode_screen.py (new), cli.py (helper updates), printer.py (chunk_writes if added there). Covers FLOW-01..FLOW-04.
- **26-02 (Wave 2, depends on 26-01):** MarkdownRenderer.close() + cancel keybinding + safe-state cleanup tests. Modifies markdown.py and tui.py. Covers FLOW-05.
- **26-03 (Wave 3, depends on 26-01 and 26-02):** Transcript integration: transcript.py write_printed_file, tui.py wire-up replacing Phase 24's notify() stub, cli.py wire-up. Covers TXN-01..TXN-03.

### Claude's Discretion
- Whether SpeedModeScreen is its own file or inlines in tui.py
- Pacer integration: extend existing `apply_pacing` or write a parallel "render with pacing" wrapper
- Where chunk_writes lives (printer.py module function, ProfilePrinterDriver method, or new utility module)
- Cancel mechanism: keybinding name (escape, ctrl+c, q)

</decisions>

<canonical_refs>
## Canonical References

### Project files
- `src/claude_teletype/markdown.py` — MarkdownRenderer (extend with close())
- `src/claude_teletype/tui.py` — _handle_picker_result (replace notify() stub)
- `src/claude_teletype/cli.py` — _render_markdown_to_driver (extend for speed mode)
- `src/claude_teletype/pacer.py` — apply_pacing async function
- `src/claude_teletype/audio.py` — bell + keystroke sound pipeline
- `src/claude_teletype/transcript.py` — make_transcript_output factory
- `src/claude_teletype/printer.py` — ProfilePrinterDriver write/write_bytes
- `src/claude_teletype/profiles.py` — profile.buffer_bytes, profile.instant_output
- `src/claude_teletype/file_picker_screen.py` — FilePickerScreen
- `src/claude_teletype/settings_screen.py` — ModalScreen pattern reference for SpeedModeScreen

</canonical_refs>

<specifics>
## Specific Ideas

- The integration test (in 26-03 or via final E2E test) renders a sample markdown file end-to-end through the TUI path → picker → speed dialog → renderer → printer mock + transcript collector, asserting all 8 FLOW + TXN requirements pass.
- The cancel test: start render, immediately fire cancel, assert no leaked style_on bytes (every style_on has matching style_off in the byte stream up to abort point).

</specifics>

<deferred>
## Deferred Ideas

- Pause/resume mid-print — too complex for v1.5
- Speed mode persisted in user config — Phase 26 keeps it per-print only
- Print queue (multiple files) — out of scope

</deferred>

---

*Phase: 26-speed-dialog-buffer-transcript*
*Context auto-generated 2026-04-28*
