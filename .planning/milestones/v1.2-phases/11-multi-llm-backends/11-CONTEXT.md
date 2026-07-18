# Phase 11: Multi-LLM Backends - Context

**Gathered:** 2026-02-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can choose their LLM provider — Claude Code CLI, OpenAI, or OpenRouter — via config or CLI flag. Each backend streams character output through the same teletype pipeline for multi-turn conversation. Backend is selected at startup and locked for the session.

</domain>

<decisions>
## Implementation Decisions

### Backend & model selection
- Default backend is config-driven (TOML config sets the default, Claude Code CLI is factory default)
- Backend is locked at startup — no mid-session switching
- `--backend` flag overrides config for a single run
- Model selection: `--model` flag overrides config, config sets default model per backend, each backend has a hardcoded fallback default
- OpenRouter is a single backend — user specifies model names like `anthropic/claude-3.5-sonnet` directly

### Streaming & pipeline integration
- All backends produce the same stream format feeding into the existing character pipeline
- Output should feel consistent regardless of backend — the typewriter effect is the product's identity

### System prompt
- Users can set a system prompt via TOML config for OpenAI/OpenRouter backends
- Claude Code CLI manages its own system prompt (not configurable through teletype)

### Conversation history
- Full message history sent with every request for OpenAI/OpenRouter backends
- No turn limit — send everything (may hit context limits on very long conversations, but keep it simple for v1)
- Claude Code CLI continues to manage its own conversation state via subprocess

### Claude's Discretion
- Streaming pacing strategy (whether to buffer and normalize speed across backends or let natural speed through)
- Internal architecture for backend abstraction
- Error handling approach (startup validation, runtime error display)
- Default model choices per backend
- Context window overflow handling (if/when full history exceeds limits)

</decisions>

<specifics>
## Specific Ideas

- OpenAI and OpenRouter both use the `openai` Python SDK — OpenRouter is just a different base URL
- Claude Code CLI streams via subprocess (existing behavior), the other backends use SDK streaming
- All backends must converge into the same async character stream that the teletype pipeline already consumes

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 11-multi-llm-backends*
*Context gathered: 2026-02-17*
