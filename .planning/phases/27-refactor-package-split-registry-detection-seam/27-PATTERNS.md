# Phase 27: Refactor — Package Split, Registry & Detection Seam - Pattern Map

**Mapped:** 2026-06-12
**Files analyzed:** 23 source modules (move/split) + 4 new modules + 29 test files (import migration)
**Analogs found:** all patterns are in-repo (this is a same-codebase refactor) — every "analog" is the current implementation being moved/split

> **Refactor nature:** Unlike a feature phase, the "closest analog" for every new file IS the existing code being moved or extracted. The value of this map is (1) the exact symbol→destination mapping for the package split, (2) the exhaustive list of test patch-target strings that break per moved module, and (3) the concrete duplicated-code call sites the registry/Classification work consolidates.

---

## File Classification

### Moved modules (Step 1: move + re-export shim)

| New file | Role | Data flow | Source (analog) | Match |
|----------|------|-----------|-----------------|-------|
| `printing/drivers.py` | driver | streaming/file-I/O | `printer.py` lines 16-418 (Protocol + 6 driver classes) | split-of-source |
| `printing/discovery.py` | service | event-driven (enumerate) | `printer.py` lines 447-801 (`discover_*`, `_find_usb_printer`, dataclasses) | split-of-source |
| `printing/selection.py` | service | transform | `printer.py` lines 804-941 (`match_saved_printer`, `create_driver_for_selection`, `discover_printer`, `select_printer`) | split-of-source |
| `printing/profiles.py` | model | CRUD (lookup) | `profiles.py` (whole file) | moved |
| `printing/__init__.py` | config | — | NEW (re-export public API) | n/a |
| `rendering/markdown.py` | utility | transform (streaming) | `markdown.py` | moved |
| `rendering/wordwrap.py` | utility | transform | `wordwrap.py` | moved |
| `rendering/pacer.py` | utility | transform | `pacer.py` | moved |
| `rendering/output.py` | utility | transform (multiplex) | `output.py` | moved |
| `screens/app.py` | provider | event-driven | `tui.py` (`TeletypeApp`) | moved |
| `screens/printer_setup.py` | component | request-response | `printer_setup_screen.py` | moved |
| `screens/settings.py` | component | request-response | `settings_screen.py` | moved |
| `screens/typewriter.py` | component | request-response | `typewriter_screen.py` | moved |
| `screens/file_picker.py` | component | request-response | `file_picker_screen.py` | moved |
| `screens/speed_mode.py` | component | request-response | `speed_mode_screen.py` | moved |

> **Note on `tui.py`:** `tui.py` (984 LOC) holds `TeletypeApp` plus inline helper screens (e.g. `ConfirmSwapScreen`, imported by `tests/test_settings_screen.py:8`). Whatever lands in `screens/app.py` must keep `ConfirmSwapScreen` importable. Decide whether `tui.py` becomes a shim re-exporting from `screens/app.py` or stays top-level (CONTEXT/ARCHITECTURE say cli.py/tui.py stay top-level — so `tui.py` likely keeps `TeletypeApp` and the screen *modules* move; confirm during planning).

### New modules (extracted/created, not moved)

| New file | Role | Data flow | Closest analog | Match |
|----------|------|-----------|----------------|-------|
| `printing/registry.py` (`ProfileRegistry`) | model/registry | CRUD + index lookup | `profiles.auto_detect_profile` map-building (lines 486-524) + `printer._find_usb_printer` | role-match (consolidates 4 duplicated matchers) |
| `printing/detection.py` (`Classification`, `classify`, `DeviceKind`) | service | transform/classify | `profiles.auto_detect_profile` (returns `profile|None`) | role-match (replaces conflated matcher) |
| cli profile-resolution helper (dedup target) | utility | transform | `cli._resolve_print_context` (lines 434-473) ↔ `cli.main` (lines 778-822) | exact-dup pair |
| `SetupDecision` sentinel split (REF-04) | model/enum | event-driven | `discovery=None` triple-use in `cli.py`/`tui.py` | role-match |

---

## Pattern Assignments

### `printing/drivers.py` (driver, streaming/file-I/O)

**Source:** `printer.py` lines 16-418.

**Symbols to move:** `PrinterDriver` (Protocol), `NullPrinterDriver`, `FilePrinterDriver`, `CupsPrinterDriver`, `UsbPrinterDriver`, `ProfilePrinterDriver`, `JukiPrinterDriver`, `A4_COLUMNS`, `make_printer_output`, `chunk_writes`.

**Import pattern at top of source** (`printer.py:1-13`):
```python
from __future__ import annotations
import re, subprocess, sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from claude_teletype.profiles import PrinterProfile, get_profile
```
After the split this becomes `from claude_teletype.printing.profiles import PrinterProfile, get_profile`.

**Codepage consumption pattern (DIR-01 — DO NOT disturb behavior)** lives entirely in `ProfilePrinterDriver` (`printer.py:229-401`). The three fields are consumed here:
- `text_fallback` applied per-char BEFORE codec (`printer.py:286-289`)
- `_needs_codepage()` gates on `text_codec` (`printer.py:316-326`)
- `_ensure_codepage()` lazily emits `codepage_command` once (`printer.py:328-340`)
- atomic CR+LF+reinit transfer (`printer.py:290-301`) — **the locked invariant; must not fragment.**

### `printing/discovery.py` (service, event-driven enumerate)

**Source:** `printer.py` lines 447-801 + the discovery dataclasses (lines 47-90).

**Symbols to move:** `UsbDeviceInfo`, `CupsPrinterInfo`, `DiscoveryResult`, `PrinterSelection`, `_find_usb_printer`, `kernel_driver_holds_printer`, `discover_usb_device`, `discover_usb_device_verbose`, `discover_macos_usb_printers`, `discover_cups_printers`, `discover_all`.

> `PrinterSelection` (`printer.py:83-91`) is consumed by both `selection.py` and `screens/printer_setup.py` — place it where both can import without a cycle (discovery.py or a small `types.py`).

**Class-7 filter pattern (3 copies — ARCHITECTURE flags these to relax for bridges):**
- `_find_usb_printer`: `printer.py:479,486` (`USB_PRINTER_CLASS = 7`)
- `discover_all`: `printer.py:745,749`
- `auto_detect_profile`: `profiles.py:457,506`
- `kernel_driver_holds_printer`: `printer.py:559`

### `printing/selection.py` (service, transform)

**Source:** `printer.py` lines 804-941.

**Symbols to move:** `select_printer`, `match_saved_printer`, `create_driver_for_selection`, `discover_printer`.

**`create_driver_for_selection` — the REF-03 device-index bug** (`printer.py:847-885`). The bug is on **line 870**:
```python
if selection.connection_type == "usb":
    driver = _find_usb_printer()   # <-- BUG: returns FIRST printer-class device,
                                   # ignores selection.device_index entirely.
```
`selection.device_index` (`printer.py:87`, the index into `discovery.usb_devices`) is captured but never used. The fix must reconnect to the SAME device the user picked (VID:PID + bus/address or serial). The identity data already exists on `UsbDeviceInfo` (`printer.py:47-57`: `vendor_id`, `product_id`, `serial`, `bus`, `address`). `_find_usb_printer` (`printer.py:447-530`) currently takes no selector — it needs a select-by-identity parameter.

**Profile-wrapping tail** (`printer.py:878-884`) — keep as-is; this is where `ProfilePrinterDriver` wrapping happens once a driver exists.

### `printing/registry.py` (NEW — `ProfileRegistry`)

**Analog — the duplicated VID:PID map-building to consolidate (4 call sites):**

1. **`profiles.auto_detect_profile`** (`profiles.py:486-524`) — the canonical pattern:
```python
exact_map: dict[tuple[int, int], PrinterProfile] = {}
vid_only_map: dict[int, PrinterProfile] = {}
for profile in all_profiles.values():
    if profile.usb_vendor_id is not None:
        if profile.usb_product_id is not None:
            exact_map[(profile.usb_vendor_id, profile.usb_product_id)] = profile
        else:
            vid_only_map[profile.usb_vendor_id] = profile
# ... exact match takes priority over vid-only
if (vid, pid) in exact_map: return exact_map[(vid, pid)]
if vid in vid_only_map:     return vid_only_map[vid]
```
2. **`match_saved_printer`** (`printer.py:818-833`) — VID:PID parse + linear scan of `discovery.usb_devices`.
3. **`printer_setup_screen._match_profile_by_vid_pid`** (`printer_setup_screen.py:262-285`) — a 4th re-implementation that scans `self._all_profiles` for `usb_vendor_id`/`usb_product_id` via `getattr`.
4. **`cli`** merge pattern (`cli.py:792-795` and `cli.py:447-448`): `all_profiles = dict(BUILTIN_PROFILES); all_profiles.update(custom_profiles_dict)` — appears twice.

**Registry shape (from ARCHITECTURE.md §A, Claude's discretion on exact API):** `get(name)`, `names()`, `match_vidpid(vid,pid) -> PrinterProfile|None`, `all()`. Constructor merges `{**builtins, **(custom or {})}` (custom overrides built-in) and builds the exact/vid-only index once. This replaces `get_profile` (`profiles.py:306-321`), the merge in cli, and the three matchers above.

**BUILTIN_PROFILES dict shape** (`profiles.py:114-303`): a module-level `dict[str, PrinterProfile]` with 8 literal entries plus 2 alias entries built via `dataclasses.replace` (`profiles.py:291-303`: `ibm`←`ppds`, `juki`←`juki-6100`). The registry must preserve these aliases. Per ARCHITECTURE, aliases eventually live next to their family in `catalog/`, but catalog/ split is OUT OF SCOPE this phase (Phase 29) — keep `BUILTIN_PROFILES` as-is, wrap it in the registry.

### `printing/detection.py` (NEW — `Classification`)

**Analog being superseded:** `auto_detect_profile` (`profiles.py:460-524`) returns `PrinterProfile | None`, conflating "found a device" with "know what it is."

**Target model (ARCHITECTURE.md §C, DET-02 — enum vs dataclass at Claude's discretion):**
```python
class DeviceKind(enum.Enum):
    NATIVE_PRINTER = "native"; BRIDGE = "bridge"; UNKNOWN = "unknown"

@dataclass(frozen=True)
class Classification:
    kind: DeviceKind
    suggested_profile: str | None  # only set for NATIVE_PRINTER
    transport_note: str = ""

def classify(dev: UsbDeviceInfo, registry: ProfileRegistry) -> Classification: ...
```
**Scope guard (CONTEXT):** this phase ships the Classification *type and seam* only — NO new detection data (`BRIDGE_CHIP_VIDS` population, VID matrix expansion, removing `juki-6100`'s `usb_vendor_id=0x1A86` pin) is Phase 28. The juki bridge-VID pin (`profiles.py:134`) and the juki-2200 comment (`profiles.py:142-146`) document the bug but stay untouched here.

### cli profile-resolution dedup (REF-05)

**Two near-identical blocks to unify:**
- `cli._resolve_print_context` (`cli.py:434-473`) — load custom, merge BUILTIN, resolve by `--printer` > config > auto-detect.
- `cli.main` (`cli.py:778-822`) — same chain plus `--juki` deprecation branch (`cli.py:806-809,815-817`) and `config.juki` backward-compat.

The `main()` version is the superset. Extract one helper (its comment at `cli.py:434` already says *"mirrors main() lines ~325-371"* — acknowledging the dup). Helper should return `(config, all_profiles, resolved_profile)` like `_resolve_print_context` does (`cli.py:473`). Once `ProfileRegistry` exists, the `dict(BUILTIN_PROFILES); .update(custom)` merge inside both collapses to registry construction.

### `discovery=None` sentinel split (REF-04)

**Three distinct meanings of `discovery=None` reaching `TeletypeApp`** (all set in `cli.py`, consumed in `tui.py`):

| Set at | Meaning | Should become |
|--------|---------|---------------|
| `cli.py:935` | `--no-tui` mode, no screen | distinct sentinel/decision |
| `cli.py:941` | `--device` override, skip setup | distinct sentinel/decision |
| `cli.py:965` | saved printer matched, skip setup | distinct sentinel/decision |
| (else) `cli.py:943` | `discovery = discover_all()` → setup screen shows | the only "show setup" case |

**Consumer:** `tui.TeletypeApp._needs_printer_setup` (`tui.py:163-172`) collapses all three Nones to "no setup," and `_show_setup_screen` (`tui.py:222-232`) only runs when discovery is truthy. The constructor param is `discovery=None` (`tui.py:131`, stored `tui.py:156`). A `SetupDecision` enum (or distinct sentinel objects) at Claude's discretion (CONTEXT specifics) makes saved-match-skip vs device-override-skip distinguishable.

---

## Shared Patterns

### Re-export shim (Step 1 — the migration's core mechanism)
**Apply to:** every old module path (`printer.py`, `profiles.py`, and the 5 `*_screen.py` files, `markdown.py`, `wordwrap.py`, `pacer.py`, `output.py`).
**Pattern (from ARCHITECTURE.md §B):**
```python
# claude_teletype/printer.py  (shim)
from claude_teletype.printing.drivers import *      # noqa: F401,F403
from claude_teletype.printing.discovery import *    # noqa: F401,F403
from claude_teletype.printing.selection import *    # noqa: F401,F403
from claude_teletype.printing.drivers import (
    PrinterDriver, NullPrinterDriver, ProfilePrinterDriver, FilePrinterDriver,
    CupsPrinterDriver, UsbPrinterDriver, JukiPrinterDriver, make_printer_output,
    chunk_writes, A4_COLUMNS,
)
from claude_teletype.printing.discovery import (
    UsbDeviceInfo, CupsPrinterInfo, DiscoveryResult, PrinterSelection,
    discover_all, discover_cups_printers, discover_usb_device,
    discover_usb_device_verbose, discover_macos_usb_printers,
    kernel_driver_holds_printer, _find_usb_printer,
)
from claude_teletype.printing.selection import (
    select_printer, match_saved_printer, create_driver_for_selection, discover_printer,
)
```
**Why explicit re-exports matter:** tests reference names by attribute on the *module* for patching (e.g. `patch("claude_teletype.printer.subprocess")`). `import *` does not re-export `subprocess`/`sys` (module-level non-`__all__` names), so **`patch("claude_teletype.printer.subprocess")` will break unless the shim also re-binds the patched globals** — OR (cleaner) the test patch targets move to the new module in Step 3. See "Test patch-target migration" below.

### Additive frozen-field extension
**Source:** `PrinterProfile` (`profiles.py:19-111`) — every field has an empty/`False`/`None` default. The codepage fields (`codepage_command`, `text_codec`, `text_fallback`, `profiles.py:97-111`) landed this way (commits d70aded/7ccdff5).
**Apply to:** any field touched during DIR-01 formalization; matching parse line in `load_custom_profiles` (`profiles.py:389-391`).
**DIR-01 scope:** formalize already-shipped codepage code via test + TOML coverage — the fields already exist; the `load_custom_profiles` parse already handles them (`profiles.py:389-391`). Work is test/TOML, not new fields.

### Import-locally + patch-at-source convention
**Source:** pervasive in `cli.py` (`from claude_teletype.printer import ...` inside functions: `cli.py:110,283,876,930,953`) and `tui.py` (`tui.py:171,194,247,319,517,699`). These local imports resolve through the shim after Step 1, so **internal imports stay green for free in Step 1**; Step 2 repoints them to `claude_teletype.printing.*`.

---

## Test Patch-Target Migration (the 700-test-preservation risk)

Every test uses absolute imports `from claude_teletype.X import Y` and patches at source-module paths. When module `X` moves, both its import lines AND its `patch("claude_teletype.X.attr")` strings must migrate **in the same Step-3 commit**.

### Imports per moved module (Step 3 search-replace count)

| Old module | # test files | New canonical path |
|------------|-------------|--------------------|
| `claude_teletype.printer` | 10 | `claude_teletype.printing.{drivers,discovery,selection}` |
| `claude_teletype.profiles` | 9 | `claude_teletype.printing.profiles` (+ `registry`) |
| `claude_teletype.markdown` | 3 | `claude_teletype.rendering.markdown` |
| `claude_teletype.wordwrap` | 3 | `claude_teletype.rendering.wordwrap` |
| `claude_teletype.output` | 2 | `claude_teletype.rendering.output` |
| `claude_teletype.pacer` | 2 | `claude_teletype.rendering.pacer` |
| `claude_teletype.tui` | 6 | top-level (likely unchanged) / `claude_teletype.screens.app` |
| `claude_teletype.printer_setup_screen` | 1 | `claude_teletype.screens.printer_setup` |
| `claude_teletype.settings_screen` | 2 | `claude_teletype.screens.settings` |
| `claude_teletype.typewriter_screen` | 2 | `claude_teletype.screens.typewriter` |
| `claude_teletype.file_picker_screen` | 3 | `claude_teletype.screens.file_picker` |
| `claude_teletype.speed_mode_screen` | 2 | `claude_teletype.screens.speed_mode` |

### Patch-target strings that break per moved module (exhaustive)

These are the `patch("...")` argument strings (and their occurrence counts) that must be rewritten to the symbol's NEW home module:

**Moving to `printing/discovery.py`:**
- `claude_teletype.printer.subprocess` ×27 (in `test_printer.py`, `test_teletype.py` — patches the `subprocess` imported into the discovery functions)
- `claude_teletype.printer.discover_usb_device` ×7
- `claude_teletype.printer.discover_cups_printers` ×7
- `claude_teletype.printer.discover_usb_device_verbose` ×5
- `claude_teletype.printer.discover_all` ×2
- `claude_teletype.printer._find_usb_printer` ×3
- `claude_teletype.printer.sys` ×3

**Moving to `printing/selection.py`:**
- `claude_teletype.printer.discover_printer` ×30  ← **highest-volume target**
- `claude_teletype.printer.create_driver_for_selection` ×1

**Moving to `printing/drivers.py`:**
- `claude_teletype.printer.chunk_writes` ×1

**Moving to `printing/registry.py` or `printing/profiles.py`:**
- `claude_teletype.profiles.auto_detect_profile` ×1 (`test_teletype.py:375`) — note: if `auto_detect_profile` is superseded by `registry.match_vidpid`/`classify`, this patch target changes module AND possibly name.

**Moving to `rendering/`:**
- `claude_teletype.markdown.MarkdownRenderer` ×10
- `claude_teletype.pacer.asyncio` ×6
- `claude_teletype.wordwrap.WordWrapper` ×2
- `claude_teletype.pacer.sys` ×1

**Subtle trap:** `patch("claude_teletype.printer.discover_printer")` (×30) and `patch("claude_teletype.printer.subprocess")` (×27) patch the name **as bound in the source module's namespace**. After Step 2 repoints `cli.py`/`teletype.py` to import from `printing.selection`/`printing.discovery`, a test patching the OLD `claude_teletype.printer.discover_printer` will patch the shim's re-exported name — which the production code no longer reads. **This is exactly why ARCHITECTURE.md orders Step 2 (repoint internals) BEFORE Step 3 (migrate tests) but keeps the suite green via shims in between** — the tests still import-resolve, but a patch may silently no-op. Validate by confirming tests that assert the mock was *called* still pass after Step 2; if any fail, that patch target must move with Step 2, not Step 3.

---

## No Analog Found

None. This is a same-codebase refactor — every target maps to existing code being moved, split, or de-duplicated. The two genuinely new files (`registry.py`, `detection.py`) consolidate existing duplicated logic rather than introducing unprecedented patterns.

---

## Metadata

**Analog search scope:** `src/claude_teletype/` (26 py modules), `tests/` (29 test files).
**Files scanned:** `printer.py` (full), `profiles.py` (full), `cli.py` (resolution + setup blocks), `tui.py` (discovery flow), `printer_setup_screen.py` (profile matcher), plus grep across all of `src/` and `tests/` for imports, patch targets, and `discovery=` usages.
**Key source line refs:** `create_driver_for_selection` bug `printer.py:870`; codepage consumption `printer.py:286-340`; 4 VID:PID matchers `profiles.py:486-524`, `printer.py:818-833`, `printer_setup_screen.py:262-285`, `cli.py:792-795`; cli dup `cli.py:434-473`↔`778-822`; discovery sentinel `cli.py:935,941,943,965` → `tui.py:131,156,163-172`.
**Pattern extraction date:** 2026-06-12
