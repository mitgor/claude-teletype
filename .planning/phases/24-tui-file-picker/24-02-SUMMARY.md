---
phase: 24-tui-file-picker
plan: 02
subsystem: ui
tags: [tui, textual, keybinding, action-handler, file-picker, integration, pilot-test]

# Dependency graph
requires:
  - phase: 24-01-tui-file-picker-widget
    provides: FilePickerScreen(Screen[Path | None]) -- the picker pushed by ctrl+o
provides:
  - "ctrl+o keybinding on TeletypeApp.BINDINGS (visible in Footer as 'Open MD')"
  - "TeletypeApp.action_open_markdown -- pushes FilePickerScreen with _handle_picker_result callback"
  - "TeletypeApp._handle_picker_result(result) -- Path arm emits notify(); None arm silently refocuses input"
  - "Paired-method convention action_<name> + _handle_<name>_result for screen-pushing actions with result callbacks"
  - "'Smoke notify' as a deliberate Phase-N stopping point that locks the Path contract for Phase N+1"
affects:
  - phase-25-cli-no-arg-path
  - phase-26-speed-dialog-render-pipeline

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Paired action_<name> + _handle_<name>_result methods for push_screen+callback flows (matches existing action_open_settings/_apply_settings and _show_setup_screen/_handle_setup_result)"
    - "Local imports inside action handlers (matches action_enter_typewriter / action_open_settings) -- keeps top-level import surface small"
    - "Refocus #prompt input in BOTH callback arms (None and value) -- matches _handle_setup_result and _apply_settings; belt-and-suspenders given Textual's auto-restore"
    - "Direct screen.dismiss(value) in Pilot tests for callback assertions -- avoids DirectoryTree keyboard timing flakiness; mirrors test_file_picker_screen.py synthesized FileSelected pattern"
    - "Patch app.notify with patch.object + side_effect list capture -- isolates notify call assertions from real toast widget"

key-files:
  created:
    - tests/test_tui_file_picker_keybinding.py (170 LOC, 10 tests)
  modified:
    - src/claude_teletype/tui.py (+46 lines: BINDINGS entry, action_open_markdown, _handle_picker_result)

key-decisions:
  - "ctrl+o chosen over ctrl+m / ctrl+shift+o -- mnemonic 'open file', zero conflict with the four existing TeletypeApp bindings (ctrl+d quit, ctrl+t typewriter, ctrl+comma settings, escape cancel_stream), unreserved by Textual"
  - "Footer label 'Open MD' (7 chars) -- matches brevity of existing labels (Quit/Typewriter/Settings/Cancel)"
  - "Binding placed between ctrl+comma and escape -- keeps show=True bindings in left-to-right Footer order; show=False escape stays last"
  - "notify() smoke chosen over real render to keep Phase 24 mergeable independent of Phase 26's speed-dialog scope; the Path argument shape and _handle_picker_result name are the locked contract Phase 26 consumes"
  - "Refocus #prompt input in BOTH arms of _handle_picker_result -- matches existing _handle_setup_result / _apply_settings pattern (Textual restores focus on pop_screen automatically in most cases, but the explicit query+focus is the established style)"
  - "Local imports inside action_open_markdown and _handle_picker_result -- matches action_enter_typewriter convention (from claude_teletype.typewriter_screen import TypewriterScreen inside the method body)"
  - "Action name action_open_markdown (not action_open_file) -- the picker is markdown-specific in this milestone; action name encodes intent so a future generic file picker can coexist"
  - "Action handler is binding-agnostic -- BINDINGS line can be edited (e.g. to ctrl+shift+o or ctrl+p) without touching the method, documented in the action's docstring"
  - "Dual-test pattern: action-direct test (test_action_open_markdown_pushes_picker) isolates handler logic; keypress test (test_ctrl_o_keypress_opens_picker) validates BINDINGS wiring -- if only one fails you know which layer is broken"
  - "Disabled-input test (test_picker_opens_during_disabled_input) locks the App-level binding contract: ctrl+o works mid-stream when the input is disabled -- important for Phase 26's stream-in-flight handling"
  - "Docstring rephrased 'MarkdownRenderer' -> 'Phase 23's renderer' so plan verification rule grep -c MarkdownRenderer src/claude_teletype/tui.py == 0 holds (Phase 23 contract is locked; this plan must not import or instantiate the renderer). Same Rule-3 docstring-grep pattern used in 24-01 for ModalScreen"

patterns-established:
  - "Pattern: paired action_<name> + _handle_<name>_result methods for push_screen+callback flows -- now used in three places (settings, printer setup, file picker)"
  - "Pattern: 'smoke notify' Phase-N stopping point -- deliberate minimal callback body that proves the integration works end-to-end while locking the data shape for Phase N+1 to consume"
  - "Pattern: structural + Pilot test split for keybinding integrations -- structural tests catch BINDINGS edits cheaply; Pilot tests verify runtime push_screen+callback wiring"
  - "Pattern: dual action-direct + keypress Pilot tests -- isolates handler-logic vs binding-registration failure modes"

requirements-completed: [PICK-01]

# Metrics
duration: 4.2min
completed: 2026-04-28
---

# Phase 24 Plan 02: TUI File Picker Keybinding Integration Summary

**ctrl+o on TeletypeApp pushes FilePickerScreen and routes the dismissed Path through _handle_picker_result, which emits notify('Selected: <abs path>') as a smoke acknowledgement (Phase 26 will replace with the speed dialog + render pipeline) -- 10 new tests, 626 total green.**

## Performance

- **Duration:** 4.2 min
- **Started:** 2026-04-28T21:22:07Z
- **Completed:** 2026-04-28T21:26:24Z
- **Tasks:** 2
- **Files created:** 1
- **Files modified:** 1

## Accomplishments

- ctrl+o keybinding wired into TeletypeApp.BINDINGS with visible Footer label "Open MD"; zero conflict with the four existing bindings (ctrl+d quit, ctrl+t typewriter, ctrl+comma settings, escape cancel_stream).
- action_open_markdown handler pushes FilePickerScreen() with _handle_picker_result as the dismiss callback (matches existing push_screen+callback patterns in action_open_settings and _show_setup_screen).
- _handle_picker_result(result) handles both arms: Path -> notify(f"Selected: {path}"); None -> silent return (PICK-04 cancel-back). Both arms refocus #prompt input.
- Phase 23 contract preserved: MarkdownRenderer is NOT imported or instantiated in tui.py (verified by grep -c MarkdownRenderer == 0). The Path argument shape and _handle_picker_result name are the locked contract Phase 26 will consume when it replaces the body with the speed dialog + render pipeline.
- 10 new tests cover every must_haves truth: 5 structural (binding registered, no duplicate, methods exist, existing bindings intact) + 5 Pilot integration (action pushes picker, ctrl+o keypress pushes picker, cancel returns silently, selection emits notify, App-level binding works during disabled input).
- Full project test suite green: 616 baseline + 10 new = 626 passing -- exact match for plan verification prediction (>=625).

## Task Commits

Each task was committed atomically:

1. **Task 1: BINDINGS + action_open_markdown + _handle_picker_result on TeletypeApp** - `cc044de` (feat)
2. **Task 2: Pilot test suite for ctrl+o keybinding integration** - `a7c2c59` (test)

Note: Task 1 `tdd="true"` cycle confirmed RED (smoke check raised AssertionError on missing ctrl+o binding) -> GREEN (smoke check returns OK after edit). Task 2 added the full test suite + a docstring tweak (see Deviations) in a single test() commit since the doc fix was a verification-driven correction surfaced by the plan's own grep checks.

## Files Created/Modified

- `src/claude_teletype/tui.py` (+46 lines) -- BINDINGS gains ctrl+o entry; action_open_markdown method placed adjacent to action_open_settings; _handle_picker_result method placed adjacent to _apply_settings.
- `tests/test_tui_file_picker_keybinding.py` (170 LOC, 10 tests) -- 5 structural BINDINGS / method-existence tests + 5 Pilot integration tests covering keypress wiring, cancel/selection callback arms, and disabled-input mid-stream binding behavior.

## Decisions Made

All major decisions are listed in the frontmatter `key-decisions` block. Highlights:

- **ctrl+o chosen over ctrl+m / ctrl+shift+o** -- mnemonic ("open file"), zero conflict with the four existing TeletypeApp bindings, unreserved by Textual. Some legacy terminals send ctrl+o as XOFF-adjacent "discard output", but Textual's input layer captures it as `key=ctrl+o` regardless (same mechanism that lets nano use ctrl+o for "Write Out").
- **notify() smoke chosen over real render** -- keeps Phase 24 mergeable independent of Phase 26's speed-dialog scope. The Path argument shape and `_handle_picker_result` method name are the locked contract Phase 26 consumes. Documented in the method's docstring.
- **Paired action_<name> + _handle_<name>_result methods** -- the existing convention used by `action_open_settings`/`_apply_settings` and `_show_setup_screen`/`_handle_setup_result`. Picker integration follows the same shape so future contributors find what they expect.
- **Dual-test pattern (action-direct + keypress)** -- the action-direct test isolates handler logic; the keypress test (`pilot.press("ctrl+o")`) validates BINDINGS wiring. If only one fails you know which layer is broken without bisecting.
- **Direct screen.dismiss() in cancel/selection tests** -- Pilot keyboard navigation through DirectoryTree to find a specific file is timing-flaky (tree expansion is async, cursor positioning depends on viewport). Driving `screen.dismiss(value)` directly tests the same observable contract -- the callback receives the value the screen dismisses with -- which is exactly what `_handle_picker_result` consumes. Mirrors the synthesized-FileSelected pattern from `test_file_picker_screen.py`.
- **Disabled-input mid-stream test** -- locks the App-level binding contract that ctrl+o works even while the input prompt is disabled (Thinking... state). Phase 26 will need to handle stream-in-flight gracefully for the real render path, but the *binding* must work regardless.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Plan verification rule `grep -c MarkdownRenderer src/claude_teletype/tui.py == 0` failed because of docstring references**
- **Found during:** Task 2 verification grep step (after the test suite was passing)
- **Issue:** The docstrings on `action_open_markdown` and `_handle_picker_result` (copied verbatim from the plan's action block) contained the literal phrase "MarkdownRenderer pipeline" twice -- once per method -- so `grep -c MarkdownRenderer` returned 2 instead of the required 0. The plan verification step #6 specifies that this count must be 0 because Phase 23's contract is locked and this plan must not import or instantiate the renderer.
- **Fix:** Rephrased both docstrings from "MarkdownRenderer pipeline" -> "Phase 23's renderer pipeline". Preserves the locked Phase 23 -> Phase 26 reference in plain English while satisfying the literal grep. Same Rule-3 pattern plan 24-01 used for "ModalScreen" -> "(not a modal overlay)".
- **Files modified:** src/claude_teletype/tui.py
- **Verification:** `grep -c MarkdownRenderer src/claude_teletype/tui.py` -> 0; tests still green (10 picker integration + 626 total).
- **Committed in:** a7c2c59 (Task 2 commit; folded with the test suite since both were verification-driven)

### Out-of-scope tracked-but-not-fixed

- **Pre-existing ruff E501** in `src/claude_teletype/tui.py:359` (status-bar f-string, 128 > 100 chars). Introduced by commit `cc2a39e5` (Feb 2026), pre-dates plan 24-02. Logged to `.planning/phases/24-tui-file-picker/deferred-items.md`. Confirmed pre-existing via `git stash` + ruff re-run on baseline. Out of scope per the SCOPE BOUNDARY rule -- this plan's edits to tui.py are themselves ruff-clean.
- **Pytest warnings** (`RuntimeWarning: coroutine 'DirectoryTree.watch_path' was never awaited`) carried forward from plan 24-01's unit tests. Same warnings, same root cause. Not introduced by this plan; tracked under 24-01's deferred items.

---

**Total deviations:** 1 auto-fixed (1 Rule 3 blocking docstring-grep correction)
**Impact on plan:** Mechanical correction to the plan's action block against the plan's own verification rule -- no scope creep, no architectural change, no new files beyond what the plan specified.

## Issues Encountered

None beyond the deviation documented above.

## User Setup Required

None -- no external services, no env vars, no config changes. The keybinding is purely additive.

## Known Stubs

- **`_handle_picker_result` Path arm emits only `notify()` (no rendering)** -- this is NOT a stub, it is an intentional Phase 24 stopping point per the plan's `<objective>` and the locked Phase 26 scope. The notify() call is the user-visible smoke test that the picker hands the right Path back; Phase 26 replaces the body with the speed dialog + Phase 23 renderer pipeline. The Path argument shape and method name are the contract.

## TDD Gate Compliance

Per-task `tdd="true"` cycles followed:

- **Task 1:** RED (`uv run python -c "..."` smoke check raised `AssertionError: [('ctrl+d', 'quit'), ('ctrl+t', 'enter_typewriter'), ('ctrl+comma', 'open_settings'), ('escape', 'cancel_stream')]` -- ctrl+o was missing) -> GREEN (smoke check returns "OK" after BINDINGS + methods edit). Confirms Textual's binding+action layer was driven by an actual contract gap.
- **Task 2:** Tests added in a single commit because the implementation was already in place from Task 1 (the plan's task split puts impl in T1 and tests in T2 by design, mirroring 24-01). All 10 tests pass on first green run after the Rule-3 docstring fix. RED was implicit: the test file did not exist (`pytest collected 0 items`).

git log shows the expected `feat(24-02)` -> `test(24-02)` sequence:

```
a7c2c59 test(24-02): add Pilot test suite for ctrl+o keybinding integration
cc044de feat(24-02): wire ctrl+o keybinding to FilePickerScreen via action_open_markdown
```

## Next Phase Readiness

- **Phase 25 (CLI no-arg path)** can land independently. The picker is reachable from the chat session via ctrl+o; Phase 25 will add a separate entry where invoking the CLI without a path argument launches the picker before the chat. Both entry points share the same `FilePickerScreen` widget (24-01's `root=` constructor parameter is already in place).
- **Phase 26 (per-print speed dialog + transcript integration)** inherits the locked contract: replace `_handle_picker_result`'s Path arm with the speed dialog push + Phase 23 renderer pipeline. The method name (`_handle_picker_result`), the Path argument shape (always absolute via `Path(event.path).resolve()` from 24-01), and the input-refocus pattern in the None arm all carry forward unchanged. The notify() body is the only line Phase 26 needs to replace.
- The docstring on `_handle_picker_result` already documents the Phase 26 substitution intent at the call site, so a future implementer reading the file finds the planned-replacement note inline.

## Self-Check: PASSED

Verified before finalizing:

- `tests/test_tui_file_picker_keybinding.py` exists (170 LOC, 10 tests).
- `src/claude_teletype/tui.py` modified (+46 lines).
- Commits exist in git log: `cc044de` (feat) + `a7c2c59` (test).
- 10 keybinding tests pass; 626 total project tests pass (616 baseline + 10 new).
- ruff clean on both touched files (the pre-existing E501 on line 359 is logged to deferred-items.md and confirmed pre-dating this plan via `git stash` baseline check).
- Verification grep checks: `open_markdown|FilePickerScreen|ctrl+o` in tui.py = 6 hits (>=3); `MarkdownRenderer` in tui.py = 0 (== 0); ctrl+o appears in `[b.key for b in TeletypeApp.BINDINGS]` -> `['ctrl+d', 'ctrl+t', 'ctrl+comma', 'ctrl+o', 'escape']`.

---
*Phase: 24-tui-file-picker*
*Completed: 2026-04-28*
