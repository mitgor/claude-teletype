# Phase 2: Terminal Simulator - Research

**Researched:** 2026-02-15
**Domain:** Textual TUI framework, split-screen terminal layout, character-by-character streaming output, dual-output mirroring, asyncio event loop integration
**Confidence:** HIGH

## Summary

Phase 2 replaces the current simple `sys.stdout.write()` output with a split-screen Terminal User Interface (TUI) built on Textual. The TUI has two panes: a scrollable output area at the top showing Claude's responses with typewriter pacing, and an input area at the bottom where the user types prompts. The existing pacer and bridge modules from Phase 1 are reused without modification -- the pacer's `output_fn` injection pattern was explicitly designed for this purpose.

The critical architectural insight is that Textual runs its own asyncio event loop via `App.run()`, which replaces the `asyncio.run()` currently used in `cli.py`. The bridge's `stream_claude_response()` is an async generator that works within any event loop, so it integrates naturally with Textual's worker pattern. The pacer's `output_fn` parameter allows redirecting character output from `sys.stdout` to the Textual `Log` widget's `write()` method, which supports appending characters without newlines.

The CHAR-02 requirement (mirroring output to both terminal and printer) is implemented via a multiplexed `output_fn` that fans out each character to multiple destinations. In Phase 2, this means writing to the TUI's Log widget. In Phase 3 (when printer hardware is added), the same `output_fn` will additionally write to the printer device. The architecture should prepare for this by making the output function a list of callables that each receive every character.

**Primary recommendation:** Use Textual 7.x with a `Log` widget (top pane, `write()` for character-by-character append) and `Input` widget (bottom pane, docked). Run the Claude bridge inside a Textual `@work(exclusive=True)` async worker. Redirect pacer output via `output_fn` to `Log.write()`. Keep the existing Phase 1 CLI mode as a fallback reachable via `--no-tui` flag.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Textual | >=7.0.0 | TUI framework | The standard Python TUI framework. Built on Rich (already a dependency). CSS-based layouts, async-native, built-in testing via `run_test()` + Pilot. Requirement SIML-01 specifies "Textual-based" explicitly. |
| Log (widget) | Textual built-in | Output pane | `Log.write()` appends text without newlines -- exactly what character-by-character streaming needs. `auto_scroll=True` keeps latest output visible. Plain text aesthetic matches typewriter requirement. |
| Input (widget) | Textual built-in | Input pane | Single-line text input with `Input.Submitted` event on Enter. Built-in focus management. Handles standard editing keys (backspace, cursor, selection). |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Typer | >=0.23.0 | CLI argument parsing | Still the entry point. Parses `--delay`, `--no-tui`, `--device` flags. Typer command calls `TeletypeApp().run()` instead of `asyncio.run()`. |
| Rich | >=14.0.0 | Text styling in TUI | Already a Textual dependency (Textual extends Rich). Used for status indicators and styled text in the Log pane if needed. |
| pytest-textual-snapshot | latest | Visual regression tests | Dev dependency. Snapshot testing for TUI layout verification. Optional but valuable. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Log widget | RichLog widget | RichLog supports Rich renderables but each `write()` call starts a new "block." Log's `write()` appends inline -- better for character streaming. |
| Log widget | Markdown widget (streaming) | Textual v4+ has `Markdown.append()` and `MarkdownStream` for LLM output. But the project is "plain text only, as a typewriter would produce." Markdown rendering contradicts the aesthetic. |
| Input widget | TextArea widget | TextArea is multi-line. The typewriter metaphor is one prompt at a time. Input's single-line constraint is correct. |
| Textual | Prompt Toolkit | Lower-level, no CSS layouts, no built-in widget system. Would require hand-rolling the split-screen layout. Textual is the modern standard. |
| Textual | urwid | Older, callback-based, no CSS. Textual is the modern replacement. |

**Installation:**
```bash
uv add textual
# Dev dependency for snapshot testing (optional)
uv add --dev pytest-textual-snapshot
```

## Architecture Patterns

### Recommended Project Structure (Phase 2 additions)

```
src/claude_teletype/
├── __init__.py
├── __main__.py
├── cli.py              # Updated: Typer adds --no-tui flag, TUI mode is default
├── bridge.py           # Unchanged from Phase 1
├── pacer.py            # Unchanged from Phase 1
├── tui.py              # NEW: Textual App class with split-screen layout
└── output.py           # NEW: Multiplexed output_fn factory
tests/
├── test_bridge.py      # Unchanged
├── test_pacer.py       # Unchanged
├── test_tui.py         # NEW: Textual app tests with run_test() + Pilot
└── test_output.py      # NEW: Multiplexed output function tests
```

### Pattern 1: Textual App with Split-Screen Layout

**What:** A Textual App with two regions: a scrollable `Log` widget filling the top (using `1fr` height) and an `Input` widget docked to the bottom with fixed height. The Log shows Claude's output character by character; the Input captures user prompts.

**When to use:** This is the main application mode (default when no `--no-tui` flag).

**Example:**
```python
# tui.py
from textual.app import App, ComposeResult
from textual.widgets import Input, Log, Header, Footer

class TeletypeApp(App):
    """Split-screen terminal simulator for Claude Teletype."""

    CSS = """
    Log {
        height: 1fr;
        border: solid green;
    }
    Input {
        dock: bottom;
        height: 3;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield Log(id="output", auto_scroll=True)
        yield Input(placeholder="Type your prompt and press Enter...")
        yield Footer()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user pressing Enter in the input field."""
        prompt = event.value
        event.input.clear()
        log = self.query_one("#output", Log)
        log.write_line(f"\n> {prompt}\n")
        self.stream_response(prompt)

    @work(exclusive=True)
    async def stream_response(self, prompt: str) -> None:
        """Stream Claude's response with typewriter pacing."""
        from claude_teletype.bridge import stream_claude_response
        from claude_teletype.pacer import pace_characters

        log = self.query_one("#output", Log)

        async for chunk in stream_claude_response(prompt):
            await pace_characters(
                chunk,
                base_delay_ms=self.base_delay_ms,
                output_fn=log.write,
            )
```
**Source:** [Textual Layout Guide](https://textual.textualize.io/guide/layout/), [Textual Workers Guide](https://textual.textualize.io/guide/workers/), [Textual Log Widget](https://textual.textualize.io/widgets/log/)

### Pattern 2: Worker for Background Streaming

**What:** The `@work(exclusive=True)` decorator turns the streaming method into a Textual worker. `exclusive=True` ensures that starting a new prompt cancels any in-progress response (preventing race conditions where two responses interleave). The worker runs inside Textual's event loop -- no `asyncio.run()` conflict.

**When to use:** Every time the user submits a prompt.

**Example:**
```python
from textual.work import work

@work(exclusive=True)
async def stream_response(self, prompt: str) -> None:
    """Worker: stream Claude response to the Log widget."""
    log = self.query_one("#output", Log)
    async for chunk in stream_claude_response(prompt):
        await pace_characters(chunk, output_fn=log.write)
```

**Key insight:** Because `stream_claude_response()` is an `AsyncIterator[str]` and `pace_characters()` is an `async` function using `asyncio.sleep()`, they both work natively inside Textual's asyncio event loop. No adapters, no threading, no `nest_asyncio`. The existing Phase 1 code was already designed for this.

**Source:** [Textual Workers Guide](https://textual.textualize.io/guide/workers/)

### Pattern 3: Multiplexed Output Function

**What:** A factory function that creates a single `output_fn` callable which fans out each character to multiple destinations. In Phase 2, there is one destination (the Log widget). In Phase 3, a printer device will be added as a second destination. The pacer already accepts `output_fn: Callable[[str], None] | None`.

**When to use:** When constructing the `output_fn` to pass to `pace_characters()`.

**Example:**
```python
# output.py
from collections.abc import Callable


def make_output_fn(*destinations: Callable[[str], None]) -> Callable[[str], None]:
    """Create a multiplexed output function that writes to all destinations.

    Args:
        *destinations: One or more callables that accept a single character string.

    Returns:
        A single callable that writes to all destinations.
    """
    def output(char: str) -> None:
        for dest in destinations:
            dest(char)
    return output
```

**Usage:**
```python
# Phase 2: TUI only
output_fn = make_output_fn(log.write)

# Phase 3: TUI + printer
output_fn = make_output_fn(log.write, printer.write)
```

This directly implements CHAR-02 (mirroring) and prepares for Phase 3 without any pacer changes.

### Pattern 4: Typer-to-Textual Bridge (replacing asyncio.run)

**What:** The Typer CLI command no longer calls `asyncio.run()` for TUI mode. Instead, it instantiates and runs the Textual app directly. Textual's `App.run()` manages the event loop. A `--no-tui` flag preserves Phase 1 behavior for piping/scripting.

**When to use:** Always, as the new default entry point.

**Example:**
```python
# cli.py
@app.command()
def chat(
    prompt: str = typer.Argument(None, help="Prompt (if omitted, interactive TUI mode)"),
    delay: float = typer.Option(75.0, "--delay", "-d"),
    no_tui: bool = typer.Option(False, "--no-tui", help="Disable TUI, use plain stdout"),
) -> None:
    """Claude Teletype: typewriter-paced AI conversation."""
    if no_tui and prompt:
        # Phase 1 mode: single prompt, stdout output
        asyncio.run(_chat_async(prompt, delay))
    else:
        # Phase 2 mode: interactive TUI
        tui_app = TeletypeApp(base_delay_ms=delay)
        tui_app.run()
```

**Key insight:** When TUI mode is active, there is no single prompt argument -- the user types prompts interactively in the Input widget. The `prompt` CLI argument becomes optional.

### Pattern 5: Textual App Testing with Pilot

**What:** Textual's `run_test()` method runs the app in headless mode (no terminal) and returns a `Pilot` object for simulating user input. Tests use `pilot.press()` to type text and press Enter, then assert on widget state.

**When to use:** All TUI tests.

**Example:**
```python
# test_tui.py
import pytest
from claude_teletype.tui import TeletypeApp


async def test_input_clears_on_submit():
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:
        # Type a prompt
        await pilot.press(*"hello")
        await pilot.press("enter")
        # Input should be cleared
        input_widget = app.query_one(Input)
        assert input_widget.value == ""


async def test_prompt_appears_in_log():
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:
        await pilot.press(*"test prompt")
        await pilot.press("enter")
        await pilot.pause()  # Allow worker to process
        log = app.query_one("#output", Log)
        assert "> test prompt" in str(log.lines)
```

**Source:** [Textual Testing Guide](https://textual.textualize.io/guide/testing/)

### Anti-Patterns to Avoid

- **Calling `asyncio.run()` inside a Textual app:** Textual already owns the event loop. Calling `asyncio.run()` from within a worker or handler raises `RuntimeError: This event loop is already running`. Use `@work` or `asyncio.create_task()` instead.

- **Using RichLog for character streaming:** RichLog's `write()` creates separate renderable blocks per call. Calling it once per character creates thousands of block objects. Use `Log.write()` which appends to the current line buffer.

- **Blocking the Textual event loop:** Never `await` a long-running subprocess read directly in an event handler. Always use a `@work` worker so the UI remains responsive to key presses and resize events.

- **Forgetting `exclusive=True` on the streaming worker:** Without it, submitting a second prompt while the first is still streaming creates two concurrent workers interleaving output in the same Log widget.

- **Using `write_line()` for character output:** `Log.write_line()` appends a newline after every call. For character-by-character output, use `Log.write()` which appends inline. Only newline characters in the text should create new lines.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Split-screen terminal layout | curses/ncurses code | Textual CSS layouts with `dock` and `fr` units | Terminal resize handling, focus management, style inheritance all handled. curses is C-era complexity. |
| Input widget with editing | Custom character reading with `sys.stdin` | Textual `Input` widget | Handles backspace, cursor movement, selection, clipboard, Unicode. Hundreds of edge cases. |
| Scrollable output log | Custom line buffer with manual scroll | Textual `Log` widget | Auto-scroll, efficient rendering, proper line management, scroll-back. |
| Background task management | Manual `asyncio.create_task` + cancellation | Textual `@work(exclusive=True)` | Automatic cancellation of previous workers, lifecycle tied to widget/screen, state change events. |
| Headless testing of TUI | Custom mock terminal | Textual `run_test()` + `Pilot` | Simulates keystrokes, clicks, resize. No real terminal needed. CI-friendly. |
| Output fan-out to multiple targets | Complex observer/pubsub pattern | Simple multiplexed `output_fn` callable | The pacer already accepts `output_fn`. A closure over a list of destinations is trivially testable and composable. |

**Key insight:** Textual provides everything needed for the TUI layer. The only new code is the `TeletypeApp` class (composing widgets + wiring events), the `output.py` multiplexer (trivial), and updated `cli.py` entry point. The bridge and pacer are unchanged.

## Common Pitfalls

### Pitfall 1: Event Loop Conflict Between Textual and asyncio.run()

**What goes wrong:** Developer calls `asyncio.run()` inside a Textual app or tries to nest Textual's `App.run()` inside an existing `asyncio.run()`. This raises `RuntimeError: This event loop is already running` or `RuntimeError: asyncio.run() cannot be called from a running event loop`.

**Why it happens:** Both Textual's `App.run()` and `asyncio.run()` create and manage their own event loop. They cannot be nested.

**How to avoid:** In TUI mode, `App.run()` replaces `asyncio.run()`. The Typer command calls `TeletypeApp().run()` directly (it is synchronous from Typer's perspective -- `App.run()` blocks until the app exits). Inside the Textual app, use `@work` for async background tasks instead of `asyncio.run()`.

**Warning signs:** `RuntimeError` about event loops on startup.

### Pitfall 2: Log.write() vs Log.write_line() Character Semantics

**What goes wrong:** Characters appear one-per-line in the output pane, making the typewriter effect look like a vertical column of characters instead of flowing text.

**Why it happens:** Developer used `write_line()` instead of `write()`. `write_line()` appends a newline after each call. When called once per character, every character gets its own line.

**How to avoid:** Use `Log.write(char)` for individual characters. `write()` appends to the current line without a newline. Newline characters within the text naturally create new lines in the Log widget.

**Warning signs:** Output in the log looks like a vertical stack of individual characters.

### Pitfall 3: Worker Not Exclusive -- Interleaved Responses

**What goes wrong:** User submits a second prompt while the first response is still streaming. Both responses interleave character by character in the output pane, creating garbled text.

**Why it happens:** Without `exclusive=True`, Textual runs both workers concurrently. Both workers write to the same Log widget.

**How to avoid:** Always use `@work(exclusive=True)` for the streaming worker. This cancels any in-progress worker before starting the new one. The cancelled worker raises `CancelledError`, which Textual handles gracefully.

**Warning signs:** Submitting a prompt while one is already running produces mixed output.

### Pitfall 4: Textual App Doesn't Receive Piped stdin

**What goes wrong:** Running `echo "hello" | claude-teletype` in TUI mode fails or behaves unexpectedly because Textual's `App.run()` takes over the terminal and stdin.

**Why it happens:** Textual enters "application mode" which captures the terminal. Piped stdin is not the same as interactive terminal input.

**How to avoid:** Detect whether stdin is a TTY. If not (piped input), fall back to `--no-tui` mode automatically. This preserves pipeline compatibility:
```python
import sys
if not sys.stdin.isatty():
    no_tui = True
```

**Warning signs:** Piped input produces blank screen or hangs.

### Pitfall 5: Thinking Indicator in TUI Mode

**What goes wrong:** The Rich `console.status()` spinner from Phase 1 does not work inside Textual because Textual owns the terminal.

**Why it happens:** Rich's `Console` writes directly to stdout, but Textual controls terminal output. Rich renderables need to go through Textual widgets.

**How to avoid:** Replace the Rich spinner with a Textual-native indicator. Options: (a) change the Input widget's placeholder text to "Thinking..." while waiting, (b) add a small `Static` widget as a status bar, or (c) append "Thinking..." to the Log and remove it when the first token arrives. Option (a) is simplest and uses existing widgets.

**Warning signs:** Spinner artifacts or blank areas in the TUI while Claude thinks.

### Pitfall 6: Pacer Sleep Blocking UI During Rapid Resize/Scroll

**What goes wrong:** During character output, resizing the terminal causes visible lag or frozen updates.

**Why it happens:** The pacer uses `asyncio.sleep()` between characters. If the sleep is on the main event loop and many sleeps queue up, UI events (resize, scroll) may be delayed.

**How to avoid:** The `@work` worker runs on the same event loop but yields control back during each `asyncio.sleep()`, allowing Textual to process UI events between characters. This should work naturally because `asyncio.sleep()` is cooperative. If lag is observed, reduce minimum sleep time or use `call_after_refresh()` for batched updates.

**Warning signs:** Terminal resize causes temporary freeze in output.

## Code Examples

Verified patterns from official sources:

### Minimal Textual Split-Screen App

```python
# Source: https://textual.textualize.io/guide/layout/
# Source: https://textual.textualize.io/widgets/log/
# Source: https://textual.textualize.io/widgets/input/

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Log


class TeletypeApp(App):
    """Claude Teletype terminal simulator."""

    TITLE = "Claude Teletype"

    CSS = """
    #output {
        height: 1fr;
    }
    #prompt {
        dock: bottom;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield Log(id="output", auto_scroll=True)
        yield Input(id="prompt", placeholder="Type a prompt and press Enter...")
        yield Footer()
```

### Textual Worker with Async Generator

```python
# Source: https://textual.textualize.io/guide/workers/

from textual.work import work

class TeletypeApp(App):
    # ...

    @work(exclusive=True)
    async def stream_response(self, prompt: str) -> None:
        """Background worker: streams Claude response with pacing."""
        from claude_teletype.bridge import stream_claude_response
        from claude_teletype.pacer import pace_characters

        log = self.query_one("#output", Log)
        output_fn = log.write  # Log.write() appends without newline

        first_token = True
        async for chunk in stream_claude_response(prompt):
            if first_token:
                first_token = False
                # Could update status indicator here
            await pace_characters(chunk, base_delay_ms=75.0, output_fn=output_fn)
```

### Multiplexed Output Function

```python
# Pattern: tee/fan-out for CHAR-02 (mirroring)
from collections.abc import Callable


def make_output_fn(*destinations: Callable[[str], None]) -> Callable[[str], None]:
    """Create output function that writes to all destinations."""
    def output(char: str) -> None:
        for dest in destinations:
            dest(char)
    return output


# Usage in TUI:
log = app.query_one("#output", Log)
output_fn = make_output_fn(log.write)

# Future Phase 3 usage:
output_fn = make_output_fn(log.write, printer_device.write)
```

### Typer-to-Textual Entry Point

```python
# cli.py -- Updated for Phase 2
import asyncio
import sys

import typer

app = typer.Typer()


@app.command()
def chat(
    prompt: str = typer.Argument(None, help="Prompt (omit for interactive TUI)"),
    delay: float = typer.Option(75.0, "--delay", "-d",
                                help="Base delay between characters in ms"),
    no_tui: bool = typer.Option(False, "--no-tui",
                                help="Disable TUI, use plain stdout (Phase 1 mode)"),
) -> None:
    """Claude Teletype: typewriter-paced AI conversation."""
    # Auto-detect piped input
    if not sys.stdin.isatty():
        no_tui = True

    if no_tui and prompt:
        # Phase 1 fallback: single prompt, stdout
        asyncio.run(_chat_async(prompt, delay))
    else:
        # Default: interactive TUI
        from claude_teletype.tui import TeletypeApp
        tui_app = TeletypeApp(base_delay_ms=delay)
        tui_app.run()
```

### Textual App Testing

```python
# Source: https://textual.textualize.io/guide/testing/
import pytest
from textual.widgets import Input, Log
from claude_teletype.tui import TeletypeApp


async def test_layout_has_log_and_input():
    """Verify the split-screen layout contains both panes."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:
        assert app.query_one("#output", Log) is not None
        assert app.query_one("#prompt", Input) is not None


async def test_enter_clears_input():
    """Input field clears after pressing Enter."""
    app = TeletypeApp(base_delay_ms=0)
    async with app.run_test() as pilot:
        await pilot.press(*"hello world")
        await pilot.press("enter")
        input_widget = app.query_one("#prompt", Input)
        assert input_widget.value == ""
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| curses for Python TUIs | Textual with CSS layouts | 2022+ (mature by 2025) | CSS-based layouts, widget system, async-native, built-in testing. curses is legacy. |
| RichLog for streaming text | Log.write() for character appending | Textual ~0.40+ | Log.write() appends inline (no newline). Better for character-by-character than RichLog. |
| Manual asyncio.create_task() in TUI | Textual @work decorator | Textual 0.18+ (2023) | Automatic lifecycle management, exclusive workers, cancellation, state events. |
| Textual <4.0 for LLM output | Textual 4.0+ with Markdown.append() / MarkdownStream | 2025 (v4.0.0) | Native streaming Markdown. Not needed here (plain text) but shows Textual is LLM-aware. |
| Snapshot testing via manual screenshots | pytest-textual-snapshot | 2023+ | Automated visual regression testing for Textual apps in CI. |

**Deprecated/outdated:**
- `TextLog` widget -- renamed to `RichLog` in Textual 0.32.0. Use `RichLog` or `Log`.
- `urwid` for Python TUIs -- still works but Textual is the modern standard with active development.
- `blessed`/`blessings` terminal libraries -- thin curses wrappers, superseded by Textual for anything beyond simple formatting.

## Open Questions

1. **Log.write() behavior with newline characters in the string**
   - What we know: `Log.write()` appends text without adding a newline. `Log.write_line()` adds a newline after content.
   - What's unclear: When `write()` receives a string containing `\n` characters (e.g., from the pacer outputting a newline character), does the Log widget create a visual line break? This needs validation during implementation.
   - Recommendation: Test empirically in the first implementation task. If `write("\n")` does not create a line break in Log, use `write_line("")` for newline characters and `write()` for all others in the output function.

2. **Worker cancellation mid-stream**
   - What we know: `exclusive=True` cancels previous workers. The bridge's `stream_claude_response()` keeps the subprocess alive until EOF.
   - What's unclear: When the worker is cancelled, does the subprocess get terminated cleanly? The bridge has a `try/except BaseException` that calls `proc.terminate()`, but `CancelledError` raised by Textual's worker needs to propagate to this handler.
   - Recommendation: Verify during implementation that cancelling a streaming worker terminates the Claude subprocess. Add explicit cleanup if needed.

3. **Performance of Log.write() at character-by-character frequency**
   - What we know: At 75ms base delay, that is ~13 characters/second. Textual's Log widget should handle this easily.
   - What's unclear: Whether there is a minimum render interval in Textual that batches multiple `write()` calls into a single repaint. If so, several characters might appear at once visually even though they are written separately.
   - Recommendation: Likely a non-issue at 13 chars/sec. Test with `base_delay_ms=10` (100 chars/sec) to find the upper limit. If batching occurs, it may actually improve visual smoothness.

4. **Header/Footer necessity**
   - What we know: Textual provides `Header` and `Footer` widgets for standard app chrome. Header shows the app title. Footer shows key bindings.
   - What's unclear: Whether these add value to the typewriter aesthetic or are visual clutter.
   - Recommendation: Include Header (shows "Claude Teletype") and Footer (shows Ctrl+C to quit, Ctrl+D to exit). They can be removed later if they feel wrong. They provide important discoverability for key bindings.

## Sources

### Primary (HIGH confidence)
- [Textual Official Docs - Layout Guide](https://textual.textualize.io/guide/layout/) -- CSS layouts with dock, fr units, vertical arrangement
- [Textual Official Docs - Workers Guide](https://textual.textualize.io/guide/workers/) -- @work decorator, exclusive flag, worker lifecycle, async worker pattern
- [Textual Official Docs - Testing Guide](https://textual.textualize.io/guide/testing/) -- run_test(), Pilot, headless mode, pytest integration
- [Textual Official Docs - Log Widget](https://textual.textualize.io/widgets/log/) -- write() vs write_line(), auto_scroll, character-level append API
- [Textual Official Docs - Input Widget](https://textual.textualize.io/widgets/input/) -- Input.Submitted event, clear(), focus management
- [Textual Official Docs - App Basics](https://textual.textualize.io/guide/app/) -- App.run(), compose(), event handlers, application mode
- [Textual PyPI](https://pypi.org/project/textual/) -- Version 7.5.0, Python >=3.9 support, latest release 2026-01-30

### Secondary (MEDIUM confidence)
- [Textual v4.0.0 Release - Streaming](https://simonwillison.net/2025/Jul/22/textual-v4/) -- Markdown.append() and MarkdownStream for LLM streaming (not needed here but confirms Textual's LLM-awareness)
- [Textual Blog - No-async async](https://textual.textualize.io/blog/2023/03/15/no-async-async-with-python/) -- Textual's internal event loop design, "await me maybe" pattern
- [Textual Blog - Workers API](https://textual.textualize.io/blog/2023/04/04/textual-0180-adds-api-for-managing-concurrent-workers/) -- Worker API design rationale and lifecycle management
- [Textual Official Docs - Markdown Widget](https://textual.textualize.io/widgets/markdown/) -- Markdown.append(), MarkdownStream for streaming (alternative not chosen)

### Tertiary (LOW confidence)
- Performance of `Log.write()` at high frequency -- based on reasoning about Textual's repaint cycle, not measured. Needs empirical validation.
- `Log.write()` behavior with embedded `\n` characters -- inferred from API description ("writes without newline"), not tested directly. Needs validation.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- Textual is explicitly required by SIML-01. Version verified on PyPI. All widgets verified in official docs.
- Architecture: HIGH -- Textual's worker pattern, compose/layout system, and event handling are well-documented. The pacer's `output_fn` injection was designed for exactly this use case.
- Pitfalls: HIGH -- Event loop conflict is a known asyncio anti-pattern. Worker exclusivity is documented. Log vs RichLog behavior verified in official docs.
- Integration: MEDIUM -- The bridge-to-worker integration is architecturally sound but the exact cancellation behavior and `Log.write()` newline handling need empirical validation.

**Research date:** 2026-02-15
**Valid until:** 2026-03-15 (stable domain -- Textual 7.x API is mature, unlikely to have breaking changes)
