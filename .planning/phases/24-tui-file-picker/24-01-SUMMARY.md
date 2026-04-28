---
phase: 24-tui-file-picker
plan: 01
subsystem: ui
tags: [tui, textual, directory-tree, screen, file-picker, pilot-test, markdown]

# Dependency graph
requires:
  - phase: 23-streaming-markdown-renderer
    provides: MarkdownRenderer ready as a downstream consumer of the picked Path
provides:
  - FilePickerScreen(Screen[Path | None]) widget -- full-screen markdown picker
  - MarkdownDirectoryTree(DirectoryTree) with filter_paths override
  - HIDDEN_DIRS module-level frozenset (.git/.venv/__pycache__/node_modules/.planning)
  - MARKDOWN_SUFFIXES module-level frozenset (.md/.markdown, case-insensitive)
  - Reusable Screen[Path | None] result-typed pattern for future picker variants
  - Unit + Pilot test split pattern for Screen widgets
affects:
  - phase-24-02-keybinding-integration
  - phase-25-cli-no-arg-path

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Screen[Path | None] result-typed full-Screen (NOT ModalScreen) -- carries forward PrinterSetupScreen / TypewriterScreen pattern"
    - "DirectoryTree subclass with filter_paths override (over per-instance callable)"
    - "Module-level frozenset for filter rules (HIDDEN_DIRS, MARKDOWN_SUFFIXES) -- discoverable, greppable"
    - "Synthesized DirectoryTree.FileSelected event in Pilot tests -- avoids keyboard-timing fragility"
    - "tmp_path fixture + root= constructor parameter -- testable picker without monkeypatching cwd"

key-files:
  created:
    - src/claude_teletype/file_picker_screen.py (143 LOC)
    - tests/test_file_picker_screen.py (228 LOC)
  modified: []

key-decisions:
  - "Subclass over filter_paths callable parameter -- keeps filter logic discoverable in same module; matches Textual idioms; future PICK-06 recents extension trivial"
  - "HIDDEN_DIRS as module-level frozenset -- visible at top of file, easy to extend, not buried in a method"
  - "root: Path | None constructor parameter with Path.cwd() default -- production behavior (PICK-02) plus test-friendliness (no cwd monkeypatching)"
  - "Path display dock=bottom Static -- maximizes tree real estate; matches tui.py #status-bar pattern"
  - "q binding shown=False -- primary cancel is escape (Footer label); q is power-user shortcut without cluttering bindings strip"
  - "No enter binding -- DirectoryTree's native FileSelected (file) and expand-toggle (directory) handle enter for free; custom binding would shadow"
  - "Path(event.path).resolve() in on_directory_tree_file_selected -- belt-and-suspenders absolute-path normalization"
  - "Synthesized FileSelected event in test_file_selected_dismisses_with_path -- driving event handler directly is the established pattern when Pilot keyboard timing is unreliable; mirrors test_printer_setup_screen.py _on_connect direct calls"
  - "str(Static.render()) for content assertions -- Static has no .renderable in this Textual version; render() returns Content with str() = display text. Avoids private attrs"
  - "Docstring rephrased 'not a ModalScreen' -> '(not a modal overlay)' so plan verification rule grep -c ModalScreen file_picker_screen.py == 0 holds (locked decision still documented)"

patterns-established:
  - "Pattern: full-Screen result-typed pattern Screen[T | None] (auth/picker dialogs return value or None). Reusable for future picker variants"
  - "Pattern: DirectoryTree subclass with filter_paths override + module-level frozenset filter rules"
  - "Pattern: unit + Pilot test split for Screen widgets (filter_paths/structural pure-Python; mount/dismiss via Pilot)"
  - "Pattern: tmp_path-based markdown fixtures for picker tests, paired with root= constructor parameter"
  - "Pattern: synthesized DirectoryTree.FileSelected event for deterministic file-selection assertions (avoids tree-expansion timing)"

requirements-completed: [PICK-02, PICK-03, PICK-04, PICK-05]

# Metrics
duration: 3.4min
completed: 2026-04-28
---

# Phase 24 Plan 01: TUI File Picker Widget Summary

**FilePickerScreen(Screen[Path | None]) full-screen markdown picker with DirectoryTree filter (.md/.markdown + non-noisy dirs), resolved-path Static display, and escape/q dismiss-with-None contracts -- 11 tests green.**

## Performance

- **Duration:** 3.4 min
- **Started:** 2026-04-28T21:14:17Z
- **Completed:** 2026-04-28T21:17:41Z
- **Tasks:** 2
- **Files created:** 2

## Accomplishments

- FilePickerScreen widget delivers all four requirements (PICK-02 cwd-rooted navigation, PICK-03 markdown filter + noise reduction, PICK-04 cancel-back semantics, PICK-05 resolved-path display + dismiss-with-Path) in a single 143-LOC module.
- MarkdownDirectoryTree subclass + filter_paths override hides .git/.venv/__pycache__/node_modules/.planning directories AND every non-markdown file extension in one pass; case-insensitive suffix match.
- 11 tests cover every must_haves truth: 5 filter_paths unit tests, 1 case-insensitive extension test, 1 structural Screen-not-ModalScreen test, 4 Pilot integration tests (mount/path-display/escape/q), 1 synthesized-FileSelected dismiss-with-Path test.
- Full project test suite green: 605 baseline + 11 new = 616 passing (matches plan verification prediction exactly).
- Reusable Screen[Path | None] result-typed pattern documented for plan 24-02 keybinding integration and Phase 25 CLI no-arg entry.

## Task Commits

Each task was committed atomically:

1. **Task 1: Build FilePickerScreen widget** - `d363689` (feat)
2. **Task 2: Pilot-based test suite** - `9df22d2` (test)

Note: Task 1 `tdd="true"` cycle confirmed RED (ModuleNotFoundError before implementation) -> GREEN (smoke test OK after implementation). Task 2 added the full test suite + a docstring tweak (see Deviations) in a single test() commit since the doc fix was a verification-driven correction surfaced while running the plan's grep checks.

## Files Created/Modified

- `src/claude_teletype/file_picker_screen.py` (143 LOC) -- FilePickerScreen + MarkdownDirectoryTree + HIDDEN_DIRS + MARKDOWN_SUFFIXES
- `tests/test_file_picker_screen.py` (228 LOC) -- 11 tests (filter unit + structural + Pilot integration + synthesized FileSelected)

## Decisions Made

All major decisions are listed in the frontmatter `key-decisions` block. Highlights:

- **Subclass over filter_paths callable parameter** -- keeps filter logic discoverable in the same module as the screen; matches Textual idioms; future PICK-06 recents extension trivial. Plan-suggested approach; affirmed during Task 1 implementation as the cleaner of the two options.
- **`root: Path | None` constructor parameter with `Path.cwd()` default** -- production behavior (PICK-02) plus test-friendliness without monkeypatching `Path.cwd()`. This single design choice eliminated `chdir` fixtures from the test plan and made the unit + Pilot split clean.
- **Synthesized `DirectoryTree.FileSelected` event** in the dismiss-with-Path test -- driving the event handler directly is the established pattern when Pilot keyboard timing is unreliable. Mirrors `test_printer_setup_screen.py` direct `_on_connect` calls. Documented as a key pattern for future picker tests.
- **`str(Static.render())` for content assertions** -- Static has no `.renderable` in this Textual version; `render()` returns a `Content` object whose `str()` is the displayed text. Surfaced as a Rule 1 fix during the first test run; documented inline so future contributors don't reach for the non-existent `renderable` attribute.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] ruff I001 (unsorted imports) + UP035 (use collections.abc.Iterable)**
- **Found during:** Task 1 (after running `uv run ruff check`)
- **Issue:** Project ruff config requires sorted imports and `collections.abc.Iterable` over `typing.Iterable`. Plan's action block had `from typing import Iterable` and an unsorted import block.
- **Fix:** Switched to `from collections.abc import Iterable`; ran `uv run ruff check --fix` to organize import block.
- **Files modified:** src/claude_teletype/file_picker_screen.py
- **Verification:** `uv run ruff check src/claude_teletype/file_picker_screen.py` clean.
- **Committed in:** d363689 (Task 1 commit; fix landed before commit)

**2. [Rule 1 - Bug] AttributeError: 'Static' object has no attribute 'renderable'**
- **Found during:** Task 2 (`test_path_display_initial_placeholder` Pilot run)
- **Issue:** Plan's test action block read `str(display.renderable)`. In this Textual version, `Static` exposes content via `render()` (returns `Content`) -- no `renderable` attribute exists.
- **Fix:** Switched to `str(display.render())`; added inline comment documenting the choice so future contributors don't reach for `.renderable` again.
- **Files modified:** tests/test_file_picker_screen.py
- **Verification:** `uv run pytest tests/test_file_picker_screen.py -v` -- 11 passed.
- **Committed in:** 9df22d2 (Task 2 commit)

**3. [Rule 3 - Blocking] Plan verification rule `grep -c ModalScreen ... == 0` failed because of doc reference**
- **Found during:** Final verification grep checks
- **Issue:** Class docstring contained the literal phrase "not a ModalScreen" which made `grep -c "ModalScreen" src/claude_teletype/file_picker_screen.py` return 1 instead of the required 0.
- **Fix:** Rephrased docstring to "(not a modal overlay)" -- preserves the locked CONTEXT.md decision in plain English while satisfying the literal grep check.
- **Files modified:** src/claude_teletype/file_picker_screen.py
- **Verification:** `grep -c "ModalScreen" src/claude_teletype/file_picker_screen.py` -> 0; `isinstance(s, ModalScreen) is False` test still asserts the structural contract; tests still green.
- **Committed in:** 9df22d2 (Task 2 commit; folded with the test suite since both were verification-driven)

### Out-of-scope tracked-but-not-fixed

- **Pytest warnings** (`RuntimeWarning: coroutine 'DirectoryTree.watch_path' was never awaited` x4 + `PytestUnraisableExceptionWarning` x4) emitted during `test_filter_paths_*` and `test_picker_mounts_with_directory_tree`. Cause: instantiating `MarkdownDirectoryTree(str(tmp_path))` outside a Textual app schedules a reactive watch coroutine that never gets awaited because there's no event loop in the unit test. Same pattern would warn for plain `DirectoryTree`; not specific to this plan. Tests still pass cleanly. Out-of-scope for plan 24-01 -- noted for plan 24-02 or a future Pilot-fixture refactor that wraps unit-test instantiations in a transient app.

---

**Total deviations:** 3 auto-fixed (2 Rule 1 bugs, 1 Rule 3 blocking)
**Impact on plan:** All three are mechanical corrections to the plan's action blocks against the actual current Textual / ruff config -- no scope creep, no architectural change, no new files beyond what the plan specified.

## Issues Encountered

None beyond the deviations documented above.

## User Setup Required

None -- no external services, no env vars, no config changes.

## TDD Gate Compliance

Per-task `tdd="true"` cycles followed:

- Task 1: RED (`ModuleNotFoundError` before implementation, confirmed via direct import) -> GREEN (smoke test OK; `uv run python -c "..."` returns OK after implementation lands).
- Task 2: Tests added in a single commit because the implementation was already in place from Task 1 (the plan's task split puts impl in T1 and tests in T2 by design). All 11 tests pass on first green run after a Rule 1 fix for the Static API.

git log shows the expected `feat(24-01)` -> `test(24-01)` sequence:
```
9df22d2 test(24-01): add Pilot-based test suite for FilePickerScreen
d363689 feat(24-01): add FilePickerScreen widget with markdown filter and dismiss contracts
```

## Next Phase Readiness

- Plan 24-02 can begin immediately. FilePickerScreen is a self-contained widget ready to be pushed from `TeletypeApp.action_print_markdown`.
- Phase 25 (CLI no-arg entry) can also import FilePickerScreen unchanged -- the `root=` constructor parameter is already in place for both production (`Path.cwd()` default) and any future entry point that wants to root the picker elsewhere.
- Phase 26 (per-print speed dialog + transcript integration) inherits the resolved `Path` contract (always absolute via `Path(event.path).resolve()`), so the speed dialog can be pushed on top of the picker result without any path-normalization concerns.

## Self-Check: PASSED

Verified before finalizing:

- `src/claude_teletype/file_picker_screen.py` exists (143 LOC).
- `tests/test_file_picker_screen.py` exists (228 LOC).
- Commits exist in git log: `d363689` (feat) + `9df22d2` (test).
- 11 picker tests pass, 616 total project tests pass.
- ruff clean on both new files.
- Verification grep checks: filter_paths=2 (>=1), dismiss=3 (>=2), ModalScreen=0 (==0).

---
*Phase: 24-tui-file-picker*
*Completed: 2026-04-28*
