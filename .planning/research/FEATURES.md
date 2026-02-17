# Feature Landscape: v1.2 Milestone

**Domain:** Configuration system, printer profiles, multi-LLM backends, TUI settings, typewriter mode
**Researched:** 2026-02-17
**Confidence:** HIGH for config/settings/typewriter, MEDIUM for printer profiles (hardware-specific), MEDIUM for multi-LLM (API patterns well-known, integration specifics need testing)

## Context: What Already Exists

The v1.1 codebase (1,839 LOC source + 3,139 LOC tests) has:

- **CLI args only:** All settings are CLI flags (`--delay`, `--device`, `--no-audio`, `--transcript-dir`, `--resume`, `--juki`, `--teletype`). No persistent configuration. Users must re-type flags every session.
- **Single printer driver model:** `PrinterDriver` protocol with `NullPrinterDriver`, `FilePrinterDriver`, `CupsPrinterDriver`, `UsbPrinterDriver`. Only `JukiPrinterDriver` wraps an inner driver with printer-specific ESC codes. No other printer profiles.
- **Claude Code CLI only:** `bridge.py` spawns `claude -p <prompt> --output-format stream-json`. No direct API calls. No support for OpenAI, OpenRouter, or any other LLM provider.
- **No settings UI:** TUI has Header, Log, Input, Footer, status bar. No modal screens, no settings panel. Only keybindings are `Ctrl+D` (quit) and `Escape` (cancel stream).
- **Existing teletype mode:** `teletype.py` already implements raw keyboard-to-printer mode with `tty.setcbreak()` and character-by-character writing. But it requires a physical printer (`--teletype` with USB detection). No pure terminal typewriter mode.

This research covers five capabilities that are largely independent but share the config system as a foundation.

---

## Table Stakes

Features users expect. Missing any of these makes the capability feel half-baked.

### CFG-01: TOML Configuration File with platformdirs Location

| Attribute | Detail |
|-----------|--------|
| **Why Expected** | Users should not need to type `--delay 75 --no-audio --device /dev/usb/lp0` every single time. Every serious CLI tool has a config file. The absence of one signals "prototype." |
| **Complexity** | MEDIUM |
| **Mechanism** | Use `platformdirs.user_config_path("claude-teletype")` to determine config location: `~/Library/Application Support/claude-teletype/config.toml` on macOS, `~/.config/claude-teletype/config.toml` on Linux. Parse with Python 3.11+ built-in `tomllib`. Validate with a Pydantic `BaseModel` or plain dataclass with defaults. |
| **Config Schema** | `[general]` (delay_ms, no_audio, transcript_dir), `[printer]` (default_profile, default_device), `[llm]` (default_backend, api_keys), `[sound]` (enabled, bell_frequency, bell_duration). Each section maps to a Pydantic model or dataclass with defaults. |
| **Priority Layering** | Defaults (hardcoded) < Config file < CLI flags. CLI flags always win. This is the universal pattern. Use `tomllib` to load, dataclass to merge, Typer CLI args override non-None values. |
| **Dependencies** | None. Foundation for all other v1.2 features. |
| **Confidence** | HIGH. `tomllib` is stdlib since 3.11. `platformdirs` is the standard solution (used by pip, black, tox). TOML is the modern Python config format. |

### CFG-02: Config File Creation and Defaults

| Attribute | Detail |
|-----------|--------|
| **Why Expected** | First-time users need a config file to exist with documented defaults and comments. `claude-teletype --init-config` or auto-create on first run with sensible defaults. Users should be able to open the file and understand every option. |
| **Complexity** | LOW |
| **Mechanism** | Ship a default config template as a string constant in the config module. On first run or `--init-config`, write it to the platformdirs location. Include inline TOML comments explaining each option. |
| **Dependencies** | CFG-01. |
| **Confidence** | HIGH. Standard pattern (e.g., `git config --global`, `black --config`). |

### CFG-03: CLI Flag Override of Config Values

| Attribute | Detail |
|-----------|--------|
| **Why Expected** | Users need `claude-teletype --delay 50` to override the config file for one session without editing the file. Every CLI tool with a config file supports this. |
| **Complexity** | LOW |
| **Mechanism** | Typer already provides CLI args. Load config first, then overlay any non-None CLI args. Typer's default of `None` for optional args naturally indicates "not provided by user." |
| **Dependencies** | CFG-01. |
| **Confidence** | HIGH. This is exactly how Typer + config file tools work. |

### PRNT-01: Printer Profile System with Named Profiles

| Attribute | Detail |
|-----------|--------|
| **Why Expected** | Users with multiple printers (Juki daisywheel + Epson dot matrix + HP inkjet) need per-printer settings without remembering which flags to pass. `--printer juki` or `--printer epson-lq` should select a complete configuration. |
| **Complexity** | MEDIUM |
| **Mechanism** | Config file defines `[printer.profiles.<name>]` sections. Each profile specifies: `type` (usb/cups/file), `device` (path or CUPS name), `columns` (wrap width), `newline` (lf/crlf), `init_codes` (hex bytes for printer initialization), `line_codes` (per-line ESC codes), `eject_code` (form feed or custom). |
| **Profile Fields** | `name`, `type` (usb|cups|file), `device_path`, `columns` (default 80), `newline` (lf|crlf, default lf), `init_sequence` (hex string like "1b1a49 1b1e09 1b51"), `line_reinit` (hex string, sent after each newline), `eject_sequence` (hex string, default "0c" for form feed), `pitch` (10|12|17, informational), `description` (human-readable). |
| **Dependencies** | CFG-01 (profiles live in config file). |
| **Confidence** | HIGH for the profile structure. MEDIUM for specific control codes per printer model (hardware-specific, needs testing). |

### PRNT-02: Built-in Profiles for Common Printers

| Attribute | Detail |
|-----------|--------|
| **Why Expected** | Users should not need to look up ESC/P manuals to print. Ship defaults that work for the most common hardware targets. |
| **Complexity** | MEDIUM (research-heavy, implementation is just data) |
| **Built-in Profiles** | See "Printer Profile Reference" section below for detailed control codes. |
| **Dependencies** | PRNT-01 (profile system). |
| **Confidence** | MEDIUM. Control codes are documented in Epson ESC/P manual (1997) and IBM PPDS reference. Juki codes verified from existing `JukiPrinterDriver`. HP PCL codes from HP LaserJet reference. But actual hardware behavior needs testing -- some printers ignore certain codes or require specific firmware versions. |

### LLM-01: Backend Abstraction Interface

| Attribute | Detail |
|-----------|--------|
| **Why Expected** | The current bridge is hardwired to Claude Code CLI subprocess. Users who want to use GPT-4, Claude via direct API, or OpenRouter models need a clean abstraction. The bridge module's `stream_claude_response()` should be one implementation of a backend protocol, not the only code path. |
| **Complexity** | MEDIUM |
| **Mechanism** | Define an `LLMBackend` protocol: `async def stream(prompt, session_id?) -> AsyncIterator[str | StreamResult]`. Implement `ClaudeCodeBackend` (existing bridge code), `OpenAIBackend` (using `openai` library), `OpenRouterBackend` (using `openai` library with `base_url="https://openrouter.ai/api/v1"`). The pacer, output pipeline, and TUI stay unchanged -- they just consume the async iterator. |
| **Dependencies** | CFG-01 (API keys and default backend selection live in config). |
| **Confidence** | HIGH for the abstraction pattern. OpenRouter uses the OpenAI-compatible API, so one implementation covers both OpenAI and OpenRouter with just a different `base_url` and `api_key`. |

### LLM-02: OpenAI and OpenRouter Direct API Backends

| Attribute | Detail |
|-----------|--------|
| **Why Expected** | Claude Code CLI is great but requires the full Claude Code installation and auth. Some users want to use GPT-4o or Claude via direct API (pay-per-token). OpenRouter gives access to 100+ models with one API key. |
| **Complexity** | MEDIUM |
| **Mechanism** | Use the `openai` Python library (already the standard for OpenAI-compatible APIs). For OpenAI: `OpenAI(api_key=...)`. For OpenRouter: `OpenAI(base_url="https://openrouter.ai/api/v1", api_key=...)`. Both support `stream=True` for SSE streaming. Parse `chunk.choices[0].delta.content` for text deltas, map to the same `str | StreamResult` pattern the existing output pipeline expects. |
| **Session Handling** | OpenAI/OpenRouter do NOT have server-side sessions. Client must maintain conversation history as a list of `{"role": "user/assistant", "content": "..."}` messages. Store in memory during session, persist to disk for `--resume`. This is the biggest architectural difference from Claude Code CLI. |
| **Dependencies** | LLM-01 (backend abstraction), CFG-01 (API keys). |
| **Confidence** | HIGH. OpenAI Python library streaming is extremely well-documented. OpenRouter's OpenAI-compatible endpoint is verified from their official docs. |

### SET-01: TUI Settings Screen via Keyboard Shortcut

| Attribute | Detail |
|-----------|--------|
| **Why Expected** | Users should be able to change settings without quitting the app and editing a TOML file. A `Ctrl+S` or `F2` shortcut to open a modal settings screen is standard in TUI applications (e.g., htop, lazygit, midnight commander all have settings accessible via hotkey). |
| **Complexity** | MEDIUM |
| **Mechanism** | Textual's `ModalScreen` class is purpose-built for this. Create a `SettingsScreen(ModalScreen)` with form widgets (Switch for booleans, Select for dropdowns, Input for text values). Push it onto the screen stack with `self.push_screen(SettingsScreen(), callback)`. When dismissed, apply changes to the running app AND optionally write back to config file. |
| **Textual Widgets** | `Switch` (on/off for audio, etc.), `Select` (printer profile dropdown, LLM backend dropdown), `Input` (delay_ms, transcript dir), `RadioSet` (mutually exclusive choices), `Button` (Save / Cancel). All are built into Textual's widget library. |
| **Dependencies** | CFG-01 (settings modify config values), Textual >= 0.40 (ModalScreen is stable). |
| **Confidence** | HIGH. Textual's ModalScreen API is well-documented and stable. The widget gallery provides all needed form elements. |

### TYPE-01: Pure Typewriter Mode in TUI (No LLM)

| Attribute | Detail |
|-----------|--------|
| **Why Expected** | The existing `--teletype` mode requires a physical USB printer. Users want to type in the TUI and see characters appear with typewriter pacing and sound effects, even without an LLM and without printer hardware. This is the "just a typewriter" experience -- pure creative writing tool. |
| **Complexity** | LOW |
| **Mechanism** | When activated (via CLI flag `--typewriter` or settings toggle), disable the prompt/response loop. Instead, every keystroke in the Input widget is (1) paced through the pacer, (2) written to the Log widget, (3) sent to printer if connected, (4) triggers bell sound on newline. No Claude Code subprocess is spawned. The Input widget becomes a live typing area instead of a prompt submission field. |
| **Changes** | (1) New flag `--typewriter` or `--type-only`. (2) TUI mode where Input keystrokes flow directly to output pipeline. (3) No `check_claude_installed()` in typewriter mode. (4) Pacing still applies (configurable delay). (5) Sound effects still apply. |
| **Dependencies** | None. Independent of other features, though benefits from CFG-01 for persistent typewriter settings. |
| **Confidence** | HIGH. The output pipeline (`make_output_fn`, pacer, printer_write, bell_write) already exists. Typewriter mode just needs to route Input keystrokes into it instead of sending them to Claude. |

---

## Differentiators

Features that elevate beyond basic expectations. Not required, but valued.

### CFG-04: `claude-teletype config show` Subcommand

| Attribute | Detail |
|-----------|--------|
| **Value** | Show the effective configuration (merged defaults + file + env vars) in a formatted table. Helps users debug "why is my delay 75 instead of 50?" without reading the TOML file manually. |
| **Complexity** | LOW |
| **Dependencies** | CFG-01. |

### CFG-05: Environment Variable Override

| Attribute | Detail |
|-----------|--------|
| **Value** | `CLAUDE_TELETYPE_DELAY=50` overrides config file. Useful in scripts, CI, Docker. Standard pattern: defaults < config file < env vars < CLI flags. |
| **Complexity** | LOW |
| **Mechanism** | Pydantic Settings natively supports this with `env_prefix="CLAUDE_TELETYPE_"`. If not using Pydantic Settings, manually check `os.environ` for prefixed variables. |
| **Dependencies** | CFG-01. |

### PRNT-03: Custom Profile Definition in Config

| Attribute | Detail |
|-----------|--------|
| **Value** | Users with unusual printers (e.g., Olivetti, Brother daisywheel, Okidata) can define custom profiles with arbitrary ESC sequences in their config file. |
| **Complexity** | LOW (if PRNT-01 is designed for extensibility) |
| **Mechanism** | Any `[printer.profiles.<name>]` section in the user's config file is loaded as a profile. Built-in profiles ship in a separate `profiles.toml` or as defaults in the code. User profiles override built-ins with the same name. |
| **Dependencies** | PRNT-01. |

### PRNT-04: Profile Auto-Selection by USB VID:PID

| Attribute | Detail |
|-----------|--------|
| **Value** | When a USB printer is detected via pyusb, match its vendor:product ID against known profiles and auto-select the right one. No `--printer <name>` flag needed. |
| **Complexity** | MEDIUM |
| **Mechanism** | Profile includes optional `usb_vid` and `usb_pid` fields. During `discover_printer()`, if a USB device matches, select the corresponding profile automatically. Fall back to generic profile. |
| **Dependencies** | PRNT-01, existing USB discovery code. |

### LLM-03: Model Selection Within Backend

| Attribute | Detail |
|-----------|--------|
| **Value** | OpenRouter has 100+ models. Users want `--model openrouter/anthropic/claude-3.5-sonnet` or similar. The config file sets a default model per backend. |
| **Complexity** | LOW |
| **Mechanism** | Config: `[llm.openrouter] model = "anthropic/claude-3.5-sonnet"`. CLI: `--model <model>`. Passed to `client.chat.completions.create(model=...)`. |
| **Dependencies** | LLM-01, LLM-02, CFG-01. |

### LLM-04: Backend Health Check on Startup

| Attribute | Detail |
|-----------|--------|
| **Value** | Before entering the TUI, verify the selected backend is reachable. "OpenRouter API key invalid" is better than a cryptic error mid-conversation. |
| **Complexity** | LOW |
| **Mechanism** | For Claude Code: `shutil.which("claude")` (already exists). For OpenAI/OpenRouter: make a lightweight API call (e.g., list models) or just validate the API key format. |
| **Dependencies** | LLM-01. |

### SET-02: Live Settings Preview

| Attribute | Detail |
|-----------|--------|
| **Value** | When changing delay_ms in the settings screen, show a preview of the pacing speed in real-time. Satisfying and helps users dial in their preferred speed. |
| **Complexity** | MEDIUM |
| **Mechanism** | Add a small preview area in the SettingsScreen that runs a sample text through the pacer at the currently-selected delay. Updates as the user adjusts the slider/input. |
| **Dependencies** | SET-01. |

### SET-03: Settings Persist to Config File

| Attribute | Detail |
|-----------|--------|
| **Value** | When user changes a setting in the TUI, offer to save it permanently (not just for the current session). "Save" button writes back to the TOML config file. |
| **Complexity** | MEDIUM (TOML writing requires `tomli-w` or manual string formatting since `tomllib` is read-only) |
| **Mechanism** | Use `tomli_w` (write companion to `tomllib`) or format TOML strings manually. Preserve user comments if possible (hard with automatic serialization -- this is a known pain point). |
| **Dependencies** | SET-01, CFG-01. |

### TYPE-02: Typewriter Mode with Line Counter and Paper Simulation

| Attribute | Detail |
|-----------|--------|
| **Value** | Show line count, character position, and a "paper edge" indicator in the status bar. Simulates the physical awareness of where you are on the page. Optional "ding at column 65" warning (like real typewriters approaching the right margin). |
| **Complexity** | LOW |
| **Dependencies** | TYPE-01. |

### TYPE-03: Typewriter Mode with Printer Output

| Attribute | Detail |
|-----------|--------|
| **Value** | In typewriter mode, keystrokes go to both the TUI display AND the connected printer simultaneously. True typewriter-to-paper experience, just with a screen mirror. |
| **Complexity** | LOW (existing output pipeline already supports multiple destinations) |
| **Dependencies** | TYPE-01, existing printer infrastructure. |

### FIX-01: `--no-tui` Mode StreamResult Fix

| Attribute | Detail |
|-----------|--------|
| **Value** | Known tech debt: `_chat_async()` in cli.py crashes with TypeError at end of response because it doesn't handle `StreamResult` from the bridge. Must guard against non-string items in the async generator. |
| **Complexity** | LOW |
| **Dependencies** | None. Bug fix for existing code. |

---

## Anti-Features

Features to explicitly NOT build for this milestone.

| Anti-Feature | Why It Seems Good | Why Avoid | What to Do Instead |
|--------------|-------------------|-----------|-------------------|
| GUI configuration editor | "A graphical config editor would be easier than editing TOML" | This is a terminal tool. GUI config editors add dependencies (tkinter, Qt) and break the aesthetic. The TUI settings screen IS the GUI. | TUI ModalScreen settings panel (SET-01). |
| Plugin system for LLM backends | "Let users write custom backends as plugins" | Massive over-engineering for 3 backends. Plugin discovery, loading, API stability contracts. Ship the 3 backends, let users submit PRs for more. | Hardcode the 3 backends. Clean protocol makes adding more trivial. |
| LiteLLM integration | "LiteLLM supports 100+ providers, use it instead of direct API" | LiteLLM is a heavy dependency (67MB+ install) with its own proxy server architecture. For a CLI tool that needs 2-3 backends, the `openai` library with different `base_url` values is far simpler and lighter. | Use `openai` library directly for OpenAI and OpenRouter. They both speak the same protocol. |
| Printer driver auto-installation | "Automatically install CUPS drivers or pyusb backends" | System-level package management is fraught with permissions issues and varies across distros. Not our problem. | Document prerequisites (`brew install libusb`, `uv sync --extra usb`). Detect and report missing dependencies clearly. |
| Real-time config file watching | "Reload config when the file changes on disk" | Over-engineering. Config changes during a session are rare. The settings screen handles runtime changes; the config file is read at startup. | Read config at startup. Settings screen for runtime changes. |
| Encrypted API key storage | "Don't store API keys in plain text TOML" | Complexity explosion (keyring integration, OS-specific credential stores). Environment variables already solve this for security-conscious users. | Support `OPENAI_API_KEY` and `OPENROUTER_API_KEY` env vars. Document that env vars are preferred over config file for API keys. |
| Network printer support | "Add TCP/IP printer support for network-attached printers" | Network printers buffer entire pages before printing, destroying the character-by-character streaming experience. This is fundamentally incompatible with the typewriter aesthetic. Already explicitly out of scope in PROJECT.md. | USB/parallel only. Document why network printers don't work. |
| Conversation history for OpenAI/OpenRouter | "Save full conversation history to disk for API backends" | Client-side conversation persistence is complex (file format, corruption handling, pruning, context window management). Start with in-memory only for v1.2. | In-memory conversation history during session. `--resume` only works with Claude Code CLI (which handles its own persistence). |
| WYSIWYG paper preview in TUI | "Show exactly what the printer output will look like with control codes rendered" | Rendering ESC/P control code effects in the terminal requires a virtual printer emulator. Massive scope creep. | Show plain text in TUI. Trust the control codes work on actual hardware. |

---

## Printer Profile Reference

Detailed control codes for each target printer family. These are the raw bytes that profiles will encode.

### Juki 6100/6300/9100 (Daisywheel Impact)

Already partially implemented in `JukiPrinterDriver`. Codes from the Juki 6100 Operation Manual (1983).

| Function | Hex Bytes | Notes |
|----------|-----------|-------|
| Full reset | `1b 1a 49` | ESC SUB I |
| Line spacing 1/6" | `1b 1e 09` | ESC RS 9 (9/48" = 1/6") |
| Fixed pitch (disable proportional) | `1b 51` | ESC Q |
| Carriage return | `0d` | CR |
| Line feed | `0a` | LF |
| Form feed (page eject) | `0c` | FF |
| Newline convention | CR+LF (`0d 0a`) | Impact printers need explicit CR |

### Epson 9-pin Dot Matrix (LX-300, FX-890, etc.)

ESC/P specification. Codes from the Epson ESC/P Reference Manual (1997).

| Function | Hex Bytes | Notes |
|----------|-----------|-------|
| Initialize printer | `1b 40` | ESC @ -- reset to defaults |
| 10 CPI (Pica) | `12` | DC2 -- standard pitch |
| 12 CPI (Elite) | `1b 4d` | ESC M |
| 17 CPI (Condensed) | `0f` | SI |
| Cancel condensed | `12` | DC2 |
| Bold on | `1b 45` | ESC E |
| Bold off | `1b 46` | ESC F |
| Underline on | `1b 2d 01` | ESC - 1 |
| Underline off | `1b 2d 00` | ESC - 0 |
| Line spacing 1/6" | `1b 32` | ESC 2 -- standard 6 LPI |
| Line spacing n/72" | `1b 41 nn` then `1b 32` | ESC A n, then ESC 2 to activate |
| Form feed | `0c` | FF |
| Carriage return | `0d` | CR |
| Newline convention | LF only (`0a`) | Most Epson printers auto-CR on LF |

### IBM Proprinter / PPDS Compatible (IBM 2380, 2390, 4201, etc.)

IBM Personal Printer Data Stream. From the IBM PPDS Reference.

| Function | Hex Bytes | Notes |
|----------|-----------|-------|
| Initialize | `1b 49` | ESC I -- initialize |
| 10 CPI | `12` | DC2 |
| 12 CPI | `1b 3a` | ESC : |
| 17 CPI (Condensed) | `0f` | SI |
| Bold on | `1b 45` | ESC E |
| Bold off | `1b 46` | ESC F |
| Line spacing set | `1b 41 nn` then `1b 32` | ESC A n + ESC 2 |
| Form feed | `0c` | FF |
| Newline convention | CR+LF (`0d 0a`) | IBM convention |

### HP Inkjet / LaserJet (PCL5)

PCL Printer Command Language. From the HP PCL 5 Technical Reference.

| Function | Hex Bytes (ASCII) | Notes |
|----------|-------------------|-------|
| Reset | `1b 45` | Ec E -- universal PCL reset |
| 10 CPI pitch | `1b 28 73 31 30 48` | Ec(s10H |
| 12 CPI pitch | `1b 28 73 31 32 48` | Ec(s12H |
| 6 LPI line spacing | `1b 26 6c 36 44` | Ec&l6D |
| Page length 66 lines | `1b 26 6c 36 36 50` | Ec&l66P |
| Top margin 0 | `1b 26 6c 30 45` | Ec&l0E |
| Form feed | `0c` | FF |
| Newline convention | LF only (`0a`) | PCL auto-handles CR |

### Generic (Fallback)

No control codes. Plain text, LF newlines. Works with any printer that accepts raw text.

| Function | Hex Bytes | Notes |
|----------|-----------|-------|
| Initialize | (none) | |
| Form feed | `0c` | FF |
| Newline convention | LF (`0a`) | |

---

## Feature Dependencies

```
[CFG-01: TOML Config File]          (FOUNDATION -- build first)
    |
    +--enables--> [CFG-02: Config Creation/Defaults]
    +--enables--> [CFG-03: CLI Override]
    +--enables--> [CFG-04: config show subcommand]
    +--enables--> [CFG-05: Env Var Override]
    |
    +--enables--> [PRNT-01: Profile System]
    |                 |
    |                 +--enables--> [PRNT-02: Built-in Profiles]
    |                 +--enables--> [PRNT-03: Custom Profiles]
    |                 +--enables--> [PRNT-04: Auto-Select by VID:PID]
    |
    +--enables--> [LLM-01: Backend Abstraction]
    |                 |
    |                 +--enables--> [LLM-02: OpenAI/OpenRouter Backends]
    |                 |                 |
    |                 |                 +--enables--> [LLM-03: Model Selection]
    |                 |
    |                 +--enables--> [LLM-04: Backend Health Check]
    |
    +--enables--> [SET-01: TUI Settings Screen]
                      |
                      +--enables--> [SET-02: Live Preview]
                      +--enables--> [SET-03: Persist to Config]

[TYPE-01: TUI Typewriter Mode]       (INDEPENDENT)
    |
    +--enables--> [TYPE-02: Line Counter / Paper Sim]
    +--enables--> [TYPE-03: Typewriter + Printer]

[FIX-01: --no-tui StreamResult Fix]  (INDEPENDENT)
```

### Dependency Notes

- **CFG-01 is the keystone for v1.2.** Printer profiles, LLM backend selection, and settings UI all read from and write to the config system. Build this first.
- **TYPE-01 is independent.** It reuses existing output pipeline infrastructure and can be built in parallel with config work.
- **FIX-01 is independent.** Known bug, quick fix, should ship early in the milestone.
- **LLM-02 depends on LLM-01** but LLM-01 is a small interface definition. They can be built together in one plan.
- **SET-01 depends on CFG-01** and benefits from PRNT-01 and LLM-01 existing (so it has interesting things to configure). Build it last.
- **No circular dependencies.** Clean layering with config as the foundation.

---

## MVP Recommendation for v1.2

### Must Ship (defines the milestone)

1. **CFG-01 + CFG-02 + CFG-03: Configuration system** -- Persistent settings, defaults, CLI override. Foundation for everything else.
2. **PRNT-01 + PRNT-02: Printer profile system with built-ins** -- Named profiles with ESC/P and PCL control codes for Juki, Epson, IBM, HP.
3. **LLM-01 + LLM-02: Multi-LLM backend with OpenAI/OpenRouter** -- Backend abstraction and two new implementations using `openai` library.
4. **SET-01: TUI settings screen** -- ModalScreen with printer profile, LLM backend, delay, audio toggles.
5. **TYPE-01: Pure typewriter mode in TUI** -- Keystrokes to screen (and optional printer) with pacing and sound. No LLM.
6. **FIX-01: --no-tui StreamResult guard** -- Bug fix.

### Should Ship (high value, low incremental cost)

7. **CFG-05: Environment variable override** -- Important for API key security.
8. **LLM-03: Model selection** -- Small addition to LLM-02, high user value.
9. **TYPE-03: Typewriter mode with printer output** -- Trivial if TYPE-01 exists.
10. **LLM-04: Backend health check** -- Prevents confusing mid-conversation errors.

### Defer (nice but not milestone-defining)

11. **CFG-04: config show subcommand** -- Debugging convenience, not essential.
12. **SET-02: Live settings preview** -- Polish feature.
13. **SET-03: Persist settings to file** -- Requires `tomli_w` dependency and comment-preservation logic.
14. **PRNT-03: Custom profile definition** -- The built-in profiles cover common printers. Custom is for power users.
15. **PRNT-04: Auto-select by VID:PID** -- Nice automation, but `--printer <name>` works fine.
16. **TYPE-02: Line counter** -- Polish, not essential.

---

## Implementation Complexity Summary

| Feature | Lines of Code (est.) | New Files | Modified Files | Risk |
|---------|---------------------|-----------|----------------|------|
| CFG-01/02/03 | ~200 | 1 (config.py) | cli.py | LOW |
| CFG-05 | ~20 | 0 | config.py | LOW |
| PRNT-01/02 | ~250 | 1 (profiles.py) | printer.py, config.py | MEDIUM (hardware testing) |
| LLM-01/02 | ~300 | 1 (backends.py) | bridge.py, tui.py, cli.py | MEDIUM (API integration) |
| LLM-03 | ~30 | 0 | backends.py, config.py | LOW |
| SET-01 | ~200 | 1 (settings_screen.py) | tui.py | LOW-MEDIUM |
| TYPE-01 | ~80 | 0 | tui.py, cli.py | LOW |
| TYPE-03 | ~20 | 0 | tui.py | LOW |
| FIX-01 | ~10 | 0 | cli.py | TRIVIAL |

**Total estimate for Must Ship:** ~1,040 lines across 4 new files and 5 modified files.
**Total estimate for Should Ship:** ~70 additional lines.

---

## Key Architecture Decisions for Features

### Config System: Pydantic vs Plain Dataclass

**Recommendation: Plain dataclass with `tomllib`.** Pydantic Settings is powerful but adds a heavy dependency for what is fundamentally "read a TOML file and merge with CLI args." Use `tomllib` (stdlib) for parsing, `@dataclass` for schema with defaults, and a simple merge function. If validation complexity grows later, migrate to Pydantic.

### LLM Backend: OpenAI Library vs LiteLLM

**Recommendation: `openai` library directly.** OpenRouter is OpenAI-compatible (same library, different `base_url`). One library covers both backends. LiteLLM adds 67MB+ of dependencies, a proxy server architecture, and support for 100+ providers we don't need. The `openai` library is ~2MB and does exactly what we need.

### LLM Session Management: Server-side vs Client-side

**Key difference:** Claude Code CLI manages conversation history server-side (`--resume <session_id>`). OpenAI/OpenRouter require client-side conversation history (accumulate messages list). The `LLMBackend` protocol must accommodate both patterns. Claude Code backend: stateless (server handles it). OpenAI backend: stateful (must maintain `messages` list).

### Printer Profiles: Hex String in TOML vs Python Constants

**Recommendation: Hex strings in TOML, parsed to bytes at load time.** This makes profiles editable by users without writing Python code. Example: `init_sequence = "1b40"` in TOML, parsed to `b"\x1b\x40"` by the profile loader. Built-in profiles are the same format, just shipped as defaults.

### Settings Screen: ModalScreen vs Separate Screen

**Recommendation: ModalScreen.** Users should see their conversation in the background while adjusting settings. ModalScreen provides this naturally with a semi-transparent overlay. Use `dismiss()` with a callback to apply changes when the user closes the settings screen.

---

## Sources

### Configuration Systems
- [Python tomllib stdlib module](https://docs.python.org/3/library/tomllib.html) -- Built-in TOML reading since Python 3.11 (HIGH confidence, official docs)
- [platformdirs API](https://platformdirs.readthedocs.io/en/latest/api.html) -- Platform-specific config/data directories (HIGH confidence, official docs)
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) -- Settings management with TOML support (HIGH confidence, official docs)
- [Python and TOML: Read, Write, and Configure](https://realpython.com/python-toml/) -- TOML configuration patterns (MEDIUM confidence)
- [Poetry Configuration](https://python-poetry.org/docs/configuration/) -- XDG config pattern example (MEDIUM confidence)

### Printer Control Codes
- [Epson ESC/P Reference Manual (1997)](https://files.support.epson.com/pdf/general/escp2ref.pdf) -- Complete ESC/P and ESC/P2 command reference (HIGH confidence, official Epson docs)
- [IBM PPDS and Epson ESC/P Control Codes](https://www.ibm.com/support/pages/list-ibm-ppds-and-epson-escp-control-codes-and-escape-sequences) -- IBM Proprinter control code reference (HIGH confidence, official IBM docs)
- [HP PCL5 Commands Reference](https://people.wou.edu/~soukupm/pcl_commands.htm) -- PCL5 escape sequences for HP printers (MEDIUM confidence)
- [python-escp library](https://github.com/yackx/python-escp) -- ESC/P printer control Python library, 9-pin reference (LOW confidence, small project)
- [ESC/P Wikipedia](https://en.wikipedia.org/wiki/ESC/P) -- ESC/P protocol overview (MEDIUM confidence)
- [Juki 6100 Operation Manual](http://www.bitsavers.org/pdf/juki/Juki_6100_Operation_Manual_Sep83.pdf) -- Juki daisywheel printer ESC codes (HIGH confidence, original manual)

### Multi-LLM Integration
- [OpenAI Python Library](https://github.com/openai/openai-python) -- Official Python library with async streaming (HIGH confidence, official)
- [OpenRouter API Documentation](https://openrouter.ai/docs/api/reference/overview) -- OpenAI-compatible API reference (HIGH confidence, official docs)
- [OpenRouter Streaming Documentation](https://openrouter.ai/docs/api/reference/streaming) -- SSE streaming for OpenRouter (HIGH confidence, official docs)
- [OpenRouter Quickstart](https://openrouter.ai/docs/quickstart) -- Shows OpenAI library compatibility (HIGH confidence, official docs)
- [LiteLLM Documentation](https://docs.litellm.ai/) -- Evaluated and rejected for this project (MEDIUM confidence)

### TUI Settings
- [Textual Screens Guide](https://textual.textualize.io/guide/screens/) -- ModalScreen, push_screen, dismiss (HIGH confidence, official docs)
- [Textual Widget Gallery](https://textual.textualize.io/widget_gallery/) -- Switch, Select, RadioSet, Button, Input widgets (HIGH confidence, official docs)
- [Creating Modal Dialogs in Textual](https://www.blog.pythonlibrary.org/2024/02/06/creating-a-modal-dialog-for-your-tuis-in-textual/) -- Modal settings dialog patterns (MEDIUM confidence)

### Typewriter Mode
- [Python tty module](https://docs.python.org/3/library/tty.html) -- Terminal raw/cbreak mode (HIGH confidence, official docs)

---
*Feature research for: Claude Teletype v1.2 -- Configuration, Printer Profiles, Multi-LLM, Settings UI, Typewriter Mode*
*Researched: 2026-02-17*
