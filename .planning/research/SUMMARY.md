# Research Summary: Claude Teletype v1.2

**Project:** Claude Teletype v1.2 - Configuration, Profiles, Multi-LLM, Settings, Typewriter
**Domain:** Configuration system and extensibility features for a CLI/TUI typewriter tool
**Researched:** 2026-02-17
**Overall confidence:** HIGH

## Executive Summary

Claude Teletype v1.2 transforms the tool from a single-backend, flag-configured CLI wrapper into a configurable, multi-backend typewriter platform. The research confirms this requires **3 new dependencies** (`openai>=2.21.0`, `tomli-w>=1.2.0`, `platformdirs>=4.9.0`) with the `openai` SDK as an optional extra to keep the core install lightweight. The configuration system uses Python 3.12's built-in `tomllib` (zero-dep) for reading and `tomli-w` for writing, with `platformdirs` for cross-platform config file location. Printer profiles are pure data (raw ESC/P, PCL, Juki bytes stored in frozen dataclasses) requiring no library. The TUI settings panel uses Textual 8.0's existing `ModalScreen`, `Select`, `Switch`, and `Input` widgets. OpenAI and OpenRouter backends both use the official `openai` Python SDK -- OpenRouter is simply a different `base_url`.

The most significant architectural change is the introduction of client-side message history for OpenAI/OpenRouter backends. Unlike the Claude Code CLI (which manages sessions via `--resume`), OpenAI/OpenRouter require the caller to maintain conversation context. This is the primary source of complexity and the area most likely to need deeper attention during implementation.

The existing fan-out pipeline (pacer -> output -> destinations) remains unchanged. Config, profiles, and backend selection converge at the startup flow in `cli.py` and `TeletypeApp.__init__`. The settings panel is a self-contained `ModalScreen` that reads/writes config and applies changes to the running app.

## Key Findings

**Stack:** 3 new deps (`openai` optional, `tomli-w`, `platformdirs`), Textual pinned to >=8.0.0, all control codes are raw bytes (no printer library needed).

**Architecture:** Config system as foundation, LLM backend protocol with 2 implementations (Claude CLI wrapper, OpenAI-compatible API), printer profiles as frozen dataclasses wrapping inner drivers, settings as ModalScreen.

**Critical pitfall:** API keys must NEVER be stored in the TOML config file -- store environment variable names instead (`openai_api_key_env = "OPENAI_API_KEY"`). Second critical pitfall: OpenAI/OpenRouter backends need client-side message history with context window guard (unlike Claude Code CLI which manages this server-side).

## Implications for Roadmap

Based on research, suggested phase structure:

1. **Configuration System** - Foundation for everything else
   - Addresses: CFG-01 (TOML config), CFG-02 (defaults/creation), CFG-03 (CLI override)
   - Avoids: Schema evolution pitfall (merge with defaults), config location confusion (platformdirs)
   - New deps: `platformdirs`, `tomli-w`
   - Update: `textual>=8.0.0`

2. **Printer Profiles** - Replaces hardcoded Juki with generic profile system
   - Addresses: PROF-01 (profile system), PROF-02 (built-in ESC/P, PCL, Juki profiles)
   - Avoids: ESC/P family incompatibility (conservative basic profile)
   - Refactors: `JukiPrinterDriver` -> `ProfiledPrinterDriver`

3. **Multi-LLM Backends** - OpenAI and OpenRouter support
   - Addresses: LLM-01 (backend abstraction), LLM-02 (OpenAI/OpenRouter implementations)
   - Avoids: Unbounded message history (context window guard), optional dep import failure (guard imports)
   - New optional dep: `openai>=2.21.0`

4. **TUI Settings Panel** - In-app configuration
   - Addresses: SET-01 (ModalScreen settings), settings persistence
   - Avoids: Apply-vs-save confusion (work on config copy), Textual v8 compat (pin >=8.0.0)
   - Uses: Select, Switch, Input, TabbedContent, ModalScreen

5. **Typewriter Mode** - Pure typing experience without LLM
   - Addresses: TYPE-01 (TUI typewriter mode)
   - Avoids: Backspace on non-impact printers (profile-based behavior)
   - Independent of phases 1-4

**Phase ordering rationale:**
- Config system must be first because profiles, backends, and settings all read/write config.
- Printer profiles before multi-LLM because they are lower risk (pure data, no API calls) and exercise the config system.
- Multi-LLM after profiles because it is the highest complexity addition (client-side history, optional dependency, API integration).
- Settings panel last because it needs all other features to exist so it has interesting things to configure.
- Typewriter mode is independent and can be built in any phase.

**Research flags for phases:**
- Phase 1 (Config): Standard patterns, skip research
- Phase 2 (Profiles): Juki 9100 codes need hardware verification (flag)
- Phase 3 (Multi-LLM): OpenAI streaming well-documented, skip research. But client-side history management needs careful design.
- Phase 4 (Settings): Textual ModalScreen well-documented, skip research
- Phase 5 (Typewriter): Standard patterns, skip research

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified on PyPI within 3 days of research. openai 2.21.0, tomli-w 1.2.0, platformdirs 4.9.2, Textual 8.0.0 all confirmed. |
| Features | HIGH | Feature landscape mapped from existing codebase analysis + official API docs for OpenAI and OpenRouter. |
| Architecture | HIGH | Existing codebase fully understood (1,839 LOC read). New modules fit cleanly into existing patterns. |
| Pitfalls | HIGH | Critical pitfalls (API key security, context window management) sourced from well-known antipatterns. Textual v8 breaking changes verified from changelog. |

## Gaps to Address

- **Juki 9100 control codes:** Extrapolated from Juki 6100. Need verification with actual hardware. LOW priority -- Juki 6100 profile works and 9100 can be added later.
- **OpenAI context window management:** Simple message cap (50 messages) is the v1.2 approach. Proper token counting would require `tiktoken` but is deferred to keep it simple.
- **Config file comment preservation:** `tomli-w` does not preserve comments on roundtrip. If users add comments to their config and then save from the settings panel, comments are lost. Acceptable for v1.2; could migrate to `tomlkit` if this becomes a pain point.
- **Textual 8.0 testing:** Version just released (2026-02-16). Real-world testing needed to confirm no regressions beyond documented breaking changes.

## Sources

### Stack Research (HIGH confidence)
- [OpenAI Python SDK v2.21.0](https://pypi.org/project/openai/) -- PyPI, verified 2026-02-17
- [OpenRouter OpenAI SDK integration](https://openrouter.ai/docs/guides/community/openai-sdk) -- Official docs
- [Python tomllib](https://docs.python.org/3.12/library/tomllib.html) -- Stdlib docs
- [tomli-w v1.2.0](https://pypi.org/project/tomli-w/) -- PyPI
- [platformdirs v4.9.2](https://pypi.org/project/platformdirs/) -- PyPI
- [Textual v8.0.0](https://pypi.org/project/textual/) -- PyPI
- [Textual 8.0 changelog](https://github.com/Textualize/textual/blob/main/CHANGELOG.md)

### Printer Control Codes (HIGH confidence)
- [Epson ESC/P reference](https://stanislavs.org/helppc/epson_printer_codes.html)
- [IBM PPDS reference](https://www.ibm.com/support/pages/list-ibm-ppds-and-epson-escp-control-codes-and-escape-sequences)
- [HP PCL reference](https://developers.hp.com/hp-printer-command-languages-pcl)

### Textual Widgets (HIGH confidence)
- [Textual widget gallery](https://textual.textualize.io/widget_gallery/)
- [Textual ModalScreen guide](https://textual.textualize.io/guide/screens/)
- [Textual Select widget](https://textual.textualize.io/widgets/select/)
- [Textual Switch widget](https://textual.textualize.io/widgets/switch/)
- [Textual Input widget](https://textual.textualize.io/widgets/input/)

### OpenAI Streaming (HIGH confidence)
- [OpenAI streaming guide](https://developers.openai.com/api/docs/guides/streaming-responses)
- [OpenAI Python SDK README](https://github.com/openai/openai-python)

---
*Research completed: 2026-02-17*
*Ready for roadmap: yes*
