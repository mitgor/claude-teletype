---
phase: 32-setup-detection-flow-fixes
verified: 2026-07-19T00:00:00Z
status: passed
score: 11/11 must-haves verified
overrides_applied: 0
---

# Phase 32: Setup & Detection Flow Fixes Verification Report

**Phase Goal:** Setup and smart startup always route the user to the driver and profile they chose — never silently to the simulator, a wrong profile, or a foreign-directory `uv sync`
**Verified:** 2026-07-19
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | SC1/CR-03: kernel-claimed USB + accepted CUPS recommendation dismisses with connection_type="cups" and a non-None resolved queue name (serial-match wins, else first enabled) | ✓ VERIFIED | printer_setup.py:335-353 resolves via `self._discovery.cups_printers` filtered to enabled, serial-match preferred; tests `test_usb_entry_cups_radio_resolves_serial_matched_queue`, `test_usb_entry_cups_radio_falls_back_to_first_enabled_queue` pass |
| 2 | CR-03 refusal: CUPS radio + zero enabled queues → screen does NOT dismiss; error written to diagnostics log | ✓ VERIFIED | printer_setup.py:344-348 writes "No enabled CUPS queue available…" to `#diagnostics-log` and returns; test `test_usb_entry_cups_radio_no_enabled_queue_refuses_dismiss` passes |
| 3 | CR-03 persist guard: `_save_printer_selection` never writes `saved_printer_id=""` for usb/cups | ✓ VERIFIED | tui.py:286-298 computes id first, early-returns before load/save_config when empty; tests `test_save_printer_selection_refuses_empty_cups_id` / `_empty_usb_id` / `_valid_cups_persists` pass |
| 4 | CR-03 factory half: `create_driver_for_selection` cups with no name picks first enabled queue, NullPrinterDriver only when queueless | ✓ VERIFIED | selection.py:163-173; tests `test_no_name_picks_first_enabled_queue`, `test_no_name_no_enabled_queues_returns_null` pass |
| 5 | SC2/WR-03: `registry.get` case-insensitive over case-preserved keys; `names()` keeps original casing | ✓ VERIFIED | registry.py:60-62 `_by_lower` index; :106 `get()` resolves through it. Runtime spot-check: `get("myprinter")`/`get("MYPRINTER")`/`get("  MyPrinter ")` all return the custom profile; `names()` contains "MyPrinter"; unknown raises ValueError. Test `test_uppercase_custom_key_reachable_any_casing` passes |
| 6 | SC2: `--printer MyPrinter` resolves via registry | ✓ VERIFIED | cli.py:470-476 `_resolve_profile_selection` calls `registry.get(printer)` (now case-insensitive); setup-screen Select is built from case-preserved `all()` keys so exact-key wrapping matches |
| 7 | SC3/WR-05: under `sys.frozen` install row hidden and `_install_pyusb` refuses | ✓ VERIFIED | printer_setup.py:233, 487 (visibility guards in on_mount and _refresh_discovery), :389-394 (refusal + log); tests `test_frozen_hides_install_row_even_without_pyusb`, `test_frozen_install_refuses_and_spawns_nothing` pass |
| 8 | SC3: non-frozen `uv sync` cwd-pinned to the directory containing pyproject.toml, or refuses | ✓ VERIFIED | printer_setup.py:43-53 `_project_root()`, :397-403 refusal when None, :419 `cwd=str(root)` on create_subprocess_exec; tests `test_install_pins_cwd_to_project_root`, `test_install_refuses_when_no_pyproject_found` pass |
| 9 | SC4/ARCH-04: `match_saved_printer(profile_name=…)` stamps both variants; caller-side mutation deleted | ✓ VERIFIED | selection.py:58, 85, 94; cli.py:986 passes `profile_name=config.saved_printer_profile or "generic"`; `grep -c "saved_match.profile_name ="` = 0; repo-wide grep finds no `.profile_name =` assignment anywhere in src/ |
| 10 | SC4: PrinterSelection frozen — assignment raises FrozenInstanceError | ✓ VERIFIED | discovery.py:81 `@dataclass(frozen=True)`; runtime spot-check raised FrozenInstanceError; test `test_assignment_raises_frozen_instance_error` passes |
| 11 | Full suite green | ✓ VERIFIED | `uv run pytest -q` → **932 passed** in 20s (gate: ≥ 912; the 2 worktree-env usb-backend failures reported in SUMMARYs do not reproduce on main) |

**Score:** 11/11 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/claude_teletype/screens/printer_setup.py` | CR-03 queue resolution in _on_connect; WR-05 frozen + cwd guards | ✓ VERIFIED | Substantive, wired into Connect/Install button dispatch |
| `src/claude_teletype/tui.py` | Empty-ID persist guard | ✓ VERIFIED | Guard sits in `_save_printer_selection`, called from `_handle_setup_result` |
| `src/claude_teletype/printing/registry.py` | Case-insensitive get via lowered-key index (contains "lower") | ✓ VERIFIED | `_by_lower` built in `__init__`; `get()` resolves through it |
| `src/claude_teletype/printing/selection.py` | `profile_name` param + cups-no-name fallback (contains "profile_name") | ✓ VERIFIED | Both PrinterSelection constructions stamp the param; loud fallback present |
| `src/claude_teletype/printing/discovery.py` | frozen PrinterSelection (contains "frozen=True") | ✓ VERIFIED | Line 81 |
| `src/claude_teletype/cli.py` | Keyword hand-off, mutation gone | ✓ VERIFIED | Line 986; grep count 0 for mutation |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| printer_setup.py `_on_connect` | `self._discovery.cups_printers` | queue resolution for usb-entry + cups radio | ✓ WIRED | Line 343 |
| printer_setup.py | `sys.frozen` | `getattr(sys, "frozen", False)` in visibility + worker | ✓ WIRED | Lines 233, 389, 487 |
| cli.py | `match_saved_printer` | `profile_name=config.saved_printer_profile or "generic"` kwarg | ✓ WIRED | Line 986, mutation deleted |
| registry.py `get()` | `self._profiles` | lowered-key index resolving to case-preserved key | ✓ WIRED | Lines 60-62, 106 |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Case-insensitive registry over case-preserved keys | inline `uv run python -c` against ProfileRegistry | All casings resolve; names() preserves case; unknown raises | ✓ PASS |
| Frozen PrinterSelection | inline assignment attempt | FrozenInstanceError raised | ✓ PASS |
| `profile_name` in match_saved_printer signature | inspect.signature | Present with default "generic" | ✓ PASS |
| Full suite | `uv run pytest -q` | 932 passed, 0 failed | ✓ PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes declared by either plan; not a migration/tooling phase. SKIPPED.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| FLOW-01 | 32-01, 32-02 | Kernel-claimed + CUPS accept → working CUPS driver, queue name set, never silent Null, empty-ID never persisted | ✓ SATISFIED | Truths 1-4 |
| FLOW-02 | 32-02 | Uppercase custom profile selectable; registry case-insensitive | ✓ SATISFIED | Truths 5-6 |
| FLOW-03 | 32-01 | Frozen .app never triggers `uv sync` against arbitrary cwd | ✓ SATISFIED | Truths 7-8 |
| FLOW-04 | 32-02 | Saved profile via explicit parameter; mutation gone; dataclass frozen | ✓ SATISFIED | Truths 9-10 |

No orphaned requirements: REQUIREMENTS.md maps exactly FLOW-01..04 to Phase 32; both plans jointly claim all four.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | No TBD/FIXME/XXX/TODO/HACK debt markers in any phase-modified file | — | — |

("placeholder" hits at printer_setup.py:116, 256 are descriptive comments about existing UI list items, not stubs.)

### Known Follow-Ups (not gaps — per verification scope note)

From 32-REVIEW.md (0 critical, 6 warnings). None falsifies a Phase 32 success criterion:

- **WR-01 / WR-02 / WR-04** (residual case-sensitive plain-dict profile lookups outside `registry.get`, case-collision shadowing policy, stderr diagnostics invisible under Textual) — within Phase 34 ARCH-CLEAN-01 scope (registry as the single seam, dict round-trips eliminated, unknown names fail loudly).
- **WR-05 (review)**: `_project_root()` trusts the first pyproject.toml found without verifying it is this project's — the frozen-app criterion (SC3) is fully guarded; this is a non-frozen wheel-install edge case. Follow-up: validate `project.name == "claude-teletype"` before syncing.
- **WR-06**: `_on_connect` reads `option_list.highlighted` while radio/profile state tracks the last *selected* entry — pre-existing desync, not introduced by this phase; the accepted-recommendation flow (the SC1 scenario) is unaffected.
- **IN-01..IN-04**: informational (recommendation gating on enabled queues, negative-index guard symmetry, status-bar profile divergence, persisted type vs fallback driver divergence).

### Human Verification Required

None. Both plans declare only `<automated>` verifies (no deferred `<human-check>` blocks), and all four success criteria are exercised end-to-end by Textual-pilot screen tests plus the full suite. Real-hardware smoke (an actually kernel-claimed printer) is outside the phase's stated criteria.

### Gaps Summary

No gaps. All four ROADMAP success criteria hold in the codebase, all plan-level must_haves verify at exists/substantive/wired levels, both plans' commits (46d5357, 68bc857, 5d3a715, e85bd11, b2e1748, 7933ee4, 7fb6310, 68c00e9) exist in the repo, and the full suite is green at 932 tests on main (exceeding both plans' ≥ 912 gate; the SUMMARYs' 2 usb-backend failures were worktree-env artifacts that do not reproduce here).

---

_Verified: 2026-07-19_
_Verifier: Claude (gsd-verifier)_
