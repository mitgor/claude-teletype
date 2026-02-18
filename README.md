# claude-teletype

Typewriter-paced output for Claude Code. Watch AI responses appear character by character in your terminal, on a dot-matrix printer, or on a Juki 6100 daisywheel — complete with bell sounds, automatic transcripts, and multi-LLM backend support.

## Features

- **Typewriter pacing** — characters appear one at a time with variable delays (punctuation pauses, newline carriage-return feel)
- **Split-screen TUI** — Textual-powered interface with scrollable output, prompt input, and status bar
- **Physical printer support** — USB direct, CUPS, and device-file backends with auto-discovery
- **Printer profiles** — built-in profiles for Juki, Epson ESC/P, IBM PPDS, HP PCL, plus custom profiles via TOML
- **Multi-LLM backends** — Claude Code CLI (default), OpenAI, and OpenRouter
- **Settings panel** — runtime-editable settings with `Ctrl+,` (delay, audio, profile, backend, model)
- **Typewriter mode** — `Ctrl+T` for keyboard-to-paper with no AI, or `--teletype` for standalone
- **Audio bell** — 880 Hz tone on every newline, keystroke clicks in typewriter mode
- **Transcripts** — timestamped session logs saved automatically
- **Configuration** — TOML config file with env var and CLI flag overrides

## Install

Requires Python 3.12+ and [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed.

```bash
# Clone and install
git clone https://github.com/mitgor/claude-teletype.git
cd claude-teletype
uv sync

# For USB printer support (pyusb + libusb)
uv sync --extra usb
brew install libusb  # macOS
```

## Usage

```bash
# Interactive TUI (default)
claude-teletype

# One-shot with a prompt
claude-teletype "explain quicksort"

# Plain stdout mode (no TUI)
claude-teletype --no-tui "hello world"

# Adjust typing speed (ms between characters, default 75)
claude-teletype -d 50 "fast typing"
claude-teletype -d 120 "slow and dramatic"

# Print to a physical printer
claude-teletype --device /dev/usb/lp0 "print this"

# Select a printer profile
claude-teletype --printer juki "letter to the editor"
claude-teletype --printer escp "dot matrix output"

# Use a different LLM backend
claude-teletype --backend openai --model gpt-4o "hello"
claude-teletype --backend openrouter --model anthropic/claude-3.5-sonnet "hello"

# Resume a previous session
claude-teletype --resume <session_id>

# Raw teletype: keyboard → printer, no AI
claude-teletype --teletype
claude-teletype --teletype --printer juki

# Disable bell sounds
claude-teletype --no-audio "quiet mode"

# Custom transcript directory
claude-teletype --transcript-dir ./logs "save here"
```

### TUI keyboard shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+T` | Enter typewriter mode (keyboard → printer) |
| `Ctrl+,` | Open settings panel |
| `Escape` | Cancel current streaming response |
| `Ctrl+D` | Quit |

## Configuration

Settings are stored in a platform-specific config directory with three-layer precedence: defaults < config file < `CLAUDE_TELETYPE_*` env vars < CLI flags.

| Platform | Config file |
|----------|-------------|
| macOS | `~/Library/Application Support/claude-teletype/config.toml` |
| Linux | `~/.config/claude-teletype/config.toml` |
| Windows | `%APPDATA%\claude-teletype\config.toml` |

```bash
# Generate a config file with defaults
claude-teletype config init

# View effective configuration
claude-teletype config show
```

Example config:

```toml
[general]
delay = 75.0
no_audio = false
no_tui = false
transcript_dir = "transcripts"

[printer]
profile = "generic"
# device = "/dev/usb/lp0"  # optional, overrides auto-discovery

[llm]
backend = "claude-cli"     # claude-cli | openai | openrouter
model = ""                 # empty = backend default
system_prompt = ""         # for OpenAI/OpenRouter only
```

### Custom printer profiles

Define custom profiles in the config file:

```toml
[printer.profiles.my-printer]
description = "My custom printer"
init = "1b40"              # hex-encoded ESC init bytes
reset = "1b40"
crlf = false               # true = CR+LF newlines
formfeed_on_close = true
columns = 80
usb_vendor_id = "04b8"     # optional, for USB auto-detection
usb_product_id = "0005"    # optional
```

## Printer profiles

Built-in profiles handle ESC code initialization, newline translation, and USB auto-detection:

| Profile | Printers | Init | Newlines | USB auto-detect |
|---------|----------|------|----------|-----------------|
| `generic` | Any printer, no ESC codes | none | LF | no |
| `juki` | Juki 6100/9100 daisywheel | `ESC SUB I` + line spacing + pitch | CR+LF | no |
| `escp` | Epson FX/LQ/LX dot-matrix | `ESC @` | LF | Epson (VID `04B8`) |
| `ppds` | IBM Proprinter compatible | `ESC @` | LF | no |
| `pcl` | HP LaserJet/DeskJet/OfficeJet | `ESC E` | LF | HP (VID `03F0`) |

Printer discovery order: `--device` path > USB direct (pyusb) > CUPS > Linux `/dev/usb/lp*` > no-op fallback.

## LLM backends

| Backend | Flag | API key | Default model |
|---------|------|---------|---------------|
| Claude Code CLI | `--backend claude-cli` | via `claude` CLI auth | Claude default |
| OpenAI | `--backend openai` | `OPENAI_API_KEY` | `gpt-4o` |
| OpenRouter | `--backend openrouter` | `OPENROUTER_API_KEY` | `openai/gpt-4o` |

If a non-default backend fails validation at startup, claude-teletype falls back to Claude CLI with a warning.

## Architecture

```
stdin/prompt
    │
    ▼
┌──────────┐   text chunks   ┌───────┐   char-by-char   ┌─────────┐
│ LLM      │────────────────▶│ Pacer │─────────────────▶│ Output  │
│ Backend  │  stream API      │       │ variable delays   │ Fan-out │
└──────────┘                  └───────┘                   └────┬────┘
                                                               │
                                             ┌─────────────────┼─────────────────┐
                                             │                 │                 │
                                             ▼                 ▼                 ▼
                                        ┌─────────┐     ┌──────────┐     ┌────────────┐
                                        │ Terminal │     │ Profile  │     │ Transcript │
                                        │ / TUI   │     │ Printer  │     │   Writer   │
                                        └─────────┘     │ Driver   │     └────────────┘
                                                        └──────────┘
                                                             │
                                                        ┌────┴────┐
                                                        │  Audio  │
                                                        │  Bell   │
                                                        └─────────┘
```

**Modules:**

| Module | Purpose |
|--------|---------|
| `backends/` | LLM backend ABC + Claude CLI, OpenAI, OpenRouter implementations |
| `config.py` | TOML config loading, env var merge, CLI flag override |
| `profiles.py` | Printer profile registry, USB auto-detection |
| `printer.py` | PrinterDriver protocol + USB/CUPS/File/Profile backends |
| `pacer.py` | Character classification and variable delay pacing |
| `output.py` | Fan-out: sends each character to multiple destinations |
| `wordwrap.py` | Streaming character-level word wrapper |
| `tui.py` | Textual split-screen app with scrollable log and input |
| `settings_screen.py` | Settings modal (delay, audio, profile, backend, model) |
| `typewriter_screen.py` | Keyboard-to-printer mode within the TUI |
| `teletype.py` | Standalone raw keyboard-to-printer mode (cbreak terminal) |
| `errors.py` | Error classification and retry logic (7 categories) |
| `audio.py` | Bell tone + keystroke click via sounddevice |
| `transcript.py` | Timestamped session file writer |

## Development

```bash
uv sync --group dev
uv run pytest
uv run ruff check .
```

## License

MIT
