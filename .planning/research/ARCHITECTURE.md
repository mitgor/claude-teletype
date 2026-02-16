# Architecture Research: Multi-Turn Conversation Integration

**Domain:** Multi-turn conversation mode for existing Python CLI/TUI wrapping Claude Code CLI
**Researched:** 2026-02-16
**Confidence:** HIGH (official Claude Code docs confirm all required CLI flags; existing codebase is well-understood; changes are surgical)

## Executive Summary

Multi-turn conversation requires three changes to the existing architecture: (1) the bridge must capture session IDs from the NDJSON init message and pass `--resume <session_id>` on subsequent calls, (2) the TUI and CLI must hold session state across prompt submissions, and (3) error handling must surface structured errors from both subprocess failures and NDJSON result messages. The existing fan-out architecture (pacer -> output -> destinations) does NOT need to change. The bridge signature changes from `stream_claude_response(prompt)` to `stream_claude_response(prompt, session_id=None)` returning `(session_id, AsyncIterator[str])`, and callers (TUI and CLI) store the returned session_id for the next call.

## Current Architecture (As-Built)

### System Overview

```
[User Input]
    |
    v
[cli.py] ----prompt----> [bridge.py] --spawn--> claude -p "prompt" --output-format stream-json
    |                         |
    |                    yields str chunks
    |                         |
    v                         v
[tui.py / _chat_async]  [pacer.py] --char-by-char--> [output.py] --fan-out--> destinations
                                                          |
                                          +---------------+---------------+
                                          |               |               |
                                     [Log.write]   [printer_write]  [bell/transcript]
```

### Key Characteristics of Current Design

1. **bridge.py** spawns a NEW `claude -p` subprocess per prompt. No session continuity.
2. **bridge.py** only extracts `text_delta` from `content_block_delta` events. It ignores the `system` init message (which contains `session_id`), `result` messages, and all error states.
3. **tui.py** calls `stream_claude_response(prompt)` in a `@work(exclusive=True)` decorated method. Each call is stateless.
4. **cli.py** `_chat_async()` calls `stream_claude_response(prompt)` once and exits.
5. The fan-out layer (output.py + pacer.py) is purely a character pipeline -- it has no knowledge of sessions, prompts, or conversation state.

## Multi-Turn Strategy: `--resume` with Session ID

### Why `--resume` (Not `--continue` or Persistent Subprocess)

Three approaches were evaluated:

| Approach | Mechanism | Verdict |
|----------|-----------|---------|
| **A. `--resume <session_id>`** | Each prompt spawns a new `claude -p --resume <id>` subprocess. Claude Code loads full conversation history from its own session storage. | **USE THIS.** Clean, stateless from our perspective. Claude manages context. |
| **B. `--continue`** | Uses most recent session in current directory. No explicit ID. | Fragile in automation. If another Claude session runs in the same directory, `--continue` picks up the wrong session. Official docs recommend `--resume` over `--continue` for programmatic use. |
| **C. Persistent subprocess** | Keep one `claude` process alive, pipe prompts via stdin with `--input-format stream-json`. | Tempting but risky: hangs, zombie processes, unclear lifecycle. Claude Code's `--input-format stream-json` is designed for SDK use, not raw stdin piping. Adds complexity with no clear benefit over A. |

**Decision: Approach A.** Use `--resume <session_id>` for all follow-up prompts. The bridge captures the session_id from the first NDJSON `system` init message and passes it to subsequent calls.

### How Claude Code Sessions Work (Verified)

From official documentation at [code.claude.com/docs/en/headless](https://code.claude.com/docs/en/headless):

```bash
# First request -- no session ID, Claude creates one
claude -p "Review this codebase" --output-format stream-json --verbose --include-partial-messages

# The NDJSON stream starts with:
# {"type": "system", "subtype": "init", "session_id": "550e8400-...", ...}

# Subsequent requests -- resume with captured session ID
claude -p "Now focus on the database queries" --resume "550e8400-..." --output-format stream-json ...
```

Key facts (HIGH confidence, official docs):
- Session ID appears in the FIRST NDJSON line (`type: "system"`, `subtype: "init"`)
- `--resume <session_id>` loads full conversation history including tool results
- Can combine `-p` + `--resume` + `--output-format stream-json` (explicitly documented)
- Session data is stored by Claude Code in `~/.claude/sessions/`
- Claude Code handles context window management and auto-truncation internally

## Recommended Architecture Changes

### Component: bridge.py (MODIFY)

The bridge needs three changes:

**Change 1: Parse the system init message to extract session_id.**

Currently `parse_text_delta` only looks for `stream_event` with `content_block_delta`. Add a new parser function:

```python
def parse_session_id(line: bytes) -> str | None:
    """Extract session_id from the system init NDJSON line."""
    if not line or not line.strip():
        return None
    try:
        msg = json.loads(line.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if msg.get("type") == "system" and msg.get("subtype") == "init":
        return msg.get("session_id")
    return None
```

**Change 2: Parse the result message for error detection.**

```python
def parse_result(line: bytes) -> dict | None:
    """Extract result message fields (is_error, result, cost)."""
    if not line or not line.strip():
        return None
    try:
        msg = json.loads(line.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if msg.get("type") == "result":
        return {
            "is_error": msg.get("is_error", False),
            "result": msg.get("result", ""),
            "cost_usd": msg.get("total_cost_usd"),
            "subtype": msg.get("subtype", ""),
        }
    return None
```

**Change 3: Modify `stream_claude_response` signature.**

Current:
```python
async def stream_claude_response(prompt: str) -> AsyncIterator[str]:
```

Proposed:
```python
@dataclass
class StreamResult:
    session_id: str | None
    is_error: bool
    error_message: str | None
    cost_usd: float | None

async def stream_claude_response(
    prompt: str,
    session_id: str | None = None,
) -> AsyncIterator[str | StreamResult]:
```

The function yields `str` chunks for text deltas as before, and yields a single `StreamResult` as the final item. The caller can capture the session_id from the StreamResult for the next call.

**Alternative (simpler):** Return a tuple `(session_id, AsyncIterator[str])` where session_id is populated after the first line is read. But async generators cannot "return" values alongside yielding. The cleanest pattern is:

```python
async def stream_claude_response(
    prompt: str,
    session_id: str | None = None,
) -> AsyncIterator[str | StreamResult]:
    """Yield text chunks, then a final StreamResult with session metadata."""
    args = ["claude", "-p", prompt, "--output-format", "stream-json",
            "--verbose", "--include-partial-messages",
            "--dangerously-skip-permissions",
            "--allowedTools", "WebSearch", "--allowedTools", "WebFetch"]

    if session_id is not None:
        args.extend(["--resume", session_id])

    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

    captured_session_id = None
    result_info = None

    try:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break

            # Try session ID extraction (first message only)
            if captured_session_id is None:
                sid = parse_session_id(line)
                if sid is not None:
                    captured_session_id = sid
                    continue

            # Try result extraction (last message)
            res = parse_result(line)
            if res is not None:
                result_info = res
                continue

            # Normal text delta
            text = parse_text_delta(line)
            if text is not None:
                yield text

        await proc.wait()

        yield StreamResult(
            session_id=captured_session_id,
            is_error=result_info["is_error"] if result_info else (proc.returncode != 0),
            error_message=result_info["result"] if result_info and result_info["is_error"] else None,
            cost_usd=result_info["cost_usd"] if result_info else None,
        )
    except BaseException:
        proc.terminate()
        await proc.wait()
        raise
```

### Component: tui.py (MODIFY)

The TUI needs to hold session state across prompt submissions.

**Change 1: Add session_id instance variable.**

```python
class TeletypeApp(App):
    def __init__(self, ...):
        ...
        self._session_id: str | None = None  # NEW: persists across prompts
```

**Change 2: Update stream_response to pass and capture session_id.**

```python
@work(exclusive=True)
async def stream_response(self, prompt: str) -> None:
    ...
    async for item in stream_claude_response(prompt, session_id=self._session_id):
        if isinstance(item, StreamResult):
            self._session_id = item.session_id  # Capture for next prompt
            if item.is_error:
                log.write(f"\n[Error: {item.error_message}]\n")
        else:
            await pace_characters(item, base_delay_ms=self.base_delay_ms, output_fn=output_fn)
    ...
```

**No change needed to:** `on_input_submitted`, `on_mount`, `on_unmount`, fan-out destinations, or any printer/audio/transcript logic. The session state lives only in the TUI app instance and is passed through the bridge.

### Component: cli.py (MODIFY -- for --no-tui multi-turn only)

Currently `_chat_async()` handles a single prompt. For multi-turn in non-TUI mode, add a REPL loop. This is a lower priority than TUI multi-turn since the TUI is the primary interface.

```python
async def _chat_loop_async(base_delay_ms, printer, no_audio, transcript_dir):
    """Interactive multi-turn REPL for --no-tui mode."""
    session_id = None
    while True:
        try:
            prompt = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not prompt:
            continue

        async for item in stream_claude_response(prompt, session_id=session_id):
            if isinstance(item, StreamResult):
                session_id = item.session_id
                if item.is_error:
                    console.print(f"[bold red]Error: {item.error_message}")
            else:
                await pace_characters(item, ...)
        print()
```

### Components NOT Modified

| Component | Why No Change |
|-----------|---------------|
| **pacer.py** | Receives text chunks, has no knowledge of sessions. No change. |
| **output.py** | Fan-out to destinations. Character-level. No change. |
| **audio.py** | Receives characters, plays bell on newline. No change. |
| **transcript.py** | Receives characters, writes to file. No change. |
| **printer.py** | All printer drivers and discovery. No change. |
| **teletype.py** | Raw keyboard-to-printer mode. No change. |

This is the key architectural strength: the fan-out pipeline is completely decoupled from conversation state.

## New Component: Word Wrap

### Problem

The current TUI uses `Log` widget which does NOT support word wrapping. Long lines extend beyond the visible area. For a typewriter aesthetic, text must wrap at word boundaries.

### Options Evaluated

| Option | Approach | Verdict |
|--------|----------|---------|
| **RichLog with wrap=True** | Replace `Log` with `RichLog(wrap=True)` | RichLog's `write()` expects complete renderables, not character-by-character. Would need to buffer lines and write them whole. Breaks the character-by-character pacing model. |
| **Manual word wrap in output pipeline** | Add a wrap function between pacer and Log.write | Best option. Wrap happens at the character level, fits existing architecture. Log widget continues receiving pre-wrapped text. |
| **CSS text-wrap** | Apply `text-wrap: wrap` CSS to Log widget | Textual's Log widget does not respect text-wrap CSS (it is a virtual widget that manages its own line rendering). |

**Decision: Manual word wrap in the output pipeline.** Add a `WordWrapper` that sits between the pacer and the Log destination. It tracks column position and inserts `\n` at word boundaries when approaching the terminal width.

### Word Wrap Architecture

```python
class WordWrapper:
    """Tracks column position and wraps at word boundaries."""

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
            # If word alone exceeds width, force break
            if len(self._word_buf) >= self._width:
                self._flush_word()

    def _flush_word(self) -> None:
        word_len = len(self._word_buf)
        if word_len == 0:
            return
        # Would this word overflow the line?
        if self._column + word_len > self._width and self._column > 0:
            self._inner("\n")
            self._column = 0
        for ch in self._word_buf:
            self._inner(ch)
        self._column += word_len
        self._word_buf.clear()
```

The WordWrapper is inserted as a destination wrapper in the TUI's `stream_response`:

```python
# In tui.py stream_response:
log_write = WordWrapper(width=self.size.width, inner=log.write).write
destinations = [log_write]  # Wrapped log.write replaces raw log.write
```

For the printer, word wrapping already exists in `make_printer_output` (wraps at `A4_COLUMNS = 80`). No change needed there.

## New Component: Error Handling

### Error Sources

| Source | How It Manifests | Current Handling | Needed |
|--------|------------------|------------------|--------|
| Claude Code not installed | `FileNotFoundError` from `create_subprocess_exec` | Crash | Catch, show "Claude Code not found" |
| Claude Code not authenticated | Non-zero exit code, stderr message | Silent failure (no output) | Parse stderr, show auth error |
| NDJSON result with `is_error: true` | Result message in stream | Ignored | Parse and surface |
| Network error during response | Subprocess exits mid-stream | Stream ends, no error shown | Detect incomplete stream |
| Invalid session ID on `--resume` | Non-zero exit code | Crash or silent | Catch, fall back to new session |
| Process timeout | Subprocess hangs | Never resolves | Add optional timeout |

### Error Handling Architecture

Errors should be surfaced through the `StreamResult` dataclass that the bridge already yields as the final item. The callers (TUI and CLI) check `StreamResult.is_error` and display appropriately.

For subprocess launch failures (FileNotFoundError, PermissionError), wrap the `create_subprocess_exec` call:

```python
try:
    proc = await asyncio.create_subprocess_exec(...)
except FileNotFoundError:
    yield StreamResult(
        session_id=None,
        is_error=True,
        error_message="Claude Code CLI not found. Install from https://code.claude.com",
        cost_usd=None,
    )
    return
```

For stderr capture on non-zero exit:

```python
await proc.wait()
if proc.returncode != 0 and result_info is None:
    stderr_output = await proc.stderr.read()
    error_msg = stderr_output.decode("utf-8", errors="replace").strip()
    yield StreamResult(
        session_id=captured_session_id,
        is_error=True,
        error_message=error_msg or f"Claude exited with code {proc.returncode}",
        cost_usd=None,
    )
    return
```

## Updated Data Flow: Multi-Turn

### First Prompt (No Session)

```
[User types prompt, presses Enter]
    |
    v
[tui.py] on_input_submitted(prompt)
    |-- self._session_id is None
    |
    v
[bridge.py] stream_claude_response(prompt, session_id=None)
    |-- spawns: claude -p "prompt" --output-format stream-json ...
    |-- NDJSON line 1: {"type":"system","subtype":"init","session_id":"abc-123",...}
    |-- captures session_id = "abc-123"
    |-- NDJSON lines: stream_event/content_block_delta -> yield text chunks
    |-- NDJSON last: {"type":"result","is_error":false,...}
    |-- yield StreamResult(session_id="abc-123", is_error=False, ...)
    |
    v
[tui.py] stream_response
    |-- for each str chunk: pace_characters -> output_fn -> [log, printer, bell, transcript]
    |-- for StreamResult: self._session_id = "abc-123"
```

### Second Prompt (With Session)

```
[User types follow-up, presses Enter]
    |
    v
[tui.py] on_input_submitted(prompt)
    |-- self._session_id is "abc-123"
    |
    v
[bridge.py] stream_claude_response(prompt, session_id="abc-123")
    |-- spawns: claude -p "prompt" --resume "abc-123" --output-format stream-json ...
    |-- Claude Code loads full conversation history internally
    |-- Response has full context of previous turns
    |-- yield StreamResult(session_id="abc-123", ...)
    |
    v
[tui.py] stream_response
    |-- same fan-out as before, session_id unchanged (or updated if Claude returns new one)
```

### Error Flow

```
[bridge.py] stream_claude_response(prompt, session_id="invalid-id")
    |-- spawns: claude -p "prompt" --resume "invalid-id" ...
    |-- Claude exits with non-zero code
    |-- stderr: "Session not found"
    |-- yield StreamResult(session_id=None, is_error=True, error_message="Session not found")
    |
    v
[tui.py] stream_response
    |-- detects is_error=True
    |-- log.write("[Error: Session not found]")
    |-- self._session_id = None  (reset to start fresh next time)
```

## Component Boundary Summary

### Modified Components

| Component | What Changes | Lines of Change (est.) |
|-----------|-------------|----------------------|
| **bridge.py** | Add `parse_session_id()`, `parse_result()`, `StreamResult` dataclass. Modify `stream_claude_response()` signature to accept `session_id` and yield `StreamResult`. Add `--resume` flag injection. Add subprocess error handling. | ~60 lines added, ~15 lines modified |
| **tui.py** | Add `self._session_id` state. Update `stream_response` to pass session_id, capture from StreamResult, handle errors. | ~15 lines modified |
| **cli.py** | Update `_chat_async()` to handle StreamResult. Optionally add `_chat_loop_async()` for multi-turn REPL in --no-tui mode. | ~20-40 lines |

### New Components

| Component | Purpose | Size (est.) |
|-----------|---------|-------------|
| **wrap.py** (or inline in tui.py) | WordWrapper class for TUI output word wrapping | ~40 lines |

### Unchanged Components

| Component | Why |
|-----------|-----|
| pacer.py | Character-level pacing. No session awareness needed. |
| output.py | Fan-out multiplexer. No session awareness needed. |
| audio.py | Bell sound on newlines. No session awareness needed. |
| transcript.py | File writer. No session awareness needed. |
| printer.py | All printer drivers and discovery. No session awareness needed. |
| teletype.py | Raw keyboard mode. Completely independent. |

## Patterns to Follow

### Pattern 1: Session State Lives at the Caller Level

**What:** Session ID is stored by the caller (TUI app or CLI loop), not by the bridge. The bridge is stateless -- it receives session_id as a parameter and returns it in the result.

**Why:** The bridge spawns a new subprocess per call. There is no persistent state to hold. The TUI app instance lives for the duration of the session, making it the natural owner of session state.

**Example:**
```python
# Good: Caller holds state
class TeletypeApp(App):
    _session_id: str | None = None

    async def stream_response(self, prompt):
        async for item in stream_claude_response(prompt, session_id=self._session_id):
            if isinstance(item, StreamResult):
                self._session_id = item.session_id

# Bad: Bridge holds state (stateful module-level variable)
_global_session_id = None  # Don't do this
```

### Pattern 2: Union Yield Type for Metadata-in-Stream

**What:** The async generator yields `str | StreamResult` -- text chunks during streaming, metadata at the end. The caller uses `isinstance()` to distinguish.

**Why:** Avoids complex return types from async generators (which can only return via `StopAsyncIteration`). Keeps the streaming interface simple. The StreamResult is always the last item, so callers can handle it in a straightforward if/else.

### Pattern 3: Graceful Degradation on Session Errors

**What:** If `--resume` fails (invalid session, session expired), reset session_id to None and inform the user. Do not crash. The next prompt starts a fresh session.

**Why:** Session storage is managed by Claude Code, not by us. Sessions can expire, be deleted, or become invalid. The user should not have to restart the app.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Managing Conversation History Ourselves

**What:** Building a list of `{"role": "user"/"assistant", "content": "..."}` messages and passing them to Claude somehow.

**Why bad:** Claude Code already manages conversation history via its session persistence. Duplicating this logic means maintaining context window limits, truncation strategy, and message formatting -- all of which Claude Code handles internally.

**Instead:** Use `--resume <session_id>`. Let Claude Code manage the conversation.

### Anti-Pattern 2: Persistent Subprocess with stdin Piping

**What:** Keeping one `claude` subprocess alive and writing prompts to its stdin.

**Why bad:** No clean shutdown semantics. Zombie process risk. Error recovery requires killing and restarting the process. The `--input-format stream-json` stdin mode is designed for the Agent SDK, not for manual piping. Risk of hangs (documented in [GitHub issue #3187](https://github.com/anthropics/claude-code/issues/3187)).

**Instead:** Spawn a new subprocess per prompt with `--resume`. Clean lifecycle per request.

### Anti-Pattern 3: Storing Session ID in a File

**What:** Writing session_id to a file so it persists across app restarts.

**Why bad:** Unnecessary complexity. Claude Code already stores sessions in `~/.claude/sessions/`. If the user wants to resume a previous conversation, they can use the `--resume` flag themselves, or we can add a `--resume` CLI flag later that passes through to Claude. The app's session_id only needs to live in memory for the current run.

**Instead:** Store session_id as an instance variable. Fresh session on app restart.

## Build Order for Multi-Turn Integration

The dependency chain dictates this order:

```
Step 1: bridge.py — StreamResult + parse_session_id + parse_result + --resume flag
    |   (Foundation. Can test in isolation with mock subprocess.)
    |   (All existing tests continue to pass -- new functionality is additive.)
    |
Step 2: tui.py — Session state + StreamResult handling + error display
    |   (Depends on Step 1. The TUI is the primary interface.)
    |
Step 3: cli.py — StreamResult handling in _chat_async + optional REPL loop
    |   (Depends on Step 1. Lower priority than TUI.)
    |
Step 4: wrap.py — WordWrapper for TUI output
    |   (Independent of Steps 1-3. Can be built in parallel.)
    |   (Only depends on knowing terminal width from TUI.)
    |
Step 5: Error handling polish
    |   (Depends on Steps 1-3. Adds edge case handling.)
    |   (FileNotFoundError, timeout, stderr parsing, session recovery.)
```

**Rationale:**
- Step 1 is the foundation. The bridge change is the smallest, most testable unit. All existing tests pass because the new `session_id` parameter defaults to `None` (backward compatible).
- Step 2 is the highest-value integration. Multi-turn in the TUI is the primary use case.
- Step 3 can be deferred if not needed immediately. The `--no-tui` mode is secondary.
- Step 4 (word wrap) is independent and can be done in parallel with Steps 2-3.
- Step 5 is polish that benefits from all paths being wired up.

## Sources

- [Claude Code CLI Reference](https://code.claude.com/docs/en/cli-reference) -- HIGH confidence. Official docs confirming `--resume`, `--continue`, `--session-id`, `-p` flag combinations.
- [Run Claude Code Programmatically (Headless)](https://code.claude.com/docs/en/headless) -- HIGH confidence. Official docs showing `claude -c -p "query"` and `session_id` capture pattern.
- [Agent SDK Session Management](https://platform.claude.com/docs/en/agent-sdk/sessions) -- HIGH confidence. Official docs for session ID lifecycle, forking, and resumption.
- [Agent SDK Streaming Output](https://platform.claude.com/docs/en/agent-sdk/streaming-output) -- HIGH confidence. Official StreamEvent reference with session_id field and event type documentation.
- [Textual Log Widget](https://textual.textualize.io/widgets/log/) -- HIGH confidence. Official docs confirming `write()` method for character-by-character output, no native word wrap.
- [Textual RichLog Widget](https://textual.textualize.io/widgets/rich_log/) -- HIGH confidence. Official docs confirming `wrap=True` parameter but renderable-level writes (not character-level).
- [Textual text-wrap CSS](https://textual.textualize.io/styles/text_wrap/) -- HIGH confidence. Official docs for CSS text-wrap property.
- [Claude Code GitHub Issue #3187](https://github.com/anthropics/claude-code/issues/3187) -- MEDIUM confidence. Documents stdin stream-json hangs.
- [Claude Code GitHub Issue #25629](https://github.com/anthropics/claude-code/issues/25629) -- MEDIUM confidence. Documents stream-json hanging after result event.
- [Claude Flow Stream Chaining Wiki](https://github.com/ruvnet/claude-flow/wiki/Stream-Chaining) -- MEDIUM confidence. Community-documented NDJSON message structure.

---
*Architecture research for: Claude Teletype multi-turn conversation integration*
*Researched: 2026-02-16*
