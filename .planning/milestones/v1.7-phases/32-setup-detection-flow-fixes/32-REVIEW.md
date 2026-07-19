---
phase: 32-setup-detection-flow-fixes
reviewed: 2026-07-19T00:00:00Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - src/claude_teletype/screens/printer_setup.py
  - src/claude_teletype/tui.py
  - src/claude_teletype/cli.py
  - src/claude_teletype/printing/discovery.py
  - src/claude_teletype/printing/registry.py
  - src/claude_teletype/printing/selection.py
  - tests/test_printer_setup_screen.py
  - tests/test_tui.py
  - tests/test_registry.py
  - tests/test_smart_startup.py
findings:
  critical: 0
  warning: 6
  info: 4
  total: 10
status: issues_found
---

# Phase 32: Code Review Report

**Reviewed:** 2026-07-19
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Reviewed the Phase 32 fixes (git range a9010a2..HEAD) for CR-03 (kernel-claimed
USB / empty CUPS queue name), WR-03 (case-insensitive registry lookup), WR-05
(frozen install guard + cwd pinning), and ARCH-04 (frozen PrinterSelection).

Verified closed:
- **ARCH-04 fully closed.** Grep over `src/` finds zero assignment sites on
  `PrinterSelection` fields; the cli.py mutation is gone; the dataclass is
  `frozen=True` and a `FrozenInstanceError` regression test exists.
- **CR-03 stale-config interaction is safe.** A pre-fix config with
  `saved_printer_type="cups"` and empty `saved_printer_id` falls through
  `match_saved_printer`'s `saved_id` truthiness checks, returns None, and the
  decision stays SHOW_SETUP. The tui.py empty-id persist guard prevents new
  broken configs; the factory fallback only fires for legacy/defensive paths.
- **WR-05 no-pyproject case handled.** `_project_root()` returns None when no
  pyproject.toml exists up the tree; `_install_pyusb` refuses with a log line
  and spawns nothing (test-covered).

Not fully closed / new defects: WR-03's case-insensitivity only covers
`ProfileRegistry.get` — every other profile lookup on the hand-off path is
still a case-sensitive plain-dict `.get()`; case-only duplicate profile names
now resolve inconsistently between the registry and those dict lookups; the
CR-03 factory fallback can silently route output to an unrelated physical
printer and its "loud" stderr diagnostics are invisible in the primary TUI
consumer; and the WR-05 cwd pin trusts the *first* pyproject.toml found rather
than verifying it belongs to this project.

## Warnings

### WR-01: WR-03 fix is partial — profile hand-off path is still case-sensitive

**File:** `src/claude_teletype/printing/selection.py:181` (also `src/claude_teletype/cli.py:996`, `src/claude_teletype/tui.py:471,547,665,953`)
**Issue:** WR-03 made `ProfileRegistry.get()` case-insensitive via the
lowered-key index, but the saved-profile hand-off never goes through
`registry.get()`. `create_driver_for_selection` does
`profiles.get(selection.profile_name)` on a plain dict, cli.py:996 does
`config.saved_printer_profile in all_profiles`, and tui.py resolves
`self._all_profiles.get(self._profile_name)` in four places — all
case-sensitive exact-key lookups. A hand-edited config with
`saved_printer_profile = "Juki"` matches the saved printer, but
`profiles.get("Juki")` returns None and the driver is silently created
**unwrapped** (no ESC sequences) — the same silent-degradation class WR-03
was meant to kill, just one layer down.
**Fix:** Route the hand-off through the registry (pass the `ProfileRegistry`
instead of `registry.all()` dict to `create_driver_for_selection`, or
normalize `selection.profile_name` through `registry.get(...)`/lowered lookup
before the dict access):
```python
# selection.py — accept the registry, not a bare dict
try:
    profile = registry.get(selection.profile_name)
except ValueError:
    profile = None
```

### WR-02: Case-only duplicate profile names resolve inconsistently (registry vs dict lookups)

**File:** `src/claude_teletype/printing/registry.py:60-62`
**Issue:** When two profiles differ only by case (builtin `escp` plus custom
`EscP`), both keys live in `self._profiles` and appear in `names()`/`all()`,
but `_by_lower` maps the single key `"escp"` to whichever registered last
(`EscP`). Result: `registry.get("escp")` returns the custom `EscP` profile —
the builtin `escp` becomes unreachable via `get()` — while the setup screen's
Select (built from `all()`) still offers both entries, and picking `escp`
there resolves through the case-sensitive `dict.get` (WR-01 path) to the
builtin. The same name string resolves to two different profiles depending on
which code path runs. Unlike the VID-only collision policy, this shadowing
logs no diagnostic.
**Fix:** In `__init__`, detect case-fold collisions while building `_by_lower`
and log a warning naming both keys (mirror the `_build_index` VID-collision
diagnostic), e.g.:
```python
self._by_lower = {}
for k in self._profiles:
    low = k.lower().strip()
    if low in self._by_lower:
        logger.warning(
            "Profile name case collision: %r shadows %r for lookup %r "
            "(last registered wins)", k, self._by_lower[low], low,
        )
    self._by_lower[low] = k
```

### WR-03: USB→CUPS factory fallback can bind an unrelated physical printer

**File:** `src/claude_teletype/printing/selection.py:143-158`
**Issue:** When USB direct fails, `create_driver_for_selection` falls back to
`enabled_queues[0]` if no serial-matched queue exists. `enabled_queues[0]` is
just the first enabled CUPS queue on the machine — it can be a completely
different device (e.g. an office laser printer) than the USB printer the user
explicitly picked or saved. On the smart-startup path (SKIP_SAVED_MATCH) this
happens with no UI at all: a saved "usb Juki" config whose device is
kernel-claimed silently prints every chat turn on whatever queue sorts first.
The serial guard only helps when the CUPS URI carried a `serial=` param AND
the USB descriptor exposed a serial — many bridge cables (CH341) expose none.
**Fix:** Constrain the no-serial fallback to queues plausibly belonging to
the picked device (match vendor/model parsed from the CUPS URI against
`identity.manufacturer`/`product_name`), and when nothing matches, return
`NullPrinterDriver` with a diagnostic instead of guessing:
```python
if fallback is None:
    fallback = next(
        (q for q in enabled_queues
         if identity is not None and identity.product_name
         and identity.product_name.lower() in (q.model or "").lower()),
        None,
    )
if fallback is None:
    return NullPrinterDriver()  # + diagnostic; do not guess a queue
```

### WR-04: Fallback diagnostics go to sys.stderr — invisible inside the running TUI

**File:** `src/claude_teletype/printing/selection.py:153-157,168-172`
**Issue:** Both new CR-03 fallback messages use `print(..., file=sys.stderr)`.
`create_driver_for_selection` is called from `tui.py:_handle_setup_result`
while the Textual app owns the terminal: the message is either swallowed by
Textual's print capture or garbles the display — the user never sees it. The
fix's whole point was to stop *silent* degradation, but in the primary
consumer (the TUI setup flow) the "loud" fallback is still silent; only the
pre-run cli.py smart-startup call renders it.
**Fix:** Return the diagnostics instead of printing — e.g. accept an optional
`diagnostics: list[str] | None` (the established pattern in
`discovery._find_usb_printer`) and have `_handle_setup_result` surface them
via `self.notify(...)`; keep the stderr print only for the CLI path.

### WR-05: `_project_root()` trusts the first pyproject.toml found — `uv sync` can run against an unrelated project

**File:** `src/claude_teletype/screens/printer_setup.py:43-53,397-420`
**Issue:** The walk-up stops at the first directory containing a
pyproject.toml without verifying it is *this* project's. For a wheel install
into a venv that happens to live under some other project's directory (e.g.
`~/projects/foo/.venv/lib/python3.x/site-packages/claude_teletype/...`), the
walk finds `~/projects/foo/pyproject.toml` and runs
`uv sync --extra usb` against project *foo* — `uv sync` prunes packages not
in foo's lock, which can uninstall claude-teletype itself from the running
venv and mutate an unrelated project's environment. The guard comment says
"only ever sync the project's own directory" but the code never checks
ownership.
**Fix:** Validate the found pyproject before using it:
```python
import tomllib
with (parent / "pyproject.toml").open("rb") as f:
    data = tomllib.load(f)
if data.get("project", {}).get("name") == "claude-teletype":
    return parent
```
(continue walking / return None otherwise).

### WR-06: `_on_connect` builds the selection from `highlighted` while radios/profile track the last *selected* entry

**File:** `src/claude_teletype/screens/printer_setup.py:321-353`
**Issue:** Radio state, profile suggestion, and the kernel-owns probe run in
`on_option_list_option_selected` (fires on Enter/click), but `_on_connect`
reads `option_list.highlighted` (moves on arrow keys without firing
OptionSelected). A user who selects entry A, arrows the highlight to entry B,
and clicks Connect gets B's `entry` combined with A's radio/profile state.
The new CR-03 code widens the blast radius: with A=CUPS entry (radio_usb
disabled, radio_cups on) and B=USB entry, `connection_type` resolves to
"cups" and the queue is resolved against **B's** serial — a queue the user
never chose for that device. Pre-existing desync (the old code also used
`highlighted`), but this phase added the queue-resolution logic on top of it
without closing it.
**Fix:** Reconfigure widget state on `OptionList.OptionHighlighted` as well
(or resolve `entry` from the index the radios were configured for, stored in
`self._configured_index` during `option_selected`).

## Info

### IN-01: Kernel-owns CUPS recommendation checks queue presence, not enabled state

**File:** `src/claude_teletype/screens/printer_setup.py:282`
**Issue:** `if kernel_owns and self._discovery.cups_printers:` pre-selects the
CUPS radio when *any* queue exists, but `_on_connect` (line 343) filters to
enabled queues and refuses when none are. With only disabled queues present,
the screen recommends CUPS and then refuses to connect via it.
**Fix:** Gate the recommendation on `any(q.enabled for q in self._discovery.cups_printers)`.

### IN-02: `_save_printer_selection` missing negative-index guard

**File:** `src/claude_teletype/tui.py:289-291`
**Issue:** Checks `device_index < len(...)` but not `0 <=`; a negative index
would silently persist the wrong device's VID:PID via Python negative
indexing. `create_driver_for_selection` (selection.py:129) does check `0 <=`.
No current caller produces negatives, but the two guards should match.
**Fix:** `0 <= selection.device_index < len(self._discovery.usb_devices)`.

### IN-03: Unknown saved profile leaves status-bar profile diverged from actual driver

**File:** `src/claude_teletype/cli.py:996-997`
**Issue:** When `saved_printer_profile` is set but not in `all_profiles`, the
driver is created unwrapped (WR-01 path) yet `resolved_profile` keeps the
value from the earlier `_resolve_profile_selection` chain (possibly a USB
auto-detect hit), so `TeletypeApp` shows a profile name that is not applied
to the driver.
**Fix:** When the saved profile fails to resolve, force `resolved_profile = None`
for the saved-match branch (or resolve both through the registry per WR-01).

### IN-04: Persisted `connection_type="usb"` can diverge from the actual CUPS-fallback driver

**File:** `src/claude_teletype/tui.py:269` (with `selection.py:143-158`)
**Issue:** `_handle_setup_result` persists the selection before/independently
of what `create_driver_for_selection` actually produced. A "usb" selection
that fell back to a CUPS queue is saved as usb; every subsequent launch
retries USB and re-falls-back (repeating WR-03/WR-04 silently). Behavior is
consistent but the saved state never converges to what actually works.
**Fix:** Have `create_driver_for_selection` report the effective connection
(or driver type) and persist that, or persist after inspecting the returned
driver class.

---

_Reviewed: 2026-07-19_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
