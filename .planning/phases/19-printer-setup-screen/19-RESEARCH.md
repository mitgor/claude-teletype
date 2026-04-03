# Phase 19: Printer Setup Screen - Research

**Researched:** 2026-04-02
**Domain:** Textual TUI screen lifecycle, async subprocess, dynamic import, widget composition
**Confidence:** HIGH

## Summary

Phase 19 builds a `PrinterSetupScreen` that users see on startup, presenting discovered USB devices and CUPS printers in a selectable list, allowing connection method choice (USB Direct vs CUPS), profile assignment with VID:PID auto-suggestion, an async pyusb install flow, and a skip-to-simulator escape hatch. All backend primitives exist: `discover_all()` returns a `DiscoveryResult` with `UsbDeviceInfo` and `CupsPrinterInfo` lists, `auto_detect_profile()` matches VID:PID to profiles, and `BUILTIN_PROFILES` provides the profile catalog.

The integration point is `cli.py`'s TUI launch path (line 490-507). Currently `discover_printer()` runs synchronously before `TeletypeApp.run()` and produces a `PrinterDriver`. Phase 19 replaces this with: (1) call `discover_all()` before TUI launch, (2) pass `DiscoveryResult` to `TeletypeApp` constructor, (3) conditionally push `PrinterSetupScreen` in `on_mount()` using `call_after_refresh` to avoid lifecycle races, (4) the screen dismisses with a `PrinterSelection` result that `cli.py`'s callback uses to create the appropriate driver.

The two highest-risk technical challenges are the async `uv sync --extra usb` subprocess (must use `asyncio.create_subprocess_exec` inside a `@work` worker to avoid event loop blocking) and the pyusb reimport after same-session install (must clear `sys.modules` keys matching `usb.*` then call `importlib.invalidate_caches()` before retrying `import usb.core`). Both patterns are verified and documented below.

**Primary recommendation:** Build `PrinterSetupScreen` as a full `Screen[PrinterSelection | None]` (not a `ModalScreen`) pushed from `on_mount()` via `call_after_refresh`. Use `OptionList` for the device list, `RadioSet` for connection method, `Select` for profile dropdown, and a `@work` async worker for the pyusb install button.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SETUP-01 | User sees a list of all discovered USB devices and CUPS printers on startup | `discover_all()` already returns `DiscoveryResult` with both lists; render via `OptionList` widget |
| SETUP-02 | User can choose between USB Direct and CUPS Queue connection methods | `RadioSet` with two `RadioButton` widgets; conditionally disable USB option when pyusb unavailable |
| SETUP-03 | User must select a printer profile for USB devices, with VID:PID auto-suggestion | `Select` widget populated from `BUILTIN_PROFILES`; `auto_detect_profile()` provides default |
| SETUP-04 | User can skip printer setup and run in simulator-only mode | "Skip (Simulator)" `Button` that dismisses screen with `None` result |
| SETUP-05 | User sees discovery progress and connection status messages inline | `Log` or `Static` widget showing `DiscoveryResult.diagnostics` list items |
| DEP-02 | User can install pyusb from within app via async `uv sync --extra usb` with progress | `@work` async worker with `asyncio.create_subprocess_exec`; `LoadingIndicator` during install |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| textual | 7.5.0 (installed) | TUI framework, screen lifecycle, widgets | Already the project's TUI foundation |
| asyncio (stdlib) | 3.12+ | `create_subprocess_exec` for `uv sync` | Stdlib, non-blocking subprocess |
| importlib (stdlib) | 3.12+ | `find_spec` + `invalidate_caches` for pyusb reimport | Stdlib, avoids import cache pollution |

### Widgets Used (all from Textual 7.5.0)
| Widget | Purpose | Verified |
|--------|---------|----------|
| `OptionList` | Device list (USB + CUPS combined) | `add_option`, `clear_options`, `OptionSelected` event |
| `RadioSet` / `RadioButton` | Connection method toggle (USB Direct / CUPS) | Two-option radio group |
| `Select[str]` | Profile dropdown (juki/escp/ppds/pcl/generic) | Same pattern as `settings_screen.py` profile select |
| `LoadingIndicator` | Shown during async pyusb install | Animated spinner |
| `Button` | "Connect", "Skip (Simulator)", "Install USB Support" | Same pattern as existing screens |
| `Static` | Title, labels, diagnostic messages | Same pattern as existing screens |
| `Log` | Diagnostic message log area | Same as `tui.py` output log |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `OptionList` for devices | `ListView`/`ListItem` | `OptionList` is simpler for string-based selection; `ListView` offers richer per-item layout but more code |
| `Screen` (full screen) | `ModalScreen` (overlay) | Full screen is correct: setup is a gate, not an overlay on chat |
| `RadioSet` for connection | `Select` dropdown | Radio buttons show both options simultaneously; more discoverable for 2-option choice |

**No new dependencies required.** All widgets ship with Textual 7.5.0.

## Architecture Patterns

### New File Structure
```
src/claude_teletype/
    printer_setup_screen.py   # NEW: PrinterSetupScreen(Screen[PrinterSelection | None])
```

### Modified Files
```
src/claude_teletype/
    printer.py                # ADD: PrinterSelection dataclass, create_driver_for_selection()
    tui.py                    # MODIFY: accept DiscoveryResult, conditional setup screen push
    cli.py                    # MODIFY: call discover_all() before TUI, pass to constructor
```

### Pattern 1: Screen[ResultType] with Typed Dismiss
**What:** `PrinterSetupScreen(Screen[PrinterSelection | None])` dismisses with a typed result
**When to use:** When a screen produces a structured result consumed by the parent
**Example:**
```python
# Source: Existing pattern in settings_screen.py + ConfirmSwapScreen in tui.py
@dataclass
class PrinterSelection:
    """Result from PrinterSetupScreen."""
    connection_type: str  # "usb" | "cups" | "skip"
    device_index: int | None = None  # index into DiscoveryResult lists
    cups_printer_name: str | None = None
    profile_name: str = "generic"

class PrinterSetupScreen(Screen[PrinterSelection | None]):
    def compose(self) -> ComposeResult:
        # ... widgets ...
        pass

    def _on_connect(self) -> None:
        self.dismiss(PrinterSelection(
            connection_type="usb",
            device_index=0,
            profile_name="juki",
        ))

    def _on_skip(self) -> None:
        self.dismiss(None)
```

### Pattern 2: Deferred Screen Push via call_after_refresh
**What:** Push setup screen after the main screen's compose/mount cycle completes
**When to use:** Pushing a screen in `on_mount()` to avoid lifecycle races
**Why not direct push_screen in on_mount:** Direct `push_screen` in `on_mount` can race with the main screen's compose cycle, causing blank screens or missing keybindings after dismiss. `call_after_refresh` defers to the next frame.
**Example:**
```python
# In TeletypeApp.on_mount():
def on_mount(self) -> None:
    # ... existing transcript/printer init ...
    if self._needs_printer_setup():
        self.call_after_refresh(self._show_setup_screen)

def _show_setup_screen(self) -> None:
    from claude_teletype.printer_setup_screen import PrinterSetupScreen
    self.push_screen(
        PrinterSetupScreen(discovery=self._discovery),
        callback=self._handle_setup_result,
    )

def _handle_setup_result(self, result: PrinterSelection | None) -> None:
    if result is None:
        # Skip — simulator mode, printer stays NullPrinterDriver
        return
    # Create driver from selection
    from claude_teletype.printer import create_driver_for_selection
    driver = create_driver_for_selection(result, self._discovery)
    self.printer = driver
    # ... update status, printer_write, etc.
```

### Pattern 3: Async Subprocess in @work Worker
**What:** Run `uv sync --extra usb` without blocking the event loop
**When to use:** Any subprocess invocation inside a Textual app
**Example:**
```python
# In PrinterSetupScreen:
@work(exclusive=True, thread=False)
async def _install_pyusb(self) -> None:
    self._show_loading(True)
    try:
        proc = await asyncio.create_subprocess_exec(
            "uv", "sync", "--extra", "usb",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            self._on_install_success()
        else:
            self._on_install_failure(stderr.decode())
    except FileNotFoundError:
        self._on_install_failure("uv not found on PATH")
    finally:
        self._show_loading(False)
```

### Pattern 4: sys.modules Cache Clearing for pyusb Reimport
**What:** After installing pyusb via `uv sync`, clear Python's import cache so `import usb.core` works in the same session
**When to use:** After any same-session package installation
**Example:**
```python
import importlib
import sys

def _reimport_pyusb() -> bool:
    """Clear import cache and retry pyusb import. Returns True on success."""
    # Remove all usb.* entries from sys.modules
    usb_keys = [k for k in sys.modules if k.startswith("usb")]
    for key in usb_keys:
        del sys.modules[key]
    # Invalidate finder caches
    importlib.invalidate_caches()
    # Retry import
    try:
        import usb.core  # noqa: F811
        return True
    except ImportError:
        return False
```

**Verified:** `importlib.util.find_spec("usb")` does NOT add keys to `sys.modules` (confirmed on this machine). The existing `discover_all()` correctly uses `find_spec` for the initial check, so if pyusb is not installed, there are no stale entries to clear.

### Pattern 5: create_driver_for_selection() Factory
**What:** Convert a `PrinterSelection` + `DiscoveryResult` into a concrete `PrinterDriver`
**Where:** `printer.py` (new function)
**Why:** The setup screen should not import or construct driver internals; a factory function in `printer.py` handles the connection logic (USB claim, CUPS queue open, profile wrapping).
```python
def create_driver_for_selection(
    selection: PrinterSelection,
    discovery: DiscoveryResult,
    profile: PrinterProfile | None = None,
) -> PrinterDriver:
    if selection.connection_type == "skip":
        return NullPrinterDriver()
    if selection.connection_type == "usb":
        # Use _find_usb_printer() to claim the device
        driver = _find_usb_printer()
        if driver is None:
            return NullPrinterDriver()
    elif selection.connection_type == "cups":
        driver = CupsPrinterDriver(selection.cups_printer_name)
    if profile and profile.name != "generic":
        driver = ProfilePrinterDriver(driver, profile)
    return driver
```

### Anti-Patterns to Avoid
- **push_screen in on_mount without deferral:** Causes race with compose cycle. Use `call_after_refresh`.
- **subprocess.run inside Textual:** Blocks event loop. Always `asyncio.create_subprocess_exec` inside `@work`.
- **import usb.core for availability check:** Pollutes `sys.modules` with failed import. Use `importlib.util.find_spec("usb")`.
- **Storing bus:address as device identity:** USB bus/address changes on replug. Use VID:PID for persistence.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Device list UI | Custom widget with manual key handling | `OptionList` | Built-in selection, keyboard nav, scroll, highlight |
| Radio selection | Manual toggle with CSS state | `RadioSet` + `RadioButton` | Built-in mutual exclusion, accessible |
| Profile dropdown | Custom popup | `Select[str]` | Already used in `settings_screen.py`; consistent UX |
| Loading spinner | ASCII animation loop | `LoadingIndicator` | Built-in, animated, composable |
| Subprocess async | `threading.Thread` + `subprocess.run` | `asyncio.create_subprocess_exec` | Textual's event loop is asyncio; mixing threads adds race conditions |

**Key insight:** Every UI element needed already ships with Textual 7.5.0. The setup screen is a composition problem, not a widget-building problem.

## Common Pitfalls

### Pitfall 1: Event Loop Blocking During uv sync
**What goes wrong:** `subprocess.run("uv", "sync", "--extra", "usb")` freezes the TUI for 2-10 seconds. User sees unresponsive screen, cannot cancel.
**Why it happens:** `subprocess.run` blocks the calling thread. Textual's event loop runs on the main thread.
**How to avoid:** Use `asyncio.create_subprocess_exec` inside a `@work(thread=False)` async worker. Show `LoadingIndicator` widget during install.
**Warning signs:** TUI stops responding to keystrokes during install.

### Pitfall 2: Python Import Cache After Same-Session pyusb Install
**What goes wrong:** After `uv sync --extra usb` succeeds, `import usb.core` still raises `ImportError`.
**Why it happens:** Python caches module lookup results in `sys.modules`. A failed import leaves a stale entry (or the finder cache says "not found").
**How to avoid:** Clear all `usb.*` keys from `sys.modules`, call `importlib.invalidate_caches()`, then retry import. The existing `discover_all()` correctly uses `importlib.util.find_spec("usb")` which does NOT pollute `sys.modules` (verified on this machine).
**Warning signs:** `find_spec` returns None even after successful install.

### Pitfall 3: Screen Lifecycle Race on on_mount push_screen
**What goes wrong:** Pushing `PrinterSetupScreen` synchronously in `TeletypeApp.on_mount()` may execute before compose/mount is complete, causing blank screen after dismiss.
**Why it happens:** `on_mount` fires during the mount phase; the screen stack may not be stable yet.
**How to avoid:** Use `self.call_after_refresh(self._show_setup_screen)` to defer the push to the next frame after the initial render.
**Warning signs:** After dismissing setup screen, main chat screen is blank or footer keybindings don't work.

### Pitfall 4: macOS Kernel Driver Conflict
**What goes wrong:** USB Direct mode fails silently on macOS because `AppleUSBPrinterClass.kext` claims the printer.
**Why it happens:** macOS kernel driver detach (`detach_kernel_driver`) silently fails for printer-class devices.
**How to avoid:** Present CUPS as co-equal option (not fallback). When USB direct fails, show diagnostic: "macOS kernel driver conflict -- use CUPS queue instead". On macOS, default radio selection to CUPS when both options are available.
**Warning signs:** USB device appears in list but "Connect" fails with no clear error.

### Pitfall 5: OptionList Selection With No Devices
**What goes wrong:** Empty `OptionList` when no devices found; "Connect" button has no selection to act on.
**Why it happens:** No USB printers connected, pyusb not installed, or no CUPS queues.
**How to avoid:** When device list is empty, disable "Connect" button. Show message in the list area: "No printers found. Install USB support or check connections." Always keep "Skip (Simulator)" enabled.
**Warning signs:** User clicks Connect with empty list; crash or silent failure.

### Pitfall 6: Profile Auto-Detection When pyusb Unavailable
**What goes wrong:** `auto_detect_profile()` imports `usb.core`, polluting `sys.modules` if pyusb is not installed.
**Why it happens:** The function does a direct `import usb.core` (line 191 of profiles.py).
**How to avoid:** When building the setup screen, check `discovery.pyusb_available` before calling auto-detect. If pyusb is unavailable, skip VID:PID matching and show "generic" as default profile. The profile dropdown still shows all options for manual selection.
**Warning signs:** After pyusb install attempt, auto-detect still fails.

## Code Examples

### Complete PrinterSetupScreen Widget Layout
```python
# Source: Synthesis of existing settings_screen.py + typewriter_screen.py patterns
from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button, Footer, Header, Label, LoadingIndicator,
    Log, OptionList, RadioButton, RadioSet, Select, Static,
)

class PrinterSetupScreen(Screen[PrinterSelection | None]):
    CSS = """
    #setup-container { padding: 1 2; }
    #device-list { height: 8; }
    #diagnostics-log { height: 4; border: solid $surface-darken-1; }
    #button-row { margin-top: 1; align: center middle; }
    .section-label { margin-top: 1; text-style: bold; }
    #install-row { margin-top: 1; }
    """

    BINDINGS = [
        Binding("escape", "skip", "Skip"),
    ]

    def __init__(self, discovery: DiscoveryResult, all_profiles: dict, **kwargs):
        super().__init__(**kwargs)
        self._discovery = discovery
        self._all_profiles = all_profiles

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="setup-container"):
            yield Static("Printer Setup", classes="section-label")

            yield Label("Discovered Devices:")
            yield OptionList(id="device-list")

            yield Label("Connection Method:", classes="section-label")
            with RadioSet(id="connection-method"):
                yield RadioButton("USB Direct", id="radio-usb")
                yield RadioButton("CUPS Queue", id="radio-cups")

            yield Label("Printer Profile:", classes="section-label")
            yield Select[str](id="profile-select", allow_blank=False)

            # Conditional install row (shown when pyusb unavailable)
            with Horizontal(id="install-row"):
                yield Button("Install USB Support", id="install-btn", variant="warning")
                yield LoadingIndicator(id="install-spinner")

            yield Label("Diagnostics:", classes="section-label")
            yield Log(id="diagnostics-log")

            with Horizontal(id="button-row"):
                yield Button("Connect", variant="primary", id="connect-btn")
                yield Button("Skip (Simulator)", id="skip-btn")
        yield Footer()
```

### Async Install with Progress
```python
@work(exclusive=True, thread=False)
async def _install_pyusb(self) -> None:
    """Install pyusb via uv sync --extra usb asynchronously."""
    import shutil
    log = self.query_one("#diagnostics-log", Log)

    uv_path = shutil.which("uv")
    if not uv_path:
        log.write("Error: uv not found on PATH\n")
        return

    self.query_one("#install-spinner").display = True
    self.query_one("#install-btn").disabled = True
    log.write("Installing pyusb via uv sync --extra usb...\n")

    proc = await asyncio.create_subprocess_exec(
        uv_path, "sync", "--extra", "usb",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    self.query_one("#install-spinner").display = False

    if proc.returncode == 0:
        log.write("pyusb installed successfully.\n")
        # Clear import cache and re-discover
        if self._reimport_pyusb():
            log.write("USB support activated. Re-scanning devices...\n")
            self._refresh_discovery()
        else:
            log.write("Installed but import failed. Restart app to detect USB devices.\n")
    else:
        log.write(f"Install failed: {stderr.decode().strip()}\n")
        self.query_one("#install-btn").disabled = False
```

### cli.py Integration Point
```python
# In main(), replace the current discover_printer() call (lines 471-473):

# Before TUI launch, run lightweight discovery
from claude_teletype.printer import discover_all
discovery = discover_all()

# Pass to TUI constructor
tui_app = TeletypeApp(
    # ... existing params ...
    discovery=discovery,
    all_profiles=all_profiles,
)
```

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv | DEP-02 (pyusb install) | Yes | 0.11.3 | Show "install manually" message |
| pyusb | SETUP-01 (USB devices) | Optional | 1.3.0+ | CUPS-only mode; install button |
| libusb | USB direct access | Platform-dependent | -- | CUPS-only mode |
| lpstat | CUPS discovery | Yes (macOS) | CUPS built-in | Skip CUPS section |

**Missing dependencies with no fallback:**
- None. All paths have graceful degradation.

**Missing dependencies with fallback:**
- pyusb: Falls back to CUPS-only mode with install button (DEP-02)
- libusb: Falls back to CUPS-only mode with diagnostic message

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] asyncio_mode = "auto" |
| Quick run command | `uv run pytest tests/test_printer_setup_screen.py -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SETUP-01 | Device list shows USB + CUPS entries | unit | `uv run pytest tests/test_printer_setup_screen.py::test_device_list_populated -x` | Wave 0 |
| SETUP-02 | Radio buttons for USB/CUPS, USB disabled when pyusb missing | unit | `uv run pytest tests/test_printer_setup_screen.py::test_connection_method_toggle -x` | Wave 0 |
| SETUP-03 | Profile select populated, auto-selects based on VID:PID | unit | `uv run pytest tests/test_printer_setup_screen.py::test_profile_auto_suggestion -x` | Wave 0 |
| SETUP-04 | Skip button dismisses with None | unit | `uv run pytest tests/test_printer_setup_screen.py::test_skip_returns_none -x` | Wave 0 |
| SETUP-05 | Diagnostics messages appear in log | unit | `uv run pytest tests/test_printer_setup_screen.py::test_diagnostics_displayed -x` | Wave 0 |
| DEP-02 | Install button triggers async subprocess | unit (mocked) | `uv run pytest tests/test_printer_setup_screen.py::test_install_pyusb_async -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_printer_setup_screen.py -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_printer_setup_screen.py` -- covers SETUP-01 through SETUP-05, DEP-02
- [ ] Test app harness pattern: follow `SettingsTestApp` pattern from `test_settings_screen.py` (push screen on_mount, capture dismiss result)

## Sources

### Primary (HIGH confidence)
- Textual 7.5.0 installed locally -- `Screen[ResultType]`, `push_screen_wait`, `call_after_refresh`, `OptionList`, `RadioSet`, `Select`, `LoadingIndicator` all verified via import and signature inspection
- Existing codebase: `settings_screen.py` (ModalScreen dismiss pattern), `typewriter_screen.py` (Screen push pattern), `tui.py` (on_mount, @work workers), `printer.py` (discover_all, DiscoveryResult), `cli.py` (startup flow)
- Python 3.12+ stdlib: `importlib.util.find_spec` verified to NOT pollute sys.modules (tested on this machine)

### Secondary (MEDIUM confidence)
- Textual docs: Screen lifecycle, push_screen timing -- https://textual.textualize.io/guide/screens/
- Textual docs: Workers and async patterns -- https://textual.textualize.io/guide/workers/
- Project research SUMMARY.md: architecture approach, pitfalls list (cross-verified against codebase)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all widgets verified installed, all patterns exist in codebase
- Architecture: HIGH -- screen lifecycle patterns verified (push_screen signature, call_after_refresh exists), factory pattern follows existing discover_printer
- Pitfalls: HIGH -- all 6 pitfalls verified against actual API behavior and codebase patterns
- Async install: HIGH -- asyncio.create_subprocess_exec is stdlib, uv 0.11.3 confirmed available
- Import cache: HIGH -- find_spec behavior verified to not add sys.modules entries on this machine

**Research date:** 2026-04-02
**Valid until:** 2026-05-02 (stable domain, no fast-moving dependencies)
