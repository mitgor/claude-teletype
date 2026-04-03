# Pitfalls Research

**Domain:** Adding printer setup TUI, USB device selection, CUPS discovery, pyusb auto-install, and config persistence to an existing Python Textual app
**Researched:** 2026-04-02
**Confidence:** HIGH (verified against existing codebase, Textual docs, pyusb/libusb issue trackers, CUPS documentation)

## Critical Pitfalls

### Pitfall 1: Subprocess (uv sync) Blocks the Textual Event Loop

**What goes wrong:**
Running `subprocess.run(["uv", "sync", "--extra", "usb"])` synchronously from within a Textual app freezes the entire TUI. The event loop stops processing repaints, key events, and timers. The user sees a frozen screen with no feedback for several seconds while `uv sync` downloads and installs pyusb.

**Why it happens:**
Textual runs on a single asyncio event loop. Any synchronous blocking call (subprocess.run, time.sleep, blocking I/O) stalls everything. Developers reach for subprocess.run because it is the simplest API and works fine outside a TUI context.

**How to avoid:**
Use `asyncio.create_subprocess_exec` inside a Textual `@work` worker. Stream stdout/stderr line-by-line and update a status widget in real time. Example pattern:

```python
@work(exclusive=True)
async def install_pyusb(self) -> bool:
    proc = await asyncio.create_subprocess_exec(
        "uv", "sync", "--extra", "usb",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode == 0
```

After `uv sync` completes, the pyusb module must be importable in the already-running process. Python caches failed imports in `sys.modules` -- if you tried `import usb.core` before installation and it raised ImportError, Python will NOT retry it automatically. You must either (a) never attempt the import before installation, or (b) delete the failed entry from `sys.modules` before retrying.

**Warning signs:**
- TUI freezes for 2-10 seconds during "installing dependencies"
- No progress indicator visible
- User hits Ctrl+C thinking the app is hung, killing the install mid-way

**Phase to address:**
Phase 1 (pyusb auto-install) -- must be async from day one, not "fix later"

---

### Pitfall 2: pyusb Import Cache After Failed Import

**What goes wrong:**
The app tries `import usb.core` at startup to check if pyusb is available, catches ImportError, offers to install it, runs `uv sync --extra usb`, then tries `import usb.core` again -- and it still fails with ImportError even though pyusb is now installed.

**Why it happens:**
Python's import system caches failed imports. After the first ImportError, `sys.modules` may contain a partial entry or a `None` marker for the module. Subsequent `import` statements return the cached failure without checking the filesystem again.

**How to avoid:**
Two strategies:

1. **Never import before installation.** Check for pyusb availability by looking for the package metadata (`importlib.util.find_spec("usb")`) rather than actually importing it.

2. **Clear the cache after installation.** After `uv sync` succeeds:
```python
for key in list(sys.modules.keys()):
    if key == "usb" or key.startswith("usb."):
        del sys.modules[key]
import usb.core  # Now works
```

Strategy 1 is cleaner. The existing codebase already uses try/except ImportError in `_find_usb_printer()` -- this pattern is fine for the "pyusb not installed" path, but the import must not be attempted module-level or at app startup before the install flow completes.

**Warning signs:**
- "pyusb installed successfully" message followed by "pyusb not found" error
- Works after restarting the app but not within the same session

**Phase to address:**
Phase 1 (pyusb auto-install) -- the install-then-reimport flow must be designed together

---

### Pitfall 3: macOS Kernel Driver Conflicts With USB Printer Devices

**What goes wrong:**
On macOS, `usb.core.find()` discovers the printer device, but `dev.set_configuration()` or `ep_out.write()` fails with USBError "Access denied" or "Resource busy." The printer appears in System Information and CUPS but pyusb cannot claim it.

**Why it happens:**
macOS loads a kernel extension (KEXT) for USB printer class devices (`AppleUSBPrinterClass.kext`). This KEXT exclusively claims the USB interface. Unlike Linux, macOS historically did not support `detach_kernel_driver()` via libusb. Since libusb 1.0.25, kernel driver detach IS supported on macOS, but it requires either root privileges or a signed app with Apple's USB entitlement -- neither of which applies to a Python CLI tool.

The existing code in `printer.py:_find_usb_printer()` already has a best-effort `detach_kernel_driver` call, but it swallows the exception silently. On macOS, this will almost always fail for printer-class devices.

**How to avoid:**
- Present USB direct mode and CUPS mode as co-equal options in the setup TUI, not USB-first with CUPS as fallback.
- When USB direct fails on macOS, show a specific diagnostic: "macOS kernel driver is claiming this device. Use CUPS printer queue instead, or run with sudo (not recommended)."
- The `discover_macos_usb_printers()` (ioreg-based) function in printer.py can verify that the device EXISTS even when pyusb cannot claim it. Use this for diagnostics.
- Consider: on macOS the realistic path for most users is CUPS, not direct USB. The setup TUI should default to showing CUPS queues on macOS.

**Warning signs:**
- USB device appears in discovery list but "Test connection" fails
- Works on Linux but not macOS
- Works with sudo but not as normal user

**Phase to address:**
Phase 2 (USB device selection + CUPS selection) -- must handle platform differences in the UI

---

### Pitfall 4: Config File Corruption on Concurrent or Partial Writes

**What goes wrong:**
The setup TUI saves printer selection to TOML config via `save_config()`. If the app crashes mid-write, or if another instance is running `config show` simultaneously, the config file can end up truncated or malformed. On next launch, `tomllib.load()` raises `TOMLDecodeError` and the app fails to start.

**Why it happens:**
The existing `save_config()` in config.py uses `path.write_text()` which is NOT atomic on most filesystems. It truncates the file first, then writes content. A crash between truncate and write-complete leaves a partial file. Additionally, the handwritten TOML template approach (string concatenation in `save_config()`) is fragile -- a single unescaped quote in a user-entered value could produce invalid TOML.

**How to avoid:**
- **Atomic writes:** Write to a temporary file in the same directory, then `os.replace()` (atomic on POSIX) to the final path:
```python
import tempfile
tmp = tempfile.NamedTemporaryFile(
    mode="w", dir=path.parent, suffix=".tmp", delete=False
)
tmp.write(content)
tmp.flush()
os.fsync(tmp.fileno())
tmp.close()
os.replace(tmp.name, str(path))
```
- **Validation after write:** Read back the written file with `tomllib.loads()` before replacing the original. If parse fails, keep the original.
- **Backup:** Copy the existing config to `config.toml.bak` before overwriting.
- The existing `_esc()` helper in `save_config()` handles backslash/quote/newline, but test it with edge cases (empty strings, Unicode, multi-line system prompts).

**Warning signs:**
- Config file is 0 bytes after a crash
- "Invalid TOML" error on startup after previously working fine
- User reports settings "disappeared"

**Phase to address:**
Phase 3 (config persistence / save-to-TOML) -- atomic write must be the implementation, not a later fix

---

### Pitfall 5: Textual Screen Lifecycle -- Setup Screen Before Main Screen

**What goes wrong:**
The setup screen is pushed during `on_mount()` but the main screen's widgets are not yet fully composed. After the setup screen is dismissed, the main screen either shows a blank output pane, fails to register keybindings, or throws an exception trying to query a widget that has not mounted yet.

**Why it happens:**
Textual's screen lifecycle is asynchronous. `on_mount()` fires when the app's DOM is ready, but if you call `push_screen()` synchronously in `on_mount()`, the default screen may not have finished its compose/mount cycle. The pushed screen obscures the default screen, and when dismissed, the default screen receives focus but may not be in a consistent state.

**How to avoid:**
Two proven patterns:

1. **Make the setup screen the default screen**, not a pushed overlay. Set `SCREENS = {"setup": SetupScreen}` and `push_screen("setup")` only when needed, or use `switch_screen`. After setup completes, `switch_screen` to the main chat screen.

2. **Use `push_screen_wait` in a worker** if you need the setup screen as a modal:
```python
@work
async def show_setup(self) -> None:
    result = await self.push_screen_wait(SetupScreen())
    if result:
        self.apply_printer_config(result)
```

Pattern 1 is simpler and avoids the "screen under screen" state management entirely. The main TeletypeApp already has complex screen management (SettingsScreen, ConfirmSwapScreen, TypewriterScreen). Adding another pushed screen increases the state space. Consider making setup a phase that happens BEFORE the main app screen is composed.

**Warning signs:**
- Blank screen after dismissing setup
- Keybindings (Ctrl+comma for settings) not working after setup
- `NoMatches` exception when querying widgets after screen pop

**Phase to address:**
Phase 2 (setup TUI screen) -- architecture decision about screen lifecycle must come first

---

### Pitfall 6: CUPS Printer Discovery Returns Stale or Missing Results

**What goes wrong:**
`discover_cups_printers()` (which calls `lpstat -v`) returns an empty list even though a USB printer is physically connected and visible in System Preferences. Or it returns a printer that was previously connected but is now physically disconnected.

**Why it happens:**
CUPS maintains its own printer registry in `/etc/cups/printers.conf`. `lpstat -v` reports registered printers, not currently-connected devices. A printer registered months ago still appears even if unplugged. Conversely, a newly-connected USB printer may not appear until CUPS auto-detects it (which can take seconds) or until the user adds it via System Preferences.

On macOS, CUPS relies on `cups-browsed` and Bonjour/DNSSD for discovery. USB printers are auto-added by `IOKit` notifications, but there is a race condition at startup -- if the app launches faster than CUPS finishes registering a just-plugged device, `lpstat` returns nothing.

**How to avoid:**
- Show CUPS printers AND raw USB devices (via ioreg/pyusb) in the setup TUI. Let the user see what the system detects even if CUPS has not registered it yet.
- Add a "Refresh" button in the setup TUI that re-runs discovery. Do not assume the first scan is complete.
- For CUPS printers, verify the printer is actually reachable before marking it as "connected." Use `lpstat -p <name>` to check if CUPS reports it as idle/ready vs. "Not Connected."
- Filter out non-USB CUPS printers (the existing code already filters by `usb://` URI, which is correct).
- Consider a brief delay (1-2 seconds) or polling loop at startup before declaring "no printers found."

**Warning signs:**
- User sees "No printers found" but the printer is plugged in
- Stale printer entries confuse users ("My old printer shows up but my new one doesn't")
- Works if user opens System Preferences > Printers first

**Phase to address:**
Phase 2 (CUPS printer selection) -- must include refresh capability and status verification

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Synchronous subprocess.run for uv sync | Simpler code, no async complexity | Frozen TUI, bad UX | Never in a TUI context |
| Module-level `import usb.core` with try/except | Clean availability check at import time | Prevents post-install reimport without cache busting | Only if you never plan to install at runtime |
| String-template TOML generation (current approach) | No extra dependency (tomlkit), comments preserved | Fragile to edge cases, no structural validation | Acceptable for v1.4 if atomic writes and validation are added |
| Hardcoded `uv sync` command | Works for uv-managed projects | Breaks if user installed via pip, pipx, or system Python | Acceptable if the app is always distributed as a uv project |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| pyusb + macOS | Assuming `detach_kernel_driver` works like Linux | Detect platform, default to CUPS on macOS, show diagnostic explaining why USB direct fails |
| CUPS lpstat | Treating output as "currently connected devices" | Treat as "registered queues" and separately verify connectivity with `lpstat -p` |
| uv sync from TUI | Running synchronously, not checking return code | Use asyncio subprocess, check returncode, parse stderr for error messages |
| tomllib round-trip | Expecting comments to survive load/save cycle | Use handwritten template (already done) or tomlkit; never load-modify-save with tomllib |
| Textual push_screen | Pushing during on_mount synchronously | Use @work + push_screen_wait, or make setup the initial screen with switch_screen to main |
| sys.modules cache | Importing optional module before install attempt | Use `importlib.util.find_spec()` for availability check, or clear sys.modules after install |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| USB enumeration on every app launch | 1-3 second startup delay while pyusb scans all USB devices | Cache the selected device in config; only enumerate if cached device is missing | Always noticeable, worse with many USB devices |
| CUPS lpstat subprocess on every launch | 0.5-1 second subprocess spawn | Skip discovery if config has a saved printer and it is still reachable | Adds up on slow systems |
| Repeated `uv sync` checks | 0.5-2 seconds for uv to verify lockfile even when nothing changed | Only run uv sync when pyusb import actually fails, not speculatively | Every launch |
| ioreg parsing on non-macOS | Subprocess call fails, wasted time | Guard with `sys.platform == "darwin"` (already done in existing code) | Linux/WSL |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Running `uv sync` with shell=True | Shell injection if any argument is user-controlled | Always use list form: `["uv", "sync", "--extra", "usb"]` |
| Suggesting `sudo` for USB access | User runs entire app as root, potential system damage | Never suggest sudo; recommend CUPS path instead |
| Storing sensitive config (API keys) with world-readable permissions | Other users on system can read OpenAI/OpenRouter keys | Set file permissions to 0o600 on config file after creation: `os.chmod(path, 0o600)` |
| Running arbitrary subprocess from user-provided config values | Config file could specify malicious commands | Never interpolate config values into subprocess arguments; hardcode the `uv sync` command |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Showing setup screen every launch | Annoys returning users who already configured their printer | Skip setup if config has a saved printer AND that printer is still available; show "Printer: Juki 6100 via CUPS" in status bar instead |
| No way to re-enter setup after initial config | User gets a new printer, no way to reconfigure without editing TOML | Add a "Printer Setup" option in settings modal (Ctrl+comma) or a CLI flag like `--setup` |
| Silent failure when saved printer disappears | User unplugs printer, app silently falls back to NullPrinterDriver, user types a long response that goes nowhere | Show a visible warning: "Configured printer 'Juki_6100' not found. Using simulator mode." with option to re-run setup |
| Showing raw USB VID:PID without friendly names | User sees "0x1a86:0x7584" and has no idea what it is | Map known VID:PID to friendly names from the profile registry; show "CH341 USB-Parallel Bridge (Juki compatible)" |
| Auto-installing dependencies without consent | User may not want uv sync running, or may be offline | Always ask: "pyusb is required for USB printing. Install now? (uv sync --extra usb)" with Yes/No |

## "Looks Done But Isn't" Checklist

- [ ] **pyusb auto-install:** Does it work when pyusb was NEVER installed before (fresh venv)? Test with `uv sync` (without --extra usb) first, then trigger the install flow.
- [ ] **USB discovery:** Does it handle the case where libusb backend (C library) is missing even though pyusb (Python package) is installed? Error is `usb.core.NoBackendError`, not `ImportError`.
- [ ] **CUPS discovery:** Does it handle systems where CUPS is not running (Linux minimal installs)? `lpstat` may not exist.
- [ ] **Config save:** Does save_config handle the case where CONFIG_DIR does not exist? (It does -- mkdir exists, but verify the setup flow uses it.)
- [ ] **Config save:** Does it preserve existing custom profiles when saving only the printer selection? (The existing save_config writes ALL fields -- verify custom_profiles survive.)
- [ ] **Setup skip logic:** Does "printer still connected" check actually verify connectivity, or just check that the config entry exists? A config entry for a disconnected printer should trigger setup.
- [ ] **Screen lifecycle:** After setup screen dismisses, does the main screen correctly receive focus and process input? Test with rapid key presses during dismiss animation.
- [ ] **uv availability:** What happens if `uv` is not on PATH? (User installed via pip/pipx instead.) The error message should be clear.
- [ ] **Offline mode:** What happens when uv sync is attempted but user has no internet? Detect and show "Cannot install pyusb: no network connection."

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Corrupted config file | LOW | Detect TOMLDecodeError on load, rename broken file to .bak, start with defaults, notify user |
| USB driver claim failure | LOW | Fall back to CUPS automatically, show diagnostic in setup screen |
| uv sync fails mid-install | MEDIUM | Catch non-zero returncode, show stderr to user, offer retry. Partial installs are handled by uv's lockfile |
| Stale CUPS printer in config | LOW | On printer open failure, clear saved printer from config, show setup screen |
| sys.modules cache prevents reimport | LOW | Clear usb.* entries from sys.modules and retry import |
| Textual screen state corruption | HIGH | Only recoverable by app restart. Prevention (correct lifecycle management) is critical |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Subprocess blocks event loop | Phase 1 (pyusb auto-install) | TUI remains responsive during install; progress indicator visible |
| Import cache after install | Phase 1 (pyusb auto-install) | `import usb.core` works immediately after install without app restart |
| macOS kernel driver conflicts | Phase 2 (USB + CUPS selection) | macOS users see CUPS as primary option; USB direct failures show clear diagnostic |
| Config file corruption | Phase 3 (config persistence) | Kill -9 during save does not corrupt config; backup file exists |
| Screen lifecycle issues | Phase 2 (setup TUI screen) | Main screen fully functional after setup dismiss; all keybindings work |
| CUPS stale results | Phase 2 (CUPS selection) | Refresh button re-scans; disconnected printers shown as unavailable |
| Silent printer fallback | Phase 2 (setup UX) | Status bar shows printer state; missing printer triggers visible warning |
| No re-entry to setup | Phase 2 or 3 | `--setup` flag or settings modal option exists for reconfiguration |
| pyusb without libusb backend | Phase 1 or diagnostic command | NoBackendError caught separately from ImportError with actionable message |

## Sources

- [Textual Workers documentation](https://textual.textualize.io/guide/workers/) -- async patterns for background tasks
- [Textual Screens documentation](https://textual.textualize.io/guide/screens/) -- push_screen lifecycle
- [Textual Discussion #1828](https://github.com/Textualize/textual/discussions/1828) -- blocking API in Textual
- [Textual Discussion #2035](https://github.com/Textualize/textual/discussions/2035) -- updating screen before push_screen
- [pyusb Issue #374](https://github.com/pyusb/pyusb/issues/374) -- macOS kernel driver detach
- [libusb Discussion #1321](https://github.com/libusb/libusb/discussions/1321) -- macOS kernel driver limitations
- [libusb PR #911](https://github.com/libusb/libusb/pull/911) -- macOS kernel driver detach implementation
- [pyusb Issue #208](https://github.com/pyusb/pyusb/issues/208) -- macOS access denied errors
- [Real Python: Python and TOML](https://realpython.com/python-toml/) -- tomllib/tomli-w round-trip limitations
- [Python Discuss: Optional imports](https://discuss.python.org/t/optional-imports-for-optional-dependencies/104760) -- patterns for optional dependency handling
- [CUPS lpstat man page](https://www.cups.org/doc/man-lpstat.html) -- lpstat output format
- [Apple CUPS Issue #756](https://github.com/apple/cups/issues/756) -- CUPS printer recovery issues
- Existing codebase: `printer.py`, `config.py`, `tui.py`, `settings_screen.py`, `profiles.py`

---
*Pitfalls research for: Printer Setup TUI (v1.4 milestone) added to existing Claude Teletype app*
*Researched: 2026-04-02*
