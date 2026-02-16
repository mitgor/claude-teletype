# Phase 5: Multi-Turn Conversation Foundation - Research

**Researched:** 2026-02-16
**Domain:** Multi-turn conversation loop, session persistence, TUI state management, subprocess lifecycle
**Confidence:** HIGH

## Summary

Phase 5 transforms the one-shot prompt/response TUI into a persistent multi-turn conversation. The core mechanism is Claude Code CLI's `--resume <session_id>` flag: the bridge captures `session_id` from the first NDJSON `system/init` message, stores it on the TUI app instance, and passes it on every subsequent `claude -p --resume <id>` invocation. Claude Code manages all conversation history, context compaction, and token limits internally -- our wrapper remains thin.

The implementation touches three files significantly (bridge.py, tui.py, cli.py) and introduces no new dependencies. The bridge gains `parse_session_id()`, `parse_result()`, and a `StreamResult` dataclass that yields session metadata after streaming completes. The TUI gains session state, a custom status bar (Static widget docked to bottom), input blocking during streaming (Input.disabled + opacity CSS), Escape-to-cancel via key binding, and kill-with-timeout subprocess cleanup. Turn formatting uses "You: " and "Claude: " labels with blank-line separation. Session resume is exposed via a `--resume <id>` CLI flag.

**Primary recommendation:** Build in strict dependency order: bridge StreamResult + session_id first, then TUI multi-turn loop, then turn formatting and status bar, then input blocking and Escape cancel, then --resume CLI flag. Each layer can be tested independently.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Turn separators:** Blank space only between turns -- no horizontal rules or dividers. User's prompt is echoed in the output pane before Claude's response (transcript-style). Prefix labels for attribution: "You: " before user prompt, "Claude: " before response. Printer output matches TUI -- same blank lines and labels.
- **Session status display:** Footer bar at the bottom of the TUI, below the input area. Shows: turn count, context usage indicator, and model name (e.g., "Turn 3 | Context: 45% | claude-sonnet-4-5-20250929"). Footer updates between turns only, not during streaming -- no flicker.
- **Input blocking UX:** Input area dims and is disabled while Claude streams a response. Escape key cancels/interrupts the current streaming response. On cancel: partial response stays visible, marked with "[interrupted]" suffix. Existing thinking indicator (from Phase 1) reused in output area between prompt submission and first response token. Kill-with-timeout pattern for subprocess cleanup on cancel (SIGTERM -> wait 5s -> SIGKILL).
- **Session resume flow:** Each launch starts a new session by default -- no auto-resume. User must explicitly pass `--resume <session_id>` to continue a previous session. Session ID printed on exit: "To resume: claude-teletype --resume <id>". On resume: brief summary displayed ("Resumed session abc123 (3 previous turns)"), no history replay. If `--resume` fails (corrupted/expired): fall back to new session with clear warning message.

### Claude's Discretion
- Context usage implementation: whether to parse NDJSON usage data or use turn count as proxy
- Exact dim styling for disabled input area
- Thinking indicator placement details in multi-turn context
- Subprocess lifecycle management internals

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CONV-01 | User can have a multi-turn conversation in the TUI (prompt -> response -> prompt loop with full context) | Bridge gains `session_id` parameter and `--resume` flag injection. TUI stores `_session_id` on app instance, passes to each `stream_claude_response()` call. Claude Code manages full context internally. |
| CONV-02 | Claude remembers all previous turns within a session via `--resume <session_id>` | Session ID captured from NDJSON `system/init` message, stored on TUI app, passed via `--resume`. CLI flag `--resume <id>` added to typer command. On failure, fall back to new session. |
| CONV-03 | User sees visual separators between conversation turns in TUI and on printer | "You: " and "Claude: " prefix labels. Blank lines between turns. Same format in TUI Log widget, printer output, and transcript file. |
| CONV-04 | User sees context usage indicator (turn count, context %) in TUI header or footer | Custom Static widget docked below input shows "Turn N | Context: X% | model-name". Context % calculated from NDJSON `result` message's `modelUsage.contextWindow` and token counts. Updated between turns only. |
| CONV-05 | User input is disabled while Claude's response is streaming to prevent race conditions | Input widget disabled via `input_widget.disabled = True` with opacity:70% CSS for visual dimming. Re-enabled in `finally` block after streaming. Escape key binding cancels the worker and triggers subprocess cleanup. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| textual | >=7.0.0 | TUI framework (Log, Input, Static widgets) | Already in stack. Static widget for status bar, Input.disabled for blocking, CSS opacity for dimming. |
| asyncio | stdlib | Subprocess lifecycle, worker cancellation | Standard Python async subprocess management. wait_for() for kill timeout. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| dataclasses | stdlib | StreamResult dataclass | Return session metadata from bridge after streaming completes |
| json | stdlib | NDJSON parsing (already used) | Parse session_id from system/init, parse result message for usage stats |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom Static status bar | Textual Footer widget | Footer only displays keybindings, cannot show custom status text. Static with dock:bottom is the correct approach. |
| Parsing NDJSON usage data | Turn count as proxy for context % | NDJSON result message contains actual `modelUsage.contextWindow` and token counts -- real percentage is available and more accurate. Recommend parsing real data. |
| Input.disabled for blocking | Placeholder text change only | Current Phase 1 changes placeholder to "Thinking..." but does not disable input. Users can still type and submit during streaming, causing race conditions. Must use actual disabled state. |

**Installation:** No changes to pyproject.toml. Zero new dependencies.

## Architecture Patterns

### Recommended Changes by File

```
src/claude_teletype/
├── bridge.py           # MODIFY: StreamResult, parse_session_id, parse_result, --resume flag
├── tui.py              # MODIFY: session state, status bar, input blocking, escape cancel, turn formatting
├── cli.py              # MODIFY: --resume flag, session_id display on exit
├── output.py           # NO CHANGE
├── pacer.py            # NO CHANGE
├── audio.py            # NO CHANGE
├── printer.py          # NO CHANGE
├── transcript.py       # NO CHANGE
└── teletype.py         # NO CHANGE
```

### Pattern 1: StreamResult Union Yield

**What:** The `stream_claude_response()` async generator yields `str` text chunks during streaming, then yields a single `StreamResult` as the final item containing session metadata.

**When to use:** Any async generator that needs to return metadata alongside its primary yield type.

**Example:**
```python
# Source: Architecture research (verified pattern from existing codebase)
from dataclasses import dataclass

@dataclass
class StreamResult:
    session_id: str | None
    is_error: bool
    error_message: str | None
    cost_usd: float | None
    model: str | None
    num_turns: int | None
    usage: dict | None  # For context % calculation

async def stream_claude_response(
    prompt: str,
    session_id: str | None = None,
) -> AsyncIterator[str | StreamResult]:
    args = ["claude", "-p", prompt, "--output-format", "stream-json",
            "--verbose", "--include-partial-messages",
            "--dangerously-skip-permissions",
            "--allowedTools", "WebSearch", "--allowedTools", "WebFetch"]
    if session_id is not None:
        args.extend(["--resume", session_id])

    # ... spawn subprocess, yield str chunks, yield StreamResult at end
```

**Caller pattern:**
```python
async for item in stream_claude_response(prompt, session_id=self._session_id):
    if isinstance(item, StreamResult):
        self._session_id = item.session_id
        # Update status bar, handle errors
    else:
        await pace_characters(item, ...)
```

### Pattern 2: Custom Status Bar with Static Widget

**What:** A `Static` widget docked below the input area, updated between turns using `widget.update()`.

**When to use:** When you need to display dynamic metadata (turn count, context %, model name) that the built-in Footer widget cannot show.

**Why not Footer:** Textual's `Footer` widget is keybinding-display only. It cannot show arbitrary text. A `Static` widget with `dock: bottom` is the documented approach for custom status content.

**Example:**
```python
# Source: Textual official docs - Static widget, Dock CSS
from textual.widgets import Static

class TeletypeApp(App):
    CSS = """
    #status-bar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    #prompt {
        dock: bottom;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield Log(id="output", auto_scroll=True, max_lines=5000)
        yield Static("Turn 0 | Context: -- | --", id="status-bar")
        yield Input(id="prompt", placeholder="Type a prompt and press Enter...")
        yield Footer()

    def _update_status(self, result: StreamResult) -> None:
        turn = result.num_turns or self._turn_count
        ctx_pct = self._calc_context_pct(result.usage) if result.usage else "--"
        model = result.model or "--"
        self.query_one("#status-bar", Static).update(
            f"Turn {turn} | Context: {ctx_pct} | {model}"
        )
```

**Compose order matters:** Widgets yielded later dock later. The order should be: Header, Log (fills remaining space), Static (status bar, docked bottom), Input (docked bottom above status), Footer (docked bottom below all). The `dock: bottom` widgets stack from bottom up in yield order.

### Pattern 3: Input Blocking with Disabled State + CSS Dimming

**What:** Disable the Input widget during streaming to prevent race conditions, with visual dimming via opacity CSS.

**When to use:** Whenever a background operation must complete before the user can submit again.

**Example:**
```python
# Source: Textual official docs - Input disabled, Opacity CSS
CSS = """
#prompt:disabled {
    opacity: 70%;
}
"""

def on_input_submitted(self, event: Input.Submitted) -> None:
    prompt = event.value.strip()
    if not prompt:
        return
    event.input.clear()
    input_widget = self.query_one("#prompt", Input)
    input_widget.disabled = True  # Block further input
    self.stream_response(prompt)

@work(exclusive=True)
async def stream_response(self, prompt: str) -> None:
    input_widget = self.query_one("#prompt", Input)
    try:
        # ... streaming logic ...
        pass
    finally:
        input_widget.disabled = False
        input_widget.focus()
```

### Pattern 4: Escape Key Cancel with Kill-with-Timeout Subprocess Cleanup

**What:** Bind Escape to an action that cancels the current streaming worker and kills the subprocess with SIGTERM -> wait 5s -> SIGKILL escalation.

**When to use:** When the user needs to interrupt a long-running streaming response.

**Example:**
```python
# Source: Textual workers guide, Python asyncio subprocess docs
from textual.binding import Binding

class TeletypeApp(App):
    BINDINGS = [
        Binding("ctrl+d", "quit", "Quit"),
        Binding("escape", "cancel_stream", "Cancel", show=False),
    ]

    _current_proc: asyncio.subprocess.Process | None = None

    def action_cancel_stream(self) -> None:
        """Cancel the current streaming response."""
        # Cancel all workers in the stream_response group
        for worker in self.workers:
            if not worker.is_finished:
                worker.cancel()

    @work(exclusive=True)
    async def stream_response(self, prompt: str) -> None:
        try:
            async for item in stream_claude_response(prompt, session_id=self._session_id):
                # ... handle items ...
                pass
        except asyncio.CancelledError:
            log.write(" [interrupted]")
            raise
        finally:
            # Kill subprocess if still running
            if self._current_proc is not None:
                await self._kill_process(self._current_proc)
                self._current_proc = None

    async def _kill_process(self, proc: asyncio.subprocess.Process) -> None:
        """SIGTERM -> wait 5s -> SIGKILL."""
        if proc.returncode is not None:
            return  # Already exited
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
```

### Pattern 5: Turn Formatting (Transcript Style)

**What:** Echo user prompts and label responses with "You: " and "Claude: " prefixes, with blank lines between turns.

**When to use:** All conversation output in TUI, printer, and transcript.

**Example:**
```python
# Source: User decision from CONTEXT.md
def on_input_submitted(self, event: Input.Submitted) -> None:
    prompt = event.value.strip()
    if not prompt:
        return
    self._turn_count += 1
    log = self.query_one("#output", Log)

    # Turn separator (blank line before, except first turn)
    if self._turn_count > 1:
        log.write("\n")

    # Echo user prompt with label
    log.write(f"You: {prompt}\n\n")

    # Write to transcript and printer (same format)
    for ch in f"You: {prompt}\n\n":
        if self._transcript_write:
            self._transcript_write(ch)
        if self._printer_write:
            self._printer_write(ch)

    # Claude label before response
    log.write("Claude: ")
    for ch in "Claude: ":
        if self._transcript_write:
            self._transcript_write(ch)
        if self._printer_write:
            self._printer_write(ch)

    self.stream_response(prompt)
```

### Anti-Patterns to Avoid

- **Managing conversation history ourselves:** Do NOT build `[{"role":"user","content":"..."}]` arrays. Claude Code manages all context via `--resume`. Our wrapper has zero knowledge of conversation content.
- **Using `--continue` instead of `--resume`:** `--continue` picks the most recent session in cwd. Fragile if another Claude session runs in the same directory. Always use explicit `--resume <session_id>`.
- **Persistent subprocess with stdin piping:** Do NOT keep one `claude` process alive and pipe prompts via stdin. Each turn spawns a fresh subprocess with `--resume`. Clean lifecycle per request.
- **Implementing auto-truncation:** Claude Code handles context compaction at ~95% capacity. Client-side truncation would fight with server-side compaction.
- **Updating status bar during streaming:** The user decided footer updates only between turns. Do NOT update turn count or context % while tokens are streaming.
- **Leaving Input enabled during streaming:** Must set `input_widget.disabled = True`. Placeholder text change alone does not prevent submission.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Conversation history | Message array, token counting, truncation | Claude Code's `--resume <session_id>` | Claude Code handles all context management, compaction, tool result tracking internally |
| Session storage | SQLite, JSON files for conversation state | Claude Code's `~/.claude/sessions/` | Only need a single UUID string in memory. Claude Code persists everything. |
| Context window tracking | tiktoken, anthropic-tokenizer | Parse `modelUsage` from NDJSON `result` message | Result message already contains `contextWindow`, `inputTokens`, `outputTokens` -- calculate percentage directly |
| Custom footer widget | Subclass `Footer` or `ScrollableContainer` | `Static` widget with `dock: bottom` CSS | Static.update() is the standard Textual pattern for dynamic text. Simple, documented, correct. |

**Key insight:** The biggest design win is what we do NOT build. Claude Code is a 200MB Node.js application that handles sessions, context, compaction, tool results, and auth. Our wrapper's job is to display characters one at a time. Keep the boundary clean.

## Common Pitfalls

### Pitfall 1: Zombie Subprocess Processes on Cancel
**What goes wrong:** User presses Escape during streaming. The Python asyncio task is cancelled via CancelledError, but the `claude` subprocess (a Node.js process consuming 200-500MB RAM) keeps running. Over a 30-minute session with several cancellations, orphaned processes accumulate.
**Why it happens:** `asyncio.CancelledError` stops the Python coroutine but does not automatically terminate the OS subprocess. The `proc.terminate()` in the current `except BaseException` may not execute if cancellation happens between terminate and wait.
**How to avoid:** Store `self._current_proc` on the app instance. In the `finally` block, always call the kill-with-timeout pattern (SIGTERM -> wait 5s -> SIGKILL). Also kill in `on_unmount` for app exit cleanup.
**Warning signs:** `ps aux | grep claude` shows multiple processes after extended use.

### Pitfall 2: Session Corruption from Killed Subprocess
**What goes wrong:** User cancels mid-response. Claude Code's session `.jsonl` file has an incomplete tool_use with no tool_result. Next `--resume` call crashes with "No messages returned" error.
**Why it happens:** Claude Code writes session events incrementally to disk. SIGKILL during an active API call leaves the session file semantically invalid (GitHub issue #18880).
**How to avoid:** On any `--resume` failure (non-zero exit code), reset `session_id` to None and start a fresh session. Do not retry `--resume` on the same session_id after failure. Inform the user that context was lost.
**Warning signs:** Non-zero exit codes after `--resume`, stderr containing "No messages returned".

### Pitfall 3: Race Condition on Rapid Prompt Submission
**What goes wrong:** User submits a new prompt while previous response is still streaming. `@work(exclusive=True)` cancels the old worker, but the old subprocess may still emit output that interleaves with the new response.
**Why it happens:** Cancelling the Python task does not immediately stop the OS subprocess. Both subprocesses can write to stdout simultaneously.
**How to avoid:** Disable the Input widget immediately on submission. Re-enable only in the `finally` block after streaming completes. This prevents the race entirely by blocking new submissions at the UI level.
**Warning signs:** Garbled text in the Log widget from two interleaved responses.

### Pitfall 4: Unbounded Log Widget Memory Growth
**What goes wrong:** A 50-turn conversation fills the Log widget's internal line buffer. Each `log.write(char)` appends to the growing list. TUI becomes sluggish.
**Why it happens:** Log widget `max_lines` defaults to None (unlimited).
**How to avoid:** Set `max_lines=5000` on the Log widget. The transcript file retains full history.
**Warning signs:** Increasing lag in TUI response after many turns.

### Pitfall 5: Status Bar Yield Order in compose()
**What goes wrong:** The status bar appears above the input area instead of below it, or the input area overlaps the status bar.
**Why it happens:** Textual's `dock: bottom` stacks widgets from the bottom of the container. The order of `yield` statements determines stacking order. Yielding Footer last puts it at the very bottom, then the status bar, then the input.
**How to avoid:** Yield in this order: Header, Log, Static (status bar), Input, Footer. Test the layout visually.
**Warning signs:** Visual overlap or wrong positioning in the TUI.

## Code Examples

Verified patterns from official sources and existing codebase:

### Parse session_id from NDJSON system/init Message
```python
# Source: Claude Code official docs (https://code.claude.com/docs/en/headless)
# Verified with existing test fixture SYSTEM_INIT in test_bridge.py
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

### Parse result Message for Usage Stats and Error Status
```python
# Source: NDJSON spec (https://gist.github.com/SamSaffron/603648958a8c18ceae34939a8951d417)
# Verified: result message contains usage, modelUsage, num_turns, is_error, model name
def parse_result(line: bytes) -> dict | None:
    """Extract result message fields including usage stats."""
    if not line or not line.strip():
        return None
    try:
        msg = json.loads(line.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if msg.get("type") != "result":
        return None
    return {
        "is_error": msg.get("is_error", False),
        "result": msg.get("result", ""),
        "cost_usd": msg.get("total_cost_usd"),
        "num_turns": msg.get("num_turns"),
        "session_id": msg.get("session_id"),
        "usage": msg.get("usage"),
        "model_usage": msg.get("modelUsage"),
    }
```

### Calculate Context Usage Percentage from Result Message
```python
# Source: NDJSON spec - modelUsage contains contextWindow and token counts
# Example result.modelUsage:
# {"claude-sonnet-4-5-20250929": {
#     "inputTokens": 9, "outputTokens": 143,
#     "cacheReadInputTokens": 39900, "cacheCreationInputTokens": 439,
#     "contextWindow": 200000, "maxOutputTokens": 64000, "costUSD": 0.0157882
# }}
def calc_context_pct(model_usage: dict | None) -> str:
    """Calculate context usage percentage from modelUsage data."""
    if not model_usage:
        return "--"
    # Use the first (usually only) model entry
    for model_name, usage in model_usage.items():
        context_window = usage.get("contextWindow", 0)
        if context_window == 0:
            return "--"
        total_tokens = (
            usage.get("inputTokens", 0)
            + usage.get("outputTokens", 0)
            + usage.get("cacheReadInputTokens", 0)
            + usage.get("cacheCreationInputTokens", 0)
        )
        pct = (total_tokens / context_window) * 100
        return f"{pct:.0f}%"
    return "--"
```

### Extract Model Name from Result Message
```python
# Source: NDJSON spec - modelUsage is keyed by model name
def extract_model_name(model_usage: dict | None) -> str | None:
    """Extract model name from modelUsage dict keys."""
    if not model_usage:
        return None
    # Return the first model name (usually the only one)
    for model_name in model_usage:
        return model_name
    return None
```

### Textual Input Disabled with Opacity CSS
```python
# Source: Textual official docs (https://textual.textualize.io/api/widget/)
# Verified: widget.disabled = True prevents interaction
# Verified: opacity CSS dims the widget (https://textual.textualize.io/styles/opacity/)
CSS = """
#prompt:disabled {
    opacity: 70%;
}
"""
# At runtime:
input_widget.disabled = True   # Prevents typing and submission
# ...later...
input_widget.disabled = False  # Re-enables
input_widget.focus()           # Return focus
```

### Kill-with-Timeout Subprocess Cleanup
```python
# Source: Python asyncio subprocess docs (https://docs.python.org/3/library/asyncio-subprocess.html)
# Pattern: SIGTERM -> wait(timeout) -> SIGKILL
async def _kill_process(proc: asyncio.subprocess.Process) -> None:
    """Kill subprocess with graceful shutdown attempt."""
    if proc.returncode is not None:
        return  # Already exited
    proc.terminate()  # SIGTERM
    try:
        await asyncio.wait_for(proc.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        proc.kill()  # SIGKILL -- cannot be caught
        await proc.wait()
```

### Escape Key Binding for Cancel
```python
# Source: Textual official docs (https://textual.textualize.io/guide/app/)
# Verified: Binding("escape", "action_name") works
# Verified: worker.cancel() raises CancelledError in async worker
BINDINGS = [
    Binding("ctrl+d", "quit", "Quit"),
    Binding("escape", "cancel_stream", "Cancel", show=False),
]

def action_cancel_stream(self) -> None:
    for worker in self.workers:
        if not worker.is_finished:
            worker.cancel()
```

## Discretion Recommendations

Research findings for the areas marked as "Claude's Discretion":

### Context Usage Implementation: Parse NDJSON Usage Data (Recommended)

**Recommendation:** Parse real usage data from the NDJSON `result` message, not turn count as proxy.

**Evidence:** The NDJSON `result` message (verified from the spec at https://gist.github.com/SamSaffron/603648958a8c18ceae34939a8951d417) contains:
- `modelUsage.<model-name>.contextWindow` -- the total context window size (e.g., 200000)
- `modelUsage.<model-name>.inputTokens` -- cumulative input tokens
- `modelUsage.<model-name>.outputTokens` -- cumulative output tokens
- `modelUsage.<model-name>.cacheReadInputTokens` -- cached tokens
- `modelUsage.<model-name>.cacheCreationInputTokens` -- tokens stored in cache
- `num_turns` -- the turn count

**Calculation:** `context_pct = (inputTokens + outputTokens + cacheReadInputTokens + cacheCreationInputTokens) / contextWindow * 100`

**Why not turn count:** Turn count tells you nothing about context fill rate. A 3-turn conversation with long code reviews uses more context than a 20-turn Q&A session. Real token data is already available in every result message at zero additional cost.

**Confidence:** HIGH -- verified from the NDJSON spec with complete field names.

### Dim Styling: opacity: 70% on :disabled Pseudo-class

**Recommendation:** Use Textual CSS `opacity: 70%` on the `#prompt:disabled` selector.

**Evidence:** Textual official docs explicitly state: "setting the opacity of a widget to 70% will make it appear dimmer than surrounding widgets, which could be used to display a disabled state." The `:disabled` CSS pseudo-class is supported on all Textual widgets.

**CSS:**
```css
#prompt:disabled {
    opacity: 70%;
}
```

**Why 70%:** It is the exact value recommended in Textual's opacity documentation for dimmed/disabled states. It is noticeable without being invisible.

**Confidence:** HIGH -- exact value and pattern from official Textual docs.

### Thinking Indicator in Multi-Turn Context

**Recommendation:** Keep the Phase 1 pattern (placeholder text "Thinking...") but place it in the Input widget's placeholder, not in the Log output.

**Evidence:** The current Phase 1 implementation already sets `self.query_one("#prompt", Input).placeholder = "Thinking..."` in `on_input_submitted`. In multi-turn, the input will be disabled during streaming anyway, so the placeholder serves double duty as both a thinking indicator and a "not accepting input" signal. No separate spinner or indicator needed in the output area for the TUI.

**Note:** The Log widget could show a brief "[Thinking...]" text before the "Claude: " label if desired, but since the user decision says "Existing thinking indicator (from Phase 1) reused," keeping the placeholder approach is correct and simpler.

**Confidence:** HIGH -- the pattern already exists and works.

### Subprocess Lifecycle Management Internals

**Recommendation:** Store `_current_proc` on the TUI app instance. The bridge returns it via a modified interface, or the TUI manages it directly.

**Approach A (cleaner):** Modify `stream_claude_response()` to accept a callback or container for the process reference. The bridge stores the proc in it immediately after spawning, so the TUI can kill it from the escape handler.

**Approach B (simpler):** The bridge exposes the process via a module-level variable or via the StreamResult. The TUI accesses it for cleanup.

**Approach C (recommended):** The bridge function yields the process reference as the first item (before text chunks), or the stream_response worker in TUI captures it from a bridge-level accessor. The simplest viable approach: have the bridge function accept an optional `proc_holder: list` parameter. After spawning, it does `proc_holder.append(proc)`. The TUI passes in `self._proc_holder = []` and can access `self._proc_holder[0]` to kill the process.

**Example:**
```python
# bridge.py
async def stream_claude_response(
    prompt: str,
    session_id: str | None = None,
    proc_holder: list | None = None,
) -> AsyncIterator[str | StreamResult]:
    proc = await asyncio.create_subprocess_exec(...)
    if proc_holder is not None:
        proc_holder.clear()
        proc_holder.append(proc)
    # ... yield chunks ...
```

This is a pragmatic, testable approach. The proc_holder is a simple list that acts as a mutable container.

**Confidence:** MEDIUM -- the pattern works but is slightly unconventional. Alternative: use an asyncio.Event or dataclass container.

## State of the Art

| Old Approach (v1.0) | Current Approach (v1.1) | When Changed | Impact |
|---------------------|------------------------|--------------|--------|
| One subprocess per session | One subprocess per TURN, with `--resume` for continuity | Phase 5 | Process lifecycle management becomes critical |
| No session state | `_session_id` stored on app instance | Phase 5 | Bridge and TUI gain session awareness |
| Input always available | Input disabled during streaming | Phase 5 | Prevents race conditions on rapid submission |
| Single `> prompt` prefix | "You: " and "Claude: " labels | Phase 5 | Transcript-style output |
| No status display | Turn count + context % + model name | Phase 5 | Requires result message parsing |
| Ctrl+C only interrupt | Escape key cancels with "[interrupted]" marker | Phase 5 | Requires kill-with-timeout subprocess cleanup |

**Deprecated/outdated:**
- Placeholder-only "Thinking..." indicator: still used, but now combined with actual input disabling
- Single prompt flow in TUI: replaced by persistent conversation loop

## Open Questions

1. **Compose widget order for Status Bar, Input, and Footer**
   - What we know: Textual `dock: bottom` stacks from bottom. Footer should be lowest, then Input, then Status bar above Input.
   - What's unclear: The exact yield order in `compose()` to achieve the desired visual layout needs empirical testing. The current code yields Header, Log, Input, Footer. Adding Static between Input and Footer may or may not produce the right stacking.
   - Recommendation: Test the yield order early. If the default stacking is wrong, adjust with explicit `height` and `dock` CSS to force correct ordering.

2. **Process Reference Propagation from Bridge to TUI**
   - What we know: The TUI needs to kill the subprocess on Escape. The subprocess is created inside `stream_claude_response()`.
   - What's unclear: The cleanest API for exposing the process reference. The `proc_holder: list` pattern works but is unconventional.
   - Recommendation: Start with the `proc_holder` approach. Refactor later if a cleaner pattern emerges during implementation.

3. **Transcript File Handling on Resume**
   - What we know: Current transcript creates one file per TUI launch. With `--resume`, a conversation spans multiple launches.
   - What's unclear: Should the resumed transcript append to the existing file or create a new one?
   - Recommendation: Create a new transcript file for each launch, but include the session_id in the transcript header. This avoids file locking complexity and matches the physical printer metaphor (you cannot un-print paper).

## Sources

### Primary (HIGH confidence)
- Claude Code CLI Reference: https://code.claude.com/docs/en/cli-reference -- `--resume`, `--continue`, `-p` flag combinations
- Claude Code Headless/Programmatic Usage: https://code.claude.com/docs/en/headless -- multi-turn chaining pattern with `--resume`, session_id capture
- NDJSON Spec (Claude Agent SDK): https://gist.github.com/SamSaffron/603648958a8c18ceae34939a8951d417 -- complete message types including `system/init` with session_id, `result` with usage/modelUsage/num_turns
- Textual Input Widget Docs: https://textual.textualize.io/widgets/input/ -- `disabled` parameter
- Textual Widget API: https://textual.textualize.io/api/widget/ -- `disabled` reactive attribute, `:disabled` CSS pseudo-class
- Textual Opacity CSS: https://textual.textualize.io/styles/opacity/ -- 70% opacity for dimmed disabled state
- Textual Static Widget Docs: https://textual.textualize.io/widgets/static/ -- `update()` method for dynamic content
- Textual Footer Widget Docs: https://textual.textualize.io/widgets/footer/ -- keybinding display only, cannot show custom text
- Textual Workers Guide: https://textual.textualize.io/guide/workers/ -- `cancel()`, exclusive workers, CancelledError
- Textual Worker API: https://textual.textualize.io/api/worker/ -- cancel(), is_running, is_cancelled, WorkerState enum
- Textual @work API: https://textual.textualize.io/api/work/ -- name parameter, exclusive parameter
- Textual Dock CSS: https://textual.textualize.io/styles/dock/ -- `dock: bottom` for fixed-position widgets
- Python asyncio Subprocess Docs: https://docs.python.org/3/library/asyncio-subprocess.html -- terminate(), kill(), wait()

### Secondary (MEDIUM confidence)
- Claude Code Session Management (Steve Kinney): https://stevekinney.com/courses/ai-development/claude-code-session-management -- session flag behavior
- Claude Code resume crash on killed sessions (issue #18880): https://github.com/anthropics/claude-code/issues/18880 -- session corruption details
- Claude Code OOM from accumulated cache (issue #13126): https://github.com/anthropics/claude-code/issues/13126 -- memory growth in long sessions
- Textual GitHub Discussions #3750 (stopping workers): https://github.com/Textualize/textual/discussions/3750 -- worker cancellation patterns
- Textual GitHub Discussions #2290 (Escape key for Input): https://github.com/Textualize/textual/discussions/2290 -- Escape key binding patterns

### Tertiary (LOW confidence)
- None -- all findings verified with primary or secondary sources.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- zero new dependencies, all patterns from existing Textual and asyncio docs
- Architecture: HIGH -- changes are surgical additions to existing well-understood modules (bridge.py, tui.py, cli.py). No architectural rewrites.
- Pitfalls: HIGH -- all pitfalls documented with verified sources (GitHub issues, official docs, codebase analysis)
- Discretion recommendations: HIGH -- context % from NDJSON data verified from spec, opacity CSS from official docs

**Research date:** 2026-02-16
**Valid until:** 2026-03-16 (30 days -- stable domain, no fast-moving dependencies)
