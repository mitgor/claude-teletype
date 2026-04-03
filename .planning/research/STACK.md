# Stack Research

**Domain:** Printer setup TUI features for existing Python CLI/TUI app
**Researched:** 2026-04-02
**Confidence:** HIGH

## Scope

This research covers ONLY the stack additions/changes needed for v1.4 Printer Setup TUI features:
1. Interactive printer setup/selection screen (Textual-based)
2. Running `uv sync --extra usb` from within the app to auto-install pyusb
3. A `claude-teletype diagnose` CLI subcommand
4. Persisting printer selection to TOML config

Existing stack (Python 3.12+, Textual 7.x, Typer, Rich, pyusb, tomllib, platformdirs) is validated and NOT re-researched.

## Verdict: No New Dependencies Required

All four features can be built with the existing dependency set. No new pip packages needed. No pyproject.toml changes required.

## Recommended Stack Additions

### New Capabilities From Existing Libraries

| Library | Current Version | New Usage | Why No Addition Needed |
|---------|----------------|-----------|----------------------|
| Textual | 7.5.0 (installed), >=7.0.0 (pinned) | Full `Screen` (not ModalScreen) for printer setup wizard | Already has `OptionList`, `RadioSet`, `RadioButton`, `Static`, `Button`, `LoadingIndicator` -- all needed widgets ship with Textual 7.x |
| Textual | 7.5.0 | `@work(thread=True)` decorator for async subprocess (`uv sync`) | Worker pattern already used in `tui.py` for streaming |
| Typer | >=0.23.0 | New `diagnose` subcommand | Same pattern as existing `config show`/`config init` subcommands |
| subprocess | stdlib | Run `uv sync --extra usb` | Already used for CUPS `lpstat` and `lp` commands in printer.py |
| shutil | stdlib | `shutil.which("uv")` to find uv binary | Already used for `shutil.which("claude")` in cli.py |
| Rich | >=14.0.0 | `Table` for structured diagnose output | Already a dependency, Console already instantiated in cli.py |

### Core Technologies (Unchanged)

| Technology | Version | Purpose | Status |
|------------|---------|---------|--------|
| Python | >=3.12 | Runtime | No change |
| Textual | 7.5.0 (installed), >=7.0.0 (pinned) | TUI framework | No version bump needed |
| Typer | >=0.23.0 | CLI argument parsing | No change |
| Rich | >=14.0.0 | CLI formatting for diagnose output | No change |
| pyusb | >=1.3.0 (optional) | USB device enumeration | No change -- this is what we help users install |

## Integration Points

### 1. Printer Setup Screen (Textual Screen)

**Use `Screen`, not `ModalScreen`.** The setup screen is a full startup flow, not a modal overlay on an existing screen.

**Why `Screen[dict | None]`:** Follows the existing `ModalScreen[dict | None]` pattern from `SettingsScreen` but as a full screen. The result type carries the selected printer config back to the app. `None` means "skip setup, use defaults."

```python
from textual.screen import Screen
from textual.widgets import OptionList, RadioSet, RadioButton, Button, Static, LoadingIndicator

class PrinterSetupScreen(Screen[dict | None]):
    """Full-screen printer setup wizard. Dismisses with selected config or None (skip)."""
```

**Key Textual widgets for the setup screen:**

| Widget | Purpose | Notes |
|--------|---------|-------|
| `OptionList` | Display discovered USB devices and CUPS printers as selectable list | Better than `ListView` for simple single-selection; fires `OptionList.OptionSelected` message |
| `RadioSet` + `RadioButton` | Connection method selection (Direct USB vs CUPS queue) and profile selection (juki/escp/ppds/pcl/generic) | Mutually exclusive selection, fires `RadioSet.Changed` |
| `Static` | Diagnostic info display (devices found, connection status) | Already used throughout the app |
| `Button` | Confirm/Skip actions | Already used in SettingsScreen |
| `LoadingIndicator` | Show during pyusb install (`uv sync`) | Built into Textual 7.x |
| `Label` | Section headers | Already used in SettingsScreen |

**Screen flow via `push_screen`:**
```python
# In TeletypeApp.on_mount():
if not self._has_saved_printer():
    self.push_screen(PrinterSetupScreen(...), callback=self._on_setup_complete)
```

**Confidence:** HIGH -- `Screen[ResultType]` with typed dismiss() verified in Textual docs and already used as `ModalScreen[dict | None]` in settings_screen.py. All widgets verified in Textual 7.x widget gallery.

### 2. Running `uv sync --extra usb` From Within the App

**Approach:** `subprocess.run()` with `shutil.which("uv")` -- no new dependencies.

**Critical design decisions:**

| Decision | Recommendation | Rationale |
|----------|---------------|-----------|
| Find uv binary | `shutil.which("uv")` | Same pattern as `check_claude_installed()` uses `shutil.which("claude")` |
| Detect if uv-managed | Check for `uv.lock` in project root, or `os.environ.get("UV_EXECUTABLE")` | UV_EXECUTABLE is set by uv when it spawns subprocesses |
| Working directory | Run from project root (where `pyproject.toml` lives) | `uv sync` needs pyproject.toml context |
| Find project root | Walk up from `__file__` looking for `pyproject.toml` | Standard Python pattern |
| Async execution | Use Textual `@work(thread=True)` decorator | Keeps TUI responsive during install; already used in tui.py for streaming |
| Error handling | Capture stderr, show in setup screen diagnostic area | User needs to see what went wrong |
| Post-install import | Call `importlib.invalidate_caches()` then retry `import usb.core` | Python caches module paths; invalidation needed after install |
| Restart guidance | Show "pyusb installed -- restart to detect USB devices" if import still fails | sys.path may not include new install location in running process |

**Implementation pattern:**
```python
import shutil
import subprocess

def install_pyusb() -> tuple[bool, str]:
    """Attempt to install pyusb via uv sync. Returns (success, message)."""
    uv = shutil.which("uv")
    if uv is None:
        return False, "uv not found. Install pyusb manually: pip install pyusb"

    project_root = _find_project_root()
    if project_root is None:
        return False, "Could not find pyproject.toml. Run: uv sync --extra usb"

    result = subprocess.run(
        [uv, "sync", "--extra", "usb"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        return False, f"uv sync failed: {result.stderr.strip()}"

    try:
        import importlib
        importlib.invalidate_caches()
        import usb.core
        return True, "pyusb installed successfully"
    except ImportError:
        return False, "pyusb installed. Restart the app to detect USB devices."
```

**Confidence:** HIGH -- subprocess.run() pattern already used in printer.py for CUPS. shutil.which() already used in cli.py. uv sync --extra syntax verified in uv docs.

### 3. Diagnose CLI Subcommand

**Use `@app.command()` not a sub-Typer.** The diagnose command is a single flat command (`claude-teletype diagnose`), not a group with subcommands.

**Typer integration is safe:** The existing `_PromptFriendlyGroup` hack in cli.py handles the conflict between the positional `prompt` argument and subcommand names. Adding `diagnose` as an `@app.command()` works because `_PromptFriendlyGroup.parse_args()` checks `self.list_commands(ctx)` for known subcommand names. "diagnose" will be recognized as a command, not consumed as a prompt.

**Rich Table for output:** Use existing `console = Console()` with `rich.table.Table` for structured diagnostic data. Rich is already a dependency.

```python
@app.command()
def diagnose():
    """Show printer diagnostic information."""
    from rich.table import Table
    # Reuse discover_cups_printers(), discover_usb_device_verbose(),
    # discover_macos_usb_printers() from printer.py
```

**Confidence:** HIGH -- same subcommand pattern as existing `config show`/`config init`. _PromptFriendlyGroup verified to handle additional command names.

### 4. Persisting Printer Selection to TOML Config

**Extend existing `TeletypeConfig` dataclass and `save_config()`.** No new libraries.

New fields needed in `TeletypeConfig`:

| Field | Type | Default | TOML Location | Purpose |
|-------|------|---------|---------------|---------|
| `cups_printer` | `str` | `""` | `[printer]` | CUPS queue name when using CUPS connection |

**Note:** The existing `device` field already handles direct USB device paths. The existing `printer_profile` field already stores the profile name. The only missing piece is a CUPS printer name field.

**The `save_config()` function** already writes TOML by hand (string template, not tomli-w) because it preserves comments. Adding new `[printer]` fields follows the exact same pattern -- append lines to the `[printer]` section.

**Skip-on-relaunch logic:** On startup, check if `printer_profile` is set to something other than "generic" AND the target device/CUPS queue still exists. If yes, skip setup screen. If no (device unplugged, CUPS queue removed), show setup screen again.

**Confidence:** HIGH -- extends existing config.py patterns. save_config() hand-formats TOML strings; adding fields is trivial.

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `pycups` (Python CUPS bindings) | Heavyweight C extension, requires CUPS development headers to compile. Only need `lpstat -v` output and `lp -o raw` to send jobs | `subprocess.run(["lpstat", "-v"])` -- already working in printer.py |
| `python-usb-monitor` or `pyudev` | Only useful for live USB hotplug events; setup screen runs once at startup, not continuously | Enumerate once with existing `usb.core.find(find_all=True)` |
| `tomli-w` for config writing | Already decided against in v1.2 -- tomli-w cannot write comments, hand-formatted template preserves documentation | Continue using the string-template approach in `save_config()` |
| `textual-wizard` or similar | No official Textual wizard library; building with Screen + widgets is straightforward | Compose widgets directly in `PrinterSetupScreen` |
| `pip` as install backend | App is a uv project (`uv.lock` exists); mixing pip and uv causes resolver conflicts | Always prefer `uv sync --extra usb` |
| `importlib.metadata` for pyusb detection | Overly complex for a simple "is it importable?" check | `try: import usb.core` -- already the pattern in profiles.py |
| Any new Textual version pin | Textual 7.5.0 has all needed widgets; no reason to bump | Keep `textual>=7.0.0` |

## Stack Patterns by Variant

**If pyusb is already installed:**
- USB devices appear in the setup screen's device list
- Profile selection offered for each USB printer-class device
- No install prompt shown

**If pyusb is NOT installed:**
- Setup screen shows "USB detection unavailable"
- Offers "Install USB support" button that runs `uv sync --extra usb`
- Falls back to showing CUPS printers only (via `lpstat`)
- After install, prompts restart or re-enumerates if import succeeds

**If neither pyusb nor CUPS printers found:**
- Setup screen shows "No printers detected"
- Offers manual device path entry (text input for `/dev/usb/lp0`)
- Offers "Continue without printer" to use simulator mode

**If running in --no-tui mode:**
- Skip the TUI setup screen entirely
- Use existing auto-detection logic (unchanged)
- The `diagnose` command works independently of TUI

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| Textual >=7.0.0 | `Screen[result_type]` | Generic Screen with typed dismiss() stable in 7.x |
| Textual >=7.0.0 | OptionList, RadioSet, RadioButton, LoadingIndicator | All shipped since Textual 0.27+, stable in 7.x |
| Textual 7.5.0 | `@work(thread=True)` | Worker pattern stable since Textual 0.18+ |
| Typer >=0.23.0 | `@app.command()` alongside `@app.callback()` | Works with _PromptFriendlyGroup hack |
| pyusb >=1.3.0 | libusb 1.0.x via homebrew | macOS requires `brew install libusb` separately |

## pyproject.toml Changes

**None required.** All dependencies already declared:
- `textual>=7.0.0` -- has all needed widgets
- `typer>=0.23.0` -- supports subcommands
- `rich>=14.0.0` -- has Table, Console for diagnostics
- `pyusb>=1.3.0` in `[project.optional-dependencies] usb` -- what we are helping users install

## Sources

- Textual widget gallery: https://textual.textualize.io/widget_gallery/ -- verified OptionList, RadioSet, RadioButton, LoadingIndicator availability (HIGH confidence)
- Textual Screen docs: https://textual.textualize.io/guide/screens/ -- Screen[ResultType] pattern (HIGH confidence)
- Textual OptionList: https://textual.textualize.io/widgets/option_list/ -- single-select list widget (HIGH confidence)
- Textual RadioSet: https://textual.textualize.io/widgets/radioset/ -- mutually exclusive selection (HIGH confidence)
- uv CLI reference: https://docs.astral.sh/uv/reference/cli/ -- `uv sync --extra` flags (HIGH confidence)
- uv environment variables: https://docs.astral.sh/uv/reference/environment/ -- UV_EXECUTABLE detection (HIGH confidence)
- Existing codebase: settings_screen.py (ModalScreen pattern), cli.py (Typer subcommand pattern, shutil.which), printer.py (CUPS/USB discovery), config.py (save_config pattern) -- all verified by code inspection
- Installed Textual version: 7.5.0 (verified via `uv run python -c "import textual; print(textual.__version__)"`)

---
*Stack research for: v1.4 Printer Setup TUI*
*Researched: 2026-04-02*
