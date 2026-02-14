# Phase 1: Streaming Pipeline - Research

**Researched:** 2026-02-14
**Domain:** Claude Code subprocess streaming, NDJSON parsing, asyncio event loop, character-by-character terminal output with typewriter pacing
**Confidence:** HIGH

## Summary

Phase 1 delivers the foundational streaming pipeline: a Python CLI that sends a user prompt to Claude Code, parses the NDJSON streaming response, and outputs Claude's response character by character with typewriter pacing. This phase has no hardware dependencies (no printer, no TUI, no audio) -- it is purely subprocess-to-terminal with pacing.

The core technical challenge is well-understood: spawn Claude Code with `asyncio.create_subprocess_exec()`, read NDJSON lines from stdout, extract `text_delta` events from `content_block_delta` stream events, and feed characters through a pacing layer that applies variable delays before printing to stdout. The NDJSON format from Claude Code's `--output-format stream-json --verbose --include-partial-messages` is now thoroughly documented by Anthropic's Agent SDK specification.

The thinking indicator requirement (CLDE-03) is addressed by detecting the gap between subprocess launch and the first `content_block_delta` with `text_delta` type -- during this window, a spinner or "Thinking..." message is shown.

**Primary recommendation:** Use `asyncio.create_subprocess_exec()` with `-p` one-shot mode per prompt to avoid bidirectional pipe deadlocks. Parse NDJSON with `json.loads()` per line. Feed characters through an async pacing function with variable delay based on character class. Output with `sys.stdout.write()` + `sys.stdout.flush()`. Use Typer for CLI with `asyncio.run()` wrapper pattern.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12+ | Runtime | Stable async support, performance improvements. Project requirement. |
| asyncio | stdlib | Async subprocess + pacing | Required for non-blocking subprocess I/O. Cannot use sync subprocess -- it blocks during Claude's thinking time and prevents concurrent pacing/output. |
| Typer | 0.23.x | CLI argument parsing | Type-hint-based CLI definition. Auto-generates --help. Depends on Rich (useful later). Modern Python CLI standard. |
| json | stdlib | NDJSON line parsing | `json.loads()` per line. No third-party JSON library needed -- NDJSON is one JSON object per line. |
| sys | stdlib | Character output | `sys.stdout.write(char)` + `sys.stdout.flush()` for unbuffered character-by-character terminal output. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| uv | 0.10.x | Project/package management | Project initialization, dependency management, virtual environment. Replaces pip/poetry/venv. |
| Rich | 14.x | Thinking spinner | `rich.console.Console` with `Status` spinner for thinking indicator. Already a Typer dependency -- zero extra cost. |
| ruff | 0.15.x | Linter + formatter | Dev dependency. Replaces flake8/black/isort. |
| pytest | 9.x | Testing | Dev dependency. Use pytest-asyncio for async test support. |
| pytest-asyncio | latest | Async test support | Dev dependency. Required for testing async functions. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Typer | Click | Click is lower-level, more boilerplate. Typer wraps Click with type hints -- strictly better DX. |
| Typer | argparse (stdlib) | Zero-dependency but verbose. Typer is cleaner and already needed for later phases. |
| `json.loads()` | `jq` subprocess | Adds subprocess overhead per line. `json.loads()` is faster, simpler, no external dependency. |
| Rich spinner | Custom print loop | Rich Status spinner is polished, handles terminal width, cleans up properly. No reason to hand-roll. |
| `asyncio.create_subprocess_exec` | `subprocess.Popen` | Popen blocks the event loop. Cannot do concurrent pacing + reading. Fatal for this project. |

**Installation:**
```bash
# Initialize project
uv init claude-teletype --package
cd claude-teletype

# Core dependencies
uv add typer rich

# Dev dependencies
uv add --dev ruff pytest pytest-asyncio
```

## Architecture Patterns

### Recommended Project Structure (Phase 1 only)

```
claude-teletype/
├── pyproject.toml              # Project metadata, [project.scripts] entry point
├── src/
│   └── claude_teletype/
│       ├── __init__.py
│       ├── __main__.py         # python -m claude_teletype support
│       ├── cli.py              # Typer app, entry point, asyncio.run() bridge
│       ├── bridge.py           # Claude Code subprocess: spawn, read NDJSON, yield text
│       └── pacer.py            # Character pacing: variable delay per character class
└── tests/
    ├── test_bridge.py          # Test NDJSON parsing with mock subprocess
    └── test_pacer.py           # Test delay calculations per character class
```

### Pattern 1: Typer-to-Asyncio Bridge

**What:** Typer commands are synchronous by default. The official pattern is to define a sync command that calls `asyncio.run()` on an async function. Typer 0.23.x may support `async def` commands directly, but the `asyncio.run()` pattern is the most reliable and well-documented approach.

**When to use:** Always in this project -- the core loop is async (subprocess + pacing), but Typer is the entry point.

**Example:**
```python
# cli.py
import asyncio
import typer

app = typer.Typer()

@app.command()
def chat(prompt: str = typer.Argument(..., help="Prompt to send to Claude")):
    """Send a prompt to Claude and watch the response appear character by character."""
    asyncio.run(_chat_async(prompt))

async def _chat_async(prompt: str) -> None:
    from .bridge import stream_claude_response
    from .pacer import pace_characters

    async for text_chunk in stream_claude_response(prompt):
        await pace_characters(text_chunk)
```

**Source:** [Typer async issue #85](https://github.com/fastapi/typer/issues/85) -- community pattern with `asyncio.run()` wrapper.

### Pattern 2: NDJSON Stream Parser

**What:** Read Claude Code's stdout line by line. Each line is a complete JSON object. Filter for `stream_event` type where `event.type == "content_block_delta"` and `event.delta.type == "text_delta"`. Extract `event.delta.text`.

**When to use:** Every time we read from the Claude Code subprocess.

**Example:**
```python
# bridge.py
import asyncio
import json
import sys
from typing import AsyncIterator

async def stream_claude_response(prompt: str) -> AsyncIterator[str]:
    """Spawn Claude Code and yield text chunks as they stream in."""
    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--include-partial-messages",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    assert proc.stdout is not None

    while True:
        line = await proc.stdout.readline()
        if not line:
            break  # EOF

        try:
            msg = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError:
            continue  # Skip malformed lines

        if msg.get("type") == "stream_event":
            event = msg.get("event", {})
            if event.get("type") == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    if text:
                        yield text

    await proc.wait()
```

**Source:** [Claude Code headless docs](https://code.claude.com/docs/en/headless) -- official jq filter pattern: `select(.type == "stream_event" and .event.delta.type? == "text_delta") | .event.delta.text`. [Claude Agent SDK spec](https://gist.github.com/POWERFULMOVES/58bcadab9483bf5e633e865f131e6c25) -- full NDJSON message type documentation.

### Pattern 3: Variable Character Pacing

**What:** Each character gets a delay before being printed to stdout. The delay varies by character class: punctuation is slower (thinking pause), spaces are faster (less visual weight), newlines get a long pause (carriage return feel).

**When to use:** Every character output from Claude's response.

**Example:**
```python
# pacer.py
import asyncio
import sys

# Delay multipliers relative to base delay
CHAR_DELAYS = {
    "punctuation": 1.5,   # . , ! ? ; : -- feels like "thinking"
    "newline": 3.0,        # \n -- carriage return pause
    "space": 0.5,          # spaces are visually light, go faster
    "default": 1.0,        # alphanumeric and everything else
}

PUNCTUATION = set(".,!?;:")

def classify_char(char: str) -> str:
    """Classify a character for pacing purposes."""
    if char == "\n":
        return "newline"
    if char == " ":
        return "space"
    if char in PUNCTUATION:
        return "punctuation"
    return "default"

async def pace_characters(
    text: str,
    base_delay_ms: float = 75.0,
) -> None:
    """Output text character by character with typewriter pacing."""
    base_delay = base_delay_ms / 1000.0

    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        multiplier = CHAR_DELAYS[classify_char(char)]
        await asyncio.sleep(base_delay * multiplier)
```

### Pattern 4: Thinking Indicator

**What:** Show a spinner/indicator between subprocess launch and the first `text_delta` event. Uses Rich's `Status` context manager which displays an animated spinner and cleans up when exited.

**When to use:** After sending prompt, before first character of response appears.

**Example:**
```python
# In the main chat flow:
from rich.console import Console

console = Console()

async def _chat_async(prompt: str) -> None:
    from .bridge import stream_claude_response
    from .pacer import pace_characters

    first_token = True

    with console.status("[bold cyan]Thinking...", spinner="dots") as status:
        async for text_chunk in stream_claude_response(prompt):
            if first_token:
                status.stop()  # Remove spinner on first text
                first_token = False
            await pace_characters(text_chunk)

    print()  # Final newline after response
```

### Anti-Patterns to Avoid

- **Synchronous subprocess:** Never use `subprocess.Popen` with blocking `readline()` in the main thread. It prevents concurrent pacing and freezes the terminal during Claude's thinking time. Always use `asyncio.create_subprocess_exec()`.

- **Using `communicate()`:** Never call `proc.communicate()` -- it waits for the process to finish and returns all output at once, destroying character-by-character streaming.

- **Bidirectional stdin/stdout piping:** Do not send prompts to Claude Code's stdin while reading from stdout. This creates deadlock risk when pipe buffers fill. Use `-p prompt` one-shot mode instead -- the prompt is a CLI argument, not stdin input.

- **Regex parsing of NDJSON:** Do not use regex to extract text from JSON lines. Use `json.loads()` per line. JSON lines format guarantees one complete object per line.

- **Unbuffered subprocess reads:** Do not use `proc.stdout.read(1)` (one byte at a time). Use `readline()` which returns one complete NDJSON line. The text_delta events may contain multi-character chunks (tokens, not individual characters) -- the pacer handles splitting these into individual characters.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CLI argument parsing | Custom sys.argv parsing | Typer | Auto --help, type validation, error messages, shell completion |
| Terminal spinner | Custom cursor animation loop | Rich Status | Handles terminal width, cleanup, multiple spinner styles, no cursor artifacts |
| NDJSON parsing | Custom line/JSON parser | `json.loads()` per line | Stdlib, handles all edge cases, fast enough for this use case |
| Async subprocess | Thread-based subprocess wrapper | `asyncio.create_subprocess_exec()` | Stdlib, no deadlock risk with proper usage, native event loop integration |

**Key insight:** Phase 1 uses only stdlib + Typer + Rich. No exotic dependencies. The complexity is in the architecture (async pipeline) not the libraries.

## Common Pitfalls

### Pitfall 1: Subprocess Buffering Destroys Character Streaming

**What goes wrong:** Output from Claude Code arrives in large chunks (thousands of characters at once) instead of line-by-line, destroying the typewriter effect.

**Why it happens:** POSIX pipes are fully buffered (64KB on macOS) when the child process detects stdout is a pipe. However, Claude Code's `--output-format stream-json` writes one JSON object per line with newlines, and `asyncio.StreamReader.readline()` reads up to each newline -- so buffering at the Python level is handled correctly. The real risk is if Claude Code itself buffers internally before flushing.

**How to avoid:**
1. Use `--output-format stream-json --verbose --include-partial-messages` -- this forces Claude Code to emit `content_block_delta` events with `text_delta` payloads as tokens arrive.
2. Use `proc.stdout.readline()` (async) to read one JSON line at a time.
3. Test early: measure time between successive `text_delta` events. If you see bursts of many events with near-zero gaps, followed by long pauses, there is a buffering issue upstream.

**Warning signs:** Characters arrive in bursts during testing. Long responses show worse behavior than short ones.

### Pitfall 2: text_delta Contains Token Chunks, Not Single Characters

**What goes wrong:** Developer assumes each `text_delta` event contains exactly one character. In reality, each event contains a token which may be a single character, a word fragment, a full word, or even multiple words.

**Why it happens:** Claude's tokenizer operates on subword tokens, not characters. The `text_delta` text field contains the decoded token text, which varies in length.

**How to avoid:** The pacer must iterate over each character within the `text_delta` text string, not treat the entire string as one unit. The bridge yields text chunks; the pacer splits them into individual characters for pacing.

**Warning signs:** Some "characters" appear to be whole words or phrases that pop in at once.

### Pitfall 3: No Thinking Indicator Creates "Frozen Tool" Perception

**What goes wrong:** After the user enters a prompt, nothing happens for 2-10 seconds while Claude thinks. The user believes the tool is frozen and hits Ctrl+C.

**Why it happens:** There is a significant delay between subprocess launch and the first `content_block_delta` event. During this time, Claude is processing the prompt, and no events are emitted except `message_start` and `content_block_start` (which contain no user-visible text).

**How to avoid:** Show a Rich `Status` spinner immediately after launching the subprocess. Stop the spinner when the first `text_delta` event arrives. The spinner provides visual feedback that the tool is working.

**Warning signs:** Users report the tool "hangs" or "does nothing" after entering a prompt.

### Pitfall 4: Forgetting to Handle Non-Text Stream Events

**What goes wrong:** The bridge crashes or produces garbage when Claude uses tools (Bash, Read, Edit), because `tool_use` content blocks produce `input_json_delta` events instead of `text_delta` events.

**Why it happens:** In `-p` mode with `--allowedTools` or default permissions, Claude may invoke tools. These produce `content_block_start` with `type: "tool_use"` followed by `content_block_delta` with `delta.type: "input_json_delta"`, not `text_delta`.

**How to avoid:** Filter strictly: only yield text when `event.type == "content_block_delta"` AND `event.delta.type == "text_delta"`. Ignore all other event types silently. For Phase 1, tool events can be skipped entirely -- they will be handled in later phases.

**Warning signs:** JSON fragments or tool input appearing in the typewriter output.

### Pitfall 5: Typer Async Integration

**What goes wrong:** Developer defines Typer command as `async def` expecting it to work, but Typer may not handle the event loop correctly in all versions, leading to "event loop already running" errors or the coroutine never executing.

**Why it happens:** Typer's async support varies by version. The safest pattern is a sync command that calls `asyncio.run()`.

**How to avoid:** Always use the sync-to-async bridge pattern:
```python
@app.command()
def chat(prompt: str):
    asyncio.run(_chat_async(prompt))
```
This works reliably across all Typer versions.

**Warning signs:** "RuntimeError: This event loop is already running" or coroutine never executes.

## Code Examples

Verified patterns from official sources:

### Spawning Claude Code Subprocess

```python
# Source: https://code.claude.com/docs/en/headless
# Official command format for streaming:
# claude -p "prompt" --output-format stream-json --verbose --include-partial-messages

import asyncio

async def spawn_claude(prompt: str) -> asyncio.subprocess.Process:
    proc = await asyncio.create_subprocess_exec(
        "claude",
        "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--include-partial-messages",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    return proc
```

### NDJSON Event Filtering with jq (for testing)

```bash
# Source: https://code.claude.com/docs/en/headless
# Official jq filter for extracting streaming text:
claude -p "Write a poem" \
  --output-format stream-json \
  --verbose \
  --include-partial-messages | \
  jq -rj 'select(.type == "stream_event" and .event.delta.type? == "text_delta") | .event.delta.text'
```

### NDJSON Message Types (Reference)

```jsonc
// Source: Claude Agent SDK Spec
// https://gist.github.com/POWERFULMOVES/58bcadab9483bf5e633e865f131e6c25

// 1. System message (first line, emitted once)
{
  "type": "system",
  "subtype": "init",
  "session_id": "550e8400-...",
  "model": "claude-sonnet-4-5-20250929",
  "tools": ["Bash", "Read", "Edit", ...],
  "claude_code_version": "2.1.3"
}

// 2. Stream event: message_start (signals response beginning)
{
  "type": "stream_event",
  "session_id": "550e8400-...",
  "event": {
    "type": "message_start",
    "message": { "model": "claude-sonnet-4-5-20250929" }
  }
}

// 3. Stream event: content_block_start (text block beginning)
{
  "type": "stream_event",
  "session_id": "550e8400-...",
  "event": {
    "type": "content_block_start",
    "index": 0,
    "content_block": { "type": "text", "text": "" }
  }
}

// 4. Stream event: content_block_delta with text_delta (THE KEY EVENT)
{
  "type": "stream_event",
  "session_id": "550e8400-...",
  "event": {
    "type": "content_block_delta",
    "index": 0,
    "delta": {
      "type": "text_delta",
      "text": "Hello"    // <-- This is the text to output
    }
  }
}

// 5. Stream event: content_block_stop
{
  "type": "stream_event",
  "session_id": "550e8400-...",
  "event": { "type": "content_block_stop", "index": 0 }
}

// 6. Stream event: message_delta (stop reason)
{
  "type": "stream_event",
  "session_id": "550e8400-...",
  "event": {
    "type": "message_delta",
    "delta": { "stop_reason": "end_turn" }
  }
}

// 7. Stream event: message_stop
{
  "type": "stream_event",
  "session_id": "550e8400-...",
  "event": { "type": "message_stop" }
}

// 8. Assistant message (complete response -- can ignore, already streamed)
{
  "type": "assistant",
  "session_id": "550e8400-...",
  "message": {
    "content": [{ "type": "text", "text": "Hello, ..." }],
    "stop_reason": "end_turn"
  }
}

// 9. Result message (final, signals completion)
{
  "type": "result",
  "subtype": "success",
  "session_id": "550e8400-...",
  "is_error": false,
  "result": "Hello, ...",
  "total_cost_usd": 0.0234
}
```

### Complete Minimal Chat Loop (Phase 1 Target)

```python
"""Minimal Phase 1 implementation showing all components working together."""
import asyncio
import json
import sys

import typer
from rich.console import Console

app = typer.Typer()
console = Console()

# --- Pacing ---

PUNCTUATION = set(".,!?;:")

def char_delay(char: str, base_ms: float = 75.0) -> float:
    """Return delay in seconds for a character."""
    base = base_ms / 1000.0
    if char == "\n":
        return base * 3.0
    if char == " ":
        return base * 0.5
    if char in PUNCTUATION:
        return base * 1.5
    return base

# --- Bridge ---

async def stream_claude(prompt: str):
    """Yield text chunks from Claude Code stream-json output."""
    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--include-partial-messages",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stdout is not None

    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        if msg.get("type") != "stream_event":
            continue
        event = msg.get("event", {})
        if event.get("type") != "content_block_delta":
            continue
        delta = event.get("delta", {})
        if delta.get("type") != "text_delta":
            continue
        text = delta.get("text", "")
        if text:
            yield text

    await proc.wait()

# --- Main ---

async def _chat(prompt: str, delay_ms: float) -> None:
    first_token = True
    with console.status("[bold cyan]Thinking...", spinner="dots") as status:
        async for chunk in stream_claude(prompt):
            if first_token:
                status.stop()
                first_token = False
            for char in chunk:
                sys.stdout.write(char)
                sys.stdout.flush()
                await asyncio.sleep(char_delay(char, delay_ms))
    print()  # Final newline

@app.command()
def chat(
    prompt: str = typer.Argument(..., help="Prompt to send to Claude"),
    delay: float = typer.Option(75.0, "--delay", "-d", help="Base delay in ms (50-100)"),
):
    """Send a prompt to Claude and watch the response appear character by character."""
    asyncio.run(_chat(prompt, delay))

if __name__ == "__main__":
    app()
```

### pyproject.toml for Phase 1

```toml
# Source: https://docs.astral.sh/uv/concepts/projects/init/
[project]
name = "claude-teletype"
version = "0.1.0"
description = "Typewriter-paced Claude Code output for terminal and dot-matrix printers"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "typer>=0.23.0",
    "rich>=14.0.0",
]

[project.scripts]
claude-teletype = "claude_teletype.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `subprocess.Popen` + threading for async | `asyncio.create_subprocess_exec` | Python 3.4+ (mature) | No threads, no deadlock risk, native event loop |
| pip + venv + requirements.txt | uv (project, venv, lock, Python version) | 2024-2025 | 10-100x faster installs, single tool for everything |
| argparse / Click for CLIs | Typer (wraps Click with type hints) | 2020+ (mature) | Less boilerplate, auto --help, type validation |
| flake8 + black + isort | ruff (single tool) | 2023+ (mature) | 100x faster, single config, replaces three tools |
| Claude Code `--print` text output | `--output-format stream-json` with `--include-partial-messages` | 2025 | Token-level streaming via NDJSON, programmatic parsing |

**Deprecated/outdated:**
- `subprocess.Popen` with sync I/O for concurrent tasks -- replaced by asyncio subprocess
- `simpleaudio` -- abandoned since 2019, not relevant to Phase 1 but noted for future
- `poetry` -- being superseded by uv for new projects

## Open Questions

1. **Token granularity of text_delta events**
   - What we know: Each `text_delta` contains one or more characters (a token). Tokens vary from single characters to full words.
   - What's unclear: The exact distribution of token sizes from Claude Code in practice. Are most tokens single words? Multi-word? This affects perceived smoothness of the typewriter effect.
   - Recommendation: Accept variable-length chunks in bridge, always iterate character-by-character in pacer. Test with real Claude responses to tune base delay. If tokens are large (5+ chars), the effect will look chunky at inter-character level but smooth at the reading level.

2. **Ctrl+C handling during streaming**
   - What we know: User may want to interrupt a long response. The subprocess needs clean termination.
   - What's unclear: Does `asyncio.run()` handle KeyboardInterrupt cleanly with the subprocess? Does the Claude Code process get terminated or orphaned?
   - Recommendation: Add a `try/finally` block in the chat function to call `proc.terminate()` and `proc.wait()` on interruption. Test manually. Can be refined in implementation.

3. **Error handling for Claude Code failures**
   - What we know: The `result` message has `subtype: "error_during_execution"` and `is_error: true` for failures.
   - What's unclear: What stderr output looks like during failures. Whether Claude Code ever writes to stderr during normal operation.
   - Recommendation: Capture stderr but do not display it during normal operation. On process exit with non-zero code, display stderr content. Handle `result` messages with `is_error: true` by printing a clear error message.

4. **Whether --verbose flag is required for stream events**
   - What we know: Official docs show `--verbose --include-partial-messages` together. The `--verbose` flag "enables verbose logging, shows full turn-by-turn output."
   - What's unclear: Whether `stream_event` messages are emitted without `--verbose`. The docs always show both flags together.
   - Recommendation: Use both flags as documented. If testing reveals `--verbose` adds unwanted extra output, try without it. The `--include-partial-messages` flag is the critical one for token-level streaming.

## Sources

### Primary (HIGH confidence)
- [Claude Code CLI Reference](https://code.claude.com/docs/en/cli-reference) -- Official flag documentation for `--output-format stream-json`, `--verbose`, `--include-partial-messages`, `-p`, `--resume`
- [Claude Code Headless Docs](https://code.claude.com/docs/en/headless) -- Official streaming example with jq filter for text_delta extraction
- [Claude Agent SDK Streaming Output](https://platform.claude.com/docs/en/agent-sdk/streaming-output) -- Official event sequence documentation: message_start -> content_block_start -> content_block_delta -> content_block_stop -> message_delta -> message_stop
- [Claude Agent SDK Spec (NDJSON)](https://gist.github.com/POWERFULMOVES/58bcadab9483bf5e633e865f131e6c25) -- Comprehensive NDJSON message type documentation with full JSON examples for system, assistant, user, result, and stream_event types
- [Python asyncio subprocess docs](https://docs.python.org/3/library/asyncio-subprocess.html) -- Official docs for `create_subprocess_exec`, `StreamReader.readline()`, `limit` parameter, deadlock warnings
- [uv Creating Projects](https://docs.astral.sh/uv/concepts/projects/init/) -- Official uv docs for `uv init --package`, src layout, pyproject.toml structure, `[project.scripts]` entry points

### Secondary (MEDIUM confidence)
- [Typer async issue #85](https://github.com/fastapi/typer/issues/85) -- Community patterns for Typer + asyncio integration; `asyncio.run()` wrapper is the standard approach
- [Typer async guide](https://pytutorial.com/python-typer-async-command-support-guide/) -- Documents Typer async support with `async def` commands and event loop management
- [How to Extract Text from Claude Code JSON Stream](https://www.ytyng.com/en/blog/claude-stream-json-jq/) -- Real-world example of parsing Claude Code stream-json with jq, confirms `.event.delta.text` path
- [asyncio subprocess streaming gist](https://gist.github.com/gh640/50953484edfa846fda9a95374df57900) -- Pattern for streaming subprocess output with `readline()` and `at_eof()` checks
- [Daktilo GitHub](https://github.com/orhun/daktilo) -- Reference for typewriter sound/timing patterns, TOML configuration, and variable tempo/volume

### Tertiary (LOW confidence)
- Typer native `async def` support -- Multiple sources claim Typer handles async commands automatically in recent versions, but the GitHub issue (#85) does not confirm this as a stable feature. Using `asyncio.run()` wrapper as the safe default.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries are stdlib or well-established (Typer, Rich), verified via official docs
- Architecture: HIGH -- asyncio subprocess + NDJSON parsing + character pacing is a straightforward pipeline with no exotic patterns
- Pitfalls: HIGH -- subprocess buffering, token granularity, and thinking indicator are well-documented concerns with clear mitigations
- NDJSON format: HIGH -- verified via official Agent SDK docs and community spec with corroborating real-world examples

**Research date:** 2026-02-14
**Valid until:** 2026-03-14 (stable domain -- asyncio subprocess and NDJSON format are unlikely to change)
