---
phase: 25-claude-teletype-print-cli-subcommand
plan: 01
subsystem: cli
tags: [cli, typer, markdown, print, render, config-chain, cli-runner]

# Dependency graph
requires:
  - phase: 23-streaming-markdown-renderer
    provides: MarkdownRenderer (text + style channels), MD-08 newline routing contract
  - phase: 22-printer-style-codes
    provides: BUILTIN_PROFILES with bold/italic/underline byte codes (escp, juki, citizen-cts2000, ...)
  - phase: 21-printer-profile-style-extension
    provides: PrinterProfile.columns, resolve_style fallback chain
  - phase: 19-printer-driver-config
    provides: ProfilePrinterDriver, discover_printer, end_response semantics
provides:
  - "@app.command('print') Typer subcommand for explicit-path one-shot markdown printing"
  - "_render_markdown_to_driver(path, config, all_profiles, resolved_profile) -> int reusable helper"
  - "_print_command_impl(path, delay, device, printer) -> int -- config + profile resolution + path validation"
  - "20-test CliRunner suite covering CLI-01, CLI-03, CLI-04 + helper-level pipeline + no-regression"
affects: [25-02, 26-print-speed-dialog, 26-render-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Typer subcommand registration adjacent to existing diagnose/config commands"
    - "Local imports inside print helpers (matches main()/action_open_markdown convention) to keep cli.py top-level imports lean"
    - "getattr(driver, 'end_response', None) duck-test pattern for the 5 driver implementations (only ProfilePrinterDriver/JukiPrinterDriver implement it)"
    - "wrapper.flush() between renderer.render() and driver.end_response() so the last word reaches the printer before the cut/paper-eject"
    - "driver.close() in finally guarantees device handle release on partial-render exceptions"

key-files:
  created:
    - "tests/test_cli_print.py"
  modified:
    - "src/claude_teletype/cli.py"

key-decisions:
  - "Local imports inside _render_markdown_to_driver and _print_command_impl: keeps cli.py's top-level import surface unchanged and matches the convention used by main() and action_open_markdown elsewhere in the project. Test patches accordingly target SOURCE modules (claude_teletype.printer.discover_printer) not cli.py shims."
  - "Path argument uses exists=False at the Typer layer so we can emit a clean 'Error: file not found: <abs path>' message instead of Typer's default error. Validation runs before any config load or driver discovery so bad paths exit fast without side effects."
  - "_print_command_impl is a parallel resolution path -- main()'s ~60 lines of profile-resolution logic are intentionally NOT extracted into a shared helper. Phase 26 may unify if it chooses; this plan stays in its lane (Phase 25 territory: no chat, no pacer, no transcript)."
  - "delay parameter is accepted by print_md but currently has no effect on rendering: the merge is preserved so the env-layer test (CLAUDE_TELETYPE_DELAY=10) proves apply_env_overrides ran. Phase 26's speed dialog wires it into the WordWrapper output_fn."

patterns-established:
  - "Typer @app.command() subcommand placement: AFTER existing leaf commands (diagnose), BEFORE the @app.callback main definition -- Plan 25-02's picker-mode subcommand should follow the same placement."
  - "Helper function shape: separate _print_command_impl (config+profile+validation) from _render_markdown_to_driver (driver lifecycle). Plan 25-02 reuses ONLY the latter; the picker callback handles its own validation since the picker itself constrains the result to a real Path."

requirements-completed: [CLI-01, CLI-03, CLI-04]

# Metrics
duration: 8.6min
completed: 2026-04-28
---

# Phase 25 Plan 1: claude-teletype print CLI Subcommand Summary

**`claude-teletype print <path>` Typer subcommand reusing main()'s config + profile resolution chain, rendering through MarkdownRenderer + WordWrapper + ProfilePrinterDriver in one shot with no chat session and no pacer (Phase 26 owns pacing).**

## Performance

- **Duration:** 8.6 min
- **Started:** 2026-04-28T21:41:12Z
- **Completed:** 2026-04-28T21:49:49Z
- **Tasks:** 2
- **Files modified:** 2 (1 modified, 1 created)

## Accomplishments

- Wired `@app.command("print")` into the existing Typer app, picked up by `_PromptFriendlyGroup` so `claude-teletype print foo.md` no longer collides with the `prompt` positional argument.
- Added `_print_command_impl(path, delay, device, printer)` that mirrors `main()`'s config-load → env-override → CLI-merge → profile-resolve flow exactly (no extraction; parallel resolution path), giving `print` the same TOML/env/CLI-flag layering as the chat command (CLI-03).
- Added `_render_markdown_to_driver(path, config, all_profiles, resolved_profile)` as the reusable driver-lifecycle helper Plan 25-02 will call from its picker callback. Locks the call order `renderer.render → wrapper.flush → driver.end_response → driver.close` so the last word reaches the printer before the per-response cut, and runs `close()` in `finally` so partial-render exceptions still release the device handle.
- Path validation (CLI-04) gives clean errors: missing file → `Error: file not found: <abs path>`, directory → `Error: not a regular file: <abs path>`, both exit 1 without opening the printer driver.
- 20 CliRunner tests across 5 classes lock CLI-01, CLI-03, CLI-04, the helper pipeline, and a no-regression sentinel for the existing `main`/`config`/`diagnose` surface. Full project suite goes 626 → 646 tests, all green.

## Task Commits

1. **Task 1: Add `print` Typer subcommand + helpers** — `85c5edc` (feat)
2. **Task 2: CliRunner test suite** — `4751505` (test)

_TDD smoke proven: pre-implementation, `print --help` was consumed as the `prompt` positional and the parent `--help` printed instead (no `print` in the Commands list). Post-implementation, `print --help` shows the new subcommand's own usage. RED → GREEN flip verified manually before each task; the test suite locks GREEN going forward._

## Files Created/Modified

- `src/claude_teletype/cli.py` — added `_render_markdown_to_driver`, `_print_command_impl`, and `@app.command("print") def print_md(...)`. No edits to `main()`, `_chat_async`, `config show/init`, `diagnose`, or the `_PromptFriendlyGroup` parser. +189 lines.
- `tests/test_cli_print.py` — new file. 20 tests in 5 classes: TestPrintCli01ExplicitPath (4), TestPrintCli04PathValidation (5), TestPrintCli03ConfigChain (5), TestPrintRenderingPipeline (3), TestNoRegression (3). +374 lines.

## Decisions Made

- **Local imports inside helpers** (matches existing convention in `main()` and `action_open_markdown`). Test patches accordingly target SOURCE modules (`claude_teletype.printer.discover_printer`, `claude_teletype.markdown.MarkdownRenderer`, `claude_teletype.wordwrap.WordWrapper`), NOT `claude_teletype.cli.discover_printer`. This convention is locked into the test docstring so Plan 25-02 follows the same pattern.
- **`exists=False` on the Typer Argument** so manual validation in `_print_command_impl` can emit a clean error message with the resolved absolute path. Typer's default `exists=True` error doesn't show the resolved path and the wording is awkward.
- **Parallel profile-resolution path, not a shared helper.** The Phase 25 plan explicitly forbids touching `main()`. The duplication is small (~30 lines) and the two paths have diverging needs (chat path also does backend creation, system-prompt warning, smart-startup match; print path doesn't). Phase 26 may unify.
- **`delay` parameter is currently a no-op for rendering**, but is still passed through `merge_cli_flags` so the env-layer test (`CLAUDE_TELETYPE_DELAY=10`) proves `apply_env_overrides` ran end-to-end. Phase 26's speed dialog will wire it into a paced wrapper around `driver.write`.

## Deviations from Plan

None - plan executed exactly as written.

The action blocks in 25-01-PLAN.md were unusually thorough (full code blocks for both helpers), so the implementation was effectively a transcription with minor formatting adjustments (line lengths kept under 100 to match project style). No Rule 1/2/3 deviations triggered, no Rule 4 architectural questions raised. The path validation, config chain, profile resolution, and driver lifecycle all worked exactly as the plan specified.

## Issues Encountered

- **Pre-existing ruff E501 warnings in `main()`:** 4 long lines on master (lines 485, 487, 510, 514 pre-edit). Confirmed pre-existing via `git stash && uv run ruff check`. Out of scope per executor scope boundary (only auto-fix issues directly caused by current task changes). Logged to `.planning/phases/25-claude-teletype-print-cli-subcommand/deferred-items.md` for a future cleanup pass.
- **Generic-profile interactive CUPS prompt:** When `print <file>` is invoked with no `--device`, no `--printer`, and no TOML `printer_profile`, `discover_printer(profile=None)` falls into `select_printer()`'s interactive `Select printer [1-3]:` loop. This is PRE-EXISTING behavior of `discover_printer` (also hits `--no-tui hello` in the same configuration) and the documented "no profile = generic CUPS selection" path. NOT a regression from Plan 25-01. Smart-startup logic in `main()` (Phase 19) already addresses this for the chat path; Phase 26's speed dialog will close the gap for the print path. Documented in `deferred-items.md`. Smoke verified the `--device /tmp/smoke_out.bin /tmp/smoke.md` path writes 8 bytes (`\nSmoke\n\n`) and exits 0.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

**Plan 25-02 (no-path picker mode) is unblocked.** The locked contract for the picker callback:

```python
from claude_teletype.cli import _render_markdown_to_driver
# After picker returns a Path:
exit_code = _render_markdown_to_driver(path, config, all_profiles, resolved_profile)
```

`_render_markdown_to_driver` handles its own driver lifecycle (discover_printer → end_response when present → close in finally). Plan 25-02 must NOT duplicate this logic. The picker is responsible for selecting a real Path; `_render_markdown_to_driver` will refuse to read a non-existent file (returns 1, driver not opened) so even a stale picker selection fails safely.

**Phase 26 (speed dialog + render pipeline)** has two clean integration points:
1. Replace `wrapper = WordWrapper(columns, driver.write)` with a paced wrapper that consults the speed-dialog selection -- the `_render_markdown_to_driver` body is the only callsite of `WordWrapper` in the print flow, so the change is local.
2. The `delay` parameter is already plumbed through `print_md → _print_command_impl → merge_cli_flags`, so Phase 26 can read it from `config.delay` inside the helper without touching the CLI signature.

## Self-Check: PASSED

Verified files exist and commits land:

- FOUND: `src/claude_teletype/cli.py` — contains `_render_markdown_to_driver`, `_print_command_impl`, `print_md` (`hasattr` check passed)
- FOUND: `tests/test_cli_print.py` — 20 tests, all passing in isolation and as part of full suite
- FOUND: commit `85c5edc` (Task 1: feat)
- FOUND: commit `4751505` (Task 2: test)
- VERIFIED: `uv run pytest -q` reports `646 passed` (626 baseline + 20 new = 646)
- VERIFIED: `uv run claude-teletype print --help` exits 0 and shows the subcommand's usage
- VERIFIED: smoke `--device /tmp/smoke_out.bin /tmp/smoke.md` exits 0 and writes 8 bytes (`\nSmoke\n\n`)
- VERIFIED: smoke `print /tmp/__definitely_not_there__.md` exits 1 with `Error: file not found:`
- VERIFIED: smoke `print /tmp` (directory) exits 1 with `Error: not a regular file:`
- VERIFIED: ruff clean on `tests/test_cli_print.py`; 4 E501 warnings on `cli.py` are pre-existing (confirmed via `git stash`)

---
*Phase: 25-claude-teletype-print-cli-subcommand*
*Completed: 2026-04-28*
