# claude-teletype

Typewriter-paced output for Claude Code. Watch AI responses appear character by character in your terminal, on a dot-matrix printer, or on a Juki 6100 daisywheel — complete with bell sounds and automatic transcripts.

## Features

- **Typewriter pacing** — characters appear one at a time with variable delays (punctuation pauses, newline carriage-return feel)
- **Split-screen TUI** — Textual-powered interface with scrollable output and prompt input
- **Physical printer support** — USB direct, CUPS, and device-file backends with auto-discovery
- **Juki 6100 mode** — ESC/P init codes, CR+LF newlines, and proper daisywheel handling
- **Raw teletype mode** — keyboard straight to printer, character by character
- **Audio bell** — 880 Hz tone on every newline, like a real typewriter carriage return
- **Transcripts** — timestamped session logs saved automatically

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

# Juki 6100 daisywheel mode
claude-teletype --juki "letter to the editor"

# Raw teletype: keyboard → printer, no AI
claude-teletype --teletype
claude-teletype --teletype --juki

# Disable bell sounds
claude-teletype --no-audio "quiet mode"

# Custom transcript directory
claude-teletype --transcript-dir ./logs "save here"
```

## Architecture

```
stdin/prompt
    │
    ▼
┌─────────┐    NDJSON     ┌───────┐    char-by-char    ┌─────────┐
│  Bridge  │──────────────▶│ Pacer │───────────────────▶│ Output  │
│ (claude  │  text_delta   │       │  variable delays   │  Fan-out │
│  -p CLI) │   events      │       │                    │         │
└─────────┘               └───────┘                    └────┬────┘
                                                            │
                                          ┌─────────────────┼─────────────────┐
                                          │                 │                 │
                                          ▼                 ▼                 ▼
                                     ┌─────────┐     ┌──────────┐     ┌────────────┐
                                     │ Terminal │     │ Printer  │     │ Transcript │
                                     │ / TUI   │     │ Driver   │     │   Writer   │
                                     └─────────┘     └──────────┘     └────────────┘
                                                          │
                                                     ┌────┴────┐
                                                     │  Audio  │
                                                     │  Bell   │
                                                     └─────────┘
```

**Modules:**

| Module | Purpose |
|--------|---------|
| `bridge.py` | Spawns `claude -p` subprocess, parses NDJSON stream, yields text chunks |
| `pacer.py` | Classifies characters and applies variable delays for typewriter feel |
| `output.py` | Fan-out: sends each character to multiple destinations |
| `tui.py` | Textual split-screen app with scrollable log and input |
| `printer.py` | PrinterDriver protocol + USB/CUPS/File/Juki backends |
| `teletype.py` | Raw keyboard-to-printer mode (cbreak terminal) |
| `audio.py` | In-memory 880 Hz bell tone via sounddevice |
| `transcript.py` | Timestamped session file writer |

## Development

```bash
uv sync --group dev
uv run pytest
uv run ruff check .
```

## License

MIT
