# Deferred items discovered during Phase 25 execution

## 25-01 ruff E501 in main() (pre-existing on master)

Four `Line too long` warnings in src/claude_teletype/cli.py inside `main()`:
- Line 485 (master)/514 (post-25-01): comment line documenting profile resolution chain
- Line 510 (master)/539 (post-25-01): typer.echo error string for unknown printer
- Line 487 (master)/676 (post-25-01): discover_printer call with profile=
- Line 514 (master)/703 (post-25-01): saved_printer_profile lookup condition

Confirmed pre-existing via `git stash && uv run ruff check`. Out of scope for
Plan 25-01 per executor scope boundary (Rule: only auto-fix issues directly
caused by current task changes). Tracked here so a future cleanup pass can
shorten these lines without conflating that with feature work.

## 25-01 generic-profile interactive CUPS prompt

When `claude-teletype print <file>` is invoked without --device, --printer,
or a TOML printer_profile, the helper calls `discover_printer(profile=None)`
which falls into `select_printer()` -- an interactive `Select printer [1-3]:`
loop. On a non-tty session (e.g. CI smoke, scripted call), the prompt fails
and re-prompts forever.

This is PRE-EXISTING behavior of `discover_printer()` (lines 866-871 of
src/claude_teletype/printer.py) and is the documented "no profile = generic
CUPS selection" path. It is NOT a regression from Plan 25-01 -- the same
path is hit by `claude-teletype --no-tui hello` when CUPS sees multiple
printers and no profile is set.

Phase 26 will address this through:
1. Smart-startup defaulting to the saved printer (already working in main()
   per smart-startup logic from Phase 19).
2. Speed dialog flow that runs BEFORE the print, guaranteeing a printer is
   selected.

For Plan 25-01 the fix is "use --printer or --device or set
printer_profile in config.toml" -- documented in the SUMMARY.
