# Milestones

## v1.1 Conversation Mode (Shipped: 2026-02-17)

**Phases:** 5-7 (3 phases, 7 plans)
**Timeline:** 2026-02-16 → 2026-02-17 (1 day)
**Code:** +1,655 lines across 11 Python files, 265 tests passing

**Key accomplishments:**
- Multi-turn conversation with session persistence via `--resume` flag
- Turn-formatted output with "You:"/"Claude:" labels, status bar, and input blocking
- Error classification system (7 categories) with automatic retry and exponential backoff
- Pre-flight CLI validation catches missing Claude Code with install instructions
- Streaming WordWrapper wraps long lines at word boundaries in TUI and printer
- Dynamic TUI resize support updates wrap width automatically

**Tech debt accepted:**
- `_chat_async` in cli.py not updated for StreamResult (--no-tui mode crashes at end of response)
- No test_cli.py for --no-tui code path

---


## v1.2 Configuration, Profiles, Multi-LLM, Settings (Shipped: 2026-02-17)

**Phases:** 8-15 (8 phases, 13 plans, 28 tasks)
**Timeline:** 2026-02-14 → 2026-02-17 (3 days)
**Code:** +9,483 lines across 52 files, 401 tests passing (3,191 LOC source + 5,349 LOC tests)

**Key accomplishments:**
- Persistent TOML configuration with three-layer merge (file < env vars < CLI flags)
- Data-driven printer profiles — 5 built-ins (Juki, Epson, IBM, HP, generic), custom TOML profiles, USB auto-detection
- Multi-LLM backends — Claude Code CLI, OpenAI, OpenRouter with streaming, error handling, and startup validation
- Pure typewriter mode — keystrokes to screen and printer with pacing and mechanical click sound
- Settings modal — runtime config changes (delay, audio, backend, profile) via ctrl+comma
- system_prompt preservation during backend hot-swap in settings modal
- Fixed --no-tui mode StreamResult crash from v1.1 tech debt

**Tech debt accepted:**
- IBM PPDS profile keyed as "ppds" not "ibm" (discoverability)
- `config show` reflects file+env but not CLI flags (Typer architectural constraint)
- system_prompt silently ignored for claude-cli backend
- Backend hot-swap loses session_id for claude-cli

**v1.1 debt resolved:**
- `_chat_async` StreamResult crash fixed (Phase 8)
- `--no-tui` code path now has test coverage

---

