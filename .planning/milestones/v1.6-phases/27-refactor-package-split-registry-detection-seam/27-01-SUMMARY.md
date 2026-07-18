---
phase: 27-refactor-package-split-registry-detection-seam
plan: 01
subsystem: infra
tags: [refactor, package-split, re-export-shim, python, pytest, mock-patch-seam]

requires:
  - phase: 21-26 (v1.5)
    provides: printer.py drivers/discovery/selection, profiles.py registry, rendering + screen modules, 718-test suite
provides:
  - printing/ package (drivers.py, discovery.py, selection.py, profiles.py) holding the former printer.py + profiles.py code
  - rendering/ package (markdown, wordwrap, pacer, output) — 1:1 moves
  - screens/ package (printer_setup, settings, typewriter, file_picker, speed_mode) — _screen suffix dropped
  - re-export shims at every old top-level module path keeping absolute imports alive
  - printing/__init__.py public API surface (explicit __all__) for Step 2 internal repointing
affects: [27-02 (repoint internal imports), 27-03 (migrate test imports + patch targets), 28 (fleet detection), 29 (profile catalog)]

tech-stack:
  added: []
  patterns:
    - "move-with-re-export-shim package split (Step 1 of 3)"
    - "call-time shim-lookup seam: cross-module functions resolve siblings through the claude_teletype.printer shim so legacy single-module mock patch targets keep intercepting until Plan 03 migrates them"

key-files:
  created:
    - src/claude_teletype/printing/__init__.py
    - src/claude_teletype/printing/drivers.py
    - src/claude_teletype/printing/discovery.py
    - src/claude_teletype/printing/selection.py
    - src/claude_teletype/printing/profiles.py
    - src/claude_teletype/rendering/{__init__,markdown,wordwrap,pacer,output}.py
    - src/claude_teletype/screens/{__init__,printer_setup,settings,typewriter,file_picker,speed_mode}.py
  modified:
    - src/claude_teletype/printer.py (now a re-export shim)
    - src/claude_teletype/profiles.py (now a re-export shim)
    - src/claude_teletype/{markdown,wordwrap,pacer,output}.py (shims)
    - src/claude_teletype/{printer_setup,settings,typewriter,file_picker,speed_mode}_screen.py (shims)

key-decisions:
  - "PrinterSelection placed in discovery.py (not selection.py) so both selection.py and screens/printer_setup.py import it without a cycle"
  - "Cross-module callers (discover_printer, create_driver_for_selection, discover_all) resolve their discovery siblings through the claude_teletype.printer shim at call time, preserving the single-module mock-patch seam that ~5 tests rely on — deferring the patch-target rename to Plan 03 as the plan specifies"
  - "drivers.py keeps importing WordWrapper from claude_teletype.wordwrap (the live module) within this step; Plan 02 repoints it to rendering.wordwrap"

patterns-established:
  - "Re-export shim: `from <new> import *  # noqa: F401,F403` + explicit named re-export block (with F811 noqa where the explicit block redefines star names)"
  - "Call-time shim-lookup for preserving mock patch targets across a module split"

requirements-completed: [REF-01]

duration: 18min
completed: 2026-06-12
---

# Phase 27 Plan 01: Package Split (move-with-shim, Step 1) Summary

**printer.py split into printing/{drivers,discovery,selection}.py and profiles.py moved to printing/profiles.py; rendering/ and screens/ packages created; every old top-level path is a re-export shim and the full 718-test suite stays green with zero test edits.**

## Performance

- **Duration:** ~18 min
- **Tasks:** 3 (all atomic-committed)
- **Files modified/created:** 21 source files (4 new printing modules, 5 rendering, 6 screens, 2 driver/profile shims, 9 rendering/screen shims, 3 package inits — with overlaps)

## Accomplishments
- Physically moved printer.py code into three cohesive printing/ modules and profiles.py into printing/profiles.py (git mv preserves blame on the 1:1 moves)
- Created rendering/ (4 modules, 1:1) and screens/ (5 modules, _screen suffix dropped per ARCHITECTURE target map)
- Left re-export shims at all 11 old module paths so every absolute import (`from claude_teletype.printer/.profiles/.markdown/.*_screen import X`) still resolves
- Populated printing/__init__.py with an explicit public-API __all__ for Step 2
- Full suite green: 718 passed, 0 failed; zero test-file edits; tui.py + ConfirmSwapScreen untouched

## Task Commits

1. **Task 1: Move printer.py + profiles.py into printing/ with shims** — `dac4af3` (refactor)
2. **Task 2: Move rendering + screen modules into packages with shims** — `362a379` (refactor)
3. **Task 3: Populate printing/__init__ public API; full suite green** — `d5045fc` (refactor)

## Decisions Made
- See key-decisions frontmatter. Core decision: preserve the single-module mock-patch seam via call-time lookup through the printer shim rather than editing tests (which Plan 03 owns).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule: blocking test failure] Cross-module mock-patch seam broken by the split**
- **Found during:** Tasks 1 and 3
- **Issue:** Tests patch `claude_teletype.printer.{discover_usb_device, discover_cups_printers, select_printer, _find_usb_printer}` expecting the patch to take effect inside `discover_printer` / `create_driver_for_selection` / `discover_all`. After the split those callers and callees live in different modules, so a name-binding patch on the shim no longer intercepted the intra-call (13 → 4 → 2 failures across the work).
- **Fix:** Made `discover_printer` (selection.py), `create_driver_for_selection` (selection.py), and `discover_all` (discovery.py) resolve their discovery siblings via a local `from claude_teletype import printer as _shim` lookup at call time. This is the explicit "preserve single-module seam until Plan 03 migrates patch targets" behavior the plan calls for — no test was edited.
- **Files modified:** src/claude_teletype/printing/selection.py, src/claude_teletype/printing/discovery.py
- **Verification:** Full suite 718 passed; `git status tests/` empty.
- **Committed in:** dac4af3 (Task 1), d5045fc (Task 3)

**2. [Rule: lint hygiene] noqa + import-order on new files**
- **Found during:** Tasks 1–3
- **Issue:** The shim's explicit re-export block redefines star-imported names (F811); ruff's isort wanted the shim import blocks reordered (I001); removed two now-unused top-level imports in selection.py (F401).
- **Fix:** Added `# noqa: F401,F811` to printer.py explicit re-export block; ran `ruff check --fix` for I001 on printer.py and screens/typewriter.py; dropped the unused `discover_cups_printers`/`discover_usb_device`/`_find_usb_printer` top-level imports from selection.py.
- **Files modified:** src/claude_teletype/printer.py, src/claude_teletype/printing/selection.py, src/claude_teletype/screens/typewriter.py
- **Verification:** Zero F-category ruff errors on printing/rendering/screens beyond the intentional noqa shims. Remaining E501/N806 on moved code are pre-existing (verified identical count against the original files at HEAD).

---

**Total deviations:** 2 auto-fixed (1 blocking test seam, 1 lint hygiene)
**Impact on plan:** Both necessary to satisfy the plan's "718 green, zero test edits" gate. No scope creep — behavior unchanged, only module boundaries moved.

## Issues Encountered
- drivers.py's `make_printer_output` initially pointed WordWrapper at the not-yet-existing `claude_teletype.rendering.wordwrap` (Task 2 target). Reverted to the live `claude_teletype.wordwrap` path for Step 1; Plan 02 repoints it. Resolved before the Task 1 commit.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- printing/ exposes its public API (explicit __all__) — Plan 02 can repoint internal imports to `from claude_teletype.printing import X`.
- Plan 03 must migrate the mock patch targets (`claude_teletype.printer.*` → new module paths) and can then remove the call-time `_shim` lookups added here as a temporary seam.
- All 11 shims remain in place; tui.py stays top-level; ConfirmSwapScreen still importable from claude_teletype.tui.

---
*Phase: 27-refactor-package-split-registry-detection-seam*
*Completed: 2026-06-12*
