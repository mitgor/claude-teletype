# Phase 5: Multi-Turn Conversation Foundation - Context

**Gathered:** 2026-02-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Enable session-persistent multi-turn conversation in the TUI with proper subprocess lifecycle management. Users can submit multiple prompts, see context-aware responses, and optionally resume sessions. Turn separators, status metadata, input blocking during streaming, and session resume via `--resume` flag are in scope. Error categorization and word wrapping belong to Phases 6 and 7.

</domain>

<decisions>
## Implementation Decisions

### Turn separators
- Blank space only between turns — no horizontal rules or dividers
- User's prompt is echoed in the output pane before Claude's response (transcript-style)
- Prefix labels for attribution: "You: " before user prompt, "Claude: " before response
- Printer output matches TUI — same blank lines and labels

### Session status display
- Footer bar at the bottom of the TUI, below the input area
- Shows: turn count, context usage indicator, and model name (e.g., "Turn 3 | Context: 45% | claude-sonnet-4-5-20250929")
- Footer updates between turns only, not during streaming — no flicker

### Input blocking UX
- Input area dims and is disabled while Claude streams a response
- Escape key cancels/interrupts the current streaming response
- On cancel: partial response stays visible, marked with "[interrupted]" suffix
- Existing thinking indicator (from Phase 1) reused in output area between prompt submission and first response token
- Kill-with-timeout pattern for subprocess cleanup on cancel (SIGTERM → wait 5s → SIGKILL)

### Session resume flow
- Each launch starts a new session by default — no auto-resume
- User must explicitly pass `--resume <session_id>` to continue a previous session
- Session ID printed on exit: "To resume: claude-teletype --resume <id>"
- On resume: brief summary displayed ("Resumed session abc123 (3 previous turns)"), no history replay
- If `--resume` fails (corrupted/expired): fall back to new session with clear warning message

### Claude's Discretion
- Context usage implementation: whether to parse NDJSON usage data or use turn count as proxy
- Exact dim styling for disabled input area
- Thinking indicator placement details in multi-turn context
- Subprocess lifecycle management internals

</decisions>

<specifics>
## Specific Ideas

- Turn format should feel like reading a transcript on paper — "You:" and "Claude:" labels keep it clear and mechanical
- The "[interrupted]" marker on cancelled responses is important for the transcript to be honest about what happened
- Footer should be informational but not distracting — update only between turns

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-multi-turn-conversation-foundation*
*Context gathered: 2026-02-16*
