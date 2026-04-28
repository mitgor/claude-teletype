# Phase 24: TUI File Picker - Context

**Gathered:** 2026-04-28
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous run, skip_discuss=true)

<domain>
## Phase Boundary

Users in the main chat session press a keybinding, browse markdown files starting from cwd, see the resolved path of the highlighted file, and either pick one to print or cancel back to the chat.

Covers PICK-01..PICK-05.

</domain>

<decisions>
## Implementation Decisions

### TUI architecture (matches existing patterns)
- New module: `src/claude_teletype/file_picker_screen.py`
- Class: `FilePickerScreen(Screen[Path | None])` — full Screen, NOT ModalScreen, matching `PrinterSetupScreen` and `TypewriterScreen` patterns (gate-style screens, not overlays)
- Uses Textual's `DirectoryTree` widget (built-in), filtered to `.md` and `.markdown` extensions
- Shows resolved absolute path of highlighted file in a `Static` widget at top or bottom
- Two key bindings: `enter` to select, `escape` to cancel (returns None)
- Optional `q` or `ctrl+c` for cancel as well

### Keybinding entry from main TUI
- New keybinding on `TeletypeApp` (the main chat TUI in `src/claude_teletype/tui.py`)
- Suggested: `ctrl+o` (mnemonic "open file") — verify it doesn't conflict with existing Textual reserved bindings
- Action handler `action_print_markdown` pushes `FilePickerScreen` and registers a callback to handle the result

### Result handling
- Picker callback receives `Path | None`
- If `None` (cancelled): return to chat without side effects
- If `Path`: read the file, instantiate MarkdownRenderer with active profile + WordWrapper-bounded text channel, render through to printer
- Wire into existing pipeline: text channel → pacer → WordWrapper → output multiplexer (TUI Log + ProfilePrinterDriver); style channel → driver.write_bytes
- Style speed dialog (typewriter vs instant) is Phase 26's territory — for Phase 24, the picker just hands the path to a "render markdown" coroutine; speed mode dialog wires in later

### File filtering
- DirectoryTree's `filter_paths` hook filters visible files to `.md` and `.markdown` extensions; directories always shown
- Hidden directories (`.git`, `.venv`, `__pycache__`, etc.) are filtered out — too noisy for a markdown picker

### Path display
- Resolved absolute path of currently-highlighted node appears in a Static widget that updates on tree cursor changes
- Display format: `<absolute path>` — no truncation; let Textual handle overflow

### Cancel-back semantics
- Picker close (cancel or selection) pops back to the chat screen with no leftover state
- App should NOT consume the keybinding while the picker is active (avoid recursive picker open)

### Test strategy
- Add `tests/test_file_picker_screen.py` modeled on existing `tests/test_printer_setup_screen.py`
- Use Textual's `Pilot` test fixture for keyboard simulation
- Test cases: picker opens with cwd as root; .md files visible; non-md files hidden; directories navigable; resolved path displays; enter selects; escape cancels; ctrl+o from main TUI opens picker

### Plan layout
Two plans recommended:
- **24-01 (Wave 1):** FilePickerScreen widget + DirectoryTree filtering + path-display + tests
- **24-02 (Wave 2, depends on 24-01):** Wire keybinding + action handler in TeletypeApp; integration test from chat → picker → result callback. The actual "render to printer" hookup is stubbed here (logs path); Phase 26 wires the speed dialog and full pipeline.

### Claude's Discretion
- Exact keybinding (ctrl+o vs ctrl+m vs other) — verify no Textual conflicts
- Static-widget layout (top vs bottom; width)
- Whether to filter hidden dirs by extension list, name list, or DirectoryTree filter callback

</decisions>

<canonical_refs>
## Canonical References

### Project files
- `src/claude_teletype/printer_setup_screen.py` — model for full-Screen pattern, action handlers, callback usage
- `src/claude_teletype/tui.py` — TeletypeApp class; existing keybinding setup; how to push screens and handle results
- `src/claude_teletype/typewriter_screen.py` — another Screen pattern reference
- `src/claude_teletype/markdown.py` — MarkdownRenderer (Phase 23) — the consumer of the picked path
- `tests/test_printer_setup_screen.py` — Pilot-based TUI test pattern

### External
- Textual DirectoryTree widget docs: https://textual.textualize.io/widgets/directory_tree/
- Textual Pilot testing: https://textual.textualize.io/guide/testing/

</canonical_refs>

<specifics>
## Specific Ideas

- The picker hands a `Path` back to the caller; the caller is responsible for opening + reading the file. Keep the picker pure (no I/O beyond DirectoryTree's tree-loading).
- Wiring into the chat is intentionally minimal in Phase 24 — Phase 26 brings the speed dialog and transcript integration. For Phase 24, picking a path can simply log it via `notify()` for the user to confirm the picker works end-to-end.

</specifics>

<deferred>
## Deferred Ideas

- Recents list (PICK-06) — Future Requirements
- Configurable notes_dir (PICK-07) — Future Requirements
- Per-print speed dialog (FLOW-01..05) — Phase 26
- Transcript integration (TXN-01..03) — Phase 26
- Print preview screen (PREV-01) — Future Requirements

</deferred>

---

*Phase: 24-tui-file-picker*
*Context auto-generated 2026-04-28*
