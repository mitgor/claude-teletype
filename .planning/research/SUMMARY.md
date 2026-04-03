# Project Research Summary

**Project:** Claude Teletype v1.4 -- Printer Setup TUI
**Domain:** Interactive hardware-setup TUI feature added to existing Python CLI/TUI app
**Researched:** 2026-04-02
**Confidence:** HIGH

## Executive Summary

Claude Teletype v1.4 replaces the current invisible, silent printer auto-detection chain with an explicit, interactive setup screen that users experience on first launch (or whenever their saved printer is unavailable). The existing codebase (Textual 7.x, Typer, Rich, pyusb, CUPS subprocess integration) already contains every hardware-discovery primitive required -- `discover_usb_device_verbose()`, `discover_cups_printers()`, `auto_detect_profile()`, `save_config()`, and an existing `ModalScreen` pattern in `settings_screen.py`. No new dependencies are needed; this milestone is purely a UI integration layer over working backend code.

The recommended approach is a three-layer build: (1) refactor discovery into a structured `DiscoveryResult` dataclass computed before Textual starts, (2) build `PrinterSetupScreen(Screen[PrinterSelection | None])` that renders the pre-computed results and lets the user pick a connection method, device, and profile, and (3) wire conditional `push_screen` on `TeletypeApp.on_mount()` so the setup screen gates the main chat screen only when needed. A fourth parallel deliverable -- the `claude-teletype diagnose` CLI subcommand -- is fully independent of the TUI and can be built at any point once `discover_all()` exists.

The two highest risks are both in the pyusb auto-install flow: (a) running `uv sync` synchronously inside Textual freezes the event loop -- it must use `asyncio.create_subprocess_exec` inside a `@work` worker from day one, and (b) Python's import cache blocks reimporting pyusb after a same-session install -- the `sys.modules` cache for `usb.*` must be cleared before retrying the import. A secondary platform risk is macOS kernel driver conflicts preventing direct USB access; the setup screen must present CUPS as a co-equal (and on macOS, often more realistic) option. Config corruption during `save_config()` must be mitigated with atomic writes (`os.replace`) from the start, not as a later fix.

## Key Findings

### Recommended Stack

No new dependencies are required for v1.4. Textual 7.5.0 (already installed) ships all needed widgets: `OptionList`, `RadioSet`, `RadioButton`, `LoadingIndicator`, `Button`, `Static`. The `@work(thread=True)` worker pattern for background tasks already exists in `tui.py`. Typer's existing `_PromptFriendlyGroup` hack correctly routes a new `diagnose` command without changes. Rich's `Table` and `Console` (already imported in `cli.py`) cover the diagnostic command output. `subprocess` and `shutil` (stdlib) cover `uv sync` invocation with the same patterns already used for CUPS and Claude binary detection.

**Core technologies:**
- Textual 7.5.0: `PrinterSetupScreen` full-screen wizard -- all widgets already available; `Screen[ResultType]` typed dismiss already used in `SettingsScreen`
- Typer >=0.23.0: `diagnose` subcommand -- identical pattern to existing `config show`/`config init` commands
- Rich >=14.0.0: structured diagnostic output table in `diagnose` command -- `Console` already instantiated in `cli.py`
- subprocess + shutil (stdlib): `uv sync --extra usb` invocation via async worker -- same patterns as existing CUPS and Claude binary checks
- tomllib + hand-formatted template (existing): TOML config persistence -- `save_config()` already works; add `cups_printer` field and `[printer.saved]` section

### Expected Features

**Must have (table stakes):**
- SETUP-01: Device enumeration list -- aggregate USB + CUPS discovery into a single visible list; this is the core value proposition replacing invisible auto-detection
- SETUP-02: Connection method selection -- USB Direct vs CUPS Queue with explicit labels distinguishing character-by-character streaming vs line-buffered
- SETUP-03: Profile assignment -- dropdown from existing `BUILTIN_PROFILES`; pre-selected via `auto_detect_profile()` VID:PID match
- SETUP-04: Save selection to config -- persist via existing `save_config()`; users must not repeat setup on every launch
- SETUP-05: Skip setup when saved printer is still connected -- match USB by VID:PID (not bus address), CUPS by queue name
- SETUP-06: Connection status indicators -- per-device "Connected / Not Found / Driver Missing" using existing diagnostic messages from `_find_usb_printer()`
- SETUP-07: Graceful pyusb-missing handling -- "USB unavailable" state shows CUPS printers; never crashes or shows blank list
- SETUP-08: Skip/simulator option -- always-visible escape hatch to `NullPrinterDriver`

**Should have (differentiators):**
- DIFF-01: Auto-install pyusb via `uv sync --extra usb` -- zero-friction USB setup; must be async from day one
- DIFF-02: Inline diagnostic messages -- show discovery progress log in setup screen; data already produced by `_find_usb_printer(diagnostics)`
- DIFF-03: VID:PID auto-match profile suggestion -- wire existing `auto_detect_profile()` result to profile dropdown default; cheap, high UX value
- DIFF-04: `claude-teletype diagnose` command -- structured Rich output for troubleshooting; fully independent of TUI

**Defer (v2+):**
- DIFF-05: Live device refresh button -- edge case (most users plug in before launching); add if requested
- DIFF-06: Test print from setup -- adds driver lifecycle complexity in setup context; defer to post-v1.4

### Architecture Approach

The setup screen integrates as a **conditional gate screen**: `discover_all()` runs before `TeletypeApp.run()`, passing a `DiscoveryResult` dataclass to the app constructor. In `on_mount()`, `_needs_printer_setup()` checks whether the saved printer config matches discovery results; if not, it pushes `PrinterSetupScreen` via a `@work` worker to avoid screen lifecycle races. The setup screen is purely reactive -- it receives pre-computed discovery data and never calls blocking I/O itself (the one exception: pyusb auto-install, which runs as a nested async worker). Two new files and four modified files carry the full implementation.

**Major components:**
1. `printer_setup_screen.py` (NEW, 200-300 lines) -- full-screen Textual `Screen[PrinterSelection | None]`; renders `DiscoveryResult`; handles USB/CUPS/skip selection; conditional "Install USB Support" async button
2. `diagnose.py` (NEW, 80-120 lines) -- standalone Rich console diagnostic report; all discovery functions, dependency checks, system info; no TUI dependency
3. `printer.py` (MODIFIED) -- add `DiscoveryResult`, `UsbDeviceInfo`, `CupsPrinterInfo` dataclasses; add `discover_all()` and `create_driver_for_selection()`
4. `tui.py` (MODIFIED) -- accept `discovery` constructor param; add `_needs_printer_setup()` and `_handle_printer_setup()` callback; conditional screen push via `@work`
5. `config.py` (MODIFIED) -- add `saved_printer_type`, `saved_printer_id`, `saved_printer_profile` fields; add `[printer.saved]` TOML section; atomic `os.replace()` writes
6. `cli.py` (MODIFIED) -- call `discover_all()` before TUI launch; add `diagnose` subcommand; split TUI vs `--no-tui` printer flow

### Critical Pitfalls

1. **Subprocess blocks event loop** -- `subprocess.run()` for `uv sync` freezes the TUI for 2-10 seconds. Use `asyncio.create_subprocess_exec` inside a `@work` async worker from day one; show `LoadingIndicator` during install. This cannot be retrofitted; it must be the initial design.

2. **pyusb import cache after same-session install** -- Python caches the failed `import usb.core` in `sys.modules`; retrying after `uv sync` still raises `ImportError`. Fix: use `importlib.util.find_spec("usb")` for pre-install checks (no import attempted), and clear all `usb.*` keys from `sys.modules` before retrying post-install.

3. **macOS kernel driver conflict** -- `AppleUSBPrinterClass.kext` exclusively claims USB printer-class devices; pyusb `detach_kernel_driver()` silently fails on macOS. Present CUPS and USB Direct as co-equal options; default to CUPS first on macOS; show "macOS kernel driver conflict -- use CUPS queue instead" diagnostic when USB direct fails.

4. **Config corruption on partial write** -- `path.write_text()` is not atomic; a mid-write crash leaves a truncated TOML file causing `TOMLDecodeError` on next launch. Write to a temp file, validate with `tomllib.loads()`, then `os.replace()` atomically. Never use direct `write_text()` for config saves.

5. **Textual screen lifecycle race** -- pushing `PrinterSetupScreen` synchronously in `on_mount()` may execute before the main screen's compose/mount cycle completes, causing blank screens or missing keybindings after dismiss. Use `@work` + `push_screen_wait` to defer the push until the event loop is stable.

## Implications for Roadmap

Based on research, the dependency graph strongly suggests a 3-phase build order that mirrors the architecture's "data structures first, then UI, then integration" principle.

### Phase 1: Data Layer and Diagnose Command

**Rationale:** All subsequent work depends on `DiscoveryResult` and the refactored `discover_all()`. Building data structures and the diagnose command first establishes the foundation, gives an independently testable deliverable, and validates the discovery refactor before the TUI is involved. The diagnose command has zero TUI risk and is useful immediately for troubleshooting.

**Delivers:** `DiscoveryResult`/`UsbDeviceInfo`/`CupsPrinterInfo` dataclasses in `printer.py`; `discover_all()` function; `PrinterSelection` result dataclass; config field additions (`saved_printer_type`, `saved_printer_id`, `saved_printer_profile`); `diagnose.py` module; `claude-teletype diagnose` CLI command wired via Typer.

**Addresses:** DIFF-04 (diagnose command), foundational data structures for all SETUP-0x features.

**Avoids:** None of the TUI pitfalls apply here. Lowest-risk phase.

### Phase 2: Setup Screen Core and TUI Integration

**Rationale:** With data structures in place, build `PrinterSetupScreen` and wire it into `TeletypeApp.on_mount()`. This is the highest-complexity phase because it involves Textual screen lifecycle management and the pyusb async install flow -- both critical pitfalls must be addressed here, not deferred. The macOS CUPS-vs-USB UX decisions are also made here.

**Delivers:** `printer_setup_screen.py` with full device enumeration list, connection method selection, profile assignment (with VID:PID auto-match), pyusb-missing state with async auto-install flow, skip/simulator button, inline diagnostic log. Conditional `push_screen` integration via `@work` in `tui.py`. Updated `cli.py` startup flow passing `DiscoveryResult` to TUI constructor.

**Addresses:** SETUP-01, SETUP-02, SETUP-03, SETUP-06, SETUP-07, SETUP-08, DIFF-01, DIFF-02, DIFF-03.

**Avoids:** Pitfall 1 (async subprocess), Pitfall 2 (import cache), Pitfall 3 (macOS kernel driver), Pitfall 5 (screen lifecycle).

### Phase 3: Config Persistence and Smart Startup

**Rationale:** Saving the selection and skipping setup on reconnect is the polish that transforms the setup screen from a recurring obstacle into a one-time event. Atomic write safety belongs here because this is when `save_config()` gains new code paths -- the corruption risk must be addressed before those paths ship.

**Delivers:** `save_config()` upgraded to atomic `os.replace()` writes with `tomllib.loads()` validation; `saved_printer_type/id/profile` fields written to `[printer.saved]` TOML section; `_needs_printer_setup()` skip logic matching USB by VID:PID and CUPS by queue name; visible warning in status bar when saved printer is missing on launch.

**Addresses:** SETUP-04, SETUP-05, and UX pitfalls (silent fallback to simulator, no path to re-run setup).

**Avoids:** Pitfall 4 (config corruption).

### Phase Ordering Rationale

- Data structures before UI: `PrinterSetupScreen` receives a `DiscoveryResult` as constructor argument; it cannot be built without that dataclass defined first.
- Diagnose command in Phase 1: it uses the same `discover_all()` output and is independently testable. Discovery bugs surface here before the TUI complicates debugging.
- Async install in Phase 2, not Phase 3: the import cache pitfall and event-loop blocking pitfall must be designed into the setup screen from the start. Retrofitting async behavior after a synchronous prototype introduces regressions.
- Config persistence last: `save_config()` changes are additive (new fields, new TOML section). They do not affect the setup screen's ability to function in-session; they only affect whether the selection survives restart.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2:** Textual screen lifecycle edge cases with `on_mount` push timing -- PITFALLS.md documents two valid patterns (`push_screen_wait` in `@work` vs `switch_screen` as initial screen); the correct choice depends on `TeletypeApp`'s existing startup state machine and needs investigation before writing screen code.
- **Phase 2:** pyusb reimport after same-session `uv sync` -- the `sys.modules` cache clearing strategy needs a focused isolated test before integration into the setup screen async flow.

Phases with standard patterns (skip research):
- **Phase 1:** All patterns are established -- Typer subcommands, Rich tables, Python dataclasses. No new territory.
- **Phase 3:** Atomic file writes with `os.replace()` are well-documented Python stdlib. Config field additions follow the exact existing pattern in `config.py`.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | No new dependencies; all widgets verified against Textual 7.5.0 (installed) and widget gallery docs; all patterns verified in existing codebase |
| Features | MEDIUM-HIGH | All 8 table-stakes features have clear implementations against existing discovery primitives; uncertainty is in UX flow details (single-screen layout, label copy), not feasibility |
| Architecture | HIGH | Build order and component boundaries derived from existing codebase patterns (SettingsScreen, ConfirmSwapScreen, TypewriterScreen); no speculative components |
| Pitfalls | HIGH | All 6 critical pitfalls verified against Textual issue tracker, pyusb issue tracker, libusb PR history, and existing codebase behavior |

**Overall confidence:** HIGH

### Gaps to Address

- **Screen lifecycle resolution:** ARCHITECTURE.md and PITFALLS.md both note two valid approaches for pushing the setup screen. The existing `TeletypeApp` has complex startup state (transcript loading, printer initialization) that needs inspection to determine whether `push_screen_wait` in `@work` or `switch_screen` as initial screen is the safer choice. Resolve during Phase 2 planning before writing any screen code.

- **pyusb post-install import in running process:** The `sys.modules` cache clearing strategy should be validated against the actual venv layout used by `uv` before committing to it. The fallback ("pyusb installed, restart to detect USB devices") is acceptable if in-session reimport proves unreliable.

- **macOS CUPS-default UX copy:** The setup screen needs platform-aware messaging for macOS users who will hit the kernel driver conflict. Exact diagnostic strings and the default selection order (CUPS first on macOS) should be finalized during Phase 2 planning.

## Sources

### Primary (HIGH confidence)
- Textual widget gallery: https://textual.textualize.io/widget_gallery/ -- OptionList, RadioSet, RadioButton, LoadingIndicator availability in Textual 7.x
- Textual Screen docs: https://textual.textualize.io/guide/screens/ -- `Screen[ResultType]` pattern, push_screen lifecycle
- Textual Workers docs: https://textual.textualize.io/guide/workers/ -- async patterns for background tasks including subprocess
- uv CLI reference: https://docs.astral.sh/uv/reference/cli/ -- `uv sync --extra` flag verification
- uv environment variables: https://docs.astral.sh/uv/reference/environment/ -- UV_EXECUTABLE detection
- Existing codebase: `printer.py`, `config.py`, `cli.py`, `tui.py`, `settings_screen.py`, `profiles.py`, `typewriter_screen.py` -- all patterns verified by code inspection against 3,381 LOC source

### Secondary (MEDIUM confidence)
- Textual Discussion #1828 -- blocking API behavior in Textual event loop
- Textual Discussion #2035 -- screen state before push_screen
- pyusb Issue #374, libusb PR #911 -- macOS kernel driver detach limitations
- Apple CUPS Issue #756 -- CUPS printer recovery and stale-queue behavior
- Real Python: Python and TOML -- tomllib/tomli-w round-trip limitations

### Tertiary (LOW confidence)
- UX patterns for CLI tools (lucasfcosta.com) -- setup screen layout conventions; useful framing but not prescriptive

---
*Research completed: 2026-04-02*
*Ready for roadmap: yes*
