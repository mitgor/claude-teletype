# Technology Stack: v1.2 Configuration, Profiles, Multi-LLM, Settings, Typewriter

**Project:** Claude Teletype v1.2
**Researched:** 2026-02-17
**Focus:** Config system, printer profiles, multi-LLM backends, TUI settings, typewriter mode
**Overall Confidence:** HIGH

---

## Executive Summary

v1.2 adds **3 new dependencies** (`openai`, `tomli-w`, `platformdirs`) and **0 library swaps**. The OpenAI Python SDK is the single largest addition -- it provides streaming for both OpenAI and OpenRouter APIs via a `base_url` override. Configuration uses Python 3.12's built-in `tomllib` for reading (zero-dep) plus `tomli-w` for writing. `platformdirs` provides cross-platform XDG-compliant config file location. Printer profiles use raw bytes (no library needed -- ESC/P and PCL are byte-level protocols). The TUI settings panel uses Textual's existing `ModalScreen`, `Select`, `Switch`, and `Input` widgets.

---

## Recommended Stack Additions

### 1. Multi-LLM Backend: `openai` Python SDK

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| openai | >=2.21.0 | Streaming chat completions for OpenAI + OpenRouter | Official SDK, both providers use identical API. OpenRouter works via `base_url="https://openrouter.ai/api/v1"`. Single dependency handles both backends. |

**Why the official SDK over raw httpx+SSE:** The openai SDK handles SSE parsing, delta extraction, error typing, retry logic, and rate-limit headers. Building this from httpx-sse would require ~200 lines of parsing code to replicate what the SDK does in one line. The SDK weighs in with transitive dependencies (httpx, pydantic, anyio, jiter, tqdm, distro, sniffio), but httpx overlaps with what we would need anyway, and pydantic is useful for config validation down the road.

**Why NOT the `anthropic` Python SDK:** The project wraps Claude Code CLI (subprocess), not the Anthropic API directly. Adding the anthropic SDK would create a parallel streaming/error/auth code path that diverges from the CLI wrapper. Claude Code CLI remains the primary backend for Claude models.

**Integration pattern with existing bridge:**

```python
# New: llm_backends.py (parallel to bridge.py)
from openai import AsyncOpenAI

async def stream_openai_response(
    prompt: str,
    messages: list[dict],
    model: str = "gpt-4o",
    base_url: str | None = None,  # None = OpenAI, URL = OpenRouter
    api_key: str | None = None,
) -> AsyncIterator[str]:
    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    stream = await client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
    )
    async for chunk in stream:
        if chunk.choices[0].delta.content is not None:
            yield chunk.choices[0].delta.content
```

**OpenRouter usage is identical -- just change base_url:**

```python
# OpenAI direct
client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

# OpenRouter (same SDK, different base_url)
client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)
```

**Key difference from Claude Code CLI bridge:** OpenAI/OpenRouter backends manage their own message history (list of dicts) since there is no `--resume` equivalent. The bridge.py `stream_claude_response()` delegates history to Claude Code; the new `stream_openai_response()` receives the full message list.

**Confidence:** HIGH -- openai SDK v2.21.0 verified on PyPI (released 2026-02-14). OpenRouter OpenAI-compatible endpoint verified in official docs.

### 2. Configuration Reading: `tomllib` (stdlib, Python 3.12+)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| tomllib | stdlib (3.12+) | Parse TOML config files | Zero-dependency, ships with Python 3.12+. TOML is the natural format for a Python project already using pyproject.toml. |

**Why TOML over YAML/JSON/INI:**
- TOML: Human-readable, comment-friendly, typed values (booleans, integers, arrays), already the Python ecosystem standard (pyproject.toml). Users are familiar.
- YAML: Requires pyyaml dependency, has surprising gotchas (Norway problem, implicit type coercion), overkill for config.
- JSON: No comments, no trailing commas, hostile to hand-editing.
- INI: No nested structures, no typed values, would need manual parsing for printer profiles.

**Usage:**

```python
import tomllib
from pathlib import Path

def load_config(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)
```

**Confidence:** HIGH -- `tomllib` is in the Python 3.12 stdlib, documented at docs.python.org.

### 3. Configuration Writing: `tomli-w`

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| tomli-w | >=1.2.0 | Write TOML config files | Minimal (zero-dep) counterpart to stdlib tomllib. Needed because tomllib is read-only. Only 2 functions: `dump()` and `dumps()`. |

**Why tomli-w over tomlkit:** tomlkit is a full style-preserving TOML editor (useful for preserving comments during roundtrips), but it is heavier and more complex. For our use case -- writing config from a settings panel -- we generate fresh TOML from a dict, so style preservation is unnecessary. tomli-w is simpler and lighter.

**Usage:**

```python
import tomli_w

def save_config(config: dict, path: Path) -> None:
    with open(path, "wb") as f:
        tomli_w.dump(config, f)
```

**Confidence:** HIGH -- tomli-w v1.2.0 verified on PyPI (released 2025-01-15). Zero dependencies, requires Python >=3.9.

### 4. Config File Location: `platformdirs`

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| platformdirs | >=4.9.0 | Cross-platform config directory (XDG on Linux, ~/Library on macOS) | Standard solution for "where do config files go." Zero dependencies. Used by pip, black, ruff, virtualenv. |

**Why platformdirs over hardcoded paths:**
- macOS: `~/Library/Application Support/claude-teletype/config.toml`
- Linux: `~/.config/claude-teletype/config.toml` (XDG_CONFIG_HOME)
- Fallback: `~/.claude-teletype/config.toml`

Hardcoding `~/.config/` is wrong on macOS. Hardcoding `~/Library/` is wrong on Linux. platformdirs handles both correctly.

**Usage:**

```python
from platformdirs import user_config_dir
from pathlib import Path

config_dir = Path(user_config_dir("claude-teletype"))
config_path = config_dir / "config.toml"
```

**Confidence:** HIGH -- platformdirs v4.9.2 verified on PyPI (released 2026-02-16). Zero dependencies, requires Python >=3.10.

---

## Printer Profile System: Raw Bytes (No New Dependencies)

Printer control codes (ESC/P, PCL, Juki) are byte-level protocols. No library exists or is needed -- you send raw escape sequences to the device. The existing `JukiPrinterDriver` in `printer.py` already demonstrates this pattern.

### Control Code Reference

**ESC/P (Epson/IBM dot matrix -- Epson FX, LQ, IBM Proprinter):**

| Function | Bytes (hex) | Sequence | Notes |
|----------|-------------|----------|-------|
| Reset | `1B 40` | ESC @ | Full printer reset |
| Bold on | `1B 45` | ESC E | Emphasized printing |
| Bold off | `1B 46` | ESC F | Cancel emphasized |
| Italic on | `1B 34` | ESC 4 | |
| Italic off | `1B 35` | ESC 5 | |
| Condensed on | `0F` | SI | 17 CPI compressed |
| Condensed off | `12` | DC2 | Back to normal pitch |
| Line spacing 1/6" | `1B 32` | ESC 2 | 6 LPI (normal) |
| Line spacing 1/8" | `1B 30` | ESC 0 | 8 LPI (compact) |
| Form feed | `0C` | FF | |
| CR + LF | `0D 0A` | CR LF | Most dot matrix need explicit CR |

**PCL (HP LaserJet/DeskJet/inkjet):**

| Function | Sequence | Notes |
|----------|----------|-------|
| Reset | `1B 45` | Ec E |
| Line spacing 6 LPI | `1B 26 6C 36 44` | Ec&l6D |
| Line spacing 8 LPI | `1B 26 6C 38 44` | Ec&l8D |
| Orientation portrait | `1B 26 6C 30 4F` | Ec&l0O |
| Bold (stroke weight) | `1B 28 73 33 42` | Ec(s3B |
| Fixed pitch 10 CPI | `1B 28 73 31 30 48` | Ec(s10H |

**Juki 6100 (already implemented -- daisywheel, uses proprietary ESC codes):**

| Function | Bytes (hex) | Existing code |
|----------|-------------|---------------|
| Reset | `1B 1A 49` | `JukiPrinterDriver.RESET` |
| Line spacing 1/6" | `1B 1E 09` | `JukiPrinterDriver.LINE_SPACING` |
| Fixed pitch | `1B 51` | `JukiPrinterDriver.FIXED_PITCH` |

**Juki 9100 (NEC Spinwriter-compatible):** The Juki 9100 uses a superset of Juki 6100 codes with additional NEC Spinwriter compatibility. Key additions include proportional spacing control and print wheel selection. The exact codes need verification from the hardware manual -- flag for phase-specific research with the actual printer.

### Implementation Pattern: Profile-Based Driver

```python
@dataclass
class PrinterProfile:
    """Control code profile for a specific printer type."""
    name: str
    reset: bytes
    line_spacing_6lpi: bytes
    bold_on: bytes
    bold_off: bytes
    condensed_on: bytes
    condensed_off: bytes
    newline: bytes  # "\n" or "\r\n"
    form_feed: bytes
    columns: int  # printable width at default pitch

ESCP_PROFILE = PrinterProfile(
    name="escp",
    reset=b"\x1b@",
    line_spacing_6lpi=b"\x1b2",
    bold_on=b"\x1bE",
    bold_off=b"\x1bF",
    condensed_on=b"\x0f",
    condensed_off=b"\x12",
    newline=b"\r\n",
    form_feed=b"\x0c",
    columns=80,
)

JUKI_6100_PROFILE = PrinterProfile(
    name="juki6100",
    reset=b"\x1b\x1aI",
    line_spacing_6lpi=b"\x1b\x1e\x09",
    bold_on=b"",  # Juki 6100 daisywheel has no bold
    bold_off=b"",
    condensed_on=b"",
    condensed_off=b"",
    newline=b"\r\n",
    form_feed=b"\x0c",
    columns=80,
)
```

This replaces the current hardcoded `JukiPrinterDriver` with a generic `ProfiledPrinterDriver` that takes any `PrinterProfile`. The existing `JukiPrinterDriver` becomes a profile dict rather than a class.

**Confidence:** HIGH for ESC/P codes (verified against Epson official reference and IBM docs). MEDIUM for Juki 9100 (extrapolated from 6100, needs hardware verification). HIGH for PCL basics (verified against HP developer docs).

---

## TUI Settings Panel: Existing Textual Widgets (No New Dependencies)

Textual (now at v8.0.0, released 2026-02-16) already has every widget needed for a settings screen.

### Textual v8.0 Compatibility Note

The project currently pins `textual>=7.0.0`. Textual 8.0 has minor breaking changes:
- `Select.BLANK` renamed to `Select.NULL`
- `OptionList` separator changed from `Separator` to `None`

Neither of these affects the existing TUI (which uses `Log`, `Input`, `Header`, `Footer`, `Static`). The settings panel should target v8.0+ APIs. **Recommend updating pin to `textual>=8.0.0`.**

### Widget Inventory for Settings Screen

| Widget | Purpose | Already in Textual |
|--------|---------|-------------------|
| `ModalScreen` | Settings overlay on main screen | Yes |
| `Select` | Dropdown for printer profile, LLM backend | Yes |
| `Switch` | Toggle audio on/off, printer on/off | Yes |
| `Input` | Character delay (ms), API keys | Yes, with `type="number"` and `validators=[Number(min, max)]` |
| `RadioSet` / `RadioButton` | LLM provider selection | Yes |
| `TabbedContent` | Organize settings into tabs (General / Printer / LLM) | Yes |
| `Button` | Save / Cancel | Yes |
| `Label` / `Static` | Section headers, descriptions | Yes |

### Settings Screen Pattern

```python
from textual.screen import ModalScreen
from textual.widgets import Select, Switch, Input, Button, TabbedContent, TabPane

class SettingsScreen(ModalScreen[dict | None]):
    """Modal settings screen. Dismissed with config dict or None (cancel)."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with TabbedContent():
            with TabPane("General"):
                yield Label("Character delay (ms)")
                yield Input(value="75", type="number", id="delay")
                yield Label("Audio")
                yield Switch(value=True, id="audio")
            with TabPane("Printer"):
                yield Label("Printer profile")
                yield Select(
                    [("ESC/P (Epson/IBM)", "escp"),
                     ("Juki 6100", "juki6100"),
                     ("PCL (HP)", "pcl"),
                     ("None", "none")],
                    id="printer-profile",
                )
            with TabPane("LLM"):
                yield Label("Backend")
                yield Select(
                    [("Claude Code CLI", "claude"),
                     ("OpenAI", "openai"),
                     ("OpenRouter", "openrouter")],
                    id="llm-backend",
                )
        yield Button("Save", variant="primary", id="save")
        yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self.dismiss(self._collect_settings())
        else:
            self.dismiss(None)

    # Called from main app:
    # self.push_screen(SettingsScreen(), callback=self._apply_settings)
```

**Confidence:** HIGH -- ModalScreen dismiss/callback pattern verified in official Textual docs. Switch, Select, Input, TabbedContent all verified in widget gallery.

---

## Typewriter Mode Enhancements: No New Dependencies

The existing `teletype.py` handles raw keyboard-to-printer mode using `termios` and `tty` (stdlib). The "simple typewriter mode" for v1.2 enhances this with:

1. **Profile-aware init codes** -- send the active PrinterProfile's reset/line_spacing on startup instead of hardcoded Juki bytes
2. **Local echo to TUI** -- optionally mirror typed characters to a Textual Log widget instead of stderr
3. **Backspace handling** -- send BS (0x08) + space + BS for overstriking on impact printers

No new dependencies needed. The current `run_teletype()` function expands to accept a `PrinterProfile` instead of a `juki: bool` flag.

---

## Existing Stack Updates

| Technology | Current Pin | Recommended Pin | Reason |
|------------|-------------|-----------------|--------|
| textual | >=7.0.0 | >=8.0.0 | Use `Select.NULL` (v8 API), smooth scrolling. Minor migration: no impact on existing Log/Input/Header usage. |

All other existing dependencies remain unchanged.

---

## Complete Dependency Changes

### pyproject.toml diff

```toml
[project]
dependencies = [
    "typer>=0.23.0",
    "rich>=14.0.0",
    "textual>=8.0.0",        # Was >=7.0.0 (v8 has Select.NULL rename)
    "sounddevice>=0.5.0",
    "numpy>=1.26.0",
    "platformdirs>=4.9.0",   # NEW: cross-platform config directory
    "tomli-w>=1.2.0",        # NEW: TOML config writing (reading is stdlib tomllib)
]

[project.optional-dependencies]
usb = ["pyusb>=1.3.0"]
llm = ["openai>=2.21.0"]    # NEW: optional, for OpenAI/OpenRouter backends
```

**Key decision: `openai` is an optional dependency.** The core Claude Teletype experience uses Claude Code CLI (subprocess, no SDK). The openai SDK is only needed if the user wants OpenAI or OpenRouter as an alternative LLM backend. This keeps the default install lightweight and avoids pulling in httpx/pydantic/etc for users who only use Claude.

### Installation Commands

```bash
# Core (Claude Code CLI only, config system, printer profiles)
uv sync

# With OpenAI/OpenRouter support
uv sync --extra llm

# With USB printer support
uv sync --extra usb

# Everything
uv sync --extra llm --extra usb

# Dev
uv sync --group dev
```

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Config format | TOML (tomllib + tomli-w) | YAML (pyyaml) | Extra dependency, surprising type coercion gotchas, not the Python ecosystem standard |
| Config format | TOML | JSON | No comments, hostile to hand-editing |
| Config location | platformdirs | Hardcoded `~/.config/` | Wrong on macOS (should be `~/Library/Application Support/`) |
| Config location | platformdirs | `~/.claude-teletype/` | Non-standard, pollutes home directory |
| Multi-LLM SDK | openai (official) | httpx + httpx-sse (raw) | ~200 lines of SSE/delta parsing to replicate; SDK handles retries, rate limits, typing |
| Multi-LLM SDK | openai (official) | litellm | Massive dependency that wraps 100+ providers. Overkill for 2 providers (OpenAI + OpenRouter). |
| Multi-LLM SDK | openai (official) | anthropic SDK | Not needed -- Claude access is via CLI subprocess, not API. Adding anthropic SDK creates parallel code path. |
| TOML writer | tomli-w | tomlkit | tomlkit preserves comments/style on roundtrip. Unnecessary since we generate config fresh from settings dict. |
| Settings UI | Textual ModalScreen | Separate CLI command | Breaks flow. Settings should be accessible from within the TUI session. |
| Printer control codes | Raw bytes in dataclass profiles | python-escpos library | python-escpos targets POS/receipt printers (ESC/POS), not dot-matrix printers (ESC/P). Different protocol. Also adds dependency for something that is literally 10 bytes per profile. |

---

## What NOT to Add

| Library | Why Not |
|---------|---------|
| `pyyaml` | TOML is better for config (comments + types + Python standard). No YAML. |
| `python-escpos` | ESC/POS != ESC/P. Targets receipt printers, not dot-matrix. Wrong protocol. |
| `tomlkit` | Style-preserving roundtrip unnecessary. We generate config from dict. |
| `litellm` | 100+ provider wrapper. Overkill. We need exactly 2 providers. |
| `anthropic` | Claude access is via CLI. SDK would create parallel auth/streaming/error paths. |
| `pydantic` | Comes as transitive dep of openai, but do NOT use it for config validation. Keep config as plain dicts with manual validation. Avoids coupling. |
| `keyring` | API key storage. Premature -- environment variables are the standard for API keys. Users can use their OS keychain manually. |
| `python-dotenv` | .env file loading. Unnecessary -- users set env vars in their shell profile. Adding dotenv creates confusion about which env vars come from where. |

---

## Integration Points with Existing Code

### New Module: `config.py`

```python
"""Application configuration: load, save, defaults, file location."""
import tomllib
import tomli_w
from pathlib import Path
from platformdirs import user_config_dir

APP_NAME = "claude-teletype"
DEFAULT_CONFIG = {
    "general": {
        "delay_ms": 75.0,
        "audio": True,
        "transcript_dir": None,  # None = ./transcripts
    },
    "printer": {
        "profile": "none",  # "escp", "juki6100", "pcl", "none"
        "device": None,
        "columns": 80,
    },
    "llm": {
        "backend": "claude",  # "claude", "openai", "openrouter"
        "model": None,  # None = backend default
        "openai_api_key_env": "OPENAI_API_KEY",
        "openrouter_api_key_env": "OPENROUTER_API_KEY",
    },
}
```

### New Module: `profiles.py`

```python
"""Printer profiles with control code definitions."""
from dataclasses import dataclass

@dataclass(frozen=True)
class PrinterProfile:
    name: str
    reset: bytes
    init_sequence: bytes  # sent once at start
    newline: bytes
    form_feed: bytes
    columns: int

PROFILES: dict[str, PrinterProfile] = {
    "escp": PrinterProfile(...),
    "juki6100": PrinterProfile(...),
    "pcl": PrinterProfile(...),
}
```

### Modified: `bridge.py` -- Unchanged for Claude Code CLI

The existing `stream_claude_response()` stays as-is. New LLM backends get a parallel module.

### New Module: `llm_backends.py`

```python
"""Alternative LLM backends via OpenAI-compatible API."""
# Only importable when openai extra is installed
```

### Modified: `printer.py` -- Profile-Based Driver

`JukiPrinterDriver` refactored into generic `ProfiledPrinterDriver` that accepts any `PrinterProfile`. The `JukiPrinterDriver` class is kept as a backward-compatible alias.

### Modified: `tui.py` -- Settings Keybinding

```python
BINDINGS = [
    Binding("ctrl+d", "quit", "Quit"),
    Binding("escape", "cancel_stream", "Cancel", show=False),
    Binding("ctrl+comma", "settings", "Settings"),  # NEW
]
```

### Modified: `cli.py` -- Config Loading

```python
@app.command()
def chat(...):
    config = load_config()  # Load from platformdirs location
    # CLI flags override config file values
    effective_delay = delay if delay != 75.0 else config["general"]["delay_ms"]
```

---

## Risk Assessment

| Area | Risk | Mitigation |
|------|------|------------|
| openai SDK dependency weight (httpx, pydantic, etc.) | LOW | Made optional via `[project.optional-dependencies] llm`. Core install stays light. |
| OpenRouter API compatibility drift | LOW | OpenRouter explicitly documents OpenAI SDK compatibility. Same `chat.completions.create()` call. |
| Textual 8.0 breaking change (`Select.BLANK` -> `Select.NULL`) | LOW | Only affects new settings code, not existing TUI. Easy to target v8 from the start. |
| Juki 9100 control codes unverified | MEDIUM | Start with Juki 6100 profile (known working). Add 9100 profile during implementation with hardware testing. |
| Config file migration (none exists yet) | LOW | v1.2 is first version with config. No migration needed. Default config generated on first run. |
| Message history management for OpenAI/OpenRouter | MEDIUM | Unlike Claude Code CLI (which manages history internally), OpenAI/OpenRouter need client-side message list. Keep it simple: in-memory list, no persistence across sessions initially. |

---

## Sources

- OpenAI Python SDK v2.21.0 on PyPI: https://pypi.org/project/openai/
  - Confirmed: `AsyncOpenAI`, `stream=True`, `chunk.choices[0].delta.content`
  - Dependencies: httpx, pydantic, anyio, jiter, tqdm, distro, sniffio
  - Confidence: HIGH (official package, verified 2026-02-17)

- OpenRouter OpenAI SDK integration: https://openrouter.ai/docs/guides/community/openai-sdk
  - Confirmed: `base_url="https://openrouter.ai/api/v1"` with standard OpenAI client
  - Confidence: HIGH (official OpenRouter docs)

- Python tomllib (stdlib): https://docs.python.org/3.12/library/tomllib.html
  - Read-only TOML parser, binary mode required
  - Confidence: HIGH (Python stdlib docs)

- tomli-w v1.2.0 on PyPI: https://pypi.org/project/tomli-w/
  - Zero dependencies, `dump()` and `dumps()` API
  - Confidence: HIGH (official package)

- platformdirs v4.9.2 on PyPI: https://pypi.org/project/platformdirs/
  - Zero dependencies, `user_config_dir()` API
  - Confidence: HIGH (official package)

- Textual v8.0.0 on PyPI: https://pypi.org/project/textual/
  - Breaking changes: Select.BLANK -> Select.NULL, OptionList separator change
  - ModalScreen, Switch, Select, Input, TabbedContent all confirmed available
  - Confidence: HIGH (official package + widget gallery)

- Textual ModalScreen docs: https://textual.textualize.io/guide/screens/
  - dismiss() callback pattern and push_screen_wait() async pattern
  - Confidence: HIGH (official docs)

- Textual widget gallery: https://textual.textualize.io/widget_gallery/
  - Confirmed: Input (with type="number"), Switch, Select, RadioSet, TabbedContent, Button, Label
  - Confidence: HIGH (official docs)

- ESC/P control codes: https://stanislavs.org/helppc/epson_printer_codes.html
  - ESC @, ESC E/F, SI/DC2, ESC 2/0 confirmed for Epson FX/LQ series
  - Confidence: HIGH (well-established protocol, cross-referenced with IBM docs)

- IBM PPDS and ESC/P reference: https://www.ibm.com/support/pages/list-ibm-ppds-and-epson-escp-control-codes-and-escape-sequences
  - Cross-reference for ESC/P codes on IBM-compatible dot matrix
  - Confidence: HIGH (IBM official support page)

- PCL command reference: https://people.wou.edu/~soukupm/pcl_commands.htm and https://developers.hp.com/hp-printer-command-languages-pcl
  - PCL5 escape sequence structure confirmed
  - Confidence: HIGH (HP developer portal)

- Juki 6100 technical manual: https://archive.org/stream/bitsavers_jukiJuki61y84_24339953/Juki_6100_Technical_Manual_May84_djvu.txt
  - ESC codes for Juki daisywheel series
  - Confidence: MEDIUM (archive.org scan, confirmed by working code in printer.py)

- OpenAI streaming API guide: https://developers.openai.com/api/docs/guides/streaming-responses
  - stream=True, delta.content extraction pattern
  - Confidence: HIGH (official OpenAI docs)
