# Phase 25: claude-teletype print CLI Subcommand - Context

**Gathered:** 2026-04-28
**Status:** Ready for planning
**Mode:** Auto-generated

<domain>
## Phase Boundary

Users print a markdown file in one shot from the shell — either by passing the path directly or by launching the picker and exiting after the print — without ever entering the chat TUI.

Covers CLI-01..CLI-04.

</domain>

<decisions>
## Implementation Decisions

### CLI architecture
- Add new Typer subcommand `print` to the existing `app = typer.Typer(...)` in src/claude_teletype/cli.py
- Pattern: `@app.command()` with name="print" or function name; mirror the existing `@config_app.command()` pattern for consistency
- Signature: `def print_md(path: Optional[Path] = None, ...)`. With path → render; without path → launch picker (Phase 26's pipeline). For Phase 25, no-path falls back to error or stub since picker integration is Phase 26.
- Honors all existing config layers: TOML, env, CLI flags (use the same `_resolve_config()` helper that `main` uses)

### Command behavior
- **CLI-01**: `claude-teletype print <path>` reads <path>, instantiates MarkdownRenderer with the configured profile + driver, prints, exits 0
- **CLI-02**: `claude-teletype print` (no path) launches FilePickerScreen — but this requires running a Textual app. For Phase 25, two options:
   1. Print error if no path passed: "path required for `claude-teletype print` (picker support: TODO Phase 26)"
   2. Launch a minimal-Textual-app wrapper that just shows the picker and prints on selection
   
   Choose option 2 (minimal Textual wrapper) since CLI-02 explicitly requires it. The wrapper is a `PickerOnlyApp(App)` that pushes FilePickerScreen on mount and exits after handling result. Reuses Phase 24's FilePickerScreen.
- **CLI-03**: Same config layer chain as `main` — load TOML, apply env, apply CLI flags. Use existing `_resolve_config()` from cli.py.
- **CLI-04**: Path validation; non-zero exit + error message on missing/non-regular file. Use Typer's exit codes.

### Driver wiring (one-shot mode, no chat session)
- Build the printer driver chain the same way `main` does: discover_all() to pick a printer or use saved config, instantiate ProfilePrinterDriver
- For `--no-tui`-style CLI-only printing: bypass TUI entirely, just send through the driver
- For picker mode (CLI-02): mount minimal Textual app, hand selection to renderer, print, exit

### Speed mode handling
- Phase 26 owns the per-print speed dialog. For Phase 25, default to "instant" (just emit through the driver as-fast-as-possible) OR follow profile.instant_output default. Pacing applies only when integrated through pacer.py — which IS the chat path. The CLI subcommand can use a simpler emit loop: text → WordWrapper → driver.write directly.
- Document this as a Phase 26 hookup point in the SUMMARY: "speed dialog will replace the immediate-emit shortcut here"

### Test strategy
- tests/test_cli_print.py: invoke the CLI via Typer's CliRunner (existing pattern in tests/test_cli.py)
- Cases: print with valid path emits expected output, print with missing path exits non-zero, print with directory exits non-zero, print honors --profile flag, print honors --device flag, picker-mode at minimum opens (mock the Textual app or assert the entrypoint exists)

### Plan layout
Two plans:
- **25-01 (Wave 1):** CLI subcommand with explicit path argument (CLI-01, CLI-03, CLI-04). Render + driver wiring. Tests via CliRunner.
- **25-02 (Wave 2, depends on 25-01):** No-path picker-mode launching minimal Textual wrapper that uses FilePickerScreen, then emits through the same driver chain. (CLI-02)

### Claude's Discretion
- Exact command name (print vs print-file) — recommend `print` for brevity
- Whether to share a `_render_to_driver(path, config, driver)` helper between CLI and Phase 26's TUI integration — strongly recommended for DRY
- How to handle a path that's a `.txt` or other non-markdown extension (treat as markdown anyway, or refuse?) — recommend: accept any UTF-8 text file, since markdown is just text with markers

</decisions>

<canonical_refs>
## Canonical References

### Project files
- `src/claude_teletype/cli.py` — existing Typer app, `_resolve_config`, `_PromptFriendlyGroup`
- `src/claude_teletype/markdown.py` — MarkdownRenderer
- `src/claude_teletype/printer.py` — driver classes
- `src/claude_teletype/profiles.py` — get_profile, resolve_style
- `src/claude_teletype/file_picker_screen.py` — Phase 24's picker
- `src/claude_teletype/wordwrap.py` — WordWrapper
- `tests/test_cli.py` — CliRunner test pattern

</canonical_refs>

<specifics>
## Specific Ideas

The CLI should print straight through `WordWrapper(width=profile.columns)` → `ProfilePrinterDriver.write(char)` for text and `ProfilePrinterDriver.write_bytes(bytes)` for style codes. No pacer for Phase 25 — that's Phase 26's speed dialog. End the print job with `driver.end_response()` then `driver.close()`.

</specifics>

<deferred>
## Deferred Ideas

- Per-print speed dialog (Phase 26)
- Transcript integration (TXN-01..03 in Phase 26)
- Background printing while TUI active (out of scope; CLI is "exit after print")

</deferred>

---

*Phase: 25-claude-teletype-print-cli-subcommand*
*Context auto-generated 2026-04-28*
