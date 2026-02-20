# Phase 17: Claude-CLI Warnings - Context

**Gathered:** 2026-02-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Two informational warnings for the claude-cli backend: (1) startup warning when system_prompt is configured but backend is claude-cli (system_prompt is ignored), and (2) settings modal warning when hot-swapping away from claude-cli (session context will be lost). Warnings are informational only — they do not block the user from proceeding (except the hot-swap confirmation).

</domain>

<decisions>
## Implementation Decisions

### Warning tone and content
- Friendly and explanatory tone — not terse technical messages
- Always include remediation suggestion (e.g., "To use system_prompt, switch to openai or openrouter backend")
- Explain WHY the limitation exists (e.g., "Claude Code manages its own context via CLAUDE.md")

### Startup warning frequency
- Show once per config combination — don't re-warn on every launch if config hasn't changed
- Re-show when relevant config changes (system_prompt or backend setting)

### Hot-swap warning behavior
- Blocking confirmation before the swap executes — user must confirm to proceed
- This is the one exception to "warnings don't block" — preventing accidental context loss warrants confirmation

### Claude's Discretion
- Visual presentation style (Rich panel, colored text, inline — whatever fits each context)
- TUI vs non-TUI mode differences (adapt to each mode's native patterns)
- Where in the settings modal the hot-swap warning appears (inline, dialog, etc.)
- Cancellation behavior when user declines the hot-swap
- Whether startup warning also triggers in settings modal when configuring the conflicting combo
- Which backend swaps trigger the context-loss warning (just away-from-claude-cli, or any context-losing swap)
- How "seen" state is tracked for once-per-config suppression
- Whether startup warning blocks briefly or appears non-blocking
- Whether a suppress_warnings config option is offered

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 17-claude-cli-warnings*
*Context gathered: 2026-02-20*
