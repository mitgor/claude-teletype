# Feature Landscape: v1.1 Milestone

**Domain:** Multi-turn conversation, word wrap, and error handling for Claude Teletype
**Researched:** 2026-02-16
**Confidence:** HIGH (verified against official Claude Code CLI docs and Textual docs)

## Context: What Already Exists

The v1.0 codebase is fully functional with one-shot conversations:
- `bridge.py` spawns `claude -p <prompt> --output-format stream-json` as a subprocess
- `bridge.py` parses NDJSON `stream_event` / `content_block_delta` / `text_delta` for streaming
- `tui.py` uses Textual `Log` widget with `log.write(char)` for character-by-character output
- `cli.py` provides `--no-tui` mode writing to `sys.stdout`
- `printer.py` has `make_printer_output()` with 80-column hard wrap (column counter, no word-boundary awareness)
- Error handling is minimal: bare `except Exception` in TUI, `KeyboardInterrupt` catch in CLI

This research focuses ONLY on what needs to change for multi-turn, word wrap, and error handling.

---

## Table Stakes

Features users expect for these capabilities. Missing any of these makes the milestone feel incomplete.

### MTURN-01: Session-Persistent Multi-Turn Conversation

| Attribute | Detail |
|-----------|--------|
| **Why Expected** | The TUI already has a prompt-response-prompt loop, but each submission spawns a fresh `claude -p` process with no memory of previous turns. Users type a follow-up and Claude has no idea what they were talking about. This is the single biggest UX gap. |
| **Complexity** | MEDIUM |
| **Mechanism** | Claude Code CLI provides `--session-id <UUID>` and `--resume <id>` flags. The first invocation emits a `{"type":"system","subtype":"init","session_id":"..."}` NDJSON message. Capture that session_id, then pass `--resume <session_id>` on every subsequent `claude -p` call. Claude Code handles all context management server-side. |
| **Changes Required** | (1) `bridge.py`: modify `stream_claude_response()` to accept an optional `session_id` parameter and return it. Add a `parse_session_id()` function to extract session_id from `system`/`init` messages. (2) `tui.py`: store `self._session_id` on the app, update after each response. (3) `cli.py`: for `--no-tui` mode, build a REPL loop that persists session_id across prompts. |
| **Dependencies** | None -- builds on existing bridge infrastructure. The NDJSON format already contains session_id in every message; we just need to stop ignoring it. |
| **Verification** | HIGH confidence. Official Claude Code docs confirm `--session-id` and `--resume` flags. NDJSON spec from Agent SDK confirms `session_id` field in system init message. Existing test fixtures in `test_bridge.py` already include `SYSTEM_INIT` with `session_id`. |

### MTURN-02: Auto-Compact / Context Window Awareness

| Attribute | Detail |
|-----------|--------|
| **Why Expected** | In long multi-turn sessions, the context window fills up. Claude Code auto-compacts, but users see no indication this is happening. When context runs out without compaction, the conversation fails silently or with a cryptic error. |
| **Complexity** | LOW |
| **Mechanism** | Claude Code handles compaction automatically on the server side. Our job is to (1) surface the `result` NDJSON message which includes `usage.input_tokens` and `modelUsage.*.contextWindow` so we can show a context usage indicator, and (2) handle the `is_error: true` result message gracefully when context is actually exhausted. |
| **Changes Required** | (1) `bridge.py`: parse `result` messages for usage stats and error status. (2) `tui.py`: optional status bar showing context usage percentage. (3) Handle `result.is_error` with a user-friendly message suggesting `/compact` or starting fresh. |
| **Dependencies** | Requires MTURN-01 (session persistence) -- context only fills up in multi-turn sessions. |
| **Verification** | HIGH confidence. NDJSON result message format verified from Agent SDK spec. Auto-compact behavior confirmed in multiple sources. |

### WRAP-01: Word-Boundary Wrap in TUI Output

| Attribute | Detail |
|-----------|--------|
| **Why Expected** | The current TUI uses Textual's `Log` widget, which does NOT wrap text. Long lines scroll horizontally off-screen. For a typewriter experience, text must wrap at the widget width, and it must wrap at word boundaries (not mid-word). |
| **Complexity** | MEDIUM |
| **Mechanism** | Two options: (A) Switch from `Log` to `RichLog` which has a `wrap=True` parameter for built-in word wrapping. Problem: `RichLog.write()` expects complete renderables, not individual characters. The current `log.write(char)` pattern would need to buffer. (B) Keep `Log` and implement a line buffer that accumulates words, flushing complete wrapped lines. Option B is better because it preserves the existing character-by-character `log.write()` pattern that the pacer depends on, while adding wrap logic in the output pipeline. |
| **Changes Required** | Create a `WordWrapBuffer` class that sits in the output pipeline. It accumulates characters, tracks column position, and when it hits the width limit, backs up to the last space and emits a newline. Width derived from widget width (reactive to terminal resize) or a configurable column count. |
| **Dependencies** | None -- additive to existing output pipeline via `make_output_fn()`. |
| **Verification** | HIGH confidence. Textual `Log` docs confirm no built-in wrap. `RichLog` docs confirm `wrap=True` but it operates on complete writes, not character streams. The streaming word-wrap buffer is the correct approach for character-by-character output. |

### WRAP-02: Word-Boundary Wrap for Printer Output

| Attribute | Detail |
|-----------|--------|
| **Why Expected** | The existing `make_printer_output()` in `printer.py` already wraps at 80 columns, but it wraps mid-word (pure column counter with hard break). This produces ugly output on paper where words split across lines. |
| **Complexity** | LOW |
| **Mechanism** | Replace the naive column counter in `make_printer_output()` with the same `WordWrapBuffer` used for TUI. When a word would exceed the column limit, emit a newline before the word instead of after the character that hits column 80. |
| **Changes Required** | (1) Create shared `WordWrapBuffer` class (used by both TUI and printer). (2) Refactor `make_printer_output()` to use it instead of the current `column >= A4_COLUMNS` check. (3) Make column width configurable (80 for A4, 132 for wide-carriage printers). |
| **Dependencies** | WRAP-01 (shared buffer implementation). |
| **Verification** | HIGH confidence. The current hard-wrap code is visible in `printer.py` lines 466-487. Word-boundary wrapping is a well-understood algorithm (Python `textwrap` stdlib proves the pattern). |

### ERR-01: Categorized Error Messages

| Attribute | Detail |
|-----------|--------|
| **Why Expected** | Current error handling shows raw Python exceptions to users. `[Error: ...]` in TUI and bare tracebacks in CLI mode. Users need to know: Is Claude Code not installed? Is it a network issue? Is the API rate-limited? Did the context window overflow? Each requires different user action. |
| **Complexity** | MEDIUM |
| **Mechanism** | Parse subprocess exit codes and stderr from the Claude Code process. Map to error categories: (1) CLI not found (exit code from OS, "command not found" in stderr), (2) Auth failure (API key issues), (3) Rate limit (429 errors, "rate limit" in output), (4) Context exhaustion (result message with `is_error: true`), (5) Network failure (connection errors), (6) Timeout (process hung). Display category-specific messages with actionable guidance. |
| **Changes Required** | (1) `bridge.py`: capture stderr, parse exit codes, parse `result` messages for `is_error`. Define error category enum. (2) New `errors.py` module: error classification, user-friendly message templates. (3) `tui.py` and `cli.py`: display categorized errors with Rich formatting. |
| **Dependencies** | None -- can be done independently. |
| **Verification** | MEDIUM confidence. Error categories inferred from multiple community sources and GitHub issues. Exact stderr formats from Claude Code are not formally documented; will need empirical testing. |

### ERR-02: Subprocess Lifecycle Management

| Attribute | Detail |
|-----------|--------|
| **Why Expected** | The current bridge spawns a subprocess and reads stdout until EOF. If the process hangs, the entire app hangs. If the user cancels mid-stream, cleanup is best-effort. In multi-turn mode, subprocess lifecycle matters more because we spawn many processes per session. |
| **Complexity** | LOW-MEDIUM |
| **Mechanism** | (1) Add a configurable timeout to `stream_claude_response()` -- if no data arrives within N seconds, raise a timeout error. (2) Ensure proper process cleanup on cancellation (the existing `proc.terminate()` / `proc.wait()` pattern is correct but needs the timeout). (3) In multi-turn mode, ensure the previous process is fully dead before spawning the next one. |
| **Changes Required** | (1) `bridge.py`: add `asyncio.wait_for()` wrapper or per-read timeout. (2) Add process cleanup verification. (3) Add a guard against concurrent subprocess spawns. |
| **Dependencies** | MTURN-01 (multi-turn mode creates the need for careful lifecycle management). |
| **Verification** | HIGH confidence. Standard async subprocess patterns. The existing code already has the right structure; it just needs timeout guards. |

---

## Differentiators

Features that elevate beyond basic expectations. Not required, but valued.

### MTURN-03: No-TUI REPL Mode

| Attribute | Detail |
|-----------|--------|
| **Value** | Currently `--no-tui` requires a prompt argument and exits after one response. For multi-turn without TUI, users need a simple REPL loop: prompt, response, prompt, response. This serves piped/scripted usage and users who prefer plain stdout. |
| **Complexity** | LOW |
| **Mechanism** | Add an `asyncio` event loop in CLI that reads from stdin (using `aioconsole` or simple `input()` in a thread), sends to bridge with session_id persistence, and loops until Ctrl-D/Ctrl-C. |
| **Dependencies** | MTURN-01 (session persistence). |

### MTURN-04: Turn Separator / Visual Markers

| Attribute | Detail |
|-----------|--------|
| **Value** | In multi-turn conversations, it becomes hard to tell where one response ends and the next begins, especially on paper. Visual separators between turns improve readability. |
| **Complexity** | LOW |
| **Mechanism** | After each response completes, emit a horizontal rule or blank line separator. On printer, emit a line of dashes or a double newline. In TUI, use a styled separator line. The transcript already prefixes user prompts with `> `. |
| **Dependencies** | MTURN-01. |

### WRAP-03: Reactive Width on Terminal Resize

| Attribute | Detail |
|-----------|--------|
| **Value** | If the user resizes their terminal during a conversation, the wrap width should update. Textual widgets handle resize events natively, but the wrap buffer needs to know the new width. |
| **Complexity** | LOW |
| **Mechanism** | In TUI mode, listen to Textual's `on_resize` event and update the `WordWrapBuffer` width. In `--no-tui` mode, query `shutil.get_terminal_size()` periodically or on SIGWINCH. For printer output, width is fixed (80 or 132 columns) and does not resize. |
| **Dependencies** | WRAP-01. |

### ERR-03: Retry with Backoff for Transient Errors

| Attribute | Detail |
|-----------|--------|
| **Value** | Rate limit (429) and overload (529) errors are transient. Instead of showing an error and stopping, automatically retry with exponential backoff. This is especially important in multi-turn mode where losing the conversation is costly. |
| **Complexity** | MEDIUM |
| **Mechanism** | In `bridge.py`, detect rate limit / overload from stderr or result message. Wait with exponential backoff (1s, 2s, 4s, max 30s). Show "Rate limited, retrying in Xs..." in the UI. Limit to 3-5 retries before giving up. |
| **Dependencies** | ERR-01 (error classification). |

### ERR-04: Graceful "Claude Code Not Found" First-Run Experience

| Attribute | Detail |
|-----------|--------|
| **Value** | If `claude` is not on PATH, the current tool crashes with a Python subprocess error. A first-run check with a clear message ("Claude Code CLI not found. Install it from...") dramatically improves onboarding. |
| **Complexity** | LOW |
| **Mechanism** | On startup, check `shutil.which("claude")`. If missing, show a Rich-formatted error panel with installation instructions and exit cleanly. |
| **Dependencies** | None. |

### MTURN-05: Session Display / Indicator

| Attribute | Detail |
|-----------|--------|
| **Value** | Show the current session ID (truncated) and turn count in the TUI header or footer. Gives users confidence that multi-turn is working and helps with debugging. |
| **Complexity** | LOW |
| **Mechanism** | Update Textual `Header` subtitle or add a status line showing "Session: abc123... | Turn 3 | Context: 45%". |
| **Dependencies** | MTURN-01, MTURN-02. |

---

## Anti-Features

Features to explicitly NOT build for this milestone.

| Anti-Feature | Why It Seems Good | Why Avoid | What to Do Instead |
|--------------|-------------------|-----------|-------------------|
| Client-side conversation history | "Store messages locally so we can resume without Claude Code sessions" | Claude Code already manages session persistence on disk. Reimplementing conversation storage creates state sync issues and doubles storage. Our bridge is intentionally thin. | Use Claude Code's native `--resume` / `--session-id` flags. They handle all persistence. |
| Client-side context truncation | "Truncate old messages when context fills up" | Claude Code's auto-compact is smarter -- it summarizes rather than truncating. Client-side truncation would fight with server-side compaction and produce worse results. | Let Claude Code handle compaction. Surface the usage stats and error messages to users. |
| Streaming input format | "Use `--input-format stream-json` for true bidirectional streaming" | This is for advanced SDK integrations where you pipe a continuous JSON stream to Claude Code's stdin. Massively more complex than sequential `--resume` calls, and unnecessary for human-paced conversation where there are natural turn boundaries. | Use sequential `claude -p --resume <sid>` calls. Each turn is a clean subprocess. Simple, debuggable, correct. |
| Markdown rendering in TUI | "Parse markdown from Claude's responses and render with Rich formatting" | The typewriter aesthetic IS plain text. Rendering markdown adds complexity, breaks the character-by-character pacing model (you would need to buffer complete blocks to format them), and conflicts with printer output which is inherently plain text. | Output raw text. The `Log` widget shows text as-is. Users who want formatted output should use Claude Code directly. |
| `/compact` and `/clear` command passthrough | "Let users type /compact or /clear to manage context" | These are Claude Code interactive REPL commands, not flags for `-p` print mode. They do not work with subprocess invocation. Attempting to implement them would require switching from `-p` to interactive mode with PTY, which is a complete architecture change. | Surface context usage stats. When context is exhausted, suggest the user start a new session (which resets context). |
| Custom system prompts per session | "Let users set a system prompt for the conversation" | Feature creep. Claude Code already supports `--append-system-prompt` and `--system-prompt`. Adding UI for this in the TUI is scope expansion beyond the milestone. | Document that users can pass `--append-system-prompt` through Claude Code if needed. Consider for a future milestone. |

---

## Feature Dependencies

```
[MTURN-01: Session Persistence]
    |
    +--enables--> [MTURN-02: Context Window Awareness]
    |                 |
    |                 +--enables--> [MTURN-05: Session Display]
    |
    +--enables--> [MTURN-03: No-TUI REPL Mode]
    |
    +--enables--> [MTURN-04: Turn Separators]
    |
    +--requires--> [ERR-02: Subprocess Lifecycle] (multi-turn = many subprocesses)

[WRAP-01: TUI Word Wrap]
    |
    +--shares-impl--> [WRAP-02: Printer Word Wrap]
    |
    +--enables--> [WRAP-03: Reactive Resize]

[ERR-01: Categorized Errors]
    |
    +--enables--> [ERR-03: Retry with Backoff]
    |
    +--enables--> [ERR-04: First-Run Check] (independent but related)

[ERR-02: Subprocess Lifecycle]
    +--independent (benefits from ERR-01 for error display)
```

### Dependency Notes

- **MTURN-01 is the keystone.** Everything multi-turn depends on session_id capture and passthrough. Build this first.
- **WRAP-01 and WRAP-02 share a `WordWrapBuffer` implementation.** Build the buffer as a standalone module, then integrate into both TUI and printer output pipelines.
- **ERR-01 and ERR-02 are independent of multi-turn** but become more important because multi-turn sessions are longer-lived and encounter more error conditions.
- **No circular dependencies.** The feature set is cleanly layered.

---

## MVP Recommendation for v1.1

### Must Ship (defines the milestone)

1. **MTURN-01: Session-Persistent Multi-Turn** -- The headline feature. Without this, there is no v1.1.
2. **WRAP-01: TUI Word Wrap** -- Visible quality improvement that users will notice immediately.
3. **WRAP-02: Printer Word Wrap** -- Completes the word wrap story; uses same buffer implementation.
4. **ERR-01: Categorized Error Messages** -- Users hit errors in multi-turn; they need to understand what went wrong.
5. **ERR-02: Subprocess Lifecycle Management** -- Timeout guards prevent the app from hanging during multi-turn.

### Should Ship (high value, low cost)

6. **MTURN-03: No-TUI REPL Mode** -- Small addition that makes `--no-tui` mode actually usable for multi-turn.
7. **MTURN-04: Turn Separators** -- Trivial to implement, significant readability improvement.
8. **ERR-04: First-Run Check** -- One function call, prevents the most confusing error new users will hit.

### Defer (nice but not milestone-defining)

9. **MTURN-02: Context Window Awareness** -- Nice status indicator, but Claude Code handles compaction automatically. Can be added later.
10. **WRAP-03: Reactive Resize** -- Edge case; most terminal sessions stay one size. Low priority.
11. **ERR-03: Retry with Backoff** -- Useful for heavy users. Not critical for milestone launch.
12. **MTURN-05: Session Display** -- Polish feature. Depends on MTURN-02 for context stats.

---

## Implementation Complexity Summary

| Feature | Lines of Code (est.) | New Files | Modified Files | Risk |
|---------|---------------------|-----------|----------------|------|
| MTURN-01 | ~60 | 0 | bridge.py, tui.py, cli.py | LOW -- well-defined CLI flags |
| MTURN-02 | ~40 | 0 | bridge.py, tui.py | LOW -- parsing existing NDJSON fields |
| MTURN-03 | ~50 | 0 | cli.py | LOW -- standard REPL pattern |
| MTURN-04 | ~15 | 0 | tui.py, cli.py | TRIVIAL |
| MTURN-05 | ~20 | 0 | tui.py | LOW |
| WRAP-01 | ~80 | 1 (wrap.py) | tui.py | MEDIUM -- streaming wrap is tricky |
| WRAP-02 | ~20 | 0 | printer.py | LOW -- reuses wrap.py |
| WRAP-03 | ~15 | 0 | tui.py, wrap.py | LOW |
| ERR-01 | ~100 | 1 (errors.py) | bridge.py, tui.py, cli.py | MEDIUM -- error formats need testing |
| ERR-02 | ~30 | 0 | bridge.py | LOW |
| ERR-03 | ~40 | 0 | bridge.py, errors.py | LOW-MEDIUM |
| ERR-04 | ~15 | 0 | cli.py | TRIVIAL |

**Total estimate for Must Ship:** ~290 lines across 2 new files and 4 modified files.
**Total estimate for Should Ship:** ~80 additional lines.

---

## Streaming Word Wrap Algorithm Detail

This is the trickiest implementation detail. Standard `textwrap.wrap()` operates on complete strings, not character streams. The `WordWrapBuffer` needs to work character-by-character because the pacer emits one character at a time.

### Algorithm

```
State: line_buffer (list of chars), word_buffer (list of chars), column (int), width (int)

on_char(ch):
    if ch == '\n':
        flush word_buffer to line_buffer
        emit line_buffer as a line
        reset column to 0
    elif ch == ' ':
        flush word_buffer to line_buffer (with the space)
        if column >= width:
            emit line_buffer as a line
            reset column to 0
    else:
        word_buffer.append(ch)
        column += 1
        if column >= width:
            # Word is too long for remaining line space
            if line_buffer has content:
                emit line_buffer as a line (without current word)
                reset: line_buffer = word_buffer, column = len(word_buffer)
            else:
                # Single word exceeds full line width -- force break
                emit word_buffer as a line
                reset column to 0
```

### Key Properties

- Emits complete wrapped lines, not individual characters
- The output function receives lines that are already wrapped to width
- The pacer still operates character-by-character on the raw input; the wrap buffer sits BETWEEN the bridge and the display
- For TUI: wrap buffer emits to `log.write()` (which handles one-line-at-a-time well)
- For printer: wrap buffer emits to `printer_write()` character-by-character within each line
- Width is configurable: terminal width for TUI, 80 for standard printer, 132 for wide-carriage

### Integration Point

The wrap buffer replaces direct `log.write(char)` calls. Instead:
```
bridge -> pacer(char-by-char) -> wrap_buffer.on_char(ch) -> log.write(wrapped_line)
```

This means the pacer still controls timing, but the display receives properly wrapped content.

---

## Sources

- [Claude Code CLI Reference](https://code.claude.com/docs/en/cli-reference) -- `--session-id`, `--resume`, `--continue`, `--output-format stream-json` flags (HIGH confidence, official docs)
- [Claude Agent SDK NDJSON Spec](https://gist.github.com/SamSaffron/603648958a8c18ceae34939a8951d417) -- Full message type definitions including `system/init` with `session_id` and `result` with usage stats (HIGH confidence)
- [Textual Log Widget Docs](https://textual.textualize.io/widgets/log/) -- `write()`, `write_line()`, no built-in wrap (HIGH confidence, official docs)
- [Textual RichLog Widget Docs](https://textual.textualize.io/widgets/rich_log/) -- `wrap=True` parameter, operates on complete renderables (HIGH confidence, official docs)
- [Textual text-wrap CSS](https://textual.textualize.io/styles/text_wrap/) -- `text-wrap: wrap | nowrap` CSS property (HIGH confidence, official docs)
- [Python textwrap Module](https://docs.python.org/3/library/textwrap.html) -- Standard library word wrapping (operates on complete strings, not streams) (HIGH confidence)
- [Python shutil.get_terminal_size()](https://docs.python.org/3/library/shutil.html) -- Terminal width detection (HIGH confidence)
- [CLI UX Patterns](http://lucasfcosta.com/2022/06/01/ux-patterns-cli-tools.html) -- Conversational CLI patterns, error suggestion, progressive disclosure (MEDIUM confidence)
- [Command Line Interface Guidelines](https://clig.dev/) -- CLI design best practices for error messages and help text (MEDIUM confidence)
- [Typer Exception Handling](https://typer.tiangolo.com/tutorial/exceptions/) -- `typer.Exit`, Rich traceback integration (HIGH confidence, official docs)
- [Claude Code Context Management](https://claudelog.com/faqs/what-is-claude-code-auto-compact/) -- Auto-compact behavior, context window limits (MEDIUM confidence)
- [Claude Code GitHub Issues](https://github.com/anthropics/claude-code/issues/42) -- Auto-compact discussion, context limit errors (MEDIUM confidence)

---
*Feature research for: Claude Teletype v1.1 -- Multi-turn, Word Wrap, Error Handling*
*Researched: 2026-02-16*
