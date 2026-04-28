---
phase: 25-claude-teletype-print-cli-subcommand
plan: 02
subsystem: cli
tags: [cli, typer, textual, picker, file-picker, no-arg, app-launcher, closure-factory, cli-runner]

# Dependency graph
requires:
  - phase: 25-claude-teletype-print-cli-subcommand
    provides: "Plan 25-01 _render_markdown_to_driver(path, config, all_profiles, resolved_profile) helper -- reused VERBATIM from picker callback"
  - phase: 24-tui-file-picker
    provides: "FilePickerScreen(root=None) reused VERBATIM -- dismisses with absolute Path on enter or None on escape/q"
  - phase: 23-streaming-markdown-renderer
    provides: "MarkdownRenderer + MD-08 newline routing (transitive via _render_markdown_to_driver)"
  - phase: 19-printer-driver-config
    provides: "ProfilePrinterDriver, discover_printer, end_response (transitive via _render_markdown_to_driver)"
provides:
  - "MarkdownPickerApp(App) one-shot picker launcher built via _make_markdown_picker_app(config, all_profiles, resolved_profile, root) factory"
  - "_print_command_impl_picker(delay, device, printer) -> int -- no-path branch helper"
  - "_resolve_print_context(delay, device, printer) -> (config, all_profiles, resolved_profile) shared resolver between explicit-path and picker branches"
  - "print_md dispatch on path=None / path=Path -- 1-line branch in the Typer command"
  - "7-test TestPrintCli02PickerMode class locking dispatch + callback contract"
affects: [26-print-speed-dialog, 26-render-pipeline, 26-transcript-integration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Closure-factory pattern for one-shot Textual apps: _make_markdown_picker_app captures resolved context as closure variables, returns a fresh MarkdownPickerApp instance whose nested class body reads them (avoids polluting __init__ with constructor args, keeps the `def __init__(self): super().__init__()` shape that Textual expects)"
    - "Shared `_resolve_print_context` between branches: both `_print_command_impl` (explicit path) and `_print_command_impl_picker` (no-arg) call the same TOML < env < CLI flag resolver + profile chain. (None, None, None) error sentinel lets callers detect resolution failure without raising"
    - "Lazy textual import inside the picker factory: keeps cli.py top-level imports lightweight when the user invokes only `config show`, `diagnose`, or the explicit-path branch -- matches Plan 25-01's local-import convention for `_render_markdown_to_driver`"
    - "Typer Optional argument shape: `path: Path | None = typer.Argument(None, exists=False, ...)` with manual dispatch on `path is None` -- Typer 0.23.1 accepts `Path | None` (modern union syntax) cleanly"
    - "App._exit_code attribute convention for one-shot apps: store the helper's return value on the app instance during the dismiss callback, read it back via getattr after .run() returns -- matches the existing TeletypeApp.session_id pattern"

key-files:
  created: []
  modified:
    - "src/claude_teletype/cli.py"
    - "tests/test_cli_print.py"

key-decisions:
  - "Extracted `_resolve_print_context` shared helper from `_print_command_impl` body (option (a) from the plan) instead of duplicating the config + profile resolution into the picker branch. Both Typer branches now share TOML/env/CLI/profile resolution; if a future flag (--no-audio for the print path? a paced print delay?) is added, both call sites pick it up automatically. Plan 25-01's `_render_markdown_to_driver` signature stays untouched -- the refactor only relocates code that was already inside the same function, no behavior change to the explicit-path branch."
  - "Closure-factory rather than constructor-arg App. The picker app needs (config, all_profiles, resolved_profile) to call _render_markdown_to_driver from its dismiss callback, but Textual's App.__init__ has a fixed signature. Passing them through .__init__ subclass would force a custom super().__init__() call shape; capturing them as closure variables in the factory and reading them from the nested class body keeps the App's __init__ to `super().__init__(); self._exit_code = 0` -- minimum surface area, framework-friendly."
  - "Plan's Pilot/inspect.getsource fallback (option (b)/(c) in the action notes) was NOT needed. Option (a) -- patch.object(app_inst, 'push_screen') BEFORE calling on_mount() -- worked first try because on_mount() only calls self.push_screen, which is now the mock. No Textual compositor dependency tripped. The test gets to assert (1) push_screen was called, (2) the first positional arg is a real FilePickerScreen instance, AND (3) the callback kwarg is the bound _on_pick method -- richer than option (c)'s structural grep would have been."
  - "`Path | None` instead of `Optional[Path]` in print_md. ruff's UP045 lint prefers the modern union syntax; Typer 0.23.1 handles it identically to `Optional[Path]`. Verified empirically with CliRunner: --help renders the path argument as `[PATH]` (optional) and the dispatch fires correctly when path is omitted."
  - "Picker callback runs render synchronously inside _on_pick (NOT in a worker). The plan explicitly notes Phase 26 will refactor this when pacing lands; for Phase 25 the print is non-paced so it's just file I/O + USB write -- fast enough that the picker dismiss → render → app.exit() sequence is imperceptible. Locked in a docstring comment for future Phase 26 reference."
  - "Test patches the FACTORY (`claude_teletype.cli._make_markdown_picker_app`) to mock the entire app at the dispatch level, AND patches `claude_teletype.cli._render_markdown_to_driver` directly for the callback unit tests. The factory IS the cli-side surface; the closure-captured `_render_markdown_to_driver` reference is patched at the cli module path because the factory's `class MarkdownPickerApp` body resolves the name through the cli module's namespace, not the textual or file_picker_screen module's."

patterns-established:
  - "One-shot Textual App pattern (factory + closure): use _make_*_app() factory functions that close over context variables and return a freshly-instantiated App subclass. The caller invokes .run() and reads result attributes after return. Used here for MarkdownPickerApp; future one-shot launchers (e.g. a confirmation dialog app, a settings-edit app) should follow the same shape."
  - "Branch dispatch in Typer commands: when a Typer command has multiple modes (explicit arg vs no-arg, flag-driven mode switch), keep the @app.command function tiny -- it should just check the dispatch condition and call the appropriate _impl helper, then `raise typer.Exit(rc)`. Both helpers share resolution via a third helper. This keeps each branch's surface independently testable."
  - "Shared resolver between sibling Typer branches: when two branches need the same config + profile resolution but diverge in what they do AFTER resolution, extract a `_resolve_<thing>_context()` helper that returns the resolved tuple OR a sentinel on error. Both callers handle the sentinel uniformly (return 1, the resolver already echo'd the error). This avoids the alternative of raising typer.Exit from inside the resolver, which makes unit-testing the resolver in isolation harder."
  - "App._exit_code attribute idiom for return-code propagation: when a Textual App needs to communicate a richer result than `App.exit(result=...)` allows (or the result is consumed by a synchronous caller, not awaited), set an attribute on the app instance during the lifecycle (here: inside the dismiss callback) and `getattr(app, '_exit_code', default)` after .run() returns. Mirrors the existing TeletypeApp.session_id pattern."

requirements-completed: [CLI-02]

# Metrics
duration: 3.6min
completed: 2026-04-28
---

# Phase 25 Plan 2: Picker-Mode Launcher for `claude-teletype print` Summary

**No-path branch of `claude-teletype print`: closure-factory `_make_markdown_picker_app` builds a minimal `MarkdownPickerApp(App)` that pushes Phase 24's `FilePickerScreen` on mount and routes the dismiss callback through Plan 25-01's `_render_markdown_to_driver` (Path arm) or exits cleanly (None arm). Sibling helper `_print_command_impl_picker` shares config + profile resolution with the explicit-path branch via a freshly-extracted `_resolve_print_context`. Closes CLI-02; Phase 25 is complete (CLI-01..CLI-04 all green).**

## Performance

- **Duration:** 3.6 min
- **Started:** 2026-04-28T21:55:03Z
- **Completed:** 2026-04-28T21:58:37Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added `_make_markdown_picker_app(config, all_profiles, resolved_profile, root)` factory in `src/claude_teletype/cli.py`. Closure-captures the resolved print context, returns a fresh `MarkdownPickerApp(App)` instance whose `on_mount` pushes `FilePickerScreen(root=root)` with `self._on_pick` as the callback. The `_on_pick(result)` method handles both arms: `None` -> `_exit_code = 0; exit()` (cancel = no print), `Path` -> `_exit_code = _render_markdown_to_driver(result, config, all_profiles, resolved_profile); exit()`.
- Added `_print_command_impl_picker(delay, device, printer) -> int` sibling helper. Shares `_resolve_print_context` with the explicit-path branch (same TOML < env < CLI flag chain, same profile resolution, same auto-detect fallback), skips path validation (no path), launches the picker app via the factory, returns `getattr(picker_app, '_exit_code', 0)` after `run()`.
- Extracted `_resolve_print_context(delay, device, printer)` shared resolver. Both `_print_command_impl` (Plan 25-01) and `_print_command_impl_picker` (this plan) now call it; on unknown-profile error it emits the error message via `typer.echo(err=True)` and returns `(None, None, None)` so callers detect failure uniformly. Plan 25-01's `_print_command_impl` was refactored to use the new helper -- behavior unchanged, all 14 explicit-path/path-validation/config-chain tests still green.
- Relaxed `print_md` Typer signature: `path: Path = typer.Argument(...)` becomes `path: Path | None = typer.Argument(None, ...)`. Body dispatches: `if path is None: rc = _print_command_impl_picker(...) else: rc = _print_command_impl(...); raise typer.Exit(rc)`. Help text gained "Omit to launch the file picker" -- verified via `claude-teletype print --help`.
- 7 new tests in `TestPrintCli02PickerMode` lock the dispatch + callback contract (factory called when no path, render NOT called from dispatch, on_mount pushes a FilePickerScreen instance, Path arm calls render with closure-captured config, None arm skips render, render exit code propagates to `_exit_code`, explicit-path regression sentinel -- factory NOT called when a path is supplied).
- Full project suite: 646 -> **653 tests green** (exact match to plan estimate of +7). Phase 24's `tests/test_tui_file_picker_keybinding.py` (10 tests) keeps passing -- chat-session ctrl+o picker integration unchanged. Plan 25-01's 20 explicit-path tests all still green.

## Task Commits

Each task was committed atomically:

1. **Task 1: MarkdownPickerApp launcher + no-path dispatch in print_md** -- `c22f6e4` (feat)
2. **Task 2: TestPrintCli02PickerMode (7 tests)** -- `b7c62bd` (test)

## Files Created/Modified

- `src/claude_teletype/cli.py` -- added `_resolve_print_context`, `_make_markdown_picker_app`, `_print_command_impl_picker`. Refactored `_print_command_impl` to use the shared resolver (the config + profile resolution code moved into `_resolve_print_context` verbatim; the path-validation block stayed put). Updated `print_md` signature + body for Optional Path dispatch. +170 lines, -36 lines (net +134; the -36 is the resolution code lifted into the shared helper). NO edits to `main()`, `_chat_async`, `config show/init`, `diagnose`, `_PromptFriendlyGroup`, or `_render_markdown_to_driver` (Plan 25-01 contract preserved exactly).
- `tests/test_cli_print.py` -- appended `TestPrintCli02PickerMode` (7 tests, +162 lines), updated module docstring to reflect the new picker-mode coverage and document the patch-target convention for the new factory. Plan 25-01's 5 existing test classes (TestPrintCli01ExplicitPath, TestPrintCli04PathValidation, TestPrintCli03ConfigChain, TestPrintRenderingPipeline, TestNoRegression) untouched.

## Decisions Made

- **Option (a) for shared resolution.** Plan suggested option (a) extract `_resolve_print_context` as DRY-shared helper, OR option (b) duplicate the resolution. Chose (a). The lift was 36 lines moving from `_print_command_impl` body into a sibling function; the explicit-path branch's behavior is identical (it now calls the helper instead of inlining the same code). Both branches benefit from any future change. Plan 25-01's external contract (`_render_markdown_to_driver` signature) is unchanged.
- **Closure-factory `_make_markdown_picker_app` rather than constructor-arg App subclass.** Rationale documented in frontmatter; in short: keeps the App's `__init__` minimal (just `super().__init__(); self._exit_code = 0`), avoids the friction of overriding Textual's constructor signature. The factory closes over `config`, `all_profiles`, `resolved_profile`, `root` and the nested class reads them by name -- standard Python closure semantics, framework-agnostic.
- **Option (a) for `test_picker_app_on_mount_pushes_filepicker` worked first try.** Plan offered three test strategies for the on_mount unit test (a: patch push_screen pre-call, b: Pilot run_test, c: inspect.getsource grep). Option (a) succeeded -- the test patches `app_inst.push_screen` BEFORE calling `app_inst.on_mount()`, so the real method is replaced and Textual's compositor isn't touched. Bonus: the test asserts (1) push_screen called once, (2) first positional arg is a FilePickerScreen instance, AND (3) callback kwarg is the bound `_on_pick` method. Richer assertions than option (c)'s structural grep would have produced.
- **`Path | None` over `Optional[Path]` in `print_md`.** Plan suggested `Optional[Path]`; ruff's UP045 lint prefers the modern union syntax. Typer 0.23.1 handles `Path | None` identically (`--help` shows `[PATH]` for the optional arg, dispatch fires correctly when path is omitted). Removed the `from typing import Optional` import that was briefly added.
- **Synchronous render inside `_on_pick`.** Plan called this out as Phase 26 territory -- when pacing lands, the render must move to a Textual worker so the picker can dismiss before the print starts. For Phase 25 the print is non-paced (just file I/O + USB write inside `_render_markdown_to_driver`), so foreground execution is fine. Locked in a docstring comment for future Phase 26 reference.

## Deviations from Plan

None -- plan executed exactly as written.

The plan's action blocks were unusually thorough (full code blocks for the factory, picker impl, and shared resolver, plus three test-strategy options for the on_mount unit test). Implementation was effectively a transcription with the recommended `Path | None` lint adjustment. No Rule 1/2/3 deviations triggered, no Rule 4 architectural questions raised.

The only minor adjustment was switching from `Optional[Path]` to `Path | None` to satisfy ruff's UP045 lint -- the plan recommended `Optional` but the project uses ruff's modern-union preference. Both syntaxes are equivalent at runtime in Typer 0.23.1; the change is purely cosmetic. (Not a deviation per Rule 1/2/3 -- this is following CLAUDE.md / project lint conventions, which take precedence per `<project_context>`.)

## Issues Encountered

- **Pre-existing ruff E501 warnings in `main()`:** 4 long lines on master (lines 649, 674, 811, 838 post-edit -- these were the same 4 lines flagged in Plan 25-01's `deferred-items.md`). Confirmed pre-existing -- they appear in `main()`, which this plan does NOT modify. Out of scope per executor scope boundary. The `deferred-items.md` from Plan 25-01 still tracks them.
- **`Optional[Path]` -> `Path | None` lint adjustment:** The plan recommended `from typing import Optional` and `path: Optional[Path]`; ruff flagged this as UP045 (prefer modern union syntax). Switched to `Path | None` and removed the unused `from typing import Optional` import. Verified Typer 0.23.1 accepts the modern syntax identically. NOT a deviation -- following project lint preferences as documented in the executor `<project_context>` section.

## User Setup Required

None -- no external service configuration required.

## Next Phase Readiness

**Phase 25 is COMPLETE.** All four CLI requirements (CLI-01..CLI-04) are now closed:
- **CLI-01** (explicit path) -- Plan 25-01 (`@app.command("print")` + `_print_command_impl` + `_render_markdown_to_driver`)
- **CLI-02** (no-path picker mode) -- Plan 25-02 (this plan; `_make_markdown_picker_app` + `_print_command_impl_picker` + dispatch in `print_md`)
- **CLI-03** (config layer chain) -- Plan 25-01 (resolved into Plan 25-02's shared `_resolve_print_context` helper without behavior change)
- **CLI-04** (path validation) -- Plan 25-01 (untouched by Plan 25-02; lives in `_print_command_impl`'s explicit-path block)

**Phase 26 (speed dialog + render pipeline) inherits two clean entry points:**

1. **Chat-session entry** (`tui.py::action_open_markdown` -> `_handle_picker_result`) -- still emits the Phase 24 smoke `notify` on selection. Phase 26 will replace the notify with a paced render (presumably reusing `_render_markdown_to_driver` or its Phase-26 successor).
2. **CLI-print entry** (`cli.py::print_md` no-path branch -> `_print_command_impl_picker` -> `_make_markdown_picker_app` -> `MarkdownPickerApp._on_pick`) -- already calls `_render_markdown_to_driver` synchronously inside the picker callback. Phase 26 may either (a) refactor the synchronous call into a Textual worker so a speed dialog can run between picker dismiss and render start, or (b) replace `_render_markdown_to_driver` with a paced variant that respects `config.delay`. Either path is local to one call site.

**The `_render_markdown_to_driver(path, config, all_profiles, resolved_profile)` signature is now reused at two call sites:**
- `_print_command_impl` (explicit path)
- `MarkdownPickerApp._on_pick` (Path arm of picker callback)

If Phase 26 changes the signature (e.g. adds a `pacer` arg or replaces it with a class), it must update both call sites. Both are inside `cli.py`, no cross-file risk.

**The dual-entry duplication (chat-session vs CLI) is intentional and locked.** Phase 26 may unify them by routing both entries through a shared "print one markdown file" helper, but this plan stays in its lane -- `tui.py::_handle_picker_result` is unchanged, `_handle_picker_result` still does the Phase 24 smoke notify, the chat-session ctrl+o flow is unaffected. All 10 tests in `tests/test_tui_file_picker_keybinding.py` continue to pass.

## Self-Check: PASSED

Verified files exist and commits land:

- FOUND: `src/claude_teletype/cli.py` -- contains `_resolve_print_context`, `_make_markdown_picker_app`, `_print_command_impl_picker`, refactored `_print_command_impl`, dispatched `print_md` (`hasattr` checks pass for all four new symbols).
- FOUND: `tests/test_cli_print.py` -- now 27 tests across 6 classes (5 from Plan 25-01 + new TestPrintCli02PickerMode with 7 tests).
- FOUND: commit `c22f6e4` (Task 1: feat) verified via `git log --oneline | grep c22f6e4`.
- FOUND: commit `b7c62bd` (Task 2: test) verified via `git log --oneline | grep b7c62bd`.
- VERIFIED: `uv run pytest -q` reports `653 passed` (646 baseline after Plan 25-01 + 7 new = 653).
- VERIFIED: `uv run pytest tests/test_cli_print.py::TestPrintCli02PickerMode -v` reports 7 passed.
- VERIFIED: `uv run pytest tests/test_tui_file_picker_keybinding.py` reports 10 passed (Phase 24 chat-session picker integration intact).
- VERIFIED: `uv run claude-teletype print --help` exits 0, shows `[PATH]` (optional), and the description includes "Omit to launch the file picker".
- VERIFIED: `uv run ruff check src/claude_teletype/cli.py` reports only the 4 pre-existing E501 warnings in `main()` (same 4 lines documented in Plan 25-01's deferred-items.md). No new ruff issues from this plan.
- VERIFIED: `uv run ruff check tests/test_cli_print.py` reports "All checks passed!".
- VERIFIED: no untracked files post-commit (`git status --short` is clean).
- VERIFIED: no unintended file deletions (`git diff --diff-filter=D --name-only HEAD~2 HEAD` is empty).

---
*Phase: 25-claude-teletype-print-cli-subcommand*
*Completed: 2026-04-28*
