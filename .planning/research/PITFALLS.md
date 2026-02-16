# Domain Pitfalls: v1.1 Multi-Turn Conversation

**Domain:** Adding multi-turn conversation, context management, word wrap, and error handling to an existing CLI wrapper tool
**Researched:** 2026-02-16
**Confidence:** HIGH (verified with Claude Code official docs, Textual docs, Python asyncio docs, GitHub issues)

## Critical Pitfalls

Mistakes that cause rewrites or major breakage if not caught early.

### Pitfall 1: Treating `--continue` as Stateless When It Relies on Claude Code's Session Storage

**What goes wrong:**
The developer builds multi-turn by spawning `claude -p "prompt" --continue --output-format stream-json` for each turn, assuming `--continue` always picks up the last conversation. It works in testing. In production, two things break: (a) if the user runs Claude Code interactively in another terminal between turns, `--continue` resumes THAT session instead of the teletype conversation; (b) if `~/.claude/projects/` is cleaned up (common OOM mitigation), all session state disappears and `--continue` starts fresh with no warning.

**Why it happens:**
`--continue` loads "the most recent conversation in the current directory." It has no affinity to your process -- it picks whatever session file was last modified in `~/.claude/projects/<project-hash>/`. Any Claude Code invocation (interactive, another script, even a pre-commit hook) can change which session is "most recent." The session state is stored in `.jsonl` files on disk that are outside your control.

**Consequences:**
- Conversation context silently switches to a completely unrelated session
- User sees Claude reference files/code from a different conversation
- Auto-truncation logic operates on wrong conversation length
- No error is raised -- everything appears to work, but context is wrong

**Prevention:**
1. Use `--resume <session_id>` instead of `--continue`. Capture the `session_id` from the first turn's JSON output (`result` message has `session_id` field) and pass it explicitly to every subsequent turn.
2. Extract session_id from the `system/init` NDJSON event (first line of stream-json output) which contains `"session_id": "..."`.
3. Store the session_id in your app state (TeletypeApp instance variable, or a module-level variable for CLI mode).
4. If `--resume` fails (session file deleted/corrupted), detect the error and start a new session cleanly rather than silently losing context.

**Detection:**
- Log the session_id from each turn's init event and compare across turns -- they should match
- Test with a second Claude Code session running in parallel

**Confidence:** HIGH -- verified from [official Claude Code CLI docs](https://code.claude.com/docs/en/cli-reference) and [headless mode docs](https://code.claude.com/docs/en/headless).

**Phase to address:** First phase (multi-turn bridge). This is the foundational session management decision.

---

### Pitfall 2: Subprocess Lifecycle Leak -- Zombie Processes and Orphaned Claude Instances

**What goes wrong:**
In the current one-shot design, each `stream_claude_response()` call spawns a subprocess, reads it to EOF, and waits for exit. Simple. In multi-turn, the user sends many prompts in a session. If any turn is interrupted (user types new prompt while response is streaming, TUI cancels the worker, KeyboardInterrupt, network timeout), the subprocess may not be properly terminated. Over a 30-minute conversation with 20 turns and a few interruptions, multiple orphaned `claude` processes accumulate, each consuming 200-500MB of RAM (Claude Code is a Node.js process with V8 heap).

**Why it happens:**
The current code has a `try/except BaseException` that calls `proc.terminate()` and `await proc.wait()`. But in the TUI, the worker uses `@work(exclusive=True)` which cancels the previous worker via `asyncio.CancelledError`. If the cancellation happens between `proc.terminate()` and `await proc.wait()`, the wait is never completed, leaving a zombie. Additionally, `terminate()` sends SIGTERM which Claude Code may not handle during active API calls -- the process keeps running.

**Consequences:**
- Memory usage grows linearly with conversation length
- System becomes sluggish after extended sessions
- macOS may kill the parent process (the TUI) via OOM pressure
- On next launch, `~/.claude/` cache accumulates from all the orphaned sessions

**Prevention:**
1. Implement a robust subprocess cleanup pattern:
   ```python
   async def _kill_process(proc):
       proc.terminate()
       try:
           await asyncio.wait_for(proc.wait(), timeout=5.0)
       except asyncio.TimeoutError:
           proc.kill()
           await proc.wait()
   ```
2. Track the current subprocess in the app/bridge state so it can be explicitly killed before spawning a new one.
3. In the TUI worker's `except asyncio.CancelledError` handler, ensure the subprocess is killed before re-raising.
4. Add an `on_unmount` cleanup that kills any running subprocess.
5. Consider using `proc.kill()` (SIGKILL) instead of `proc.terminate()` (SIGTERM) for Claude Code, since it is a Node.js process that may not handle SIGTERM during API calls.

**Detection:**
- Run `ps aux | grep claude` after a few interrupted conversations
- Monitor RSS memory growth over a 10-turn session with some cancellations

**Confidence:** HIGH -- based on Python asyncio subprocess documentation and [Claude Code OOM issue #13126](https://github.com/anthropics/claude-code/issues/13126).

**Phase to address:** First phase (multi-turn bridge). Must be designed into the subprocess lifecycle from the start.

---

### Pitfall 3: Session Corruption from `--resume` on Killed/Interrupted Sessions

**What goes wrong:**
The user's teletype session is interrupted (Ctrl+C, macOS sleep, network drop) while Claude Code is mid-response. The session `.jsonl` file in `~/.claude/projects/` now has an incomplete tool_use record with no corresponding tool_result. On the next turn, `claude -p "next prompt" --resume <session_id>` crashes with `Error: No messages returned` or produces unpredictable behavior.

**Why it happens:**
Claude Code writes session events to `.jsonl` files incrementally. If the process is killed between writing a tool_use and its tool_result, the session file is semantically invalid. The `--resume` loader expects matched pairs and crashes when it finds an orphaned tool_use. This is a [known bug](https://github.com/anthropics/claude-code/issues/18880) with no automatic recovery.

**Consequences:**
- Next turn crashes with an opaque Node.js error
- Session cannot be resumed -- all conversation context is lost
- User sees a cryptic error and must restart from scratch
- If the wrapper retries `--resume` in a loop, it crashes in a loop

**Prevention:**
1. Always check the subprocess exit code after each turn. If non-zero, do NOT retry with `--resume` on the same session_id.
2. Implement a session recovery strategy: on `--resume` failure, start a fresh session (new session_id) and inform the user that context was lost.
3. Read stderr from the subprocess -- Claude Code writes error details there. Parse for known error patterns like "No messages returned" or "Conversation too long."
4. Before each `--resume`, consider using `--fork-session` to create a new session based on the old one, avoiding corruption of the original.
5. Alternatively, manage conversation history in-process (see Pitfall 4) instead of relying on Claude Code's session persistence.

**Detection:**
- Kill the subprocess mid-response and attempt to resume
- Test with `kill -9` during an active stream

**Confidence:** HIGH -- verified from [Claude Code issue #18880](https://github.com/anthropics/claude-code/issues/18880) which documents exact crash behavior.

**Phase to address:** First phase (multi-turn bridge). Error recovery must be designed alongside the happy path.

---

### Pitfall 4: Choosing Between Claude Code Session Management vs. In-Process History -- Getting Stuck Between Two Incomplete Approaches

**What goes wrong:**
The developer starts with `--resume` for multi-turn (let Claude Code manage context), then hits corruption issues (Pitfall 3), then partially switches to maintaining conversation history in-process (building message arrays and passing them somehow), but cannot cleanly pass history to `claude -p` since it only accepts a single prompt string. They end up with a hybrid: sometimes using `--resume`, sometimes reconstructing context in the prompt, with no clear ownership of conversation state.

**Why it happens:**
There are two fundamentally different approaches to multi-turn in a CLI wrapper:

**Approach A: Claude Code manages sessions** -- Use `--resume <session_id>` and let Claude Code's internal session storage handle context. Pros: zero token counting, automatic tool result tracking, handles compaction. Cons: session corruption, no control over truncation, relies on disk state you do not own.

**Approach B: In-process history management** -- Build conversation history in your process, concatenate it into the prompt string, spawn fresh `claude -p` each time. Pros: full control, no session corruption, portable. Cons: must implement token counting/truncation yourself, lose tool use context, prompt gets huge, no access to Claude Code's compaction.

Neither approach is complete on its own. The trap is starting one, hitting a wall, and grafting the other on top.

**Consequences:**
- Inconsistent context across turns (some turns have full history, some do not)
- Duplicate code paths for session management
- Truncation logic fights with Claude Code's own compaction
- Impossible to test reliably because behavior depends on disk state

**Prevention:**
Pick ONE approach and commit to it. For Claude Teletype, the recommendation is **Approach A (Claude Code manages sessions)** because:
1. The tool already uses `--output-format stream-json` which provides `session_id`
2. Claude Code handles its own context compaction at ~95% capacity
3. Tool use results (WebSearch, WebFetch) are tracked automatically
4. The only mitigation needed is robust error handling for session corruption (Pitfall 3)

If Approach A is chosen:
- Extract `session_id` from first turn, store it, pass via `--resume` on subsequent turns
- On any subprocess error, fall back to a new session (lose context gracefully)
- Do NOT also try to track history in-process -- let Claude Code own it entirely
- Set `max_lines` on the Log widget to prevent unbounded UI memory growth (separate from API context)

**Detection:**
- Code review: search for both `--resume` AND manual prompt history construction in the same codebase
- If conversation history is stored in two places, architecture is confused

**Confidence:** HIGH -- synthesis of official docs and architectural analysis of the codebase.

**Phase to address:** First phase (multi-turn bridge). This is the foundational architecture decision.

---

## Moderate Pitfalls

Mistakes that cause significant bugs or rework but are contained to specific modules.

### Pitfall 5: Word Wrap in Textual Log Widget Breaks Mid-Word During Character-by-Character Streaming

**What goes wrong:**
The developer adds `text-wrap: wrap` CSS to the Log widget to enable word wrapping. It works for complete lines. But Claude Teletype writes characters one at a time via `log.write(char)`. The Log widget has no way to know that the current sequence of characters is a word in progress. It wraps at the widget boundary mid-word, then when the next character arrives, the layout re-flows and the word jumps to a new position. The visual effect is jarring -- text jitters and re-wraps constantly as each character is added.

**Why it happens:**
Textual's Log widget (and its CSS text-wrap property) operates on complete lines. When you call `log.write("H")`, `log.write("e")`, `log.write("l")`, `log.write("l")`, `log.write("o")`, each write potentially triggers a layout recalculation. The widget does not buffer partial words or defer wrapping until a word boundary (space or newline). There was a [historical bug](https://github.com/Textualize/textual/issues/1554) with TextLog and wrap=True causing layout corruption, which was fixed, but the fundamental issue of character-by-character writing conflicting with word-level wrapping remains.

**Prevention:**
1. Do NOT apply word wrap at the Log widget level for character-by-character streaming. Instead, implement word wrap in the output pipeline BEFORE writing to the Log.
2. Create a `WordWrapFilter` in the output chain that buffers characters, tracks column position, and emits wrapped text:
   - On space/newline: flush the current word to the Log
   - On non-space: buffer the character
   - When buffered word + column position would exceed width: emit a newline first, then the word
3. This filter sits between the pacer and the Log write, so the Log only receives pre-wrapped text and never needs to re-flow.
4. The printer already has column-tracking word wrap in `make_printer_output()` (wraps at 80 columns). Apply the same pattern to the TUI output, but with the Log widget's width.
5. Handle widget resize: when the Log width changes, the wrap width changes. For simplicity, only apply the new width to NEW text -- do not re-wrap existing content (matches physical printer behavior where printed text cannot be un-printed).

**Detection:**
- Type a long prompt, watch the Log output -- if text visibly jumps/re-flows as characters appear, wrapping is fighting with streaming
- Test with a response containing long words or URLs that exceed the widget width

**Confidence:** MEDIUM -- Textual docs confirm text-wrap CSS exists but do not specifically document behavior with character-by-character write(). The jitter behavior is inferred from how layout recalculation works. Needs validation.

**Phase to address:** Word wrap phase. Must be designed as a pipeline filter, not a CSS property.

---

### Pitfall 6: Not Reading stderr -- Missing Claude Code Error Messages

**What goes wrong:**
The current `stream_claude_response()` creates the subprocess with `stderr=asyncio.subprocess.PIPE` but never reads from it. When Claude Code encounters an error (network failure, authentication expired, rate limit, model overloaded), it writes the error to stderr and exits with a non-zero code. The wrapper sees an empty stdout stream (no text_delta events), reports "No response received from Claude," and the user has no idea what went wrong. This is already a latent bug in v1.0 but becomes critical in multi-turn where errors need to be surfaced and recovered from.

**Why it happens:**
In the v1.0 one-shot design, the error path was simple: no output = no response, show a generic message. The developer never needed stderr because there was no recovery action to take. In multi-turn, the error type determines the recovery: network error = retry, auth expired = tell user, rate limit = wait and retry, session corrupt = new session.

**Consequences:**
- User sees "No response received" for every error type -- no actionable information
- Multi-turn retry logic cannot distinguish recoverable from fatal errors
- Rate limit hits cause immediate retry, making the rate limit worse
- Authentication failures loop forever instead of exiting

**Prevention:**
1. After `await proc.wait()`, check `proc.returncode`. If non-zero, read stderr:
   ```python
   stderr_bytes = await proc.stderr.read()
   error_msg = stderr_bytes.decode("utf-8", errors="replace")
   ```
2. Classify errors by parsing stderr content:
   - "not found" / exit code 127 = Claude Code not installed
   - "rate limit" / "overloaded" = transient, retry with backoff
   - "authentication" / "API key" = fatal, tell user
   - "No messages returned" = session corruption, start new session
   - "context" / "too long" = conversation exceeded limits
3. Surface the classified error to the user in the TUI (write to Log) and CLI (print to stderr).
4. Drain stderr concurrently with stdout to prevent deadlock (unlikely with stderr being small, but correct practice):
   ```python
   stderr_task = asyncio.create_task(proc.stderr.read())
   # ... read stdout lines ...
   stderr_bytes = await stderr_task
   ```

**Detection:**
- Test with `claude` not on PATH -- should show "Claude Code not installed," not "No response"
- Test with expired auth token
- Test by killing network mid-response

**Confidence:** HIGH -- verified by reading the current `bridge.py` code which pipes stderr but never reads it, and [Claude Code exit code documentation](https://github.com/anthropics/claude-code/issues/771).

**Phase to address:** Error handling phase, but the stderr reading infrastructure should be added to the bridge in the multi-turn phase.

---

### Pitfall 7: Unbounded Memory Growth in Long Conversations -- Log Widget and Transcript

**What goes wrong:**
A user has a 50-turn conversation over 2 hours. Each Claude response averages 500 words. The Textual Log widget stores all text in memory (no `max_lines` set -- current default is None/unlimited). The transcript writer keeps a file handle open and writes incrementally (good), but the Log widget's internal line buffer grows to tens of thousands of lines. Combined with the pacer's character-by-character writes causing layout recalculation on each character, the TUI becomes sluggish, then unresponsive.

**Why it happens:**
The Log widget's `max_lines` parameter defaults to `None` (unlimited). Each `log.write(char)` call appends to the internal line list. Over a long conversation, this list grows without bound. The widget must render all lines for scrollback, even if only the last screenful is visible.

Additionally, Claude Code's own session cache in `~/.claude/` grows with conversation length. The `.jsonl` session file can reach 77MB+ in extended sessions, and `shell-snapshots/` can grow to 1.5GB ([issue #13126](https://github.com/anthropics/claude-code/issues/13126)). This is outside the wrapper's control but affects overall system memory.

**Prevention:**
1. Set `max_lines` on the Log widget to a reasonable limit (e.g., 5000 lines). This drops the oldest lines when the limit is reached. The transcript file retains everything.
2. In `compose()`, change: `Log(id="output", auto_scroll=True, max_lines=5000)`
3. For the CLI mode (stdout), memory is not an issue since stdout is not buffered by the app.
4. Consider adding a status indicator showing conversation length/turn count so users know how long the session has been.
5. Document that very long sessions (50+ turns) may slow down due to Claude Code's own session management overhead.

**Detection:**
- Monitor RSS memory over a 20-turn automated conversation
- Check `len(log.lines)` after extended use

**Confidence:** HIGH -- Textual Log docs confirm `max_lines` exists and defaults to None.

**Phase to address:** Multi-turn phase (set max_lines when adding conversation loop).

---

### Pitfall 8: Race Condition -- User Submits New Prompt While Previous Response Is Still Streaming

**What goes wrong:**
In the TUI, the user types a new prompt and presses Enter while Claude's previous response is still streaming character-by-character. The current code uses `@work(exclusive=True)` which cancels the previous worker. But cancellation races with subprocess I/O: the old subprocess may still be writing to stdout while the new one is spawning. Both subprocesses' output intermixes in the Log widget, producing garbled text.

**Why it happens:**
`@work(exclusive=True)` cancels the previous worker's asyncio task, which raises `CancelledError` in the `stream_response` coroutine. But the subprocess is a separate OS process -- cancelling the Python task does not immediately stop the subprocess. Between cancellation and subprocess termination, the old process may emit more NDJSON lines. If the new subprocess starts before the old one is fully dead, there is a window where both are writing.

In v1.0 this was not an issue because each prompt started a separate subprocess and the TUI did not support rapid prompt submission during streaming.

**Prevention:**
1. In the TUI's `on_input_submitted`, disable the input widget immediately while a response is streaming (already partially done with placeholder text, but the widget is not actually disabled).
2. In `stream_response`, before spawning the new subprocess, explicitly await termination of any previous subprocess.
3. Add a gate: store the current subprocess reference on the app instance. Before spawning a new one, kill and wait for the old one:
   ```python
   if self._current_proc is not None:
       self._current_proc.kill()
       await self._current_proc.wait()
       self._current_proc = None
   ```
4. Alternatively (simpler): disable the Input widget during streaming and re-enable after the response completes. This prevents the race entirely by blocking new submissions.

**Detection:**
- Rapidly submit prompts in the TUI while responses are streaming
- Watch for interleaved text from different responses in the Log

**Confidence:** HIGH -- direct analysis of current TUI code and Textual's `@work(exclusive=True)` behavior.

**Phase to address:** Multi-turn phase. The input disable/enable pattern must be part of the conversation loop design.

---

## Minor Pitfalls

Mistakes that cause user-facing bugs but are quick to fix.

### Pitfall 9: `--resume` Session ID Not Available in `stream-json` Init Event Until Process Starts

**What goes wrong:**
The developer tries to extract `session_id` from the first NDJSON line (the `system/init` event) to store for future `--resume` calls. But on the first turn (no session to resume), the session_id in the init event is the one Claude Code just created. The developer stores it. On the second turn, they pass `--resume <stored_id>`. This works. But if the first turn's subprocess exits with an error before emitting the init event (e.g., Claude Code not installed, immediate crash), `session_id` is never captured and the code tries to `--resume None`.

**Prevention:**
1. Default session_id to None. Only set it when successfully parsed from the init event.
2. On the second turn, if session_id is None (first turn failed), start a fresh session without `--resume`.
3. Validate that session_id is a UUID format before passing to `--resume`.

**Detection:**
- Test the flow where the first turn fails (claude not found, network error) and verify the second turn still works.

**Confidence:** HIGH -- straightforward edge case.

**Phase to address:** Multi-turn bridge phase.

---

### Pitfall 10: Transcript File Per-Session vs. Per-Conversation Confusion

**What goes wrong:**
In v1.0, the transcript writer creates one file per TUI app launch (session-scoped, init in `on_mount`, close in `on_unmount`). In multi-turn, a single TUI session now contains many turns. The transcript captures everything correctly. But if the user quits and restarts the TUI, resuming the same Claude Code session (via `--resume`), the transcript starts a new file. The conversation is now split across two transcript files with no cross-reference.

**Prevention:**
1. Include the Claude Code session_id in the transcript filename (e.g., `transcript_<session_id>_<timestamp>.txt`).
2. When resuming a session, append to the existing transcript file for that session_id instead of creating a new one.
3. Alternatively, accept the split and include a header in each transcript file noting the session_id and whether it is a continuation.

**Detection:**
- Resume a session after restarting the TUI. Check that both parts of the conversation are findable.

**Confidence:** MEDIUM -- depends on product decision about transcript continuity.

**Phase to address:** Multi-turn phase, alongside session_id management.

---

### Pitfall 11: Printer Word Wrap and TUI Word Wrap Disagree on Column Width

**What goes wrong:**
The printer wraps at 80 columns (A4_COLUMNS constant). The TUI wraps at the Log widget's current width, which varies by terminal size. The same response wraps at different points on paper vs. screen. In multi-turn, where the user is watching screen output and expecting the printer to match, the mismatch is noticeable -- especially if they are reading the printed output to someone while looking at the screen.

**Prevention:**
1. Accept the mismatch as intentional -- screen and paper have different widths. Document it.
2. OR: Add a "printer column width" setting that the TUI word-wrap filter also uses, so both outputs wrap at the same column. This means the TUI output may not fill the screen width, but it matches the paper.
3. For v1.1, option 1 (accept mismatch) is simpler. The printer already has its own wrap in `make_printer_output()`.

**Detection:**
- Compare printed output vs. TUI output for the same response with long lines.

**Confidence:** HIGH -- direct code analysis shows A4_COLUMNS=80 hardcoded.

**Phase to address:** Word wrap phase, as a design decision.

---

### Pitfall 12: Auto-Truncation Confusion -- Claude Code Already Does Compaction

**What goes wrong:**
The developer implements auto-truncation (dropping old messages when context gets too long) in the wrapper, AND Claude Code's internal compaction runs at ~95% context capacity. Both systems fight: the wrapper drops messages to stay under a token estimate, but Claude Code's compaction runs anyway because the wrapper's estimate is wrong, or the wrapper's truncation point differs from what Claude Code considers "old." The conversation summary from compaction references messages the wrapper already dropped.

**Why it happens:**
Claude Code has [built-in automatic context compaction](https://platform.claude.com/docs/en/build-with-claude/compaction) that triggers at ~95% of context window capacity. When using `--resume`, Claude Code manages the full conversation history internally. If the wrapper ALSO tries to manage history length, the two systems have conflicting views of what the conversation contains.

**Prevention:**
1. Since the recommendation is Approach A (Claude Code manages sessions -- see Pitfall 4), do NOT implement auto-truncation in the wrapper. Let Claude Code's compaction handle it.
2. The wrapper's job is to: capture session_id, pass `--resume`, handle errors, display output. NOT to manage conversation length.
3. If you must show the user that compaction happened, watch for compaction events in the NDJSON stream (Claude Code emits a system message about "organizing thoughts").
4. The only "truncation" the wrapper should do is `max_lines` on the Log widget (visual only, not affecting API context).

**Detection:**
- Search the codebase for both "truncat" and "resume" -- if both exist, there may be a conflict.

**Confidence:** HIGH -- verified from [Claude Code compaction docs](https://platform.claude.com/docs/en/build-with-claude/compaction).

**Phase to address:** Multi-turn phase. Explicitly decide NOT to implement truncation, and document why.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Multi-turn bridge | Using `--continue` instead of `--resume` (Pitfall 1) | Capture session_id, use `--resume` explicitly |
| Multi-turn bridge | Subprocess zombies from interrupted turns (Pitfall 2) | Kill-with-timeout pattern, track current proc |
| Multi-turn bridge | Session corruption on interrupted turns (Pitfall 3) | Check exit code, fall back to new session |
| Multi-turn bridge | Hybrid context management (Pitfall 4) | Commit to Approach A, let Claude Code manage sessions |
| Multi-turn bridge | Implementing auto-truncation (Pitfall 12) | Do NOT implement -- rely on Claude Code's compaction |
| Multi-turn bridge | Race condition on rapid prompts (Pitfall 8) | Disable input during streaming, kill old proc before new |
| Multi-turn bridge | Unbounded Log memory (Pitfall 7) | Set max_lines on Log widget |
| Word wrap | Character-by-character jitter (Pitfall 5) | Pipeline filter, not CSS property |
| Word wrap | Printer vs TUI width mismatch (Pitfall 11) | Accept mismatch or sync to printer width |
| Error handling | Not reading stderr (Pitfall 6) | Read and classify stderr on non-zero exit |
| Error handling | Session_id not captured on first-turn failure (Pitfall 9) | Default to None, handle gracefully |
| Transcript | Split transcripts across restarts (Pitfall 10) | Include session_id in filename |

## Integration Gotchas Specific to v1.1

| Integration Point | Common Mistake | Correct Approach |
|-------------------|----------------|------------------|
| bridge.py + multi-turn | Passing `--continue` flag | Pass `--resume <session_id>` captured from first turn's init event |
| bridge.py + error handling | Ignoring subprocess return code | Check `proc.returncode`, read stderr, classify error type |
| tui.py + multi-turn | Allowing input during streaming | Disable Input widget while worker is active, re-enable on completion |
| tui.py + word wrap | Using CSS `text-wrap: wrap` on Log | Implement word-wrap filter in output pipeline before Log.write() |
| tui.py + long sessions | Unbounded Log line storage | Set `max_lines=5000` (or similar) on Log widget |
| cli.py + multi-turn | Using asyncio.run() per prompt in a loop | Use a single asyncio event loop with a prompt-response loop inside |
| printer + word wrap | Different wrap widths for printer vs TUI | Document the difference or sync to a common column width |
| transcript + multi-turn | New file per TUI launch | Include session_id in filename, consider append-on-resume |

## "Changed Assumptions" Checklist

Things that were true in v1.0 but are no longer true in v1.1:

- [ ] **One subprocess per session:** v1.0 spawned one process and read it to completion. v1.1 spawns one process per TURN. Process lifecycle management is now critical.
- [ ] **No session state:** v1.0 had no state between prompts. v1.1 must track session_id across turns.
- [ ] **Input always available:** v1.0's input was always ready (one prompt, done). v1.1 must manage input availability during streaming.
- [ ] **Short conversations:** v1.0 was one turn. v1.1 conversations can be 50+ turns. Memory management matters.
- [ ] **Simple error path:** v1.0's error was "no response." v1.1 needs classified errors with different recovery actions.
- [ ] **Transcript is one exchange:** v1.0 wrote one prompt and one response. v1.1 transcripts contain full multi-turn conversations.

## Sources

- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference) -- session management flags, --resume vs --continue
- [Claude Code headless/programmatic docs](https://code.claude.com/docs/en/headless) -- multi-turn chaining with session_id
- [Claude Code --resume crash on killed sessions (issue #18880)](https://github.com/anthropics/claude-code/issues/18880) -- session corruption details
- [Claude Code OOM from accumulated cache (issue #13126)](https://github.com/anthropics/claude-code/issues/13126) -- memory growth in long sessions
- [Claude Code auto-compact failure (issue #13929)](https://github.com/anthropics/claude-code/issues/13929) -- context limit edge cases
- [Claude Code context compaction docs](https://platform.claude.com/docs/en/build-with-claude/compaction) -- automatic context management
- [Textual Log widget docs](https://textual.textualize.io/widgets/log/) -- max_lines, auto_scroll, write methods
- [Textual text-wrap CSS](https://textual.textualize.io/styles/text_wrap/) -- wrap/nowrap behavior
- [Textual TextLog wrap=True layout bug (issue #1554)](https://github.com/Textualize/textual/issues/1554) -- historical wrapping issues (fixed)
- [Python asyncio subprocess docs](https://docs.python.org/3/library/asyncio-subprocess.html) -- process lifecycle, deadlock prevention
- [Steve Kinney - Claude Code Session Management](https://stevekinney.com/courses/ai-development/claude-code-session-management) -- session flag behavior
- [Mastering Claude Code Sessions](https://www.vibesparking.com/en/blog/ai/claude-code/docs/cli/2025-08-28-mastering-claude-code-sessions-continue-resume-automate/) -- --continue vs --resume distinction

---
*Pitfalls research for: v1.1 multi-turn conversation, context management, word wrap, and error handling*
*Researched: 2026-02-16*
