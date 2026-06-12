# Deferred Items - Phase 24

Out-of-scope discoveries logged during execution.

## 24-02 (2026-04-28)

- **Pre-existing ruff E501** in src/claude_teletype/tui.py:359 (status-bar f-string, 128>100 chars). Introduced by commit cc2a39e5 (Feb 2026). Out of scope for plan 24-02 — touching this line is unrelated to the picker keybinding wiring. Suggested fix: split the f-string across lines or extract a helper. Plan 24-02 leaves the file's existing lint state intact.

