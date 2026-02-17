# Architecture Research: v1.2 Integration (Config, Printer Profiles, Multi-LLM, Settings UI, Typewriter Mode)

**Domain:** Configuration system, printer profiles, multi-LLM backends, TUI settings, typewriter mode for existing Python CLI/TUI
**Researched:** 2026-02-17
**Confidence:** HIGH (existing codebase fully understood; technologies verified against official docs)

## Executive Summary

v1.2 adds five features that thread through the existing architecture in different ways. The key insight is that most of these features converge on a single integration point: the startup flow in `cli.py` and the `TeletypeApp.__init__` constructor. A new `config.py` module loads a TOML config file and produces a typed settings dataclass. That dataclass replaces the scattered CLI arguments currently threaded through constructors. Printer profiles replace the hardcoded `JukiPrinterDriver` decorator pattern with a generic `ProfilePrinterDriver` that wraps any inner driver with profile-defined ESC sequences. Multi-LLM backends introduce an `LLMBackend` protocol with two implementations: the existing `ClaudeCodeBackend` (wrapping `bridge.py`) and a new `OpenAIBackend` (using the `openai` SDK with configurable `base_url` for both OpenAI and OpenRouter). The TUI settings page is a `ModalScreen` pushed via keyboard shortcut. Typewriter mode is a flag on `TeletypeApp` that bypasses the LLM entirely.

None of these changes require modifying the core pipeline (pacer.py, output.py, wordwrap.py). The fan-out architecture remains untouched. The changes are concentrated in: (1) a new config layer, (2) a new LLM abstraction layer, (3) printer profile data, (4) TUI screen additions, and (5) wiring changes in cli.py and tui.py.

## Current Architecture (As-Built, v1.1)

```
[User Input]
    |
    v
[cli.py] ----prompt----> [bridge.py] --spawn--> claude -p "prompt" --output-format stream-json
    |                         |
    |                    yields str | StreamResult
    |                         |
    v                         v
[tui.py]              [pacer.py] --char-by-char--> [output.py] --fan-out--> destinations
                                                        |
                                        +---------------+---------------+
                                        |               |               |
                                   [WordWrapper    [printer_write   [bell/transcript]
                                    -> Log.write]   -> WordWrapper
                                                    -> driver.write]
```

### Key Architecture Properties

1. **bridge.py** is the sole LLM interface. It spawns `claude` CLI, parses NDJSON, yields `str | StreamResult`.
2. **printer.py** has a `PrinterDriver` protocol and a `JukiPrinterDriver` decorator that wraps any driver with Juki-specific ESC codes.
3. **cli.py** is the wiring layer. It parses CLI args, discovers printers, creates the TUI app with all options threaded through constructor params.
4. **tui.py** holds runtime state (`_session_id`, `_turn_count`, `_proc_holder`) and wires the streaming pipeline per-turn in `stream_response`.
5. **output.py** `make_output_fn` is a pure fan-out multiplexer. It has no knowledge of what it fans out to.
6. **All configuration is via CLI flags.** No config file. No saved preferences.

## Proposed Architecture (v1.2)

### System Overview

```
                          [config.toml]
                               |
                               v
                          [config.py] -----> AppConfig dataclass
                               |
                    +----------+----------+
                    |                     |
                    v                     v
               [cli.py]             [tui.py]
                    |                  |  |
          +---------+------+           |  +---> [settings.py] (ModalScreen)
          |                |           |              |
          v                v           v              v
    [printer.py]     [backends.py]  [TeletypeApp]  [config.py] (save)
         |                |              |
         v                v              v
  [ProfilePrinterDriver]  [LLMBackend]  [pacer/output/wordwrap] (UNCHANGED)
         |                |
         v                v
  [profiles/*.toml]  [ClaudeCodeBackend | OpenAIBackend]
                          |                    |
                          v                    v
                     [bridge.py]         [openai SDK]
                     (UNCHANGED)         (AsyncOpenAI)
```

### New Modules

| Module | Purpose | Size (est.) | Dependencies |
|--------|---------|-------------|--------------|
| **config.py** | Load/save TOML config, AppConfig dataclass, defaults, validation | ~120 lines | tomllib (stdlib), tomli_w |
| **backends.py** | LLMBackend protocol, ClaudeCodeBackend, OpenAIBackend | ~200 lines | openai SDK, bridge.py |
| **settings.py** | TUI settings ModalScreen with tabbed panes | ~180 lines | textual, config.py |
| **profiles/** | Directory of TOML printer profile files | ~20 lines each | N/A (data files) |

### Modified Modules

| Module | What Changes | Lines (est.) |
|--------|-------------|--------------|
| **cli.py** | Load config at startup, pass AppConfig to TUI, add `--config` flag | ~30 modified |
| **tui.py** | Accept AppConfig, wire LLMBackend instead of bridge directly, add settings binding | ~40 modified |
| **printer.py** | Add `ProfilePrinterDriver` (replaces JukiPrinterDriver pattern), load profile from TOML | ~60 added |

### Unchanged Modules

| Module | Why |
|--------|-----|
| **bridge.py** | Wrapped by ClaudeCodeBackend, not modified directly |
| **pacer.py** | Character-level pacing. No knowledge of config or backends. |
| **output.py** | Fan-out multiplexer. Character-level. No change. |
| **wordwrap.py** | Stream word wrapper. Character-level. No change. |
| **audio.py** | Bell sound. No change. |
| **transcript.py** | File writer. No change. |
| **errors.py** | Error classification. Extended by backends.py, not modified. |
| **teletype.py** | Raw keyboard mode. Enhanced by typewriter mode in TUI, but teletype.py itself unchanged. |

## Component Design: config.py

### Config File Location

Use platform-appropriate XDG-style path:

```python
import os
from pathlib import Path

def config_dir() -> Path:
    """~/.config/claude-teletype/ on macOS and Linux."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "claude-teletype"
    return Path.home() / ".config" / "claude-teletype"

def config_path() -> Path:
    return config_dir() / "config.toml"
```

### AppConfig Dataclass

```python
from dataclasses import dataclass, field

@dataclass
class AppConfig:
    # LLM settings
    llm_backend: str = "claude-code"     # "claude-code" | "openai" | "openrouter"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"
    openrouter_api_key: str | None = None
    openrouter_model: str = "anthropic/claude-sonnet-4"

    # Pacing
    base_delay_ms: float = 75.0

    # Audio
    no_audio: bool = False

    # Printer
    printer_profile: str | None = None   # e.g., "juki-6100", "epson-lx300", "generic"
    printer_device: str | None = None    # /dev/usb/lp0 override
    paper_columns: int = 80              # A4 at 10 CPI

    # Transcript
    transcript_dir: str | None = None

    # Typewriter mode
    typewriter_mode: bool = False
```

### Why TOML (Not JSON, YAML, or INI)

| Format | Verdict |
|--------|---------|
| **TOML** | **USE THIS.** Human-readable, comments allowed, stdlib `tomllib` for reading (Python 3.12+ required anyway), `tomli_w` for writing. Already used for `pyproject.toml`. Familiar to Python developers. |
| JSON | No comments. Trailing commas break parsing. Not human-friendly for config. |
| YAML | Implicit typing creates gotchas (e.g., `no` becomes `False`). Extra dependency. |
| INI | No nested structures. No typed values. Too limited. |

### Config File Format

```toml
# ~/.config/claude-teletype/config.toml

[llm]
backend = "claude-code"    # "claude-code", "openai", "openrouter"
# openai_api_key = "sk-..."
# openai_model = "gpt-4o"
# openrouter_api_key = "sk-or-..."
# openrouter_model = "anthropic/claude-sonnet-4"

[pacing]
base_delay_ms = 75.0

[audio]
enabled = true

[printer]
profile = "juki-6100"     # see profiles/ directory
# device = "/dev/usb/lp0"
paper_columns = 80

[transcript]
# dir = "./transcripts"
```

### Load/Save Pattern

```python
import tomllib
import tomli_w

def load_config() -> AppConfig:
    """Load config from TOML file, falling back to defaults."""
    path = config_path()
    if not path.exists():
        return AppConfig()
    with open(path, "rb") as f:
        data = tomllib.load(f)
    # Map nested TOML sections to flat dataclass fields
    return AppConfig(
        llm_backend=data.get("llm", {}).get("backend", "claude-code"),
        openai_api_key=data.get("llm", {}).get("openai_api_key"),
        # ... etc
    )

def save_config(config: AppConfig) -> None:
    """Save config to TOML file."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "llm": {"backend": config.llm_backend},
        "pacing": {"base_delay_ms": config.base_delay_ms},
        # ... etc
    }
    with open(path, "wb") as f:
        tomli_w.dump(data, f)
```

### CLI Override Pattern

CLI flags override config file values. Config file overrides hardcoded defaults:

```
Priority: CLI flags > config.toml > hardcoded defaults
```

In `cli.py`:
```python
config = load_config()
if delay != 75.0:  # User explicitly passed --delay
    config.base_delay_ms = delay
if device is not None:
    config.printer_device = device
```

## Component Design: backends.py (Multi-LLM)

### LLMBackend Protocol

```python
from collections.abc import AsyncIterator
from typing import Protocol

class LLMBackend(Protocol):
    """Interface for all LLM streaming backends."""

    async def stream(
        self,
        prompt: str,
        session_id: str | None = None,
        proc_holder: list | None = None,
    ) -> AsyncIterator[str | StreamResult]:
        """Yield text chunks, then a final StreamResult."""
        ...
```

This protocol matches the existing `stream_claude_response` signature exactly. The `ClaudeCodeBackend` is a thin wrapper.

### ClaudeCodeBackend

```python
from claude_teletype.bridge import StreamResult, stream_claude_response

class ClaudeCodeBackend:
    """Wraps existing bridge.py stream_claude_response."""

    async def stream(
        self,
        prompt: str,
        session_id: str | None = None,
        proc_holder: list | None = None,
    ) -> AsyncIterator[str | StreamResult]:
        async for item in stream_claude_response(prompt, session_id, proc_holder):
            yield item
```

Zero overhead. Bridge.py stays unchanged. The backend is just a protocol adapter.

### OpenAIBackend

```python
from openai import AsyncOpenAI

class OpenAIBackend:
    """Direct OpenAI API streaming via openai SDK."""

    def __init__(self, api_key: str, model: str = "gpt-4o", base_url: str | None = None):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._messages: list[dict] = []  # Conversation history (we manage it)

    async def stream(
        self,
        prompt: str,
        session_id: str | None = None,   # Ignored for OpenAI
        proc_holder: list | None = None,  # Ignored for OpenAI
    ) -> AsyncIterator[str | StreamResult]:
        self._messages.append({"role": "user", "content": prompt})

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=self._messages,
                stream=True,
            )

            full_response = []
            async for chunk in response:
                delta = chunk.choices[0].delta
                if delta.content:
                    full_response.append(delta.content)
                    yield delta.content

            # Store assistant response for conversation history
            self._messages.append({"role": "assistant", "content": "".join(full_response)})

            yield StreamResult(
                session_id=None,  # OpenAI has no session concept
                is_error=False,
                model=self._model,
            )

        except Exception as exc:
            yield StreamResult(
                session_id=None,
                is_error=True,
                error_message=str(exc),
            )
```

### OpenRouter via OpenAI SDK

OpenRouter is OpenAI-API-compatible. Use the same `OpenAIBackend` with a custom `base_url`:

```python
def make_backend(config: AppConfig) -> LLMBackend:
    """Factory: create the appropriate LLM backend from config."""
    if config.llm_backend == "claude-code":
        return ClaudeCodeBackend()
    elif config.llm_backend == "openai":
        return OpenAIBackend(
            api_key=config.openai_api_key,
            model=config.openai_model,
        )
    elif config.llm_backend == "openrouter":
        return OpenAIBackend(
            api_key=config.openrouter_api_key,
            model=config.openrouter_model,
            base_url="https://openrouter.ai/api/v1",
        )
```

This is confirmed to work because OpenRouter explicitly documents OpenAI SDK compatibility with `base_url="https://openrouter.ai/api/v1"` (HIGH confidence, official OpenRouter docs).

### Key Difference: Session Management

| Backend | Session Model | Who Manages History |
|---------|---------------|---------------------|
| **Claude Code** | `--resume <session_id>`, Claude manages history in `~/.claude/sessions/` | Claude Code CLI |
| **OpenAI / OpenRouter** | No sessions. Conversation history sent in every request. | Our `OpenAIBackend._messages` list |

This means:
- `ClaudeCodeBackend` is stateless (passes session_id to CLI, Claude manages context).
- `OpenAIBackend` is stateful (holds `_messages` list in memory, grows each turn).
- `StreamResult.session_id` is `None` for OpenAI backends (no resume capability).
- Context window management for OpenAI backends is deferred (future: implement truncation when messages exceed model's context window).

### proc_holder Consideration

The `proc_holder` pattern exists so the TUI can kill the Claude Code subprocess on cancel. For `OpenAIBackend`, there is no subprocess -- cancellation is handled by the Textual worker's `cancel()` which raises `asyncio.CancelledError` in the async generator. The `httpx` client used by the `openai` SDK handles cancellation gracefully when the task is cancelled.

## Component Design: Printer Profiles

### Profile as TOML Data Files

Replace the hardcoded `JukiPrinterDriver` class with a data-driven `ProfilePrinterDriver` that loads ESC sequences from TOML profiles.

Profile location: `~/.config/claude-teletype/profiles/` and bundled defaults in the package.

### Profile Format

```toml
# profiles/juki-6100.toml
[profile]
name = "Juki 6100 Daisywheel"
type = "daisywheel"
pins = 0  # Not applicable for daisywheel

[init]
# Sent once at startup. Hex-encoded escape sequences.
reset = "1b1a49"              # ESC SUB I - full reset
line_spacing = "1b1e09"       # ESC RS 9 - 1/6" line spacing
fixed_pitch = "1b51"          # ESC Q - disable proportional spacing
sequence = ["reset", "line_spacing", "fixed_pitch"]

[newline]
# How bare \n is handled
cr_lf = true                  # Convert \n to \r\n
reinit_after_newline = ["line_spacing", "fixed_pitch"]  # Re-send after each newline (CUPS job boundary)

[close]
form_feed = true              # Send FF on close

[paper]
columns = 80                  # Printable width at default pitch
```

```toml
# profiles/epson-lx300.toml
[profile]
name = "Epson LX-300+ (9-pin ESC/P)"
type = "dot-matrix"
pins = 9

[init]
reset = "1b40"                # ESC @ - initialize printer
line_spacing = "1b32"         # ESC 2 - 1/6" line spacing
draft_mode = "1b78 00"        # ESC x 0 - draft quality
pitch_10cpi = "1b50"          # ESC P - 10 CPI pica
sequence = ["reset", "line_spacing", "draft_mode", "pitch_10cpi"]

[newline]
cr_lf = false                 # ESC/P printers handle LF correctly

[close]
form_feed = true

[paper]
columns = 80
```

```toml
# profiles/generic.toml
[profile]
name = "Generic Printer"
type = "generic"

[init]
sequence = []                 # No init codes

[newline]
cr_lf = false

[close]
form_feed = false

[paper]
columns = 80
```

### ProfilePrinterDriver

```python
class ProfilePrinterDriver:
    """Data-driven printer driver that applies ESC sequences from a TOML profile.

    Replaces JukiPrinterDriver. Wraps any inner PrinterDriver.
    """

    def __init__(self, inner: PrinterDriver, profile: PrinterProfile) -> None:
        self._inner = inner
        self._profile = profile
        self._initialized = False

    def _send_raw(self, hex_codes: list[str]) -> None:
        """Send raw bytes from hex-encoded strings."""
        for hex_str in hex_codes:
            data = bytes.fromhex(hex_str.replace(" ", ""))
            for b in data:
                self._inner.write(chr(b))

    def _ensure_init(self) -> None:
        if not self._initialized:
            self._initialized = True
            init_codes = [self._profile.init_codes[name]
                         for name in self._profile.init_sequence
                         if name in self._profile.init_codes]
            self._send_raw(init_codes)

    @property
    def is_connected(self) -> bool:
        return self._inner.is_connected

    def write(self, char: str) -> None:
        if not self._inner.is_connected:
            return
        self._ensure_init()
        if char == "\n":
            if self._profile.cr_lf:
                self._inner.write("\r")
            self._inner.write("\n")
            if self._profile.reinit_after_newline:
                reinit_codes = [self._profile.init_codes[name]
                               for name in self._profile.reinit_after_newline
                               if name in self._profile.init_codes]
                self._send_raw(reinit_codes)
        else:
            self._inner.write(char)

    def close(self) -> None:
        if self._initialized and self._inner.is_connected and self._profile.form_feed_on_close:
            self._inner.write("\f")
        self._inner.close()
```

### PrinterProfile Dataclass

```python
@dataclass
class PrinterProfile:
    name: str
    printer_type: str                        # "daisywheel", "dot-matrix", "thermal", "generic"
    init_codes: dict[str, str] = field(default_factory=dict)   # name -> hex string
    init_sequence: list[str] = field(default_factory=list)     # ordered list of init code names
    cr_lf: bool = False
    reinit_after_newline: list[str] = field(default_factory=list)
    form_feed_on_close: bool = False
    columns: int = 80
```

### Migration from JukiPrinterDriver

The existing `JukiPrinterDriver` becomes the `juki-6100.toml` profile. The `--juki` flag in cli.py becomes `--profile juki-6100`. For backward compatibility:

```python
if juki:
    config.printer_profile = "juki-6100"  # Legacy flag maps to profile
```

### Profile Discovery

```python
def discover_profiles() -> list[str]:
    """List available printer profiles (bundled + user-defined)."""
    bundled = Path(__file__).parent / "profiles"
    user = config_dir() / "profiles"
    profiles = []
    for d in [bundled, user]:
        if d.exists():
            for f in sorted(d.glob("*.toml")):
                profiles.append(f.stem)
    return profiles
```

Bundled profiles ship in `src/claude_teletype/profiles/`. Users can add custom profiles in `~/.config/claude-teletype/profiles/`.

## Component Design: TUI Settings (settings.py)

### ModalScreen with TabbedContent

```python
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Select, Static, Switch, TabbedContent, TabPane

class SettingsScreen(ModalScreen[AppConfig | None]):
    """Settings modal with tabs for LLM, Printer, and Pacing."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config

    def compose(self) -> ComposeResult:
        with TabbedContent():
            with TabPane("LLM", id="llm-tab"):
                yield Label("Backend")
                yield Select(
                    [("Claude Code CLI", "claude-code"),
                     ("OpenAI", "openai"),
                     ("OpenRouter", "openrouter")],
                    value=self._config.llm_backend,
                    id="backend-select",
                )
                # ... model selection, API key inputs
            with TabPane("Printer", id="printer-tab"):
                yield Label("Printer Profile")
                yield Select(
                    [(p, p) for p in discover_profiles()],
                    value=self._config.printer_profile or "generic",
                    id="profile-select",
                )
                # ... paper columns
            with TabPane("Pacing", id="pacing-tab"):
                yield Label("Base Delay (ms)")
                # ... delay slider or input
                yield Label("Audio")
                yield Switch(value=not self._config.no_audio, id="audio-switch")
        yield Button("Save", variant="primary", id="save-btn")
        yield Button("Cancel", id="cancel-btn")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            # Read widget values into config
            updated = self._build_config_from_widgets()
            self.dismiss(updated)
        elif event.button.id == "cancel-btn":
            self.dismiss(None)
```

### TUI Integration

In `tui.py`, add a binding and handler:

```python
BINDINGS = [
    Binding("ctrl+d", "quit", "Quit"),
    Binding("escape", "cancel_stream", "Cancel", show=False),
    Binding("ctrl+comma", "settings", "Settings"),  # ctrl+, is common for settings
]

def action_settings(self) -> None:
    """Open settings modal."""
    self.push_screen(SettingsScreen(self._config), callback=self._apply_settings)

def _apply_settings(self, result: AppConfig | None) -> None:
    """Apply settings returned from modal."""
    if result is not None:
        self._config = result
        save_config(result)
        # Rebuild backend if LLM changed
        self._backend = make_backend(result)
        # Update pacing
        self.base_delay_ms = result.base_delay_ms
```

### Settings Screen Data Flow

```
[User presses Ctrl+,]
    |
    v
[TeletypeApp.action_settings()]
    |-- push_screen(SettingsScreen(self._config))
    |
    v
[SettingsScreen renders with current config values]
    |
    v
[User changes settings, clicks Save]
    |
    v
[SettingsScreen.dismiss(updated_config)]
    |
    v
[TeletypeApp._apply_settings(updated_config)]
    |-- save_config(updated_config)    -> writes TOML
    |-- self._backend = make_backend() -> swaps LLM backend
    |-- self.base_delay_ms = ...       -> updates pacing
```

## Component Design: Typewriter Mode

### What It Is

A mode where the TUI accepts keyboard input and sends it directly to the printer/screen with pacing and sound -- no LLM involved. It recreates a pure typewriter experience.

### How It Differs from teletype.py

| Feature | `teletype.py` (existing) | Typewriter Mode (new) |
|---------|-------------------------|-----------------------|
| Interface | Raw terminal, no TUI | Full TUI with Log widget |
| Audio | No | Yes (bell on newline) |
| Pacing | Instant | Character pacing with delays |
| Word wrap | No | Yes (via WordWrapper) |
| Requires printer | Yes (exits if none) | No (works in simulator) |

### Integration into TUI

Typewriter mode is activated via `--typewriter` CLI flag or toggled in TUI settings. When active:

1. `on_input_submitted` does NOT call `stream_response` (no LLM).
2. Instead, it routes the typed text through the pacing/output pipeline directly.
3. User types in the Input widget, presses Enter, and the text appears in the Log with typewriter pacing and goes to the printer.

```python
# In tui.py:
async def on_input_submitted(self, event: Input.Submitted) -> None:
    prompt = event.value.strip()
    if not prompt:
        return

    event.input.clear()
    self._prev_input_value = ""

    if self._config.typewriter_mode:
        self._type_to_output(prompt)
    else:
        # ... existing LLM flow
        self.stream_response(prompt)

@work(exclusive=True)
async def _type_to_output(self, text: str) -> None:
    """Typewriter mode: pace user text to all destinations."""
    # Build output pipeline (same as stream_response but no LLM)
    log = self.query_one("#output", Log)
    # ... wire destinations ...
    await pace_characters(text + "\n", base_delay_ms=self.base_delay_ms, output_fn=output_fn)
```

## Updated Data Flow: v1.2

### Startup Flow

```
[User runs: claude-teletype]
    |
    v
[cli.py: chat()]
    |-- load_config() -> AppConfig from ~/.config/claude-teletype/config.toml
    |-- Apply CLI flag overrides (--delay, --device, --profile, etc.)
    |-- check_claude_installed() (ONLY if backend is claude-code)
    |-- discover_printer(config)
    |-- If profile specified: wrap driver in ProfilePrinterDriver
    |-- make_backend(config) -> LLMBackend
    |
    v
[TeletypeApp(config=config, backend=backend, printer=driver)]
    |-- Stores config, backend, printer
    |-- on_mount: initialize transcript, printer_write
```

### Streaming Turn (LLM Mode)

```
[User types prompt, presses Enter]
    |
    v
[tui.py: on_input_submitted(prompt)]
    |-- typewriter_mode? NO -> stream_response(prompt)
    |
    v
[tui.py: stream_response(prompt)]
    |-- async for item in self._backend.stream(prompt, session_id, proc_holder):
    |       if isinstance(item, StreamResult): update session/status
    |       else: await pace_characters(item, ..., output_fn)
    |
    v
[pacer.py] -> [output.py fan-out] -> [WordWrapper->Log, printer_write, bell, transcript]
```

### Streaming Turn (Typewriter Mode)

```
[User types text, presses Enter]
    |
    v
[tui.py: on_input_submitted(text)]
    |-- typewriter_mode? YES -> _type_to_output(text)
    |
    v
[tui.py: _type_to_output(text)]
    |-- await pace_characters(text + "\n", ..., output_fn)
    |
    v
[pacer.py] -> [output.py fan-out] -> [WordWrapper->Log, printer_write, bell, transcript]
```

Note: the pipeline from pacer onwards is IDENTICAL in both modes. The only difference is the source of text (LLM vs user keyboard).

### Settings Change Flow

```
[User presses Ctrl+, in TUI]
    |
    v
[SettingsScreen modal opens]
    |-- Shows current config values in form widgets
    |-- User edits values
    |-- Clicks Save
    |
    v
[TeletypeApp._apply_settings(new_config)]
    |-- save_config(new_config) -> write TOML to disk
    |-- self._backend = make_backend(new_config) -> swap backend
    |-- self.base_delay_ms = new_config.base_delay_ms
    |-- NOTE: printer profile change requires app restart (profile wraps driver at startup)
```

## Component Boundary Summary

### Integration Points

| New Feature | Touches | Integration Point |
|-------------|---------|-------------------|
| **Config** | cli.py, tui.py | Replaces scattered CLI args with single AppConfig |
| **Printer Profiles** | printer.py, cli.py | ProfilePrinterDriver wraps any driver at startup |
| **Multi-LLM** | tui.py (stream_response) | LLMBackend.stream() replaces direct bridge call |
| **Settings UI** | tui.py | ModalScreen pushed on Ctrl+,, returns updated AppConfig |
| **Typewriter Mode** | tui.py (on_input_submitted) | Conditional: bypass LLM, route text directly to output pipeline |

### Dependency Graph Between New Features

```
config.py (FOUNDATION - build first)
    |
    +---> printer profiles (depends on config for profile path)
    |
    +---> backends.py (depends on config for API keys, model selection)
    |
    +---> tui.py wiring (depends on config, backends, profiles)
              |
              +---> settings.py (depends on config, profile discovery, backend factory)
              |
              +---> typewriter mode (depends on config flag, no other new deps)
```

## Patterns to Follow

### Pattern 1: Config as Single Source of Truth

**What:** All runtime settings flow through a single `AppConfig` dataclass. CLI flags, config file, and settings UI all produce/modify an AppConfig.

**Why:** Eliminates the current pattern of threading 6+ constructor parameters through cli.py -> TeletypeApp. Makes adding new settings trivial (add field to dataclass, add to TOML schema, add to settings UI).

**Example:**
```python
# Before (v1.1): scattered params
TeletypeApp(base_delay_ms=delay, printer=printer, no_audio=no_audio,
            transcript_dir=transcript_dir, resume_session_id=resume)

# After (v1.2): single config
TeletypeApp(config=config, backend=backend, printer=driver,
            resume_session_id=resume)
```

### Pattern 2: Backend Protocol with Factory

**What:** `LLMBackend` protocol defines the streaming interface. A `make_backend(config)` factory creates the right implementation. TUI code only knows about the protocol.

**Why:** Swapping backends at runtime (from settings UI) becomes trivial. Testing is easier (mock backend). Adding new backends later (Gemini, local models) requires no TUI changes.

**Example:**
```python
# TUI only knows the protocol
self._backend: LLMBackend = make_backend(config)
async for item in self._backend.stream(prompt, session_id, proc_holder):
    ...
```

### Pattern 3: Decorator Pattern for Printer Profiles

**What:** `ProfilePrinterDriver` wraps any inner `PrinterDriver` and applies ESC sequences from a data file. Same pattern as existing `JukiPrinterDriver` but data-driven.

**Why:** Adding a new printer requires only a TOML file, not code. The Juki-specific logic currently hardcoded in Python becomes just another profile file.

### Pattern 4: Modal Screen for Settings

**What:** Settings is a `ModalScreen` pushed onto the Textual screen stack. It receives current config, returns updated config (or None on cancel).

**Why:** Clean separation. Settings screen does not directly mutate app state. The callback pattern (`dismiss(result)`) lets the app decide what to apply. Textual's `ModalScreen` blocks interaction with the main screen automatically.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Global Mutable Config

**What:** Storing config in a module-level global that any module can read/modify.

**Why bad:** Invisible dependencies. Testing nightmare. Race conditions if settings UI saves while streaming is active.

**Instead:** Pass AppConfig explicitly. TUI holds the authoritative copy. Config file is the persistence layer.

### Anti-Pattern 2: Rewriting bridge.py for Multi-LLM

**What:** Modifying `bridge.py` to conditionally call OpenAI or Claude Code depending on config.

**Why bad:** bridge.py is the Claude Code subprocess bridge. It has one job. Mixing in OpenAI HTTP calls violates single responsibility and makes testing harder.

**Instead:** Create a separate `backends.py` with the `LLMBackend` protocol. `ClaudeCodeBackend` wraps bridge.py. `OpenAIBackend` is independent.

### Anti-Pattern 3: Client-Side Context Management for Claude Code

**What:** Keeping a messages list for Claude Code like we do for OpenAI, to "unify" the interfaces.

**Why bad:** Claude Code already manages conversation history via `--resume`. Duplicating it wastes tokens and risks inconsistency. Claude Code has auto-compact; our manual truncation would be worse.

**Instead:** Let each backend manage conversation state its own way. Claude Code uses `session_id`. OpenAI uses `_messages` list.

### Anti-Pattern 4: Embedding ESC Sequences in Python Code

**What:** Hardcoding printer escape sequences as class constants (like the current `JukiPrinterDriver.RESET`, `LINE_SPACING`, `FIXED_PITCH`).

**Why bad:** Adding a new printer requires modifying Python source, writing tests for the new class, and a code review. Configuration data should be data, not code.

**Instead:** TOML profile files with hex-encoded escape sequences. New printer = new TOML file.

### Anti-Pattern 5: Hot-Swapping Printer Profiles

**What:** Allowing the settings UI to change the printer profile while the app is running and immediately applying it.

**Why bad:** The `ProfilePrinterDriver` sends init sequences at first write. Sending a different printer's init codes to an already-initialized printer can leave it in an inconsistent state. Some ESC sequences are irreversible without a full reset.

**Instead:** Printer profile changes require app restart. The settings UI should save the new profile to config and display "Restart to apply printer changes."

## Recommended Build Order

The dependency chain dictates this order:

```
Phase A: Configuration System (FOUNDATION)
    config.py + config.toml schema + CLI wiring
    WHY FIRST: Every other feature depends on config for settings storage.

Phase B: Printer Profiles
    ProfilePrinterDriver + PrinterProfile dataclass + TOML profiles
    WHY SECOND: Self-contained. Only depends on config for profile path discovery.
    Validates the TOML profile loading pattern before using it elsewhere.
    Immediately useful: replaces hardcoded Juki code with data.

Phase C: Multi-LLM Backends
    LLMBackend protocol + ClaudeCodeBackend + OpenAIBackend + factory
    WHY THIRD: Depends on config for API keys. Independent of printer profiles.
    OpenAI streaming is a well-understood pattern (official SDK).
    Biggest value-add for users who want to use different models.

Phase D: TUI Settings + Typewriter Mode + Bug Fixes
    SettingsScreen + typewriter mode + --no-tui StreamResult fix
    WHY LAST: Depends on config (to display/edit), backends (to list options),
    and profiles (to list printers). Settings UI is the "glue" that exposes
    all previous features to the user. Typewriter mode is simple wiring.
    Bug fixes are low-dependency cleanup.
```

**Rationale for this ordering:**
- Config is the foundation everything builds on. Without it, backends and profiles have nowhere to store settings.
- Printer profiles are the smallest new subsystem. Good for validating the TOML-as-data pattern.
- Multi-LLM is the highest-value feature but has the most external dependencies (openai SDK). Build it after config is proven.
- Settings UI is the integration layer. It needs everything else to exist first.
- Typewriter mode is trivially simple once the TUI wiring exists. Bundle it with the final phase.

## Sources

- [Python tomllib documentation](https://docs.python.org/3/library/tomllib.html) -- HIGH confidence. Stdlib TOML parser, read-only, Python 3.11+.
- [tomli-w on PyPI](https://pypi.org/project/tomli-w/) -- HIGH confidence. TOML writer companion to tomllib.
- [OpenAI Python SDK (GitHub)](https://github.com/openai/openai-python) -- HIGH confidence. Official SDK with AsyncOpenAI, stream=True, httpx backend.
- [OpenRouter Quickstart Guide](https://openrouter.ai/docs/quickstart) -- HIGH confidence. Official docs showing `base_url="https://openrouter.ai/api/v1"` with OpenAI SDK.
- [OpenRouter Streaming Docs](https://openrouter.ai/docs/api/reference/streaming) -- HIGH confidence. SSE streaming format, `data: [DONE]` sentinel.
- [OpenRouter OpenAI SDK Integration](https://openrouter.ai/docs/guides/community/openai-sdk) -- HIGH confidence. Official guide for using OpenAI Python SDK with OpenRouter.
- [Textual Screens Guide](https://textual.textualize.io/guide/screens/) -- HIGH confidence. ModalScreen, push_screen, dismiss, callback pattern.
- [Textual TabbedContent Widget](https://textual.textualize.io/widgets/tabbed_content/) -- HIGH confidence. TabPane composition, programmatic switching.
- [Textual Select Widget](https://textual.textualize.io/widgets/select/) -- HIGH confidence. Dropdown selection for settings.
- [Textual Switch Widget](https://textual.textualize.io/widgets/switch/) -- HIGH confidence. Boolean toggle for audio enable/disable.
- [Epson ESC/P2 and FX Commands Reference](https://support2.epson.net/manuals/english/page/epl_n4000plus/ref_g/APCOM_3.HTM) -- HIGH confidence. Official Epson reference for ESC/P2 commands.
- [IBM PPDS and Epson ESC/P Control Codes](https://www.ibm.com/support/pages/list-ibm-ppds-and-epson-escp-control-codes-and-escape-sequences) -- HIGH confidence. Official IBM reference.
- [Juki 6100 Operation Manual (Archive.org)](https://archive.org/stream/bitsavers_jukiJuki61p83_7056599/Juki_6100_Operation_Manual_Sep83_djvu.txt) -- MEDIUM confidence. Scanned original manual from 1983.
- [python-escp (GitHub)](https://github.com/yackx/python-escp) -- MEDIUM confidence. Third-party ESC/P library, GPL-3.0, limited testing scope.
- [python-escpos (GitHub)](https://github.com/python-escpos/python-escpos) -- MEDIUM confidence. ESC/POS (thermal receipt), not ESC/P (dot matrix). Referenced for contrast.
- [Epson ESC/P Reference Manual (PDF)](https://files.support.epson.com/pdf/general/escp2ref.pdf) -- HIGH confidence. Official Epson ESC/P2 reference manual from 1997.
- [pydantic-settings Configuration Files](https://deepwiki.com/pydantic/pydantic-settings/3.2-configuration-files) -- MEDIUM confidence. Alternative to manual TOML parsing, considered but rejected (too heavy for this use case).

---
*Architecture research for: Claude Teletype v1.2 integration (config, printer profiles, multi-LLM, settings UI, typewriter mode)*
*Researched: 2026-02-17*
