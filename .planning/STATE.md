# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-17)

**Core value:** The physical typewriter experience -- characters appearing on paper one at a time with authentic pacing and sound, making AI conversation feel tangible and mechanical.
**Current focus:** Phase 12 - Typewriter Mode

## Current Position

Phase: 12 of 13 (Typewriter Mode)
Plan: 1 of 2 in current phase (done)
Status: Executing phase 12
Last activity: 2026-02-17 — Completed 12-01 TypewriterScreen and Keystroke Audio

Progress: [█████████████████████] 96% (25/~26 plans, 11/13 phases complete)

## Performance Metrics

**Velocity:**
- Total plans completed: 25
- Average duration: 3.6min
- Total execution time: 1.52 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-streaming-pipeline | 2 | 5min | 2.5min |
| 02-terminal-simulator | 2 | 8min | 4min |
| 03-printer-hardware | 2 | 5min | 2.5min |
| 04-audio-and-persistence | 2 | 4min | 2min |
| 05-multi-turn-conversation-foundation | 3 | 9min | 3min |
| 06-error-handling-and-recovery | 2 | 5min | 2.5min |
| 07-word-wrap-for-tui-and-printer | 2 | 6min | 3min |
| 08-no-tui-bug-fix | 1 | 2min | 2min |
| 09-configuration-system | 2 | 14min | 7min |
| 10-printer-profiles | 2 | 13min | 6.5min |
| 11-multi-llm-backends | 2 | 11min | 5.5min |
| 12-typewriter-mode | 1 | 3min | 3min |

**Recent Trend:**
- Last 5 plans: [5min, 8min, 4min, 7min, 3min]
- Trend: Fast execution for typewriter mode integration

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- WordWrapper as pipeline filter (not CSS) -- Textual Log widget hardcodes no_wrap=True
- Per-destination wrapping -- TUI and printer get wrapped output; transcript and audio get unwrapped
- StreamResult as final yield from async generator -- clean metadata propagation
- Minimal StreamResult handling in headless mode -- only display errors, silently consume success metadata
- Three-layer config merge: defaults < TOML file < env vars < CLI flags
- Pre-formatted string template for config file (tomli-w cannot write TOML comments)
- Data-driven printer profiles via frozen dataclass -- all printer behavior encoded as data, not conditional code
- USB printer class 7 filter before VID:PID matching -- prevents false matches against non-printer devices
- ProfilePrinterDriver as standalone class, JukiPrinterDriver as thin deprecated subclass -- generic profile support with backward compat
- Profile resolution chain: --printer > --juki (deprecated) > config > auto-detect > generic
- Placeholder API key in AsyncOpenAI constructor to defer validation to validate() method
- max_retries=0 on AsyncOpenAI -- TUI retry loop handles retries consistently across all backends
- SDK error messages match ERROR_PATTERNS substrings for seamless classification
- check_claude_installed() replaced by create_backend + validate() -- single validation path for all backends
- TUI _kill_process uses backend.proc_holder -- no-op for API backends
- Model name fallback chain: model_usage -> item.model -> "--" for API backends
- asyncio.Queue created in on_mount not __init__ to avoid event loop mismatch
- Backspace intentionally ignored for typewriter authenticity (append-only)
- Keystroke click is 20ms with deterministic noise seed (rng=42) for reproducible sound

### Pending Todos

None yet.

### Blockers/Concerns

- Textual 8.0 just released (2026-02-16) -- may have undocumented breaking changes beyond changelog
- OpenAI/OpenRouter need client-side message history (unlike Claude Code CLI) -- highest complexity area
- API keys must NEVER go in TOML config -- store env var names instead
- Juki 9100 control codes extrapolated from 6100 -- need hardware verification

## Session Continuity

Last session: 2026-02-17
Stopped at: Completed 12-01-PLAN.md (TypewriterScreen and Keystroke Audio)
Resume file: None
