# Feature Landscape: v1.4 Printer Setup TUI

**Domain:** Interactive printer setup TUI for CLI hardware tool
**Researched:** 2026-04-02
**Confidence:** MEDIUM-HIGH (existing codebase has all discovery primitives; UX design is the main new work)

## Context: What Already Exists

The v1.3 codebase (3,381 LOC source + 5,709 LOC tests) has all the hardware discovery and configuration primitives this milestone builds upon:

- **Discovery functions:** `discover_usb_device_verbose()` with diagnostic messages, `discover_cups_printers()` with URI parsing, `discover_macos_usb_printers()` via ioreg, `auto_detect_profile()` with VID:PID matching
- **Driver classes:** `UsbPrinterDriver` (pyusb direct), `CupsPrinterDriver` (lp subprocess), `FilePrinterDriver` (device file), `NullPrinterDriver` (simulator fallback), `ProfilePrinterDriver` (ESC code wrapper)
- **Profile system:** `BUILTIN_PROFILES` dict (generic, juki, escp, ppds, pcl, ibm), `get_profile()`, `load_custom_profiles()` from TOML
- **Config persistence:** `save_config()` writes TOML, `load_config()` reads it, `TeletypeConfig` dataclass with `device`, `printer_profile` fields
- **Existing TUI patterns:** `SettingsScreen(ModalScreen)` with Select, Switch, Input, Button widgets; `ConfirmSwapScreen` for modal confirmations
- **Silent discovery chain:** `discover_printer()` in cli.py runs silently at startup with priority chain: device override > USB > CUPS > Linux /dev > Null
- **Diagnostic output:** `_find_usb_printer(diagnostics)` already collects human-readable step-by-step messages; used in `--teletype` mode's fallback error display

**What's missing:** All discovery happens invisibly. Users never see what was found or why auto-detection picked what it did. No interactive selection. No dependency installation help. No dedicated diagnostic command.

---

## Table Stakes

Features users expect from an interactive printer setup flow. Missing any of these makes the setup feel broken.

| Feature | Why Expected | Complexity | Dependencies on Existing | Notes |
|---------|--------------|------------|--------------------------|-------|
| **SETUP-01: Device enumeration list** | Users need to see what is connected before choosing. Invisible auto-detection is the problem this milestone solves. | Low | `discover_usb_device_verbose()`, `discover_cups_printers()`, `discover_macos_usb_printers()` | All discovery code exists. Need to aggregate results into a unified device list with type labels (USB Direct / CUPS Queue). |
| **SETUP-02: Connection method selection** | USB direct enables character-by-character streaming (the core experience). CUPS queue is line-buffered (degraded but functional). Users must understand the tradeoff. | Low | `UsbPrinterDriver`, `CupsPrinterDriver` | Binary choice. USB direct should be recommended when available. CUPS is the fallback. Label clearly: "USB Direct (recommended for character streaming)" vs "CUPS Queue (line-buffered)". |
| **SETUP-03: Profile assignment for USB devices** | USB devices need ESC code profiles to send correct init/reset/newline sequences. Without a profile, output is garbled or missing formatting. | Low | `BUILTIN_PROFILES`, `get_profile()`, custom profiles from `config.custom_profiles` | Dropdown/list from existing profile registry. When VID:PID matches a known profile (via `auto_detect_profile()` logic), pre-select it. |
| **SETUP-04: Save selection to config** | Users should not repeat setup every launch. The whole point of interactive setup is "do it once." | Med | `save_config()` already writes TOML, `TeletypeConfig.device` and `TeletypeConfig.printer_profile` fields exist | Write selected printer name/device + profile to TOML config. The `save_config()` function and relevant config fields already exist. |
| **SETUP-05: Skip setup when saved printer still connected** | Returning users with the same hardware should get instant startup, not a setup screen every time. | Med | `auto_detect_profile()`, `discover_cups_printers()`, `load_config()` | On launch: load saved config, check if saved device/printer is still present, bypass setup if match found. Match USB by VID:PID (not bus address, which changes). Match CUPS by queue name via `lpstat`. |
| **SETUP-06: Connection status indicators** | User needs confirmation that a selected device actually works, not just that it was enumerated. | Low | `_find_usb_printer(diagnostics)` diagnostic messages | Show "Connected" / "Not Found" / "Driver Missing" next to each device. For USB, attempt to claim the device. For CUPS, verify queue is accepting jobs. |
| **SETUP-07: Graceful pyusb-missing handling** | pyusb is an optional dependency. Many first-time users will not have it installed. The setup screen must not crash or show a blank list. | Low | Existing `try: import usb.core except ImportError` pattern in `_find_usb_printer()` | Show "USB detection unavailable -- Install pyusb for direct USB access" with an action button. CUPS printers should still appear. |
| **SETUP-08: Skip/simulator option** | Simulator mode is a core feature (used for development and no-hardware demos). Setup must never block users who have no printer. | Low | `NullPrinterDriver` | Prominent "Skip setup (use terminal simulator)" option. Always visible, not buried in a submenu. |

---

## Differentiators

Features that elevate the setup experience. Not expected, but valued.

| Feature | Value Proposition | Complexity | Dependencies on Existing | Notes |
|---------|-------------------|------------|--------------------------|-------|
| **DIFF-01: Auto-install pyusb via uv** | Zero-friction dependency resolution. User never leaves the app. "Install USB support?" prompt + background `uv sync --extra usb` + re-scan. | Med | pyproject.toml `[project.optional-dependencies] usb = ["pyusb>=1.3.0"]` | Must handle: uv not on PATH (suggest `pip install pyusb` fallback), sync failure (show error), permission errors, and re-import after install (may need `importlib.reload` or subprocess re-scan). |
| **DIFF-02: Inline diagnostic messages** | Show discovery progress directly in the setup screen. "Scanning USB... found 3 devices... 1 printer-class... pyusb OK... libusb OK..." Builds user confidence in the tool. | Low | `_find_usb_printer(diagnostics)` already returns diagnostic message list | Render the diagnostics list in a scrollable log region of the setup screen. Already-structured data, just needs a display widget. |
| **DIFF-03: VID:PID auto-match profile suggestion** | When a connected USB device matches a built-in profile's VID:PID, pre-select that profile automatically. Reduces clicks for known hardware (e.g., Juki 6100 via CH341 bridge). | Low | `auto_detect_profile()` has the full VID:PID matching logic with exact and vendor-only fallback | Wire the existing function's result into the profile dropdown's default value. Trivial once enumeration is done. |
| **DIFF-04: `claude-teletype diagnose` command** | Dedicated troubleshooting for bug reports and support. Collects all discovery info, dependency status, config state into structured output. Separate from setup screen -- runs without TUI. | Med | All discovery functions, `config show` logic, pyusb/libusb detection | New Typer subcommand. Outputs: pyusb installed (Y/N), libusb backend found (Y/N), USB devices found (list with VID:PID), CUPS printers (list with URIs), macOS IOKit devices (if darwin), current config, saved printer status. |
| **DIFF-05: Live device refresh** | USB devices can be plugged in after the app starts. A "Refresh" button re-runs discovery without restarting. | Low-Med | All discovery functions | Manual "Refresh" button (not auto-polling timer). Re-runs `discover_usb_device_verbose()` + `discover_cups_printers()` and updates the list. Simple but requires wiring reactive updates to the widget. |
| **DIFF-06: Test print from setup** | "Send test page" button to verify connection works before committing the selection. Prints a short string through the selected driver. | Med | `ProfilePrinterDriver.write()`, driver construction | Must instantiate the driver temporarily, send test data, close it, report success/failure. Adds driver lifecycle complexity in setup context. Worth doing but not in first pass. |

---

## Anti-Features

Features to explicitly NOT build. Each would add complexity without matching the project's values.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Network printer discovery/support** | Network printers buffer entire pages, destroying the character-by-character streaming that IS the product. Already in PROJECT.md Out of Scope. | Filter out non-USB CUPS queues. Show "Network printers not supported (buffered output destroys typewriter effect)" if only network queues found. |
| **Multi-step wizard with Back/Next navigation** | Over-engineered for a 2-3 decision flow (connection method, device, profile). Adds navigation state complexity, back-button edge cases, and feels sluggish. | Single screen with all choices visible. Use progressive disclosure: show profile picker only after device is selected. Everything on one screen, top-to-bottom flow. |
| **Automatic PPD-based profile detection** | CUPS PPD files describe page formatting (margins, media sizes), NOT ESC code control sequences. They would give false confidence in auto-configuration. | Let user explicitly pick ESC code profile. Auto-suggest only when VID:PID matches a known profile. |
| **System package installation (libusb, CUPS drivers)** | Installing system packages (`brew install libusb`, `apt install libusb-1.0-0`) requires elevated permissions and varies by OS/distro. Not the app's responsibility. | Show clear prerequisite messages with platform-specific install commands. `diagnose` command checks prerequisites. |
| **Background USB polling/hotplug detection** | Continuous USB enumeration adds complexity, power drain, and platform-specific hotplug APIs (udev, IOKit notifications). USB is typically plugged in before launching. | Manual "Refresh" button. One-time scan at setup screen open. |
| **Edit custom TOML profiles from setup TUI** | Custom profiles require hex-encoded ESC sequences. Building a form for this is complex and error-prone. Power users who define custom profiles are comfortable editing TOML. | Document custom profile format in config template (already done in `DEFAULT_CONFIG_TEMPLATE`). Setup screen only selects from existing profiles. |
| **Printer test page with formatting** | A full test page with alignment, character set display, etc. is a separate feature. The setup screen just needs to verify the connection works. | Simple "Hello from Claude Teletype!" test string if test print is implemented. No formatting, no alignment chart. |

---

## Feature Dependencies

```
SETUP-07: pyusb-missing handling ──→ DIFF-01: Auto-install pyusb (enhance the "missing" state)
                                     |
                                     └──→ SETUP-01: Device enumeration (re-scan after install)

SETUP-01: Device enumeration ──→ SETUP-02: Connection method selection (need devices to show)
                             ──→ SETUP-06: Connection status (status per enumerated device)
                             ──→ DIFF-03: VID:PID auto-match (match against enumerated devices)
                             ──→ DIFF-05: Live refresh (re-run enumeration)

SETUP-02: Connection method  ──→ SETUP-03: Profile assignment (only for USB direct; CUPS uses generic)

SETUP-03: Profile assignment ──→ SETUP-04: Save to config (need device + profile to persist)
                             ──→ DIFF-06: Test print (need driver + profile to test)

SETUP-04: Save to config     ──→ SETUP-05: Skip on reconnect (need saved state to compare)

DIFF-04: diagnose command     ──→ (independent, builds on same discovery functions but no TUI dependency)

DIFF-02: Inline diagnostics  ──→ (independent display concern, can layer onto any setup screen state)

SETUP-08: Skip/simulator     ──→ (independent, always available regardless of other features)
```

---

## MVP Recommendation

### Phase 1: Setup Screen Core

Build the screen with device enumeration, selection, profile assignment, and config persistence.

1. **SETUP-01: Device enumeration list** -- aggregate existing discovery functions into unified view
2. **SETUP-02: Connection method selection** -- USB direct vs CUPS queue with clear labeling
3. **SETUP-03: Profile assignment** -- dropdown from existing profile registry
4. **DIFF-03: VID:PID auto-match** -- pre-select profile when hardware matches (cheap, high UX value)
5. **SETUP-07: Graceful pyusb-missing** -- "USB unavailable" state with install hint
6. **SETUP-08: Skip/simulator option** -- always-visible escape hatch
7. **SETUP-04: Save to config** -- persist selection via existing `save_config()`
8. **SETUP-06: Connection status** -- indicators next to each device

### Phase 2: Smart Startup + Dependency Help

Make returning users fast and help first-time users get dependencies.

9. **SETUP-05: Skip when saved printer connected** -- check hardware on launch, bypass if matched
10. **DIFF-01: Auto-install pyusb** -- prompt + subprocess `uv sync --extra usb` + re-scan
11. **DIFF-02: Inline diagnostics** -- show discovery progress in setup screen

### Phase 3: Diagnostic Command

Separate from setup TUI. Useful for troubleshooting without launching the full app.

12. **DIFF-04: `claude-teletype diagnose`** -- Typer subcommand with comprehensive report

### Defer to Future Milestones

- **DIFF-05: Live device refresh** -- Useful but edge case. Most users plug in first, then launch. Add later if requested.
- **DIFF-06: Test print from setup** -- Nice but adds driver lifecycle complexity in setup context. Better as a future enhancement.

---

## Complexity Assessment

| Feature | Effort | Risk | Notes |
|---------|--------|------|-------|
| SETUP-01: Device enumeration | Small | Low | Aggregate 3 existing functions into one list |
| SETUP-02: Connection method | Small | Low | RadioSet or similar 2-option widget |
| SETUP-03: Profile assignment | Small | Low | Select widget from existing `BUILTIN_PROFILES` + custom |
| SETUP-04: Save to config | Small-Med | Low | `save_config()` exists; wire up field mapping |
| SETUP-05: Skip on reconnect | Medium | Medium | USB devices change bus addresses; must match by VID:PID not path. CUPS queues may be renamed. |
| SETUP-06: Connection status | Small | Low | Display diagnostic strings already generated by `_find_usb_printer()` |
| SETUP-07: pyusb-missing | Small | Low | Conditional display based on ImportError already handled |
| SETUP-08: Skip/simulator | Trivial | Low | Button that dismisses setup with NullPrinterDriver |
| DIFF-01: Auto-install pyusb | Medium | Medium | `uv` may not be installed; module reload after install is tricky; need subprocess error handling |
| DIFF-02: Inline diagnostics | Small | Low | Render existing diagnostic message list |
| DIFF-03: VID:PID auto-match | Small | Low | Wire existing `auto_detect_profile()` result to dropdown default |
| DIFF-04: diagnose command | Medium | Low | New Typer subcommand; all data sources exist |
| DIFF-05: Live refresh | Small-Med | Low | Re-run discovery, update reactive list |
| DIFF-06: Test print | Medium | Medium | Temporary driver lifecycle in setup context |

---

## Textual Implementation Notes

The setup screen should be a **full `Screen`** (not `ModalScreen`) since it runs at startup before the main conversation TUI. Key design decisions:

- **When to show:** On first launch (no saved config) or when saved printer is not detected. Show conditionally from `TeletypeApp.on_mount()` via `push_screen()`.
- **When to skip:** When saved device/printer from config is still connected. Go straight to main TUI.
- **Screen structure (top to bottom):**
  1. Title: "Printer Setup"
  2. Diagnostic log area (`RichLog` or `Static`): discovery progress messages
  3. Device list (`OptionList` or `ListView`): enumerated devices with type/status labels
  4. Profile selector (`Select`): enabled after device selection, pre-populated if VID:PID matches
  5. Action buttons (`Button`): "Save & Continue" / "Skip (use simulator)" / "Install USB Support" (conditional)
- **Widgets to use** (all exist in Textual's widget library):
  - `OptionList` for device selection -- better than `ListView` for labeled items
  - `Select` for profile dropdown -- matches existing `SettingsScreen` pattern
  - `Static` or `RichLog` for diagnostic messages
  - `Button` for Save / Skip / Install actions
  - `Label` for section headers and status indicators
- **Result passing:** Dismiss with a dict containing `{"device": ..., "profile": ..., "driver_type": "usb"|"cups"|"null"}` -- same pattern as `SettingsScreen.dismiss(dict | None)`.
- **Config update:** On "Save & Continue", call `save_config()` to persist. On "Skip", proceed with `NullPrinterDriver` without saving.

---

## Sources

- Existing codebase analysis: `profiles.py` (profile registry + VID:PID matching), `printer.py` (drivers + discovery functions + diagnostic collection), `cli.py` (startup flow + profile resolution), `config.py` (TOML persistence + `save_config()`), `settings_screen.py` (TUI modal pattern)
- [UX patterns for CLI tools](https://lucasfcosta.com/2022/06/01/ux-patterns-cli-tools.html) -- interactive prompts, organized layouts, semantic color coding
- [Textual Screens documentation](https://textual.textualize.io/guide/screens/) -- screen stacks, push/pop, modes
- [Textual Tutorial](https://textual.textualize.io/tutorial/) -- widget composition, compose patterns
- [uv documentation](https://docs.astral.sh/uv/) -- `uv sync --extra` for optional dependency groups

---
*Feature research for: Claude Teletype v1.4 -- Printer Setup TUI*
*Researched: 2026-04-02*
