---
phase: 34-architecture-cleanup
reviewed: 2026-07-19T00:00:00Z
depth: standard
files_reviewed: 19
files_reviewed_list:
  - src/claude_teletype/printing/registry.py
  - src/claude_teletype/printing/selection.py
  - src/claude_teletype/printing/profiles.py
  - src/claude_teletype/printing/catalog/__init__.py
  - src/claude_teletype/printing/catalog/juki.py
  - src/claude_teletype/printing/catalog/ibm.py
  - src/claude_teletype/printing/catalog/oki.py
  - src/claude_teletype/printing/catalog/panasonic.py
  - src/claude_teletype/printing/catalog/tally.py
  - src/claude_teletype/printing/catalog/citizen.py
  - src/claude_teletype/printing/catalog/hp.py
  - src/claude_teletype/printing/catalog/epson.py
  - src/claude_teletype/printing/__init__.py
  - src/claude_teletype/printing/drivers.py
  - src/claude_teletype/cli.py
  - src/claude_teletype/tui.py
  - src/claude_teletype/screens/printer_setup.py
  - src/claude_teletype/config.py
  - packaging/claude-teletype.spec
findings:
  critical: 0
  warning: 5
  info: 6
  total: 11
status: issues_found
---

# Phase 34: Code Review Report

**Reviewed:** 2026-07-19
**Depth:** standard
**Files Reviewed:** 19
**Status:** issues_found

## Summary

Reviewed the Phase 34 architecture cleanup (491fcdf..HEAD): ProfileRegistry
threading, pkgutil catalog discovery, facade/dead-code deletion, and the
juki plumbing removal.

**Byte fidelity: VERIFIED.** All 8 dict-literal profiles in the pre-move
`git show 491fcdf:...profiles.py` were AST-extracted and compared
field-for-field against the live `BUILTIN_PROFILES` — zero mismatches
(generic, juki-6100, juki-2200, escp, ppds, pcl, oki-3390,
citizen-cts2000). The `dataclasses.replace` aliases (ibm, juki,
lexmark-forms, oki-ml-*, panasonic-*, tally-*) inherit those verified
bytes and override only name/description/VID. The 491fcdf..HEAD diffs of
the two pre-existing catalog modules (epson.py, oki.py) contain only
added byte lines (the moved escp/oki-3390) — escp2/epson-tm/
oki-microline-native bytes untouched.

**Registry threading: mostly sound.** cli → TeletypeApp →
PrinterSetupScreen → create_driver_for_selection all carry the one
registry object; no `dict(BUILTIN_PROFILES)` rebuilds remain; the
deleted 91-line facade has no surviving importers (grep clean);
JukiPrinterDriver and --juki plumbing are gone; `driver.inner` replaces
the `_inner` reach-in in tui.py. The PyInstaller spec correctly adds
`collect_submodules("claude_teletype.printing.catalog")` for the
pkgutil-invisible imports.

The findings below are silent-fallback holes and back-compat traps —
exactly the class the fail-loud policy claims to have closed.

## Warnings

### WR-01: Stale `[printer] juki = true` config is silently ignored — Juki output degrades with no diagnostic

**File:** `src/claude_teletype/config.py:147-149` (the `filtered` field filter), removal at `config.py` (former `juki: bool` field)
**Issue:** Pre-phase, `config.juki = true` (and `CLAUDE_TELETYPE_JUKI=1`)
selected the juki profile on the chat path (`honor_config_juki` at
491fcdf). The field was deleted, and `load_config`'s
`{k: v for k, v in flat.items() if k in valid}` drops the unknown TOML
key with no message. A user whose stale config carries `juki = true`
now gets auto-detect — which for the CH341 bridge VID deliberately
suggests nothing — so their daisywheel prints unwrapped: no ESC init,
no CR+LF (carriage return without paper advance), no reinit-on-newline.
The phase's own review scope names this exact trap. Note `--juki` on
the CLI fails loudly (Typer "no such option") and `profile = "juki"`
still resolves via the alias — only the boolean key degrades silently.
**Fix:** In `load_config`, detect the retired key and warn once:
```python
if raw.get("printer", {}).get("juki") is True:
    print(
        "Warning: [printer] juki = true is retired -- "
        'set profile = "juki-6100" instead',
        file=sys.stderr,
    )
```
(or map it: `flat.setdefault("printer_profile", "juki")`).

### WR-02: Unknown `config.printer_profile` falls back to generic with zero diagnostic (cli path)

**File:** `src/claude_teletype/cli.py:362-368` (`_resolve_profile_selection`)
**Issue:** When `config.printer_profile` names an unknown profile, the
`except ValueError: resolved_profile = None` branch emits nothing —
no stderr line, no notify. A typo'd profile in config.toml silently
prints generic. This contradicts the phase's stated "unknown profiles
fail loudly" policy, and is inconsistent with the same situation one
layer down: `create_driver_for_selection` emits "Unknown printer
profile ... Check saved_printer_profile in config." for the saved-match
case. Second subtlety: the unknown-name branch also skips
`detect_native_profile`, so the user gets generic even when auto-detect
would have found their printer — an empty profile value behaves better
than a typo'd one.
**Fix:** Emit before falling back:
```python
except ValueError:
    typer.echo(
        f"Warning: unknown printer_profile {config.printer_profile!r} "
        "in config -- using auto-detect",
        err=True,
    )
    resolved_profile = detect_native_profile(registry)
```

### WR-03: Saved-printer-match diagnostics go to stderr, which Textual immediately covers

**File:** `src/claude_teletype/cli.py:895-897`
**Issue:** The smart-startup path calls
`create_driver_for_selection(saved_match, discovery, registry=registry)`
without a `diagnostics` list, so `_emit` prints to stderr. `tui_app.run()`
enters the alternate screen milliseconds later — the "USB direct
unavailable — falling back to CUPS queue X" and "Unknown printer
profile ..." messages are effectively invisible for the whole session.
The WR-04 notify routing was wired only for the in-TUI setup-screen path
(tui.py:281-286); this launch path recreates the exact problem that fix
addressed. This is the path a stale `saved_printer_profile` actually
takes, so the "fail loudly via notify diagnostics" claim does not hold
here.
**Fix:** Collect and forward:
```python
saved_diags: list[str] = []
printer_driver = create_driver_for_selection(
    saved_match, discovery, registry=registry, diagnostics=saved_diags,
)
```
then pass `saved_diags` to `TeletypeApp` (new param) and `notify` each
on mount.

### WR-04: USB pick with no CUPS fallback silently becomes the simulator

**File:** `src/claude_teletype/printing/selection.py:201-202`
**Issue:** In `create_driver_for_selection`, when the user explicitly
picked a USB device, `_find_usb_printer` fails, and there are no
enabled CUPS queues, `driver` stays None and the function returns
`NullPrinterDriver()` with no `_emit` call. Both loud-fallback branches
(lines 179, 194) only fire when a fallback queue exists; the
worst outcome — the user's explicit hardware pick degrading to the
simulator — is the one case that says nothing. The CR-03 comment at
line 190 states the policy ("must not silently become the simulator")
but the code only honors it when a queue is available.
**Fix:** Before `return NullPrinterDriver()`:
```python
if driver is None:
    if selection.connection_type in ("usb", "cups"):
        _emit(
            diagnostics,
            f"Could not open the selected {selection.connection_type} "
            "printer and no CUPS fallback exists -- simulator only",
        )
    return NullPrinterDriver()
```

### WR-05: Unresolvable forward reference `ProfileRegistry` in `create_driver_for_selection` signature

**File:** `src/claude_teletype/printing/selection.py:112`
**Issue:** The annotation `registry: "ProfileRegistry | None" = None`
references a name never imported in the module (not even under
`TYPE_CHECKING`). Verified:
`typing.get_type_hints(create_driver_for_selection)` raises
`NameError: name 'ProfileRegistry' is not defined`. Runtime is
unaffected today, but any hint-evaluating consumer (type checkers,
runtime validators, doc generators) breaks on this public factory. The
quoting is also redundant under the module's
`from __future__ import annotations`. registry.py:34-35 shows the
correct pattern in this same package.
**Fix:**
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from claude_teletype.printing.registry import ProfileRegistry
...
    registry: ProfileRegistry | None = None,
```

## Info

### IN-01: "juki" alias shadows "juki-6100" in the registry's exact VID:PID index

**File:** `src/claude_teletype/printing/catalog/juki.py:55-59`, `src/claude_teletype/printing/registry.py:93`
**Issue:** Verified live: `registry.match_vidpid(0x1A86, 0x7584).name ==
"juki"` — the alias is registered after its target and wins the exact
`(vid, pid)` slot, so any VID:PID consumer surfaces the deprecated
alias name, not the canonical `juki-6100`. Benign today only because
0x1A86 is in `BRIDGE_CHIP_VIDS` and classify() suppresses bridge
suggestions. Also, juki.py:54 still says "and the deprecated --juki
flag" — that flag no longer exists (stale comment).
**Fix:** Drop `usb_vendor_id`/`usb_product_id` in the alias replace
(`usb_vendor_id=None`, matching the oki-ml-epson pattern), or accept
and delete the stale flag mention from the comment.

### IN-02: Cross-module catalog key collisions are silent last-wins at runtime

**File:** `src/claude_teletype/printing/profiles.py:153-159` (`_load_catalog`)
**Issue:** `merged.update(module.PROFILES)` silently overwrites on a
duplicate key across catalog modules; the only guard is the snapshot
test. A one-line runtime check would make the stated "collisions are a
bug" policy self-enforcing.
**Fix:** `dupes = merged.keys() & module.PROFILES.keys()`; raise or
`logger.warning` naming the module and keys before `update`.

### IN-03: `profiles.get_profile` is a legacy bypass of the registry with no src callers

**File:** `src/claude_teletype/printing/profiles.py:167-182`
**Issue:** Only tests call it. It ignores custom profiles and its
case-insensitivity works only because every builtin key happens to be
lowercase — a future mixed-case catalog key would resolve via the
registry but not via `get_profile`. Two lookup authorities is the
pattern ARCH-02 was meant to end.
**Fix:** Migrate the remaining test callers to
`ProfileRegistry(BUILTIN_PROFILES).get` and delete, or add a docstring
line marking it test-legacy-only.

### IN-04: Case-shadowed loser names remain visible in `names()`; collision warnings invisible under the TUI

**File:** `src/claude_teletype/printing/registry.py:64-75, 127-129`
**Issue:** After a case-fold collision, `names()` lists both keys but
`get()` on either resolves to the last-registered winner — the setup
Select and settings screen offer a choice that silently returns a
different profile. The documented safeguard (`logger.warning`) goes to
stderr, which Textual covers (same visibility class as WR-03).
Documented last-wins policy, so noting only.
**Fix:** Consider filtering shadowed keys out of `names()` or surfacing
construction warnings through the notify channel.

### IN-05: Config template's profile comment predates the catalog

**File:** `src/claude_teletype/config.py:41`
**Issue:** `# Printer profile name (generic, juki, escp, ppds/ibm, pcl)`
leads with the deprecated `juki` alias and omits every Phase-34-era
name (juki-6100, juki-2200, escp2, oki-*, citizen-cts2000, ...). New
users are steered to the compat alias.
**Fix:** `# Printer profile name (generic, juki-6100, escp, ppds, pcl, ... — see claude-teletype diagnose for the full list)`.

### IN-06: A catalog module without `PROFILES` crashes app import with a raw AttributeError

**File:** `src/claude_teletype/printing/profiles.py:158`
**Issue:** `module.PROFILES` on a stray/incomplete module in `catalog/`
raises a bare `AttributeError` at first import of profiles.py — the
whole app fails to start with no hint that the catalog contract was
violated. Fail-loud is correct; the message is just opaque.
**Fix:** One-line contract check:
`profs = getattr(module, "PROFILES", None); if profs is None: raise TypeError(f"catalog module {info.name} must export PROFILES")`.

---

_Reviewed: 2026-07-19_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
