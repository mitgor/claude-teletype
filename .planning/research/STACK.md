# Technology Stack: v1.1 Conversation Mode

**Project:** Claude Teletype v1.1
**Researched:** 2026-02-16
**Focus:** Multi-turn conversation, word wrap, error handling
**Overall Confidence:** HIGH

---

## Key Finding: No New Dependencies Required

The v1.1 milestone needs **zero new pip packages**. Every capability -- multi-turn conversation via Claude Code CLI `--resume`, word wrap via a custom `WordWrapper` class using stdlib only, and error handling via stdlib `asyncio`/`shutil` patterns -- is already available through the existing stack or Python's standard library. No changes to `pyproject.toml`.

---

## Recommended Stack Changes

### 1. Multi-Turn Conversation: Claude Code CLI Session Management

**What changes:** The bridge module (`bridge.py`) currently spawns `claude -p <prompt>` as a one-shot command for each request. For multi-turn conversation, it needs to use Claude Code's built-in session continuity flags.

| Mechanism | CLI Flag | Purpose | Why |
|-----------|----------|---------|-----|
| Resume by ID | `--resume <id>` / `-r <id>` | Resume specific session by UUID | Deterministic; captures session_id from first response, passes it on subsequent calls |
| Session ID capture | Parse `system` init event | Get session_id from NDJSON stream | The `system` init event in stream-json includes `session_id` field (already present in test fixture `SYSTEM_INIT`) |
| Continue last session | `--continue` / `-c` | Resume most recent conversation in cwd | Simpler but fragile -- picks up wrong session if another runs in same directory. Use `--resume` instead. |
| Fork session | `--fork-session` | Branch from existing session | Useful future feature for "try a different approach" without losing original thread |

**Rationale:** Claude Code CLI already handles context window management, auto-truncation/compaction, and session storage internally (persisted to `~/.claude/sessions/`). The bridge does NOT need to implement its own message history, token counting, or truncation logic. This dramatically simplifies the implementation.

The bridge just needs to:
1. Parse `session_id` from the first `system` init event in the NDJSON stream
2. Store that session_id on the bridge/app instance
3. Pass `--resume <id>` on subsequent calls within the same conversation

**Auto-truncation is handled by Claude Code:** When a conversation approaches the context window limit, Claude Code automatically compacts/summarizes earlier messages. No client-side token counting needed.

**Confidence:** HIGH -- verified against official Claude Code docs at https://code.claude.com/docs/en/cli-reference and https://code.claude.com/docs/en/headless. The `--resume` + `-p` pattern is documented with working examples.

### 2. Word Wrap in TUI: Custom WordWrapper with Log Widget (NOT RichLog)

**CRITICAL FINDING: RichLog is NOT suitable for character-by-character streaming.**

After source code analysis of both widgets:

- **`Log.write(char)`** appends the character **inline to the current line** (`self._lines[-1] += char`). This is exactly what character-by-character typewriter streaming needs.
- **`RichLog.write(char)`** creates a **new renderable block per call** (`Segment.split_lines(segments)` -> `self.lines.extend(strips)`). Each single character would appear as a separate block/line.

Switching to `RichLog(wrap=True)` would completely break the typewriter effect. Each character would appear on its own line instead of flowing inline.

**Solution: Keep `Log` widget. Add a custom `WordWrapper` class** that sits between the pacer output and `Log.write()`. The wrapper tracks column position and inserts `\n` at word boundaries when approaching the terminal width.

| What | How | Why |
|------|-----|-----|
| Keep `Log` widget | No widget change | `Log.write(char)` provides inline append needed for character streaming |
| Add `WordWrapper` class | New ~40-line module or inline class | Tracks column position, buffers current word, inserts `\n` at word boundaries |
| Get terminal width | `self.query_one("#output", Log).size.width` in TUI | Wraps to actual widget width, not hardcoded |
| Handle resize | Re-read width on new stream | Width changes between prompts are fine; mid-stream resize is edge case |

**WordWrapper pattern (stdlib only):**

```python
class WordWrapper:
    """Character-level word wrapper for streaming output."""

    def __init__(self, width: int, inner: Callable[[str], None]):
        self._width = width
        self._inner = inner
        self._column = 0
        self._word_buf: list[str] = []

    def write(self, char: str) -> None:
        if char == "\n":
            self._flush_word()
            self._inner("\n")
            self._column = 0
        elif char == " ":
            self._flush_word()
            if self._column < self._width:
                self._inner(" ")
                self._column += 1
        else:
            self._word_buf.append(char)
            if len(self._word_buf) >= self._width:
                self._flush_word()

    def _flush_word(self) -> None:
        if not self._word_buf:
            return
        word_len = len(self._word_buf)
        if self._column + word_len > self._width and self._column > 0:
            self._inner("\n")
            self._column = 0
        for ch in self._word_buf:
            self._inner(ch)
        self._column += word_len
        self._word_buf.clear()
```

**Printer word wrap already exists:** `make_printer_output()` in `printer.py` already wraps at `A4_COLUMNS = 80`. No change needed for printer output.

**Alternatives rejected:**

| Alternative | Why Rejected |
|-------------|-------------|
| `RichLog(wrap=True)` | `write()` creates new block per call, breaks character-by-character streaming entirely |
| CSS `text-wrap: wrap` on `Log` | Textual's `text-wrap` CSS is documented for `Static` widgets only, not confirmed for `Log` |
| `textwrap.fill()` before write | Cannot apply to character-by-character stream; would need line buffering that breaks typewriter pacing |
| Custom widget subclassing `ScrollableContainer` | Over-engineered; a 40-line wrapper class achieves the same result |

**Confidence:** HIGH -- verified by reading actual Textual source code for both `Log._log.py` and `RichLog._rich_log.py` on GitHub. `Log.write()` does `self._lines[-1] += line` (inline append). `RichLog.write()` does `self.lines.extend(strips)` (new blocks).

### 3. Error Handling: Python Standard Library Only

**What changes:** No new dependencies. Use stdlib `asyncio` patterns and structured exception handling.

| Error Category | Current Handling | v1.1 Improvement | Implementation |
|----------------|-----------------|-------------------|----------------|
| Claude Code not installed | Subprocess fails, no response shown | Check `shutil.which("claude")` before spawning, show install URL | stdlib `shutil` |
| Non-zero exit code | `proc.wait()` called but return code ignored | Check `proc.returncode`, read stderr for error details | stdlib `asyncio.subprocess` |
| Network failure mid-stream | Generic `except Exception` in TUI worker | Parse error events from NDJSON stream, surface specific messages | Parse `type: "error"` and `type: "result", "is_error": true` events |
| Process hang/timeout | No timeout (blocks forever) | `asyncio.wait_for()` with configurable timeout on readline | stdlib `asyncio` |
| Graceful subprocess shutdown | `proc.terminate()` then `proc.wait()` | SIGTERM -> wait(5s) -> SIGKILL escalation pattern | stdlib `asyncio`, `signal` |
| Session resume failure | N/A (new feature) | Try `--resume`, if error, fall back to new session | Retry without `--resume` flag |
| Empty response | "No response received" message | Distinguish "no tokens" from "error" by checking exit code and stderr | Check both stream content and process exit |

**Error events in NDJSON stream:** The Claude Code CLI stream-json format includes error-type events that the bridge should parse in addition to `text_delta`:

```python
# Events to handle:
# {"type": "error", "error": {"message": "...", "type": "..."}}
# {"type": "result", "subtype": "error", "is_error": true, "error": "..."}
# Non-zero proc.returncode with stderr content
```

**Confidence:** HIGH -- standard Python patterns, no external dependencies.

---

## Existing Stack (No Changes Needed)

Confirmed adequate for v1.1. Do NOT upgrade or replace.

| Technology | Version | Purpose | v1.1 Status |
|------------|---------|---------|-------------|
| Python | >=3.12 | Runtime | No change |
| typer | >=0.23.0 | CLI argument parsing | No change |
| rich | >=14.0.0 | Console spinners, formatting | No change |
| textual | >=7.0.0 | TUI framework (Log widget) | No change (keep Log, do NOT switch to RichLog) |
| sounddevice | >=0.5.0 | Audio bell | No change |
| numpy | >=1.26.0 | Bell waveform generation | No change |
| pyusb | >=1.3.0 | USB printer (optional) | No change |
| pytest | >=9.0.2 | Testing | No change |
| pytest-asyncio | >=1.3.0 | Async test support | No change |
| ruff | >=0.15.1 | Linting | No change |
| hatchling | (build) | Build system | No change |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Multi-turn context | Claude Code `--resume <id>` | Manual message history + re-send via `--input-format stream-json` | Unnecessary complexity; Claude Code manages context, truncation, session persistence internally. Our own message list means token count disagreements and duplicated state. |
| Multi-turn context | `--resume <id>` (explicit) | `--continue` (implicit) | `--continue` picks most recent session in cwd. Fragile if another Claude session runs in same directory. `--resume` is deterministic. |
| Word wrap (TUI) | Custom `WordWrapper` + `Log` | `RichLog(wrap=True)` | **RichLog.write() creates new block per call, incompatible with char-by-char streaming.** Log.write() does inline append. |
| Word wrap (TUI) | Custom `WordWrapper` + `Log` | `Log` + `textwrap.fill()` | Cannot apply `textwrap` to character stream. Would need line buffering that breaks typewriter pacing. |
| Word wrap (TUI) | Custom `WordWrapper` + `Log` | CSS `text-wrap: wrap` on `Log` | Not documented for `Log` widget. Only confirmed for `Static`. |
| Token counting | Delegate to Claude Code CLI | `tiktoken` or `anthropic-tokenizer` | Claude Code handles limits internally. Client-side counting adds dependency and disagreement risk. |
| Error handling | stdlib patterns | `tenacity` retry library | Overkill; retries should be user-initiated in a conversation UI, not automatic. |
| Session storage | Claude Code's `~/.claude/sessions/` | SQLite or file-based store | Redundant; we only need a single `session_id` string in memory. |

---

## What NOT to Add

These libraries are explicitly NOT needed for v1.1:

| Library | Why Not |
|---------|---------|
| `tiktoken` / `anthropic-tokenizer` | Claude Code CLI manages context limits via auto-compaction. Client-side counting would disagree with server. |
| `tenacity` | Retries should be user-initiated in conversation UI. Automatic retries risk duplicate messages. |
| `prompt_toolkit` | Textual's `Input` widget is sufficient. prompt_toolkit conflicts with Textual's event loop. |
| `anthropic` Python SDK | We wrap CLI, not API. SDK would create parallel auth/error/streaming code paths. |
| `aiofiles` | Transcript writes are sync, char-by-char, buffered on newline. Fast enough at typewriter speed. |
| `pydantic` | No complex data models. Session state is one UUID string. |
| `dataclasses` (for message history) | We are NOT building message history. Claude Code owns conversation state. (Note: `dataclass` may be used for `StreamResult`, but that is stdlib, not a new dependency.) |

---

## Integration Points

### bridge.py: Session-Aware Streaming

```python
# Current signature:
async def stream_claude_response(prompt: str) -> AsyncIterator[str]:

# v1.1 signature adds session_id parameter and StreamResult yield:
async def stream_claude_response(
    prompt: str,
    session_id: str | None = None,
) -> AsyncIterator[str | StreamResult]:
    """Yield text chunks, then a final StreamResult with session metadata."""
```

New parsers (session_id already in test fixture `SYSTEM_INIT`):

```python
def parse_session_id(line: bytes) -> str | None:
    """Extract session_id from the system init NDJSON line."""
    # msg.get("type") == "system" and msg.get("subtype") == "init"
    # -> return msg.get("session_id")

def parse_error(line: bytes) -> str | None:
    """Extract error message from error/result events."""
    # msg.get("type") == "error" -> msg["error"]["message"]
    # msg.get("type") == "result" and msg.get("is_error") -> msg["error"]
```

CLI args with `--resume`:

```python
args = ["claude", "-p", prompt, "--output-format", "stream-json",
        "--verbose", "--include-partial-messages",
        "--dangerously-skip-permissions",
        "--allowedTools", "WebSearch", "--allowedTools", "WebFetch"]
if session_id:
    args.extend(["--resume", session_id])
```

### tui.py: Session State + WordWrapper

```python
# NO widget change -- keep Log:
from textual.widgets import Footer, Header, Input, Log

# Add session state:
self._session_id: str | None = None

# In stream_response, wrap log.write with WordWrapper:
from claude_teletype.wrap import WordWrapper
log = self.query_one("#output", Log)
wrapped_write = WordWrapper(width=log.size.width, inner=log.write).write
destinations = [wrapped_write]  # Instead of [log.write]
```

### cli.py: Interactive Loop for --no-tui Mode

```python
# After first response, enter REPL loop:
while True:
    try:
        prompt = input("\n> ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if not prompt:
        continue
    await _chat_async(prompt, delay, session_id=session_id, ...)
```

### Startup validation:

```python
import shutil
if shutil.which("claude") is None:
    console.print("[bold red]Error: claude CLI not found.")
    console.print("Install: https://code.claude.com/docs/en/quickstart")
    raise typer.Exit(1)
```

---

## pyproject.toml Changes

**None.** The dependencies section stays exactly as-is:

```toml
# No changes needed
dependencies = [
    "typer>=0.23.0",
    "rich>=14.0.0",
    "textual>=7.0.0",
    "sounddevice>=0.5.0",
    "numpy>=1.26.0",
]
```

---

## Installation

No changes to install commands:

```bash
uv sync              # Core (unchanged)
uv sync --extra usb  # With USB printer support (unchanged)
uv sync --group dev  # Dev dependencies (unchanged)
```

---

## Risk Assessment for v1.1

| Area | Risk | Mitigation |
|------|------|------------|
| WordWrapper edge cases (long words, tab chars, wide Unicode) | MEDIUM | Test with: URLs (no spaces), code blocks (backticks), emoji. Long words without spaces get force-broken at width. Tab chars treated as single column (good enough). |
| Session resume with `--resume` on stale/expired sessions | MEDIUM | Claude Code may fail if session is too old or corrupted. Catch error, fall back to fresh session, inform user. |
| `Log.write(char)` performance with long conversations | LOW | Log widget uses LRUCache for rendered lines. At 75ms/char, throughput is ~13 chars/sec. No performance issue. |
| `--continue` picks wrong session | LOW | Avoided entirely by using `--resume <id>` with explicit session ID. |
| Claude Code auto-compaction changes response quality | LOW | Claude Code's problem. Long conversations get summarized context. User can start fresh conversation. |
| WordWrapper width vs actual Log widget width | LOW | Read `log.size.width` at start of each stream. Width changes mid-stream are rare; next prompt picks up new width. |

---

## Sources

- Claude Code CLI Reference (official): https://code.claude.com/docs/en/cli-reference
  - `--continue`, `--resume`, `--session-id`, `--fork-session` flags
  - `--output-format stream-json` event format with session_id
  - Confidence: HIGH

- Claude Code Headless/Programmatic Usage (official): https://code.claude.com/docs/en/headless
  - Session continuation: `claude -p "query" --resume "$session_id"`
  - Session ID capture from JSON output
  - Confidence: HIGH

- Textual Log Widget source code: https://github.com/Textualize/textual/blob/main/src/textual/widgets/_log.py
  - `write()` does `self._lines[-1] += line` (inline append) -- confirmed suitable for char streaming
  - Confidence: HIGH (source code verified)

- Textual RichLog Widget source code: https://github.com/Textualize/textual/blob/main/src/textual/widgets/_rich_log.py
  - `write()` does `Segment.split_lines()` -> `self.lines.extend(strips)` (new block per call) -- NOT suitable for char streaming
  - Confidence: HIGH (source code verified)

- Textual RichLog docs (official): https://textual.textualize.io/widgets/rich_log/
  - `wrap=True` parameter exists but irrelevant since widget itself is incompatible
  - Confidence: HIGH

- Textual Log Widget docs (official): https://textual.textualize.io/widgets/log/
  - No built-in word wrap -- manual wrapper needed
  - Confidence: HIGH

- Claude Code SDK Python Error Handling: https://deepwiki.com/anthropics/claude-code-sdk-python/4-error-handling
  - ProcessError, CLIJSONDecodeError, CLINotFoundError hierarchy
  - Confidence: MEDIUM (third-party documentation of official SDK)

- Claude API Context Windows (official): https://platform.claude.com/docs/en/build-with-claude/context-windows
  - 200K token standard context, auto-compaction for long sessions
  - Confidence: HIGH
