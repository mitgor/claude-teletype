# Architecture Patterns

**Domain:** Standalone TUI/CLI app driving a large fleet of USB/USB-LPT dot-matrix printers
**Researched:** 2026-06-12
**Scope:** Integration of v1.6 NEW capabilities (expanded VID:PID matrix, large profile set, package reorg, PyInstaller build) with the existing v1.5 architecture. This is a *subsequent-milestone* architecture study — it assumes the 23-module flat package, the `PrinterDriver` Protocol, `PrinterProfile` frozen dataclass, and 700 passing tests as fixed starting points.

---

## Executive Recommendation (read first)

Four sub-questions, four opinionated answers:

1. **Profile data architecture:** **Keep profiles as Python dataclass literals. Do NOT move to shipped TOML/JSON data files.** Add a thin `registry` layer and a `capabilities()` introspection method. (Section A)
2. **Package layout:** **Reorganize into `printing/`, `rendering/`, `screens/` sub-packages — but keep public import paths stable via re-export shims in the old module names.** Migrate tests *last*, mechanically, in a dedicated commit. (Section B)
3. **VID:PID matrix + bridge chips:** **Two physically different detection concepts must become two different code paths.** Native-USB printers are identified *by* VID:PID (the device IS the printer). Bridge chips (CH340/CH341/PL2303/FTDI) are identified by VID:PID as *a serial/parallel transport*, behind which the printer is **unknowable** — so bridge detection yields a transport + a *profile prompt*, never an auto-assigned profile. (Section C)
4. **PyInstaller:** **One-dir (then optionally one-file) build, console mode, driven by a checked-in `.spec`. Profiles stay importable Python so they need zero `datas` handling. The only real packaging work is `pyusb`+`libusb` as an optional/conditional bundle and Textual's CSS/data files via `collect_data_files`.** (Section D)

**Build order:** Refactor (packages + tech-debt) **first**, fleet expansion **second**, PyInstaller **last**. Rationale in "Suggested Build Order".

---

## Recommended Architecture (target module map)

```
src/claude_teletype/
├── __init__.py
├── __main__.py
├── cli.py                  # Typer entry (slimmed: profile-resolution extracted)
├── config.py
├── errors.py / warnings.py
├── bridge.py               # Claude Code subprocess
├── backends/               # (unchanged) LLM backends
│
├── printing/               # NEW package — everything that touches paper
│   ├── __init__.py         # re-exports public API (see Section B)
│   ├── drivers.py          # Null/File/Cups/Usb/ProfilePrinterDriver + Protocol
│   ├── discovery.py        # discover_all, DiscoveryResult, Cups/USB enumeration
│   ├── detection.py        # NEW: VID:PID matrix + bridge-chip classification
│   ├── selection.py        # PrinterSelection, create_driver_for_selection, match_saved_printer
│   ├── profiles.py         # PrinterProfile dataclass + resolve_style + load_custom_profiles
│   ├── registry.py         # NEW: profile catalog (built-ins + custom merge + lookup)
│   └── catalog/            # NEW: built-in profiles as Python modules, one per family
│       ├── __init__.py     # assembles BUILTIN_PROFILES from family modules
│       ├── epson.py        # FX / LQ / LX / TM
│       ├── oki.py          # Microline
│       ├── ibm.py          # PPDS / Proprinter / Lexmark
│       ├── star_citizen.py # Star + Citizen thermal/impact
│       ├── juki.py         # 6100 / 9100 / 2200 daisywheel
│       └── misc.py         # Panasonic KX-P, Tally, Seiko, generic
│
├── rendering/              # NEW package — bytes-on-the-way-to-paper
│   ├── __init__.py
│   ├── markdown.py         # streaming markdown renderer
│   ├── wordwrap.py
│   ├── pacer.py
│   └── output.py           # multiplexer
│
├── screens/                # NEW package — Textual UI
│   ├── __init__.py
│   ├── app.py              # TeletypeApp (from tui.py)
│   ├── printer_setup.py
│   ├── settings.py
│   ├── typewriter.py
│   ├── file_picker.py
│   └── speed_mode.py
│
├── audio.py / transcript.py / diagnose.py   # leaf utilities, can stay flat
└── teletype.py             # orchestration glue
```

This keeps the three high-churn v1.6 concerns (printers, rendering, screens) cohesive while leaving stable leaf utilities alone. `printing/` is where ~all v1.6 work lands.

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `printing/detection.py` (NEW) | Classify an enumerated USB device: native-printer (→ profile suggestion) vs bridge-chip (→ transport + "pick a profile") vs unknown | `discovery.py` (consumes raw `UsbDeviceInfo`), setup screen (provides suggestion) |
| `printing/registry.py` (NEW) | Single source of truth for "all profiles": built-ins ∪ custom; name lookup; VID:PID index build | `catalog/`, `config.py` (custom TOML), `detection.py`, setup screen, diagnose |
| `printing/catalog/*` (NEW) | Per-family `PrinterProfile` literals | assembled by `catalog/__init__.py` into `BUILTIN_PROFILES` |
| `printing/profiles.py` (MOVED) | The `PrinterProfile` dataclass + `resolve_style` + custom-TOML loader | imported everywhere; gains `capabilities()` method |
| `printing/drivers.py` (MOVED) | Driver classes + Protocol; `ProfilePrinterDriver` codepage/style logic | unchanged behavior |
| `printing/selection.py` (MOVED) | Turn a `PrinterSelection`+`DiscoveryResult` into a live driver | fixes `create_driver_for_selection` device-index bug |
| PyInstaller `.spec` (NEW, repo root) | Freeze the app; bundle Textual data + conditional pyusb/libusb | build-time only; no runtime import |

### Data Flow (detection path, the part that changes most)

```
pyusb enumerate ──► DiscoveryResult.usb_devices: [UsbDeviceInfo(vid,pid,...)]
                          │
                          ▼
         detection.classify(UsbDeviceInfo)  ◄── reads registry VID:PID index
                          │
        ┌─────────────────┼──────────────────────────┐
        ▼                 ▼                           ▼
  NATIVE PRINTER     BRIDGE CHIP                 UNKNOWN / non-printer
  (vid in printer    (vid in bridge set:         (no match)
   matrix)            CH34x/PL2303/FTDI)
        │                 │                           │
  suggest exact      transport=parallel-over-USB;    no suggestion;
  profile (high      profile UNKNOWN → setup must    user picks
  confidence)        PROMPT for family (cannot infer) manually
        │                 │                           │
        └─────────────────┴───────────────┬──────────┘
                                           ▼
                              PrinterSelection(profile_name=...)
                                           ▼
                          selection.create_driver_for_selection
                                           ▼
                       UsbPrinterDriver wrapped in ProfilePrinterDriver
```

The key architectural insight: **today there is a single `auto_detect_profile()` that conflates "I found a device" with "I know what it is."** For a fleet with bridge chips that distinction must become explicit, because a CH341 behind a vintage Epson and a CH341 behind a Juki daisywheel are byte-for-byte indistinguishable at the USB layer.

---

## (A) Profile Data Architecture at Scale

**Decision: keep Python dataclass literals. Add a registry + capability introspection. Do not externalize to shipped data files.**

### Why NOT move to TOML/JSON data files

This is the tempting "scale" move (dozens of profiles → "surely these belong in data files"). It is the wrong call here, for concrete reasons rooted in this codebase:

1. **The data is bytes, not config.** Profiles are full of `b"\x1b\x1e\x09"` literals with inline manual citations (`# ESC RS 9 (1/6" spacing)`). In TOML these become opaque hex strings (`line_spacing = "1b1e09"`) that lose the verbatim-from-manual provenance the project explicitly treats as a contract ("Encoding-table-as-contract for Phase 22 byte literals", "when unsure, leave empty"). Python literals keep code + citation + the "leave empty" discipline in one reviewable place.
2. **PyInstaller cost.** Python modules are frozen automatically with zero `datas` wiring and zero `importlib.resources` runtime lookup. External TOML files must be added to the `.spec` `datas` and read via `importlib.resources.files()` at runtime — a new failure mode (path resolution inside a frozen one-file bundle) for no benefit.
3. **The custom-TOML loader already exists and is the right seam for user data.** `load_custom_profiles()` already parses `[printer.profiles.*]` from user config with hex→bytes and validation. **Users** who want data-driven profiles already have a data-driven path. Built-ins are *code* because they are *the project's verified knowledge*, version-controlled with tests.
4. **Type safety + tests.** `test_builtin_profiles_have_positive_buffer_bytes` and the style-resolution tests operate on real dataclass instances at import time. Externalizing built-ins would push these failures from import-time/CI to runtime.

> **Confidence: HIGH.** This follows directly from existing code structure and the project's own logged decisions. The "data files at scale" instinct is real but the PyInstaller + provenance + existing-custom-loader trifecta makes Python literals strictly better *here*.

### Registry design (the actual scaling fix)

The scaling problem is NOT the storage format — it's that today `BUILTIN_PROFILES` is one flat dict in one file, and three different call sites (`auto_detect_profile`, `create_driver_for_selection`, `get_profile`) each rebuild their own view of it. Introduce a registry:

```python
# printing/registry.py
class ProfileRegistry:
    def __init__(self, builtins: dict[str, PrinterProfile],
                 custom: dict[str, PrinterProfile] | None = None):
        self._profiles = {**builtins, **(custom or {})}      # custom overrides built-in
        self._exact:    dict[tuple[int,int], str] = {}        # (vid,pid) -> name
        self._vid_only: dict[int, str] = {}                   # vid -> name
        self._build_index()

    def get(self, name: str) -> PrinterProfile: ...           # replaces get_profile
    def names(self) -> list[str]: ...
    def match_vidpid(self, vid: int, pid: int) -> PrinterProfile | None: ...
    def all(self) -> dict[str, PrinterProfile]: ...
```

- `catalog/__init__.py` assembles `BUILTIN_PROFILES` by merging per-family dicts. Aliases (`ibm`→`ppds`, `juki`→`juki-6100`) live next to their family.
- `auto_detect_profile()` becomes `registry.match_vidpid()` (one index, no per-call rebuild) — kills the duplicated map-building currently in both `profiles.auto_detect_profile` and `printer._find_usb_printer`.
- The registry is the natural home for the conflict the fleet introduces: **two profiles claiming the same VID** (e.g. multiple OKI VID-only entries). Detect at index-build time, prefer exact-PID, and log/raise on ambiguous VID-only collisions so the fleet stays coherent.

### Capability introspection for `diagnose`

`diagnose` should print "what can this printer do?" without branching on printer name. Add to the dataclass:

```python
def capabilities(self) -> dict[str, bool]:
    return {
        "bold":      bool(self.bold_on),
        "italic":    bool(self.italic_on),
        "underline": bool(self.underline_on),
        "codepage":  bool(self.codepage_command or self.text_codec),
        "auto_cut":  bool(self.end_of_response_sequence),
        "reinit":    self.reinit_on_newline,
        "instant":   self.instant_output,
    }
```

This is pure introspection over existing fields — no new state — and lets `diagnose` render a capability matrix across the whole fleet (great for the "conservative leave-empty rule" verification: a glance shows which families still have empty style codes pending hardware confirmation). It also gives the setup screen a way to show "this profile supports: underline" without hardcoding.

> **Confidence: HIGH** for registry + capabilities; both are refactors of existing data with clear call sites.

### Richer direct-mode fields (init/reset/status, paper handling)

The dataclass already absorbed `codepage_command`/`text_codec`/`text_fallback` cleanly — the same additive, empty-default pattern works for the new fleet fields. Add `status_query: bytes`, `paper_out_sequence`/`form_feed: bytes`, etc., as **empty-default frozen fields**. The frozen-dataclass-with-empty-defaults pattern is the project's proven extension mechanism (every field added since v1.2 followed it). **Do not** add a separate "capabilities sub-object" — flat fields keep `load_custom_profiles` and the TOML contract simple.

---

## (B) Package Layout & Test-Preserving Migration

### The constraint that dictates everything: tests import by absolute path

Every one of the 29 test files imports via `from claude_teletype.X import Y` (verified: `from claude_teletype.profiles`, `from claude_teletype.printer`, etc.). **A naive move of `printer.py` → `printing/drivers.py` breaks ~14 test files at import time** — exactly the 700-test-preservation risk the milestone flags.

### Migration strategy: move + re-export shim, tests migrate last

Three-step, each step independently green:

**Step 1 — Create packages with shims (zero test changes).**
Physically move code into `printing/`, `rendering/`, `screens/`. Then make the *old* module names thin re-export shims:

```python
# claude_teletype/printer.py  (shim — keeps old import path alive)
from claude_teletype.printing.drivers import *          # noqa: F401,F403
from claude_teletype.printing.discovery import *        # noqa: F401,F403
from claude_teletype.printing.selection import *        # noqa: F401,F403
# explicit re-exports for names tests reference by attribute
from claude_teletype.printing.drivers import (
    PrinterDriver, NullPrinterDriver, ProfilePrinterDriver, ...
)
```

After Step 1, **all 700 tests pass unchanged** because `claude_teletype.printer` and `claude_teletype.profiles` still resolve to the same symbols. Run the suite — green is the gate to proceed.

**Step 2 — Repoint internal (non-test) imports** to the new canonical paths (`from claude_teletype.printing.drivers import ...`). Tests still pass via shims. This is where you confirm no module ends up importing through the shim (keeps the shim a pure compatibility surface).

**Step 3 — Migrate tests mechanically, in one dedicated commit per concern.** Rename `from claude_teletype.printer` → `from claude_teletype.printing.drivers` etc. This is a search-replace, reviewable as pure import churn. Optionally rename test files to mirror (`test_printer.py` → `test_drivers.py`) but that is cosmetic — do it last or skip it.

**Step 4 — Delete shims** (optional, end of milestone) once tests and internals no longer reference old paths. Keeping `profiles.py`/`printer.py` shims indefinitely is also defensible if any docs/configs reference them.

### Why this order beats a big-bang move

- Each step has a green-test gate, so a break is localized to the step that caused it.
- The risky physical move (Step 1) is decoupled from the noisy import churn (Step 3), so review is tractable.
- `git mv` preserves blame on the moved files; the shim is new and obviously disposable.

> **Confidence: HIGH.** The re-export-shim pattern is the standard Python package-split technique and is directly validated by the observed absolute-import test style.

### Sizing note

`printer.py` (1036 LOC), `cli.py` (1010), and `tui.py` (984) are the three giants. The package split naturally cleaves `printer.py` into drivers/discovery/detection/selection (each ~150-300 LOC) — this is the single highest-value structural change and also the file where all fleet work lands. `cli.py`'s ~30-line profile-resolution duplication should be extracted to a `printing/selection.py` (or cli-helpers) function as part of this, retiring that tech-debt item.

---

## (C) VID:PID Matrix & Bridge-Chip Detection

**This is the architecturally novel part of v1.6.** The current model (`auto_detect_profile` returns a profile or None) cannot represent the bridge-chip case correctly, and forcing it to will produce wrong auto-assignments.

### Two fundamentally different identity models

| Aspect | Native-USB printer | USB-LPT / USB-serial bridge |
|--------|--------------------|-----------------------------|
| What VID:PID means | Identity of the **printer** (Epson 0x04B8, OKI 0x06BC, HP 0x03F0) | Identity of the **cable/adapter chip** (CH340/341 0x1A86, Prolific PL2303 0x067B, FTDI 0x0403) |
| USB interface class | Usually class 7 (printer) | class 7 **or** vendor-specific/CDC (serial) — NOT reliably 7 |
| Can we infer the profile? | **Yes**, with high confidence (vid→family) | **No.** Any parallel printer can sit behind the bridge. The chip tells you the *transport*, never the *printer*. |
| Correct behavior | Auto-suggest profile, let user confirm | Detect transport, then **prompt** "which printer is connected?" — never auto-assign |

The existing `juki-6100` profile already half-acknowledges this: it pins `usb_vendor_id=0x1A86` (CH341), and the `juki-2200` comment explicitly says *"shares the CH341 USB-LPT adapter with the 6100 (same VID:PID), so VID:PID is left unset to avoid hijacking auto-detect; pick this profile explicitly."* That comment **is the bug** the fleet exposes: pinning a profile to a bridge VID is wrong because the bridge is shared across unrelated printers. v1.6 should generalize this hard-won lesson into the detection architecture.

### Architecture: a classifier, not a matcher

Introduce `printing/detection.py` with a small classification result instead of "profile | None":

```python
class DeviceKind(enum.Enum):
    NATIVE_PRINTER = "native"     # vid in printer matrix
    BRIDGE         = "bridge"     # vid in bridge-chip set
    UNKNOWN        = "unknown"

@dataclass(frozen=True)
class Classification:
    kind: DeviceKind
    suggested_profile: str | None  # set ONLY for NATIVE_PRINTER (or None)
    transport_note: str = ""       # e.g. "CH341 USB-LPT bridge — select printer manually"

def classify(dev: UsbDeviceInfo, registry: ProfileRegistry) -> Classification:
    if dev.vendor_id in BRIDGE_CHIP_VIDS:
        return Classification(DeviceKind.BRIDGE, None,
                              transport_note=BRIDGE_CHIP_VIDS[dev.vendor_id])
    profile = registry.match_vidpid(dev.vendor_id, dev.product_id)
    if profile is not None:
        return Classification(DeviceKind.NATIVE_PRINTER, profile.name)
    return Classification(DeviceKind.UNKNOWN, None)
```

- **Bridge VIDs are a separate data set** (`BRIDGE_CHIP_VIDS = {0x1A86: "CH340/CH341 (QinHeng)", 0x067B: "Prolific PL2303", 0x0403: "FTDI", ...}`), NOT entries in the profile registry. This cleanly prevents the "CH341 hijacks auto-detect" bug: bridge VIDs never carry a profile.
- **No native printer profile should set `usb_vendor_id=0x1A86` anymore.** The juki profiles' bridge-VID pin should be removed; bridge devices are surfaced as "bridge present → pick a profile," with the setup screen pre-highlighting the daisywheel/parallel families.
- Setup-screen UX: NATIVE_PRINTER → preselect suggested profile. BRIDGE → show transport note + force an explicit profile pick (default to last-used or `generic`). UNKNOWN → manual pick.

### Where the matrix lives

`printing/detection.py` (bridge set) + `printing/catalog/*` (native VID:PIDs, co-located with each profile). The registry's VID:PID index (built from `catalog`) is the native matrix; the bridge set is a standalone constant. Two data sets because they answer two different questions. **Class-7 filtering must become advisory, not gating, for bridge devices** — many USB-serial bridges enumerate as CDC/vendor-specific, so the current `bInterfaceClass == 7` filter would hide them. Detection should enumerate all devices and classify by VID first, applying the class-7 heuristic only to disambiguate UNKNOWN devices.

> **Confidence: HIGH** on the native/bridge split (directly evidenced by the juki-2200 comment and USB fundamentals). **MEDIUM** on the exact VID list and per-chip interface-class behavior — the specific PIDs and whether a given adapter exposes class 7 vs CDC needs **hardware verification per adapter** (flag for a verification phase, consistent with the project's existing `human_needed` discipline).

---

## (D) PyInstaller Build Integration

**Decision: checked-in `.spec`, console (non-windowed) app, one-dir build for dev / one-file for distribution, profiles need zero packaging work, pyusb+libusb is the only real packaging task.**

### Entry point

The app already exposes `claude_teletype.cli:app` (Typer) and a `__main__.py`. PyInstaller freezes from a **script**, so add a tiny launcher (or point the spec at `__main__.py`):

```python
# build/entry.py  (or reuse __main__.py)
from claude_teletype.cli import app
if __name__ == "__main__":
    app()
```

`.spec` `Analysis(['build/entry.py'], ...)`, `console=True` (this is a TUI — it needs a terminal; do **not** use `--windowed`/`.app` bundle semantics that detach stdio).

### Data files

- **Profiles:** none. Because built-ins stay Python (Section A), they are frozen as normal modules — **this is a direct payoff of the keep-as-code decision.** Had they been TOML, they'd need `datas` + `importlib.resources` runtime lookups inside the frozen bundle.
- **Textual:** Textual ships CSS/`.tcss` and other data files; pull them in with the hook helper rather than hand-listing:
  ```python
  from PyInstaller.utils.hooks import collect_data_files, collect_submodules
  datas  = collect_data_files("textual")
  hidden = collect_submodules("textual") + collect_submodules("claude_teletype.backends")
  ```
  (`collect_all("textual")` is the heavier hammer if the targeted approach misses anything.) Verify by running the frozen binary's TUI — missing `.tcss` shows as unstyled widgets, an obvious smoke-test signal.
- **Rich / Typer / openai:** generally freeze cleanly; add as `hiddenimports` only if a frozen-run `ImportError` appears. `openai` sometimes needs `collect_data_files("openai")` for its data — verify empirically.

### Optional `pyusb` extra + libusb native lib (the only hard part)

`pyusb` is an *optional* extra and dlopen-loads the native **libusb** shared library at runtime — PyInstaller's static analysis will not see libusb. Two viable strategies:

1. **Recommended: ship a USB-capable build.** Install the `usb` extra into the build env, add libusb explicitly as a binary:
   ```python
   binaries = [("/opt/homebrew/lib/libusb-1.0.0.dylib", ".")]   # macOS; verify path
   hidden  += collect_submodules("usb")
   ```
   The runtime already degrades gracefully when pyusb/libusb is absent (`importlib.util.find_spec`, `NoBackendError` handling) — so a build *with* libusb keeps USB-Direct working, and a build *without* still runs (CUPS/simulator).
2. **Alternative: two build variants** (`-usb` and `-cups-only`) via a spec flag. Adds CI matrix complexity; only worth it if libusb licensing/size is a concern. Start with strategy 1.

The project's existing pyusb-optionality design (find_spec probing, CUPS-only fallback, no hard import) means **the frozen binary inherits graceful degradation for free** — if libusb fails to bundle, the app still launches. That is a strong reason to do PyInstaller *after* the fleet/refactor work is stable.

### macOS specifics

- Console TUI → plain executable, **not** a `.app` bundle (no `BUNDLE()` step). `.app` bundles detach from the terminal and break a TUI.
- Code signing / Gatekeeper: an unsigned one-file binary triggers quarantine on first run. For "macOS primary," plan an ad-hoc `codesign` step (and document `xattr -d com.apple.quarantine` for users) — a distribution detail, not architecture, but flag it for the packaging phase.
- One-file (`--onefile`) unpacks to a temp dir each launch (slower start, ~normal for a CLI). One-dir is faster and easier to debug — use one-dir during development, switch to one-file for release artifacts.

> **Confidence: HIGH** on structure (spec, console mode, profiles-as-code payoff). **MEDIUM** on the exact libusb bundling incantation and macOS signing — both need a real build iteration to confirm (classic "works on my machine until frozen" territory).

---

## Patterns to Follow

### Pattern 1: Additive frozen-field extension
**What:** New profile capabilities (status, paper handling) = new `bytes`/`bool` fields with empty/False defaults on the frozen dataclass + matching `load_custom_profiles` parse line.
**When:** Every new fleet capability.
**Why:** Proven path (codepage landed this way); preserves immutability, custom-TOML compat, and "leave empty when unverified."

### Pattern 2: Re-export shim during package split
**What:** Old module re-exports from new package location until tests migrate.
**When:** Step 1 of the package reorg.
**Why:** Keeps 700 absolute-path-import tests green across the physical move.

### Pattern 3: Classify-then-select (not match-then-assign) for detection
**What:** Detection returns a `Classification` (native/bridge/unknown), and only native devices carry a profile suggestion.
**When:** All fleet USB detection.
**Why:** Bridge chips are transports, not printers — the profile is unknowable from USB alone.

### Pattern 4: Single registry index, not per-call-site map building
**What:** Build VID:PID maps once in `ProfileRegistry`; call sites query it.
**When:** Replaces the duplicated map-building in `auto_detect_profile` and `_find_usb_printer`.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Externalizing built-in profiles to shipped TOML/JSON
**Why bad:** Loses byte-provenance/citations, adds PyInstaller `datas` + runtime `importlib.resources` failure modes, moves invariant checks from import-time to runtime — all for a "scale" benefit the per-family `catalog/` split already delivers.
**Instead:** Per-family Python modules assembled by `catalog/__init__.py`; users get data-driven profiles via the *existing* custom-TOML loader.

### Anti-Pattern 2: Pinning a native-printer profile to a bridge-chip VID
**Why bad:** A CH341/PL2303 is shared across unrelated parallel printers; pinning `juki-6100` to `0x1A86` hijacks auto-detect for every CH341 device (the juki-2200 comment documents this exact pain).
**Instead:** Bridge VIDs live in a separate `BRIDGE_CHIP_VIDS` set that carries no profile; bridge presence triggers a manual profile prompt.

### Anti-Pattern 3: Big-bang package move with simultaneous test rename
**Why bad:** A single commit that moves code *and* rewrites 14 test files' imports makes any breakage ambiguous (move or rename?) and un-reviewable.
**Instead:** Move-with-shim (green) → repoint internals (green) → migrate tests (pure churn).

### Anti-Pattern 4: Building a `.app` bundle / `--windowed` for the TUI
**Why bad:** Detaches stdio; a Textual TUI needs a live terminal.
**Instead:** Console executable, one-dir for dev, one-file for release.

### Anti-Pattern 5: Gating detection on USB class 7 for bridges
**Why bad:** USB-serial bridges often enumerate as CDC/vendor-specific, so the class-7 filter hides them entirely.
**Instead:** Enumerate all devices, classify by VID first; use class-7 only to disambiguate UNKNOWN.

---

## Suggested Build Order (with dependency rationale)

**Refactor → Fleet → Packaging.** Each stage is independently shippable/green.

1. **Stage 1 — Refactor (do first).**
   - Package split via shims (Section B) + tech-debt fixes: registry extraction, `create_driver_for_selection` device-index fix, `discovery=None` dual-meaning split, cli.py profile-resolution extraction.
   - **Why first:** Fleet work lands almost entirely in `printing/`. Doing the reorg + registry *before* adding dozens of profiles means the new profiles are authored directly into the clean `catalog/` structure rather than bloating the 1036-line `printer.py`/524-line `profiles.py` and then being moved. Also: the registry and the classify-then-select detection model are *prerequisites* for representing the fleet correctly.
   - **Test strategy:** shim-preserved green at every step; tests migrate at the end of this stage.

2. **Stage 2 — Fleet expansion (do second).**
   - New `catalog/` family modules, expanded native VID:PID matrix, `BRIDGE_CHIP_VIDS` set, `Classification` detection, richer fields (status/paper/codepage formalized), `capabilities()` + diagnose matrix.
   - **Why second:** Depends on Stage 1's registry + detection split. Each family is additive and independently testable (one test module per family, mirroring `catalog/`).
   - **Verification flag:** mark spec-derived byte codes and bridge interface-class behavior `human_needed` (consistent with existing Phase-22 discipline).

3. **Stage 3 — PyInstaller (do last).**
   - Spec file, Textual `collect_data_files`, conditional libusb bundling, macOS console build + signing.
   - **Why last:** Freezing a *moving* codebase is wasted effort — every refactor would invalidate the spec's hidden-imports/datas tuning. Freeze once the module map and dependency graph are stable. The app's existing graceful pyusb degradation means a libusb-bundling hiccup won't block launch, lowering the risk of doing this last.

**Dependency summary:** Stage 2 needs Stage 1's registry + detection seam. Stage 3 needs Stages 1–2's stable import graph + dependency set. No stage benefits from being earlier than listed.

---

## Scalability Considerations

| Concern | Few profiles (today) | Dozens (v1.6) | Hundreds (future) |
|---------|----------------------|---------------|-------------------|
| Profile storage | one dict, one file | per-family `catalog/` modules + registry | same; consider generated `catalog` from a verified manifest |
| VID:PID lookup | rebuilt per call | single registry index | same index; add collision diagnostics |
| Bridge ambiguity | implicit (juki comment) | explicit `Classification` + manual prompt | per-bridge "recent printer" memory in config |
| Test count | 700 | +per-family modules | mirror `catalog/` 1:1 so test growth is mechanical |
| Frozen-bundle size | n/a | profiles-as-code add ~nothing | still negligible (bytes literals) |

---

## Open Questions / Gaps (flag for phase-specific research)

1. **Exact bridge-chip USB interface-class behavior** — does a CH341 USB-LPT adapter enumerate as class 7 or CDC/vendor-specific? Determines whether detection can keep any class-7 fast path. *Needs hardware.* (MEDIUM)
2. **Specific PIDs for each printer family** — many entries will be VID-only (as OKI/Epson already are); the matrix's PID precision needs `diagnose`-on-real-device confirmation. *Needs hardware.* (MEDIUM)
3. **libusb bundling path + macOS signing** — exact dylib path, bundle-vs-require, ad-hoc vs notarized signing for distribution. *Needs a build iteration.* (MEDIUM)
4. **Multiple-printer support** — the device-index fix in `create_driver_for_selection` enables selecting among several USB printers; the fleet makes multi-device setups more likely. Is full multi-printer selection in scope for v1.6 or just the index-bug fix? (clarify with roadmap)
5. **Textual data-file completeness under freeze** — confirm `collect_data_files("textual")` captures all `.tcss`/widget assets; smoke-test the frozen TUI. (LOW — easily verified empirically)

---

## Sources

- Existing codebase: `src/claude_teletype/printer.py`, `profiles.py`, `PROJECT.md`, `pyproject.toml`, `tests/*` import analysis (HIGH — primary source).
- PyInstaller docs via Context7 `/pyinstaller/pyinstaller` v6.14.1: `collect_data_files`, `collect_all`, spec `datas`/module-data patterns (HIGH).
- USB device-class fundamentals and bridge-chip identity model (CH34x/PL2303/FTDI as transports) — general domain knowledge corroborated by the project's own `juki-2200` bridge-sharing comment (HIGH on the principle; MEDIUM on per-chip specifics pending hardware).
