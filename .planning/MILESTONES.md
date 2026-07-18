# Milestones

## v1.6 Printer Fleet & Standalone (Shipped: 2026-07-18)

**Phases:** 27-30 (4 phases; Phase 27 GSD-tracked with 6 plans, Phases 28-30 executed reactively outside GSD tracking)
**Timeline:** 2026-06-12 → 2026-06-13 (29 commits)
**Code:** +8,303/−1,688 lines across 82 files, 905 tests passing (7,901 LOC source + 12,925 LOC tests)
**Requirements:** 27/29 complete (REF-06, PKG-03 deferred — see Known Gaps)

**Key accomplishments:**

- Package refactor: printer.py/profiles.py split into `printing/` (drivers, discovery, selection, detection, registry), plus `rendering/` and `screens/` packages — shims used during the move, then deleted; full suite green at every step
- `ProfileRegistry` + per-family `catalog/` modules (epson, oki, star) replace the flat `BUILTIN_PROFILES` dict; `SetupDecision` enum replaces the `discovery=None` dual-meaning sentinel; USB driver selection by device identity
- Two-tier fleet detection: curated `BRIDGE_CHIPS` registry (CH341/Prolific/MosChip/FTDI) kept separate from printer profiles, `classify()` yielding NATIVE_PRINTER/BRIDGE/UNKNOWN, bridges routed to the manual family picker, serial-only chip warnings, kernel-claim → CUPS fallback
- Per-family profile catalog verified-from-manual: escp2 (ESC/P2), epson-tm (ESC/POS), enriched ppds, OKI emulation aliases + opt-in native MICROLINE, star-line, Panasonic KX-P / Tally aliases — undocumented capabilities left empty, `human_needed` where uncited
- DIR-01 codepage formalization: `codepage_command`/`text_codec`/`text_fallback` tracked, test-covered, custom-TOML supported; per-language default codepages shipped
- Standalone macOS packaging: checked-in PyInstaller onedir spec bundling libusb (frozen `usb_backend` seam), PortAudio, Textual data; `make_app.py` assembler + 10-check `smoke_frozen.sh`; graceful no-USB degradation
- Unconditional `diagnose` fleet matrix — per-device classification and per-profile capability summary; GET_PORT_STATUS readback on native USB, absent-not-broken on bridges

### Known Gaps

- **REF-06**: code-review pass over the refactored codebase never produced a findings artifact — run `/gsd:code-review` to close
- **PKG-03**: frozen `.app` verified only via headless smoke script; true clean-machine (no Homebrew/dev Python) run still manual `human_needed`

Known deferred items at close: 4 (see STATE.md Deferred Items)

---

## v1.5 Markdown File Printing (Shipped: 2026-04-28, archived 2026-06-12)

**Phases:** 21-26 (6 phases, 14 plans, 28 tasks)
**Timeline:** 2026-04-28 → 2026-04-29 (~3hr execution)
**Code:** +16,122 lines across 56 files, 700 tests passing (6,647 LOC source + 10,201 LOC tests)

**Key accomplishments:**

- `PrinterProfile` style capability fields — bold/italic/underline byte pairs + per-profile `buffer_bytes` — with custom-TOML support and the `resolve_style` fallback chain (italic→underline→plain, bold→underline→plain)
- Verified bold/italic/underline ESC sequences for all built-in profiles (Epson ESC/P, IBM PPDS, HP PCL, Juki, OKI, Citizen) from published reference manuals; capabilities left as empty bytes where undocumented (no fabricated codes)
- Streaming markdown renderer — headings, lists, fenced code, blockquotes, GFM tables, inline emphasis — composing with `WordWrapper` and the atomic CR+LF+reinit newline path via a dual-channel text/style API (`write_bytes` on all five drivers)
- TUI file picker (`ctrl+o`) rooted at cwd with `.md`/`.markdown` filtering and cancel-back-to-chat semantics
- `claude-teletype print [path]` CLI subcommand — explicit path or picker mode — honoring all config layers (TOML/env/flags)
- Per-print speed dialog (typewriter vs instant), `buffer_bytes` write chunking for impact printers, cancel-safe `renderer.close()` style cleanup, and printed-file transcript integration

**Tech debt accepted:**

- Real-hardware verification of style ESC sequences deferred (Phase 22 verification `human_needed`) — automated spec checks pass; physical confirmation pending on Epson, IBM PPDS, HP PCL, OKI ML 3390 (FX-2 mode), Citizen CT-S2000, and Juki 6100/2200 underline
- Per-profile `buffer_bytes` defaults need real-hardware validation (Juki, Epson) before instant mode is fully trusted
- WordWrapper strips the renderer's 4-space code-block indent (content survives, visual indent lost)
- Table cells truncate rather than wrap on narrow profiles (e.g. Citizen 42-col thermal)

Known deferred items at close: 1 (see STATE.md Deferred Items)

---

## v1.4 Printer Setup TUI (Shipped: 2026-04-03)

**Phases completed:** 3 phases, 6 plans, 10 tasks

**Key accomplishments:**

- Structured DiscoveryResult dataclass with discover_all() aggregator and Rich-formatted `claude-teletype diagnose` CLI command
- PrinterSelection dataclass and create_driver_for_selection() factory for typed setup-screen-to-driver conversion
- Full interactive PrinterSetupScreen with device list, connection method toggle, profile auto-detect, pyusb install worker, and 8 passing tests
- Wire PrinterSetupScreen into startup: cli.py calls discover_all(), TeletypeApp conditionally pushes setup screen on mount, callback converts selection to live printer driver
- Saved printer fields on TeletypeConfig with atomic TOML writes and TUI persistence after setup
- Skip printer setup screen on launch when saved USB/CUPS printer is still connected, via VID:PID and queue-name matching against discovery results

---

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

## v1.3 Tech Debt Cleanup (Shipped: 2026-02-20)

**Phases:** 16-17 (2 phases, 2 plans, 4 tasks)
**Timeline:** 2026-02-20 (1 day)
**Code:** +515 lines across 10 files, 430 tests passing (3,381 LOC source + 5,709 LOC tests)

**Key accomplishments:**

- "ibm" alias for PPDS printer profile — `--profile ibm` resolves to PPDS with case-insensitive lookup
- Annotated `config show` — every setting displays its source (default/file/env) via `resolve_sources()`
- Startup warning when system_prompt configured with claude-cli backend (shown in both CLI and TUI)
- Backend hot-swap confirmation dialog when switching away from claude-cli (context loss prevention)
- warnings.py module with pure check functions and per-process suppression pattern

**v1.2 debt resolved:**

- IBM PPDS profile now discoverable as "ibm" (Phase 16)
- `config show` now annotates sources for file and env layers (Phase 16, CLI flags excluded by design)
- system_prompt conflict warned at startup (Phase 17)
- Backend hot-swap now requires confirmation when leaving claude-cli (Phase 17)

**Remaining tech debt:**

- `config show` cannot detect CLI flag sources (Typer architectural constraint — separate subcommand)
- Pre-existing test_cli_teletype_passes_no_profile failure (USB auto-detection test)
- Juki 9100 control codes extrapolated from 6100 (need hardware verification)

---
