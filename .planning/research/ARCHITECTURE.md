# Architecture Patterns

**Domain:** Printer setup TUI integration into existing CLI/TUI app
**Researched:** 2026-04-02

## Recommended Architecture

The printer setup TUI should integrate as a **conditional gate screen** in the startup flow, pushed before the main TUI is usable, with a `diagnose` subcommand as a separate Typer command group.

### High-Level Integration

```
cli.py main()
  -> load config
  -> resolve profile (existing)
  -> create backend (existing)
  -> discover_printer (MODIFIED: non-interactive, returns discovery results)
  -> IF TUI mode:
       -> TeletypeApp.run()
         -> on_mount:
           -> IF needs_printer_setup(config, discovery_results):
                push_screen(PrinterSetupScreen(...))
              ELSE:
                focus input (existing behavior)
  -> IF --no-tui:
       -> existing behavior (no setup screen)
```

### Component Boundaries

| Component | Responsibility | Communicates With | New/Modified |
|-----------|---------------|-------------------|--------------|
| `printer_setup_screen.py` | Interactive TUI screen for printer discovery, selection, profile assignment | `printer.py` discovery functions, `config.py` save, `profiles.py` lookup | **NEW** |
| `cli.py` main() | Pass discovery results to TUI, add `diagnose` subcommand group | `printer.py`, `config.py` | **MODIFIED** |
| `tui.py` TeletypeApp | Conditionally push setup screen on mount, receive printer from setup | `printer_setup_screen.py` | **MODIFIED** |
| `printer.py` | New `discover_all()` returning structured results (not interactive) | USB/CUPS subsystems | **MODIFIED** (new function) |
| `config.py` | New fields for saved printer selection | TOML file | **MODIFIED** |
| `diagnose.py` | Standalone diagnostic command logic | `printer.py` discovery, system info | **NEW** |

### Data Flow

```
1. CLI startup:
   config = load_config()
   discovery = discover_all()  # NEW: returns DiscoveryResult dataclass
   
2. TeletypeApp receives both config and discovery:
   TeletypeApp(discovery=discovery, ...)

3. on_mount() checks:
   - Does config have a saved printer? (config.saved_printer_id)
   - Is that saved printer still present in discovery results?
   - YES: auto-connect silently (skip setup screen)
   - NO: push PrinterSetupScreen

4. PrinterSetupScreen flow:
   - Shows discovered USB devices (from discovery.usb_devices)
   - Shows discovered CUPS printers (from discovery.cups_printers)
   - User selects connection method + device + profile
   - Screen dismisses with PrinterSelection result
   - TeletypeApp callback creates driver, saves to config

5. diagnose command:
   claude-teletype diagnose
   - Runs all discovery functions
   - Checks pyusb installation
   - Checks libusb backend
   - Reports system info
   - No TUI needed (Rich console output)
```

## New Data Structures

### DiscoveryResult (printer.py)

```python
@dataclass
class UsbDeviceInfo:
    """A discovered USB printer-class device."""
    vendor_id: int
    product_id: int
    product_name: str
    manufacturer: str
    matched_profile: str | None  # Profile name if VID:PID matches

@dataclass  
class CupsPrinterInfo:
    """A discovered CUPS printer queue."""
    name: str
    uri: str
    vendor: str
    model: str
    is_usb: bool

@dataclass
class DiscoveryResult:
    """All discovered printer devices and connection options."""
    usb_devices: list[UsbDeviceInfo]
    cups_printers: list[CupsPrinterInfo]
    pyusb_available: bool
    libusb_available: bool
    diagnostics: list[str]  # Human-readable discovery log
```

### Config Additions (config.py)

```python
# New fields in TeletypeConfig:
saved_printer_type: str = ""    # "usb" | "cups" | "file" | ""
saved_printer_id: str = ""      # USB VID:PID or CUPS queue name
saved_printer_profile: str = "" # Profile name assigned at setup

# New TOML section:
# [printer.saved]
# type = "usb"
# id = "1a86:7584"
# profile = "juki"
```

### PrinterSelection (printer_setup_screen.py result)

```python
@dataclass
class PrinterSelection:
    """User's printer setup choice, returned from setup screen."""
    connection_type: str  # "usb" | "cups" | "skip"
    device_id: str        # VID:PID for USB, queue name for CUPS
    profile_name: str     # Selected printer profile
    save_to_config: bool  # Whether to persist this selection
```

## Patterns to Follow

### Pattern 1: Screen-as-Gate (conditional push on mount)
**What:** Push PrinterSetupScreen in on_mount() before user interaction, similar to how TypewriterScreen is pushed via action but this one is automatic.
**When:** No saved printer or saved printer not found.
**Why:** Keeps the setup flow within Textual's screen stack. The user sees the setup screen first, completes it, then lands on the main chat screen. No changes to CLI startup logic needed beyond passing discovery data.

```python
# tui.py on_mount() addition:
def on_mount(self) -> None:
    # ... existing transcript/printer init ...
    
    if self._needs_printer_setup():
        self.push_screen(
            PrinterSetupScreen(
                discovery=self._discovery,
                all_profiles=self._all_profiles,
                saved_config=self._saved_printer_config,
            ),
            callback=self._handle_printer_setup,
        )
    else:
        self.query_one("#prompt", Input).focus()
    
    self._update_status()
```

**Why this over "before TUI launch":** Injecting setup before `tui_app.run()` would require either (a) a separate Textual app for setup or (b) interactive console prompts that conflict with Textual's terminal takeover. Pushing a screen inside on_mount is the idiomatic Textual pattern and avoids these issues.

### Pattern 2: Screen with typed result (existing pattern)
**What:** PrinterSetupScreen extends Screen (not ModalScreen) since it replaces the full view, but dismisses with a typed result like SettingsScreen does.
**When:** Setup screen completion.

```python
class PrinterSetupScreen(Screen[PrinterSelection | None]):
    """Full-screen printer setup wizard."""
    
    def _on_select(self) -> None:
        self.dismiss(PrinterSelection(
            connection_type="usb",
            device_id="1a86:7584",
            profile_name="juki",
            save_to_config=True,
        ))
    
    def _on_skip(self) -> None:
        self.dismiss(None)  # User skipped setup, use NullPrinter
```

### Pattern 3: Non-interactive discovery (decouple UI from discovery)
**What:** All printer discovery happens before the TUI launches, returning structured data. The setup screen only renders and handles selection -- it never calls discovery functions itself.
**When:** Always. Discovery is I/O-bound (USB enumeration, subprocess calls to lpstat) and should not block the TUI event loop.

```python
# In cli.py main(), before TUI launch:
from claude_teletype.printer import discover_all
discovery = discover_all()

# Pass to TUI:
tui_app = TeletypeApp(discovery=discovery, ...)
```

**Why not discover inside the screen:** USB enumeration and lpstat subprocess calls are blocking. Running them before Textual starts avoids jank. The setup screen receives pre-computed results and is purely reactive.

### Pattern 4: Diagnose as Typer command (not subcommand group)
**What:** Add `diagnose` as a top-level Typer command, not a subcommand group.
**When:** User runs `claude-teletype diagnose`.

```python
# cli.py:
@app.command()
def diagnose() -> None:
    """Run printer diagnostics and show system info."""
    from claude_teletype.diagnose import run_diagnostics
    run_diagnostics()
```

**Why a single command, not a group:** There is no need for `diagnose show`, `diagnose fix`, etc. Keep it simple: `claude-teletype diagnose`.

**Caveat with _PromptFriendlyGroup:** The existing `_PromptFriendlyGroup.parse_args` override handles the ambiguity between subcommand names and the positional `prompt` argument. Adding `diagnose` as a command means it will be detected by `first_non_option in self.list_commands(ctx)`, so `claude-teletype diagnose` will route correctly. No changes needed to the parse_args override.

### Pattern 5: pyusb auto-install via subprocess
**What:** When pyusb is missing and user wants USB connection, offer to install it by running `uv sync --extra usb` as a subprocess.
**When:** User selects a USB device but pyusb is not available.

```python
import subprocess
result = subprocess.run(
    ["uv", "sync", "--extra", "usb"],
    capture_output=True, text=True, timeout=60,
)
```

**Where:** Inside the setup screen, as a button action. Show a loading indicator during install, then re-run discovery. This is the one exception to "no discovery in the screen" -- after installing a dependency, re-discovery is necessary and expected.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Two-Phase TUI (separate app for setup)
**What:** Running a separate Textual app for setup before the main app.
**Why bad:** Textual takes over the terminal. Starting app1.run(), exiting, then starting app2.run() causes visible terminal flicker and reinitializes the terminal state. Screen push within a single app is seamless.
**Instead:** Single TeletypeApp with conditional screen push on mount.

### Anti-Pattern 2: Interactive discovery inside Textual
**What:** Running `select_printer()` (which uses `input()`) or subprocess calls inside the TUI event loop.
**Why bad:** `input()` blocks the event loop and conflicts with Textual's terminal. Subprocess calls to `lpstat` or pyusb enumeration are blocking I/O that cause UI freezes.
**Instead:** Run all discovery before `tui_app.run()`, pass results to TUI constructor.

### Anti-Pattern 3: Storing printer selection as device path
**What:** Saving `/dev/usb/lp0` or similar device path as the saved printer config.
**Why bad:** Device paths change between reboots, USB port changes, and OS updates. A saved `/dev/usb/lp0` may not be the same printer next time.
**Instead:** Save VID:PID for USB devices (stable hardware identifier) and CUPS queue name for CUPS printers (admin-assigned stable name). Resolve to actual driver at startup.

### Anti-Pattern 4: Making setup mandatory on every launch
**What:** Always showing the setup screen.
**Why bad:** After initial setup, the user wants to go straight to chatting. Forcing setup on every launch is friction that will make users add a `--skip-setup` flag.
**Instead:** Save selection to config. On next launch, check if saved printer is still present. If yes, auto-connect silently. Setup screen only appears when: (a) no saved config, (b) saved printer not found, or (c) user explicitly requests it (e.g., via settings).

## Integration Points: Detailed Changes

### cli.py Changes

1. Add `discover_all()` call before TUI launch (after profile resolution, line ~462)
2. Pass discovery results to TeletypeApp constructor
3. Add `diagnose` command (simple `@app.command()`)
4. Split printer flow: `--no-tui` uses `discover_printer()` as-is; TUI mode defers printer creation to setup screen callback
5. Remove the interactive `select_printer()` call from the TUI path (setup screen replaces it)

### tui.py Changes

1. Add `discovery` parameter to `__init__`
2. Add `_needs_printer_setup()` method checking saved config vs discovery
3. Modify `on_mount()` to conditionally push setup screen
4. Add `_handle_printer_setup()` callback that creates the driver, updates `self.printer` and `self._printer_write`, optionally saves to config
5. Add "Printer Setup" action binding (e.g., ctrl+p) so user can re-run setup from the main screen

### config.py Changes

1. Add `saved_printer_type`, `saved_printer_id`, `saved_printer_profile` fields to TeletypeConfig
2. Add `[printer.saved]` section to DEFAULT_CONFIG_TEMPLATE
3. Update `save_config()` to write saved printer section
4. Update `load_config()` to read `[printer.saved]` nested section

### printer.py Changes

1. Add `DiscoveryResult`, `UsbDeviceInfo`, `CupsPrinterInfo` dataclasses
2. Add `discover_all()` function using existing discovery logic refactored into structured returns
3. Add `_enumerate_usb_printers()` that returns `list[UsbDeviceInfo]` (metadata, not drivers)
4. Add `create_driver_for_selection(selection, discovery)` that creates the appropriate PrinterDriver from a setup screen selection

## New Files

| File | Purpose | Lines (est.) |
|------|---------|-------------|
| `printer_setup_screen.py` | Textual Screen for printer discovery/selection UI | 200-300 |
| `diagnose.py` | Diagnostic command implementation (Rich console output) | 80-120 |

## Modified Files

| File | Changes | Impact |
|------|---------|--------|
| `cli.py` | Add discover_all() call, diagnose command, split TUI vs no-tui printer flow | Medium |
| `tui.py` | Add discovery param, conditional setup screen push, setup callback | Medium |
| `printer.py` | Add DiscoveryResult, discover_all(), _enumerate_usb_printers(), create_driver_for_selection() | Medium |
| `config.py` | Add saved printer fields, update load/save/template | Low |
| `profiles.py` | No changes needed | None |

## Build Order (dependency-driven)

1. **Data structures first:** Add DiscoveryResult, UsbDeviceInfo, CupsPrinterInfo to printer.py. Add PrinterSelection dataclass. Add config fields. These are pure data with no behavioral changes.

2. **Discovery refactor:** Add discover_all() and _enumerate_usb_printers() to printer.py. This extracts existing discovery logic into a structured return. Existing discover_printer() keeps working unchanged.

3. **Diagnose command:** Add diagnose.py and wire into cli.py. Uses discover_all() from step 2. Can be tested independently, no TUI dependency.

4. **Setup screen:** Build PrinterSetupScreen in printer_setup_screen.py. Receives DiscoveryResult, renders UI, returns PrinterSelection. Can be developed and tested in isolation.

5. **TUI integration:** Wire setup screen into TeletypeApp.on_mount() with conditional push and callback. Wire discovery into cli.py startup flow. This is the integration step that connects everything.

6. **Config persistence:** Save/load printer selection to TOML. Skip-setup-on-reconnect logic. This is the polish step.

7. **pyusb auto-install:** Add the "install pyusb" button/flow in the setup screen. This is optional enhancement, works without it (user just gets told to install manually).

## Sources

- Existing codebase analysis (cli.py, tui.py, printer.py, config.py, profiles.py, settings_screen.py, typewriter_screen.py)
- Textual Screen patterns from TypewriterScreen and SettingsScreen implementations in the codebase
- Textual ModalScreen callback pattern from ConfirmSwapScreen implementation
