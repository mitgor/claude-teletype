# Project Research Summary

**Project:** Claude Teletype v1.1 - Multi-Turn Conversation Mode
**Domain:** CLI wrapper enhancement for conversation continuity
**Researched:** 2026-02-16
**Confidence:** HIGH

## Executive Summary

Claude Teletype v1.1 adds multi-turn conversation capability to an existing Python CLI/TUI wrapper around the Claude Code CLI. The research confirms this can be achieved with **zero new dependencies** by leveraging Claude Code's built-in `--resume <session_id>` flag for session continuity. The bridge module captures the session_id from the NDJSON stream's init event, stores it, and passes it on subsequent turns. Claude Code handles all context window management, auto-compaction, and session persistence internally.

The recommended approach is to let Claude Code own conversation state entirely (Approach A) rather than building in-process message history. This eliminates token counting complexity and session corruption risks. Three critical changes are required: (1) bridge.py must parse session_id from NDJSON and accept `--resume` parameter, (2) TUI/CLI must hold session_id across prompt submissions, and (3) error handling must parse stderr and classify failure types to enable graceful recovery from session corruption, rate limits, and network failures.

The architecture remains clean: the existing fan-out pipeline (pacer -> output -> destinations) is unchanged. Session state lives only at the caller level (TUI app instance or CLI loop). The most significant risk is subprocess lifecycle management -- in multi-turn conversations with many subprocess spawns, zombie processes accumulate if interruptions aren't handled with explicit kill-with-timeout patterns. Word wrap can be added via a custom WordWrapper class in the output pipeline without changing the Log widget. All capabilities -- multi-turn via `--resume`, word wrap via stdlib-only character tracking, error handling via asyncio patterns -- use existing dependencies or Python standard library.

## Key Findings

### Recommended Stack

**No changes to pyproject.toml required.** Every v1.1 capability is available through the existing stack (typer, rich, textual, sounddevice, numpy) or Python standard library. Multi-turn conversation is handled via Claude Code CLI's `--resume <session_id>` flag -- no message history tracking, no anthropic SDK, no tiktoken. Word wrap is implemented via a custom WordWrapper class using stdlib only (no textwrap dependency, as it cannot operate on character streams). Error handling uses stdlib asyncio subprocess patterns with stderr capture and exit code classification.

**Core technologies (unchanged):**
- **Python >=3.12**: Runtime -- no change
- **typer >=0.23.0**: CLI argument parsing -- no change
- **rich >=14.0.0**: Console spinners and formatting -- no change
- **textual >=7.0.0**: TUI framework (Log widget) -- Keep Log, do NOT switch to RichLog which breaks character-by-character streaming
- **sounddevice >=0.5.0**: Audio bell -- no change
- **numpy >=1.26.0**: Bell waveform generation -- no change
- **Claude Code CLI**: External dependency (must be installed by user) -- verify at startup with `shutil.which("claude")`

**Key finding:** Claude Code CLI provides `--resume <session_id>` for session continuity. The first invocation emits `{"type":"system","subtype":"init","session_id":"abc-123",...}` in the NDJSON stream. Subsequent calls use `claude -p "prompt" --resume "abc-123"` to load full conversation history. Claude Code manages context limits via auto-compaction at ~95% capacity. The wrapper does NOT need to implement token counting, message truncation, or session persistence.

**What NOT to add:**
- tiktoken/anthropic-tokenizer (Claude Code manages context limits)
- tenacity (retry should be user-initiated in conversation UI)
- prompt_toolkit (conflicts with Textual's event loop)
- anthropic SDK (we wrap CLI, not API)
- aiofiles (char-by-char transcript writes are fast enough)
- pydantic (session state is a single UUID string)

### Expected Features

Research synthesized from FEATURES.md identifies table stakes, competitive differentiators, and anti-features to avoid.

**Must have (table stakes):**
- **MTURN-01: Session-Persistent Multi-Turn** -- Capture session_id from NDJSON init event, pass `--resume` on subsequent turns. Users expect follow-up prompts to have context. Without this, v1.1 has no purpose.
- **MTURN-02: Context Window Awareness** -- Surface usage stats from NDJSON result messages, handle `is_error: true` when context exhausted. Claude Code auto-compacts, but users need to see when compaction happens.
- **WRAP-01: Word-Boundary Wrap in TUI** -- Custom WordWrapper class sits between pacer and Log.write(). Current Log widget scrolls long lines off-screen. Word wrap at widget width is expected for typewriter aesthetic.
- **WRAP-02: Word-Boundary Wrap for Printer** -- Replace naive column counter in printer.py with same WordWrapper. Current code hard-breaks mid-word at 80 columns.
- **ERR-01: Categorized Error Messages** -- Parse stderr and exit codes to classify: CLI not found, auth failure, rate limit, context exhaustion, network error, timeout. Users need actionable guidance.
- **ERR-02: Subprocess Lifecycle Management** -- Kill-with-timeout pattern (SIGTERM -> wait 5s -> SIGKILL). Multi-turn spawns many subprocesses; interruptions leave zombies that consume 200-500MB each.

**Should have (competitive):**
- **MTURN-03: No-TUI REPL Mode** -- Add asyncio REPL loop to cli.py for multi-turn in `--no-tui` mode. Low complexity, high value for piped/scripted usage.
- **MTURN-04: Turn Separators** -- Emit visual markers (horizontal rule, blank line) between turns in TUI and on paper. Trivial to implement, improves readability.
- **ERR-04: First-Run Check** -- Check `shutil.which("claude")` at startup, show install URL if missing. Prevents most confusing error new users will hit.
- **MTURN-05: Session Display** -- Show truncated session_id, turn count, context usage in TUI header/footer. Confirms multi-turn is working.

**Defer (v2+):**
- **MTURN-02: Advanced Context Awareness** (beyond basic usage display) -- Context percentage indicators in status bar. Nice-to-have polish.
- **WRAP-03: Reactive Resize** -- Update wrap width on terminal resize. Edge case; most terminals stay one size.
- **ERR-03: Retry with Backoff** -- Auto-retry transient errors (rate limit, 529 overload) with exponential backoff. Useful for heavy users but not milestone-critical.

**Anti-features (explicitly do NOT build):**
- **Client-side conversation history** -- Duplicates Claude Code's session storage, causes state sync issues.
- **Client-side context truncation** -- Fights with Claude Code's auto-compaction, produces worse results.
- **Streaming input format** -- `--input-format stream-json` is for SDK integrations, not human-paced conversation.
- **Markdown rendering in TUI** -- Breaks character-by-character pacing, conflicts with printer's plain text output.
- **`/compact` and `/clear` command passthrough** -- These are interactive REPL commands, not available in `-p` print mode.
- **Custom system prompts** -- Feature creep; Claude Code already supports `--append-system-prompt` flag.

### Architecture Approach

Multi-turn requires surgical changes to three components, leaving the fan-out pipeline completely unchanged. The bridge becomes session-aware by capturing session_id from NDJSON and yielding a final `StreamResult` dataclass with metadata. The TUI/CLI callers store session_id as instance variables and pass it to the next bridge call. Error handling surfaces classified errors through `StreamResult.is_error` after reading subprocess stderr. The existing pacer/output/audio/transcript/printer modules have no session awareness and require no changes.

**Major components:**
1. **bridge.py (MODIFY)** -- Add `parse_session_id()`, `parse_result()`, `StreamResult` dataclass. Change `stream_claude_response(prompt, session_id=None) -> AsyncIterator[str | StreamResult]`. Inject `--resume <session_id>` flag if provided. Parse stderr on non-zero exit code. (~60 lines added, ~15 modified)
2. **tui.py (MODIFY)** -- Add `self._session_id: str | None` instance variable. Update `stream_response` to pass session_id, capture from StreamResult, handle errors. Wrap log.write with WordWrapper for word-boundary wrapping. (~15 lines modified)
3. **cli.py (MODIFY)** -- Add `_chat_loop_async()` for multi-turn REPL in `--no-tui` mode. Handle StreamResult. (~20-40 lines added)
4. **wrap.py (NEW)** -- WordWrapper class for character-level word-boundary wrapping. Tracks column position, buffers current word, emits newline at word boundaries. (~40 lines)
5. **pacer.py (UNCHANGED)** -- Character-level pacing has no session awareness.
6. **output.py (UNCHANGED)** -- Fan-out multiplexer is session-agnostic.
7. **audio.py, transcript.py, printer.py, teletype.py (UNCHANGED)** -- All downstream consumers of character pipeline require no changes.

**Key pattern:** Session state lives at the caller level (TUI app, CLI loop), NOT in the bridge. The bridge is stateless -- it receives session_id as parameter, returns it in StreamResult. This allows clean subprocess lifecycle per request.

**Word wrap integration:** WordWrapper sits between pacer output and Log.write() in the TUI. It buffers characters, tracks column position, and emits wrapped lines. The Log widget receives pre-wrapped text and never needs to re-flow. For printer, reuse WordWrapper to replace the existing naive column counter.

### Critical Pitfalls

The research identified 12 pitfalls across three severity levels. The top 5 critical pitfalls require design-level prevention:

1. **Using `--continue` instead of `--resume <id>`** -- `--continue` picks the most recent session in the current directory, which can silently switch to an unrelated conversation if another Claude Code process runs. **Prevention:** Capture session_id from the NDJSON `system/init` event (first line of stream-json output) and pass `--resume <session_id>` explicitly on subsequent turns. Store session_id on TUI app instance or CLI loop state.

2. **Subprocess lifecycle leak** -- In multi-turn with many subprocess spawns, interruptions (cancellation, Ctrl-C, timeout) leave zombie `claude` processes consuming 200-500MB each. Over a 30-turn conversation with interruptions, memory usage grows unbounded. **Prevention:** Implement kill-with-timeout pattern: `proc.terminate()` -> `wait(5s)` -> `proc.kill()`. Track current subprocess on app instance and explicitly kill before spawning next one. Add cleanup in `on_unmount` and `except CancelledError`.

3. **Session corruption from interrupted responses** -- If the Claude Code process is killed mid-response (incomplete tool_use without tool_result), the session `.jsonl` file becomes invalid. Next `--resume` crashes with "No messages returned." **Prevention:** Check subprocess exit code after each turn. If non-zero, do NOT retry `--resume` with the same session_id. Start a new session and inform user that context was lost. Read stderr to distinguish session corruption from other errors.

4. **Hybrid context management** -- Starting with `--resume` (Claude Code manages context), hitting corruption, then partially switching to in-process message history. Creates state sync issues and duplicate logic. **Prevention:** Commit to Approach A (Claude Code manages sessions via `--resume`). Do NOT build in-process message history. Let Claude Code's auto-compaction handle context limits. Only mitigation needed is robust error recovery for session corruption.

5. **Word wrap via CSS breaks character-by-character streaming** -- Applying `text-wrap: wrap` CSS to Log widget causes jitter as each character triggers layout recalculation. RichLog with `wrap=True` creates new renderable blocks per character, completely breaking the typewriter effect. **Prevention:** Implement word wrap as a pipeline filter BEFORE Log.write(). Create WordWrapper class that buffers characters, tracks column position, and emits wrapped text. Log receives pre-wrapped content and never needs to re-flow.

## Implications for Roadmap

Based on research, the milestone naturally divides into 3 phases with clear dependencies. Phase 1 is foundational (multi-turn), Phase 2 builds on it (error handling), Phase 3 is parallel (word wrap).

### Phase 1: Multi-Turn Conversation Foundation
**Rationale:** Session continuity is the keystone feature. Everything else depends on or benefits from multi-turn. The bridge changes are the smallest, most testable unit. All existing tests continue to pass because the new `session_id` parameter defaults to None (backward compatible).

**Delivers:**
- Session-persistent conversation via `--resume <session_id>`
- bridge.py: parse_session_id(), parse_result(), StreamResult dataclass
- tui.py: session_id state management
- cli.py: StreamResult handling (defer REPL loop if needed)
- Subprocess lifecycle management (kill-with-timeout)
- Input widget disable during streaming (prevents race condition)
- Log widget max_lines setting (prevents unbounded memory growth)

**Addresses features:**
- MTURN-01 (Session-Persistent Multi-Turn) -- MUST HAVE
- ERR-02 (Subprocess Lifecycle) -- MUST HAVE

**Avoids pitfalls:**
- Pitfall 1: Using `--continue` -- Explicit session_id capture and `--resume`
- Pitfall 2: Subprocess zombies -- Kill-with-timeout pattern
- Pitfall 3: Session corruption -- Exit code checking, graceful fallback
- Pitfall 4: Hybrid context management -- Commit to Approach A
- Pitfall 8: Race condition -- Input disable during streaming
- Pitfall 7: Unbounded memory -- Set max_lines

**Research needs:** Standard patterns. Skip `/gsd:research-phase`. Implementation is well-documented in STACK.md and ARCHITECTURE.md.

### Phase 2: Error Handling and Recovery
**Rationale:** Depends on Phase 1 (multi-turn infrastructure). Multi-turn sessions encounter more error conditions (rate limits, session corruption, network failures) and run longer, making error classification critical. Builds on StreamResult infrastructure from Phase 1.

**Delivers:**
- stderr capture and parsing
- Error classification: CLI not found, auth failure, rate limit, context exhaustion, network error, timeout
- Categorized error messages in TUI and CLI
- First-run check for Claude Code installation
- Graceful session recovery (start new session on corruption)

**Addresses features:**
- ERR-01 (Categorized Error Messages) -- MUST HAVE
- ERR-04 (First-Run Check) -- SHOULD HAVE

**Avoids pitfalls:**
- Pitfall 6: Not reading stderr -- Parse and classify errors
- Pitfall 9: Session_id not captured on failure -- Handle None gracefully

**Uses stack:**
- Python stdlib: asyncio subprocess patterns, shutil.which()
- No new dependencies

**Research needs:** Standard patterns. Skip `/gsd:research-phase`. Python asyncio error handling is well-documented.

### Phase 3: Word Wrap for TUI and Printer
**Rationale:** Independent of Phases 1-2. Can be built in parallel with Phase 2. Only dependency is knowing terminal width from TUI, which is available via widget.size. Benefits from multi-turn (long responses show wrapping value) but does not require it technically.

**Delivers:**
- wrap.py: WordWrapper class for character-level word-boundary wrapping
- TUI integration: wrap log.write with WordWrapper
- Printer integration: replace naive column counter with WordWrapper
- Configurable column width (terminal width for TUI, 80 for printer)

**Addresses features:**
- WRAP-01 (TUI Word Wrap) -- MUST HAVE
- WRAP-02 (Printer Word Wrap) -- MUST HAVE

**Avoids pitfalls:**
- Pitfall 5: CSS wrap breaks streaming -- Pipeline filter, not widget property
- Pitfall 11: Width mismatch -- Document that screen and paper wrap differently (or sync to printer width)

**Implements architecture:**
- WordWrapper as output pipeline filter between pacer and destinations

**Research needs:** Standard patterns. Skip `/gsd:research-phase`. Textual Log widget behavior is confirmed from source code.

### Phase 4 (Optional): Polish and Advanced Features
**Rationale:** Deferred features that are nice-to-have but not milestone-defining. Can be added post-v1.1 launch based on user feedback.

**Delivers:**
- MTURN-03: No-TUI REPL Mode (asyncio input loop)
- MTURN-04: Turn Separators (visual markers between turns)
- MTURN-05: Session Display (status bar with session_id, turn count, context %)
- WRAP-03: Reactive Resize (update wrap width on terminal resize)
- ERR-03: Retry with Backoff (auto-retry rate limits)

**Rationale for deferral:** These add polish but are not blocking for basic multi-turn functionality. MTURN-03 (REPL mode) is simple but serves a smaller audience than TUI. MTURN-04 (separators) and MTURN-05 (status) are trivial but not critical for conversation continuity. WRAP-03 (resize) handles an edge case. ERR-03 (retry) is useful but automatic retries in conversation UI are contentious.

### Phase Ordering Rationale

- **Phase 1 must come first:** Multi-turn is the foundation. Session state, subprocess lifecycle, and StreamResult infrastructure are prerequisites for error handling and enable word wrap testing with long responses.
- **Phase 2 builds on Phase 1:** Error handling uses the StreamResult structure from Phase 1 and becomes critical only in multi-turn sessions where errors accumulate.
- **Phase 3 is parallel:** Word wrap is independent. Can be built alongside Phase 2 or after Phase 1. Does not block error handling. Only soft dependency is that long multi-turn responses demonstrate wrapping value.
- **Phase 4 is post-launch:** Deferred features add incremental value. None block the core milestone goal (multi-turn conversation).

**Dependency chain:**
```
Phase 1 (Multi-Turn)
    |
    +--enables--> Phase 2 (Error Handling) [sequential]
    |
    +--parallel--> Phase 3 (Word Wrap) [can build during Phase 2]
    |
    +--post-launch--> Phase 4 (Polish) [defer]
```

### Research Flags

**Skip research for all phases:** All three phases use standard patterns with high-confidence documentation.

- **Phase 1:** Claude Code CLI reference (official), Python asyncio subprocess docs (official), Textual widget docs (official). Implementation path is clear from STACK.md and ARCHITECTURE.md.
- **Phase 2:** Python stdlib error handling patterns (official), subprocess stderr capture (standard). No complex integrations.
- **Phase 3:** Textual Log widget source code (verified), word-wrap algorithms (well-understood, proven in existing printer.py). No niche domain knowledge required.

**No `/gsd:research-phase` needed.** Proceed directly to requirements definition for each phase.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All recommendations verified against official Claude Code CLI docs, Textual docs, Python stdlib docs. Zero new dependencies confirmed by source code analysis. |
| Features | HIGH | Table stakes identified from Claude Code session management docs and Textual streaming patterns. Anti-features validated by architecture constraints (no PTY for `/compact`, no markdown buffering for streaming). |
| Architecture | HIGH | Surgical changes to 3 modules verified by reading existing codebase. Fan-out pipeline decoupling confirmed. StreamResult pattern matches asyncio best practices. WordWrapper algorithm proven in existing printer.py. |
| Pitfalls | HIGH | Critical pitfalls sourced from official Claude Code issue tracker (session corruption #18880, OOM #13126) and subprocess lifecycle docs. Word-wrap jitter confirmed by reading Textual Log/RichLog source code on GitHub. |

**Overall confidence:** HIGH

All recommendations are based on official documentation, verified source code, or existing codebase analysis. No speculative patterns or unverified community practices.

### Gaps to Address

**No significant gaps.** Research coverage is comprehensive across stack, features, architecture, and pitfalls.

**Minor validation items during implementation:**
- **Subprocess stderr format:** Exact error message formats from Claude Code are not formally documented. Will need empirical testing to refine error classification regex patterns. (MEDIUM priority, Phase 2)
- **WordWrapper edge cases:** Long words (URLs), tab characters, wide Unicode. Test with real Claude responses during Phase 3. (LOW priority, Phase 3)
- **Terminal resize behavior:** Whether Textual's `on_resize` event fires during active streaming. Easy to validate in Phase 3. (LOW priority, Phase 4 if deferred)

**Handling:** All gaps are implementation-level validation, not design blockers. Proceed with recommended architecture; adjust error message parsing or wrap edge cases based on testing.

## Sources

### Primary (HIGH confidence)
- [Claude Code CLI Reference](https://code.claude.com/docs/en/cli-reference) -- `--resume`, `--continue`, `--session-id`, `-p` flag combinations, `--output-format stream-json`
- [Run Claude Code Programmatically (Headless)](https://code.claude.com/docs/en/headless) -- session_id capture pattern, multi-turn chaining
- [Agent SDK Streaming Output](https://platform.claude.com/docs/en/agent-sdk/streaming-output) -- NDJSON event types, session_id field, result message format
- [Agent SDK Session Management](https://platform.claude.com/docs/en/agent-sdk/sessions) -- session ID lifecycle, forking, resumption
- [Claude API Context Windows](https://platform.claude.com/docs/en/build-with-claude/context-windows) -- 200K token context, auto-compaction behavior
- [Claude Code Context Compaction](https://platform.claude.com/docs/en/build-with-claude/compaction) -- automatic context management at ~95% capacity
- [Textual Log Widget](https://textual.textualize.io/widgets/log/) -- `write()` method, `max_lines`, no native word wrap
- [Textual Log Widget Source](https://github.com/Textualize/textual/blob/main/src/textual/widgets/_log.py) -- Confirms `write()` does `self._lines[-1] += line` (inline append)
- [Textual RichLog Widget](https://textual.textualize.io/widgets/rich_log/) -- `wrap=True` parameter, renderable-level writes
- [Textual RichLog Source](https://github.com/Textualize/textual/blob/main/src/textual/widgets/_rich_log.py) -- Confirms `write()` does `Segment.split_lines()` -> new block per call
- [Textual text-wrap CSS](https://textual.textualize.io/styles/text_wrap/) -- CSS property behavior
- [Python asyncio subprocess](https://docs.python.org/3/library/asyncio-subprocess.html) -- Process lifecycle, SIGTERM/SIGKILL, deadlock prevention
- [Python shutil](https://docs.python.org/3/library/shutil.html) -- `shutil.which()`, `get_terminal_size()`
- [Python textwrap](https://docs.python.org/3/library/textwrap.html) -- Standard library word wrapping (operates on complete strings)
- [Typer Exception Handling](https://typer.tiangolo.com/tutorial/exceptions/) -- `typer.Exit`, Rich traceback integration

### Secondary (MEDIUM confidence)
- [Claude Code Session Corruption Issue #18880](https://github.com/anthropics/claude-code/issues/18880) -- Session file corruption from incomplete tool_use records
- [Claude Code OOM Issue #13126](https://github.com/anthropics/claude-code/issues/13126) -- Memory growth in long sessions, session cache accumulation
- [Claude Code Auto-Compact Failure #13929](https://github.com/anthropics/claude-code/issues/13929) -- Context limit edge cases
- [Claude Code Exit Codes Issue #771](https://github.com/anthropics/claude-code/issues/771) -- Exit code documentation
- [Claude Code stdin Hang Issue #3187](https://github.com/anthropics/claude-code/issues/3187) -- Stream-json stdin hangs
- [Claude Code Result Hang #25629](https://github.com/anthropics/claude-code/issues/25629) -- Hanging after result event
- [Textual TextLog Wrap Bug #1554](https://github.com/Textualize/textual/issues/1554) -- Historical layout corruption with wrap=True (fixed)
- [Claude Flow Stream Chaining Wiki](https://github.com/ruvnet/claude-flow/wiki/Stream-Chaining) -- Community-documented NDJSON message structure
- [Steve Kinney - Claude Code Session Management](https://stevekinney.com/courses/ai-development/claude-code-session-management) -- Session flag behavior
- [Mastering Claude Code Sessions](https://www.vibesparking.com/en/blog/ai/claude-code/docs/cli/2025-08-28-mastering-claude-code-sessions-continue-resume-automate/) -- `--continue` vs `--resume` distinction
- [CLI UX Patterns](http://lucasfcosta.com/2022/06/01/ux-patterns-cli-tools.html) -- Conversational CLI patterns, error suggestion
- [Command Line Interface Guidelines](https://clig.dev/) -- CLI design best practices
- [Claude API Tokenizer Discussion](https://claudelog.com/faqs/what-is-claude-code-auto-compact/) -- Auto-compact behavior
- [Claude Code SDK Python Error Handling](https://deepwiki.com/anthropics/claude-code-sdk-python/4-error-handling) -- ProcessError, CLIJSONDecodeError, CLINotFoundError (third-party docs of official SDK)

---
*Research completed: 2026-02-16*
*Ready for roadmap: yes*
