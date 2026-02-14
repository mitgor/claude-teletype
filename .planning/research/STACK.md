# Stack Research

**Domain:** Python CLI tool — hardware printer interface, process wrapping, audio playback, terminal UI
**Researched:** 2026-02-14
**Confidence:** MEDIUM-HIGH (core libraries verified via PyPI; printer I/O path has LOW confidence due to macOS USB-LPT adapter limitations)

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| Python | 3.12+ | Runtime | Stable, async-native, broad library support. 3.12 has significant perf improvements. 3.13 acceptable but 3.12 is safest for library compat. | HIGH |
| uv | 0.10.x | Package/project manager | Replaces pip, venv, poetry. 10-100x faster installs, universal lockfile, manages Python versions. The 2025-2026 standard for new Python projects. Written in Rust by Astral. | HIGH |
| Textual | 7.5.0 | Terminal UI framework | The dominant Python TUI framework. CSS-like layout, built-in widgets (split panes, text areas, scrollable panels), async-native, MIT licensed. Supports split-screen layout natively via Horizontal/Vertical containers. Made by Textualize (same team as Rich). | HIGH |
| Rich | 14.3.2 | Terminal text formatting | Textual's foundation. Provides styled text, progress bars, panels, syntax highlighting. Textual depends on it already — no extra dependency. | HIGH |
| asyncio | stdlib | Async coordination | Needed to simultaneously: read subprocess output, write to printer, play sounds, update TUI. All character-by-character streaming is inherently async. Standard library — zero dependency cost. | HIGH |

### Printer Communication (Tiered Approach)

The USB-LPT-to-dot-matrix path on macOS is the highest-risk area. No single library solves it cleanly. Use a tiered approach with fallbacks.

| Tier | Method | Library | When to Use | Confidence |
|------|--------|---------|-------------|------------|
| 1 (preferred) | CUPS raw queue | `subprocess` (lp/lpr) | Printer is set up as raw CUPS queue. `lp -o raw -d <printer> <file>` sends bytes directly. Works on macOS and Linux. No Python library needed — use `subprocess.run(["lp", ...])`. | MEDIUM |
| 2 (fallback) | Direct device file | `open()` / `os.write()` | Linux: printer appears at `/dev/usb/lp0`. Write raw bytes directly. macOS: rare — most USB-LPT adapters do NOT create device files on macOS. | MEDIUM (Linux) / LOW (macOS) |
| 3 (fallback) | PyUSB raw USB | pyusb 1.3.1 | Native USB printers (NOT USB-LPT adapters). Requires libusb backend. Can send raw bytes to USB endpoint. Useful if printer has native USB port. | MEDIUM |
| 4 (simulation) | Virtual printer | Textual widget | No hardware available. Render characters in a dedicated TUI panel with typewriter-style pacing. This is the development/demo mode. | HIGH |

**Critical finding:** USB-to-Parallel adapters are unreliable for programmatic control. The python-escpos project explicitly warns: "Stay away from USB-to-Parallel-Adapter since they are unreliable and produce arbitrary errors." The most reliable macOS path is configuring the printer as a CUPS raw queue, then using `lp -o raw` to send text. On Linux, direct `/dev/usb/lp0` writes are more reliable.

### Claude Code CLI Integration

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| `asyncio.create_subprocess_exec` | stdlib | Spawn Claude CLI | Launch `claude -p "<prompt>" --output-format stream-json --verbose --include-partial-messages`. Read stdout as newline-delimited JSON. Each line is a streaming event. Filter for `text_delta` events to get character-by-character text. | HIGH |
| pexpect | 4.9.0 | Interactive mode fallback | If we need to wrap Claude Code in interactive (non -p) mode, pexpect provides PTY-based process control. Reads character-by-character via `read(1)`. Last release 2023-11-25 but stable/mature. | MEDIUM |

**Key insight from Claude Code docs:** Use `--output-format stream-json --verbose --include-partial-messages` to get token-level streaming. Filter JSON events where `type == "stream_event"` and `event.delta.type == "text_delta"`, then extract `event.delta.text`. This gives character/token-level granularity for the typewriter effect.

### Audio Playback

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| sounddevice | 0.5.5 | Play typewriter sound effects | Actively maintained (Jan 2026 release). Wraps PortAudio. Supports async-compatible non-blocking playback. Can play NumPy arrays directly — useful for low-latency sound effects triggered per-character. | HIGH |
| soundfile | 0.13.1 | Load WAV/audio files | Reads WAV files into NumPy arrays that sounddevice can play. Based on libsndfile. Companion to sounddevice. | HIGH |

### CLI Framework

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| Typer | 0.23.1 | CLI argument parsing | Built on Click, uses type hints for argument definitions. Auto-generates --help. Depends on Rich (already needed). Active development (Feb 2026 release). The modern Python CLI standard. | HIGH |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| numpy | latest stable | Audio buffer manipulation | Required by sounddevice for playing audio arrays. Lightweight for this use case. |
| pycups | 2.0.4 | CUPS printer discovery | Optional. Use to enumerate available CUPS printers programmatically instead of shelling out to `lpstat`. Only needed if auto-discovery beyond `lpstat -p` is desired. |
| pyusb | 1.3.1 | USB device discovery | Optional. Use for Tier 3 (native USB printer) path. Requires `libusb` installed via Homebrew on macOS (`brew install libusb`). |

### Development Tools

| Tool | Version | Purpose | Notes |
|------|---------|---------|-------|
| uv | 0.10.x | Project management, venv, locking | `uv init`, `uv add`, `uv run`. Replaces pip/poetry/venv. |
| ruff | 0.15.1 | Linter + formatter | Replaces flake8, black, isort. 10-100x faster. From Astral (same team as uv). |
| ty | beta | Type checker | From Astral. 10-60x faster than mypy. Beta status — use mypy 1.19.1 if stability is preferred. |
| mypy | 1.19.1 | Type checker (stable fallback) | Production-stable. Use if ty proves too buggy in beta. |
| pytest | 9.0.2 | Testing framework | Standard Python testing. Use pytest-asyncio for async test support. |
| pre-commit | latest | Git hooks | Run ruff + type checking on commit. |

## Installation

```bash
# Initialize project with uv
uv init claude-teletype
cd claude-teletype

# Core dependencies
uv add textual rich typer sounddevice soundfile numpy

# Optional: printer discovery
uv add pycups pyusb

# Optional: interactive CLI wrapping
uv add pexpect

# Dev dependencies
uv add --dev ruff mypy pytest pytest-asyncio pre-commit
```

### System Dependencies (macOS)

```bash
# Required for sounddevice (PortAudio)
brew install portaudio

# Required only if using pyusb (Tier 3 printer path)
brew install libusb

# Required only if using pycups
brew install cups
# (cups is pre-installed on macOS but headers may be needed for pycups compilation)
```

### System Dependencies (Linux)

```bash
# Required for sounddevice
sudo apt install libportaudio2 portaudio19-dev

# For direct USB printer access (Tier 2)
# Printer typically appears at /dev/usb/lp0
# May need: sudo usermod -a -G lp $USER

# Required only if using pyusb
sudo apt install libusb-1.0-0-dev
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Textual 7.5.0 | curses (stdlib) | Never for this project. curses is low-level, no widgets, no CSS layout, painful to build split-screen UIs. Textual abstracts all of this. |
| Textual 7.5.0 | prompt_toolkit | Only if you need readline-style input completion without a full TUI. We need split-screen, so Textual wins. |
| sounddevice 0.5.5 | pygame.mixer | Only if you already depend on pygame. pygame is a 30+ MB dependency for game development — massive overkill for playing WAV clicks. |
| sounddevice 0.5.5 | simpleaudio | Never. Abandoned since 2019 (v1.0.4). No Python 3.12+ testing. Will break. |
| Typer 0.23.1 | Click | Only if you need maximum control over CLI parsing. Typer wraps Click with type hints — strictly better DX for new projects. |
| Typer 0.23.1 | argparse (stdlib) | Only for zero-dependency constraints. argparse requires verbose boilerplate. Typer is cleaner. |
| uv 0.10.x | poetry | Only if team is already invested in poetry. uv is faster, simpler, and handles more (Python version management, scripts). Poetry is being superseded. |
| uv 0.10.x | pip + venv | Never for new projects. Manual venv management, no lockfile, no Python version management. |
| CUPS raw queue (`lp`) | python-escpos | Only for ESC/POS thermal receipt printers with native USB. Not suitable for parallel dot-matrix printers via USB-LPT adapters. |
| asyncio subprocess | os.popen / subprocess.Popen (sync) | Never. Synchronous subprocess blocks the event loop. We need concurrent printer output, sound playback, and TUI updates. |
| ruff 0.15.1 | flake8 + black + isort | Never for new projects. Ruff replaces all three, runs 100x faster, single config file. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| simpleaudio | Abandoned since 2019. No releases in 6+ years. Likely broken on Python 3.12+. | sounddevice 0.5.5 |
| pyparallel | Dead project. No releases published. Only supports Windows/Linux. Requires Python 2.2+. Last copyright 2016. | CUPS raw queue or direct device file I/O |
| pygame (for audio only) | 30+ MB dependency. Brings SDL, window management, sprite rendering. Massive overkill for playing WAV click sounds. | sounddevice 0.5.5 |
| curses (for TUI) | No widget system, no layout engine, no CSS, no async integration. Building a split-screen TUI from curses is weeks of work vs. hours with Textual. | Textual 7.5.0 |
| python-escpos | Designed for ESC/POS thermal receipt printers. Not for dot-matrix printers. Different command set. Will send wrong control codes. | Direct raw text via CUPS or device file |
| poetry | Being superseded by uv. Slower installs, no Python version management, more complex config. | uv 0.10.x |
| playsound | Abandoned, buggy, cross-platform issues. Multiple open CVEs. | sounddevice 0.5.5 |

## Stack Patterns by Variant

**If printer is a CUPS-configured raw queue (preferred on macOS):**
- Discover printers via `subprocess.run(["lpstat", "-p"], capture_output=True)`
- Send text via `subprocess.run(["lp", "-o", "raw", "-d", printer_name], input=text_bytes)`
- Character-by-character: accumulate chars, flush to printer in small batches (per-line or per-word) to avoid per-char subprocess overhead
- Alternative: hold a pipe open to `lp` via `asyncio.create_subprocess_exec`

**If printer is a direct device file (Linux /dev/usb/lp0):**
- Open device file: `fd = open("/dev/usb/lp0", "wb", buffering=0)`
- Write characters directly: `fd.write(char.encode('ascii'))`
- True character-by-character streaming is possible
- Requires user to be in `lp` group

**If no printer hardware (simulation mode):**
- Textual split-screen: top panel = "paper" (scrolling text area), bottom panel = input
- Typewriter effect: append characters to text widget with `asyncio.sleep(0.05-0.1)` between each
- Play sound effects on each character append
- This is the default/development mode

**If using Claude Code in non-interactive (-p) mode (preferred):**
- Spawn: `asyncio.create_subprocess_exec("claude", "-p", prompt, "--output-format", "stream-json", "--verbose", "--include-partial-messages")`
- Read stdout line-by-line (each line is JSON)
- Filter for text_delta events: `select(.type == "stream_event" and .event.delta.type == "text_delta")`
- Extract `.event.delta.text` for each token
- Continue conversations with `--resume <session_id>`

**If wrapping Claude Code interactively (future/advanced):**
- Use pexpect to spawn `claude` in a PTY
- Read output character-by-character via `child.read(1)`
- More complex but allows full interactive mode with tool use approval

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| textual >= 7.0 | Python 3.9-3.14 | Textual 7.x requires Python >= 3.9. Pin to `>=7.5.0,<8.0` for stability. |
| sounddevice 0.5.5 | Python 3.7+ | Requires PortAudio system library. On macOS: `brew install portaudio`. |
| soundfile 0.13.1 | sounddevice 0.5.x | Companion library. Loads WAV files into NumPy arrays for sounddevice playback. |
| typer 0.23.x | rich 14.x, click 8.x | Typer bundles Rich and Click as dependencies. Compatible with Textual's Rich dependency. |
| pyusb 1.3.1 | libusb 1.x | Requires `brew install libusb` on macOS. Only needed for Tier 3 native USB path. |
| pycups 2.0.4 | CUPS 1.7+ | macOS ships CUPS. May need Xcode command line tools for compilation. |
| ruff 0.15.x | Python 3.9+ | No Python runtime dependency (Rust binary). Configured via pyproject.toml. |
| uv 0.10.x | Python 3.9+ | Standalone Rust binary. Manages Python versions itself. |

## Risk Assessment

| Area | Risk Level | Mitigation |
|------|------------|------------|
| USB-LPT printer communication on macOS | HIGH | Tiered approach. CUPS raw queue is most reliable. Test with actual hardware early. Simulation mode as development fallback. |
| Claude Code CLI streaming interface | LOW | Well-documented `--output-format stream-json` flag. Stable API. |
| Audio latency for per-character sound effects | MEDIUM | sounddevice supports non-blocking playback. Pre-load WAV into memory as NumPy array. Use `sd.play()` with short buffer. May need to overlap/reuse play objects for rapid fire. |
| Textual split-screen TUI | LOW | Native support for Horizontal/Vertical containers. Well-documented layout system. Large community. |
| Async coordination (subprocess + printer + audio + TUI) | MEDIUM | asyncio event loop handles this naturally. Textual is async-native. Key risk: blocking I/O in printer writes — must use `asyncio.to_thread()` or executor for device file writes. |

## Sources

- [Textual PyPI](https://pypi.org/project/textual/) — version 7.5.0 verified (HIGH)
- [Textual docs](https://textual.textualize.io/) — layout system, widgets verified (HIGH)
- [Rich PyPI](https://pypi.org/project/rich/) — version 14.3.2 verified (HIGH)
- [Typer PyPI](https://pypi.org/project/typer/) — version 0.23.1 verified (HIGH)
- [sounddevice PyPI](https://pypi.org/project/sounddevice/) — version 0.5.5, released 2026-01-23 (HIGH)
- [soundfile PyPI](https://pypi.org/project/soundfile/) — version 0.13.1 verified (HIGH)
- [pyusb PyPI](https://pypi.org/project/pyusb/) — version 1.3.1, released 2025-01-08 (HIGH)
- [pycups PyPI](https://pypi.org/project/pycups/) — version 2.0.4, released 2024-04-18 (HIGH)
- [pexpect PyPI](https://pypi.org/project/pexpect/) — version 4.9.0, released 2023-11-25 (HIGH)
- [uv PyPI](https://pypi.org/project/uv/) — version 0.10.2, released 2026-02-10 (HIGH)
- [ruff PyPI](https://pypi.org/project/ruff/) — version 0.15.1, released 2026-02-12 (HIGH)
- [pytest PyPI](https://pypi.org/project/pytest/) — version 9.0.2, released 2025-12-06 (HIGH)
- [Claude Code CLI docs](https://code.claude.com/docs/en/headless) — streaming JSON output format verified (HIGH)
- [python-escpos USB-LPT warning](https://github.com/python-escpos/python-escpos/issues/214) — USB-to-Parallel adapter unreliability (MEDIUM)
- [macOS CUPS raw printing setup](https://www.printnode.com/en/docs/raw-printing-for-osx) — lp -o raw approach (MEDIUM)
- [simpleaudio PyPI](https://pypi.org/project/simpleaudio/) — last release 2019, confirmed abandoned (HIGH)
- [pyparallel GitHub](https://github.com/pyserial/pyparallel) — no releases, Windows/Linux only, confirmed dead (HIGH)
- [ty type checker](https://astral.sh/blog/ty) — beta status, 10-60x faster than mypy (MEDIUM)

---
*Stack research for: Python CLI — USB-LPT dot-matrix printer interface, Claude Code wrapper, terminal UI*
*Researched: 2026-02-14*
