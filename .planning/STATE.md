---
gsd_state_version: 1.0
milestone: v1.5
milestone_name: Markdown File Printing
status: "v1.5 milestone COMPLETE. Plan 26-03 closed Phase 26 with 4 atomic commits (2 RED + 2 GREEN per TDD discipline). transcript.write_printed_file helper landed (TXN-01..03); _render_markdown_to_driver gained transcript_write parameter via parallel-collector pattern (TXN-02 byte-cleanliness by construction); _print_command_impl auto-builds transcript writer when config.transcript_dir is set; tui.py _handle_picker_result Path arm replaced with SpeedModeScreen + _handle_speed_mode_result + _run_print_pipeline pipeline; renderer.close() in finally locks FLOW-05 cancel safety end-to-end. 16 new pilot/unit tests = 700 total green (684 -> 700, zero regressions). All 8 Phase 26 requirements (FLOW-01..05 + TXN-01..03) traced to passing tests. v1.5 markdown printing user journey end-to-end functional from CLI direct, CLI picker-mode, and TUI ctrl+o entry points."
stopped_at: Completed 26-03-PLAN.md (Phase 26 done; v1.5 milestone COMPLETE; transcript pipeline + tui.py picker callback replacement + FLOW-05 cancel-safety wiring; 16 new tests = 700 total green; all 8 Phase 26 requirements green)
last_updated: "2026-04-28T22:53:00Z"
last_activity: 2026-04-28 -- 26-03 landed (write_printed_file + transcript_write parameter + tui.py SpeedModeScreen pipeline + _run_print_pipeline finally:renderer.close(); 4 atomic commits baf4de3/8c2123f/ad0663a/e5b0cd5; 700 total green; v1.5 COMPLETE)
progress:
  total_phases: 9
  completed_phases: 6
  total_plans: 14
  completed_plans: 14
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-28)

**Core value:** The physical typewriter experience -- characters appearing on paper one at a time with authentic pacing and sound, making AI conversation feel tangible and mechanical.
**Current focus:** v1.5 milestone (Markdown File Printing) — **COMPLETE** (Phases 21..26 all done). Plan 26-03 closed Phase 26 with the speed-dialog -> renderer -> transcript pipeline wired into tui.py (replaces Phase 24 notify() stub) + transcript.write_printed_file helper + FLOW-05 cancel-safety try/finally renderer.close() integration. All 8 Phase 26 requirements green; 700 total tests pass. v1.6 direction TBD (deferred candidates: pause/resume mid-print, speed-mode persisted in config, print queue, page-numbering option).

## Current Position

Phase: 26 — Speed Dialog, Buffer Chunking, Cancel & Transcript — **COMPLETE** (3/3 plans)
Plan: 26-03 done. v1.5 milestone closed. Awaiting v1.6 planning.
Status: v1.5 milestone COMPLETE. Plan 26-03 closed Phase 26 with 4 atomic commits (2 RED + 2 GREEN per TDD discipline). transcript.write_printed_file helper landed (TXN-01..03); _render_markdown_to_driver gained transcript_write parameter via parallel-collector pattern (TXN-02 byte-cleanliness by construction); _print_command_impl auto-builds transcript writer when config.transcript_dir is set; tui.py _handle_picker_result Path arm replaced with SpeedModeScreen + _handle_speed_mode_result + _run_print_pipeline pipeline; renderer.close() in finally locks FLOW-05 cancel safety end-to-end. 16 new pilot/unit tests = 700 total green (684 -> 700, zero regressions). All 8 Phase 26 requirements (FLOW-01..05 + TXN-01..03) traced to passing tests. v1.5 markdown printing user journey end-to-end functional from CLI direct, CLI picker-mode, and TUI ctrl+o entry points.
Last activity: 2026-04-28 -- 26-03 landed (write_printed_file + transcript_write parameter + tui.py SpeedModeScreen pipeline + _run_print_pipeline finally:renderer.close(); 4 atomic commits baf4de3/8c2123f/ad0663a/e5b0cd5; 700 total green; v1.5 COMPLETE)

## Performance Metrics

**Velocity:**

- Total plans completed: 42
- Average duration: 3.4min
- Total execution time: 2.5 hours

**Recent plan metrics:**

| Plan | Duration | Tasks | Files | Completed |
|------|----------|-------|-------|-----------|
| 23-03 | 4.1min | 2 | 2 | 2026-04-28 |
| 24-01 | 3.4min | 2 | 2 | 2026-04-28 |
| 24-02 | 4.2min | 2 | 2 | 2026-04-28 |
| 25-01 | 8.6min | 2 | 2 | 2026-04-28 |
| 25-02 | 3.6min | 2 | 2 | 2026-04-29 |
| 26-01 | 5.9min | 2 | 6 | 2026-04-28 |
| 26-02 | 4.0min | 1 | 2 | 2026-04-28 |
| 26-03 | 7.2min | 2 | 6 | 2026-04-28 |

**By Milestone:**

| Milestone | Phases | Plans | Duration | Timeline |
|-----------|--------|-------|----------|----------|
| v1.0 MVP | 4 | 8 | 22min | 2026-02-15 |
| v1.1 Conversation Mode | 3 | 7 | 20min | 2026-02-16 → 2026-02-17 |
| v1.2 Config/Profiles/LLM/Settings | 8 | 13 | 57min | 2026-02-14 → 2026-02-17 |
| v1.3 Tech Debt Cleanup | 2 | 2 | 8min | 2026-02-20 |
| v1.4 Printer Setup TUI | 3 | 6 | 15min | 2026-04-03 |
| v1.5 Markdown File Printing | 6 | 14 | ~3hr | 2026-04-28 (COMPLETE) |

## Accumulated Context

### Decisions

All decisions logged in PROJECT.md Key Decisions table (24 entries).
v1.3 decisions archived in MILESTONES.md.

Carry-forward from v1.4 still in force for v1.5:

- CR+LF+reinit must remain a single atomic USB transfer for newlines (Juki/CH341 drops fragmented LF). The markdown renderer must compose with `ProfilePrinterDriver.write` for `\n` rather than re-implementing the newline path.
- `dataclasses.replace` is the supported way to alias profiles (preserves frozen immutability of `PrinterProfile`).
- Custom-TOML profiles use `bytes.fromhex()` decoding for byte fields and `int(..., 16)` for VID/PID — Phase 21 must mirror this convention for the new `bold_on`/`italic_on`/`underline_on` and integer `buffer_bytes` fields.

Decisions added in 21-01:

- Empty bytes (b"") is the sentinel for absent style capability — the markdown renderer's fallback chain (italic→underline→plain, bold→underline→plain, lands in 21-03) reads that state to decide whether to substitute underline or plain text.
- buffer_bytes default 256 is conservative for unknown hardware; per-profile overrides apply real-world tuning (CH341 byte-fragility=64, thermal=128) without scattering hardware knowledge in conditional code. Applied values: juki-6100=64, juki-2200=64, juki alias inherits 64, citizen-cts2000=128, others=256.
- Style codes (bold/italic/underline) intentionally LEFT EMPTY on every built-in profile in Plan 21-01; Phase 22 encodes verified per-family sequences. Sentinel test `test_builtin_profiles_have_empty_style_codes_in_phase_21` enforces this and will be updated/removed in Phase 22.

Decisions added in 21-02:

- buffer_bytes is a plain int in TOML, NOT a hex string — distinct from usb_vendor_id/usb_product_id which use int(x, 16) because they are USB identifiers. buffer_bytes is a count of bytes, so plain int is the natural type. The loader docstring documents this distinction explicitly so future contributors don't unify the three TOML decoding patterns into one.
- Three TOML decoding conventions coexist cleanly in load_custom_profiles: (1) bytes.fromhex(data.get(KEY, "")) for raw byte sequences with empty default, (2) int(data[KEY], 16) if KEY in data else None for hex-encoded USB IDs with None sentinel, (3) data.get(KEY, default) for plain ints/bools/strings.

Decisions added in 21-03:

- resolve_style is a free function in profiles.py (not a method on PrinterProfile) — keeps the dataclass purely data and avoids coupling the data shape to fallback logic that may evolve independently. Renderer imports it via `from claude_teletype.profiles import resolve_style`.
- Underline is the terminal node of the fallback chain — bold and italic fall back to underline, but underline does NOT substitute bold or italic. Rationale: underline is universally supported on impact printers; if a printer lacks underline too, the renderer emits plain text rather than fabricating a substitute that may print garbage.
- Italic wins over underline when both are set; bold wins over underline when both are set. The fallback chain only fires when the primary capability is empty — no precedence ambiguity for profile authors who declare both.

Decisions added in 22-01:

- Encoding-table-as-contract: 22-CONTEXT.md's "Encoding sources" table was the authoritative spec. Every byte literal in the planner's action blocks was copied character-for-character into profiles.py — no interpretation, no creative substitution. Fabricated codes would print garbage on real hardware; the conservative-default rule (when unsure, leave empty) was already baked into the table.
- Citizen ESC/POS bold uses BINARY 1/0 in the third byte (`\x1b\x45\x01`/`\x1b\x45\x00`), NOT ASCII '1'/'0'. The `test_citizen_cts2000_bold_codes` docstring flags this gotcha explicitly so future contributors don't "correct" it back to `\x1b\x45\x31`/`\x1b\x45\x30`.
- Removed the Phase 21 sentinel `test_builtin_profiles_have_empty_style_codes_in_phase_21` rather than rewriting it — its stated purpose explicitly anticipated removal once Phase 22 landed. Replacement is strictly stronger: TestStyleCodesPerProfile asserts exact byte literals per cell + paired-symmetry sentinel asserts the structural invariant (non-empty `*_on` implies non-empty `*_off`) closing Phase 21 REVIEW IN-05 carry-forward.
- Aliases (ibm, juki) are NOT separately encoded — they pick up codes through the existing `dataclasses.replace` pattern. Two explicit alias-inheritance tests verify this works after the encoding edit.

Decisions added in 23-01:

- write_bytes is a public Protocol method (not an adapter wrapper). Keeps the dual-channel seam visible at the type-checker layer so renderer code accepts any `PrinterDriver` and the Protocol enforces the contract. Adapter approach would have hidden the seam behind a wrapper class and complicated downstream injection.
- ProfilePrinterDriver.write_bytes empty-bytes guard fires BEFORE _ensure_init(). `write_bytes(b"")` is a true no-op that does not initialize the printer — protects against the renderer's `resolve_style` returning `(b"", b"")` and accidentally booting hardware on every plain-text run.
- MD-08 boundary held in two places: (1) docstring on ProfilePrinterDriver.write_bytes telling renderer to use write('\n') for newlines, (2) `test_write_bytes_does_not_handle_newlines_specially` asserting `b'\n'` passes through verbatim (no CR+LF, no reinit). The contract is owned by the caller — write_bytes will not silently rescue a misuse.
- CupsPrinterDriver.write_bytes appends the decoded chunk as a single list element (not character-by-character). Preserves the atomicity hint and matches `_flush_line()`'s `"".join()` pattern. Verified by `test_cups_driver_write_bytes_buffers_until_newline` asserting `b"\x1bEhi\x1bF\n"` reaches `lp` as a single subprocess call.

Decisions added in 23-02:

- Trailing empty line from `text.split("\n")` is dropped at `render()` entry. A document ending with `\n` (POSIX convention) splits to `[..., ""]`; the trailing newline is structural delimitation, not a blank-line paragraph. Without the drop, `# Hello\n` would render `\nHello\n\n\n` instead of the spec `\nHello\n\n`. Discovered while writing Task 2's hand-checkable expected strings — landed as a Rule-1 fix commit between Task 1 (feat) and Task 2 (test).
- Tables render eagerly in `render()` via 2-line look-ahead (header `|` + delimiter `|---|`). Clearer than the alternative flush-time validation; keeps `_dispatch_block_line` free of table state. `_flush_table` kept as a no-op stub for a future streaming-mode renderer that can't peek.
- Code-block 4-space leading indent is intentionally NOT preserved through WordWrapper. WordWrapper's canonical leading-space-at-column-0 rule (`test_leading_space_dropped`) strips them. Code content survives, but visual indent is lost in the wrap stage. This is documented in the MD-07 integration test rather than fixed in WordWrapper (changing WordWrapper would break its existing contract).
- `_render_inline` is a separate method emitting chars verbatim through `text_output_fn`. Plan 23-03 swaps just the method body; the 5 call sites (heading text, ulist content, olist content, blockquote content, paragraph content) inherit the inline-emphasis upgrade automatically. `_handle_code_line` deliberately bypasses `_render_inline` (MD-04: literal pass-through inside fences).
- `style_output_fn` defaults to a no-op lambda. Lets the renderer be unit-tested without a profile/driver — every block test in TestHeadings/TestLists/etc passes only `text_output_fn`. The MD-08 negative test exercises the style channel explicitly to assert no newline byte ever leaks into it.

Decisions added in 23-03:

- Heading wraps inline span in an OUTER bold pair via direct `_emit_style_on/off("bold")` calls — independent of inline `_bold_open` state. `_close_open_styles` closes inner spans BEFORE the outer `_emit_style_off("bold")` so the LIFO order is natural. `# **Inner**` produces 2 bold-on / 2 bold-off pairs (outer + inner) — symmetry verified by `test_emphasis_in_heading_pairs_correctly`.
- Greedy two-then-one tokenization for emphasis markers in `_render_inline`: `**`/`__` checked before `*`/`_`. `***foo***` parses as bold-on, italic-on, foo, italic-off, bold-off (4 emits); no special-cased triple-marker token needed.
- Markdown emphasis markers are state-machine tokens, NOT text. The `*`/`_` characters are consumed by the toggle path and never reach `text_output_fn`. Pure-paragraph tests assert `text.count('*') == 0 and text.count('_') == 0` after rendering.
- `_close_open_styles()` invoked from 7 sites: heading (close-before-outer-bold-off), ulist, olist, blockquote, paragraph, code-block-enter (defensive — emphasis is suppressed inside code fences per MD-04), end-of-render (defensive close for unclosed `**hello`). Italic closes BEFORE bold to mirror the natural LIFO open order for nested `**outer *inner* outer**` spans.
- `resolve_style` consulted at every emit; `(b"", b"")` returns silently no-op via `if on:` / `if off:` guards — text falls back to plain without renderer-side branching. `_profile is None` short-circuit makes the renderer unit-testable without a profile.

Decisions added in 24-01:

- FilePickerScreen subclasses `Screen[Path | None]` (NOT `ModalScreen`) — locked carry-forward of v1.4's `PrinterSetupScreen` / `TypewriterScreen` pattern. Documented in CONTEXT.md and enforced via `test_screen_is_full_screen_not_modal` (`isinstance(s, Screen) and not isinstance(s, ModalScreen)`).
- `MarkdownDirectoryTree` is a DirectoryTree subclass that overrides `filter_paths` (rather than passing a per-instance callable). Filter rules live in module-level frozensets (`HIDDEN_DIRS`, `MARKDOWN_SUFFIXES`) at the top of the file — discoverable, greppable, easy to extend for PICK-06 recents. Suffix match is case-insensitive (`.MD`/`.Markdown` accepted).
- FilePickerScreen accepts `root: Path | None = None` defaulting to `Path.cwd()`. Production callers get PICK-02 cwd-rooting for free; tests pass `tmp_path` directly without monkeypatching `Path.cwd()` or using `chdir` fixtures. This single design choice eliminated `chdir` from the test plan.
- No `enter` key binding on FilePickerScreen — DirectoryTree's native FileSelected (file) and expand-toggle (directory) handle enter for free. Adding a custom binding would shadow this and break "enter on a directory expands, doesn't dismiss".
- `escape` is the primary cancel binding (Footer-visible); `q` is an alternate cancel with `show=False` so it doesn't clutter the visible bindings strip. Both call `action_cancel` which dismisses with None (PICK-04).
- Pilot tests for file selection synthesize `DirectoryTree.FileSelected(node=_StubNode(), path=target)` and call `screen.on_directory_tree_file_selected(event)` directly. Avoids the keyboard-timing fragility of Pilot navigation through an expanding tree. Mirrors `test_printer_setup_screen.py`'s direct `_on_connect` calls.
- `Static` content assertion uses `str(display.render())` not `display.renderable` — the latter doesn't exist in this Textual version; `render()` returns a `Content` whose `str()` is the displayed text. Documented inline in `test_path_display_initial_placeholder` so future contributors don't reach for the non-existent attr.
- Class docstring says "(not a modal overlay)" not "not a ModalScreen" — preserves the locked decision in plain English while keeping `grep -c ModalScreen file_picker_screen.py == 0` green (verification rule from the plan).

Decisions added in 24-02:

- ctrl+o chosen over ctrl+m / ctrl+shift+o for the file picker entry. Mnemonic ("open file"), zero conflict with the four existing TeletypeApp bindings (ctrl+d quit, ctrl+t typewriter, ctrl+comma settings, escape cancel_stream), unreserved by Textual. Some legacy terminals send ctrl+o as XOFF-adjacent "discard output", but Textual's input layer captures it as `key=ctrl+o` regardless (same mechanism that lets nano use ctrl+o for "Write Out").
- Footer label "Open MD" (7 chars) — matches brevity of existing labels (Quit/Typewriter/Settings/Cancel). Binding placed between ctrl+comma and escape so show=True bindings stay in left-to-right Footer order; show=False escape stays last.
- notify() smoke chosen over real render for `_handle_picker_result`'s Path arm. Keeps Phase 24 mergeable independent of Phase 26's speed-dialog scope. Phase 26 will replace only the body — the method name (`_handle_picker_result`), the Path argument shape (always absolute via 24-01's `Path(event.path).resolve()`), and the input-refocus pattern in the None arm are the locked contract Phase 26 consumes.
- Paired action_<name> + _handle_<name>_result methods convention now used in three places: settings (action_open_settings + _apply_settings), printer setup (_show_setup_screen + _handle_setup_result), file picker (action_open_markdown + _handle_picker_result). Future push_screen+callback flows should follow the same shape.
- Action handler is binding-agnostic — `action_open_markdown` does not reference `ctrl+o`, so the BINDINGS line can be edited (e.g. to ctrl+shift+o or ctrl+p) without touching the method. Documented in the action's docstring.
- Refocus #prompt input in BOTH arms of `_handle_picker_result` (None and Path) — matches existing `_handle_setup_result` / `_apply_settings`. Textual restores focus on `pop_screen` automatically in most cases, but the explicit `query_one("#prompt", Input).focus()` is the established belt-and-suspenders style.
- ctrl+o is App-level (not Input-level) — works even when the input prompt is disabled (Thinking... mid-stream state). Locked by `test_picker_opens_during_disabled_input`. Phase 26 will need to handle stream-in-flight gracefully for the real render path, but the binding works regardless.
- Dual-test pattern (action-direct + keypress) for keybinding integration: action-direct test isolates handler logic; keypress test validates BINDINGS wiring. If only one fails you know which layer is broken without bisecting.
- Direct `screen.dismiss(value)` in cancel/selection Pilot tests — same shape as 24-01's synthesized FileSelected pattern. Avoids DirectoryTree timing flakiness; tests the same observable contract the callback consumes.
- Docstring rephrased "MarkdownRenderer pipeline" -> "Phase 23's renderer pipeline" so plan verification rule `grep -c MarkdownRenderer src/claude_teletype/tui.py == 0` holds. Phase 23 contract is locked — this plan must not import or instantiate the renderer. Same Rule-3 docstring-grep pattern plan 24-01 used for ModalScreen.

Decisions added in 25-01:

- Local imports inside `_render_markdown_to_driver` and `_print_command_impl` (matches the convention used by `main()` and `action_open_markdown` in the project). Test patches accordingly target SOURCE modules (`claude_teletype.printer.discover_printer`, `claude_teletype.markdown.MarkdownRenderer`, `claude_teletype.wordwrap.WordWrapper`), NOT `claude_teletype.cli.discover_printer` shims. Plan 25-02's tests should follow the same pattern.
- Typer `Argument(..., exists=False)` chosen over `exists=True` so manual validation in `_print_command_impl` can emit a clean `Error: file not found: <abs path>` / `Error: not a regular file: <abs path>` with the resolved absolute path. Typer's default error wording omits the resolved path and is awkward for users.
- Parallel profile-resolution path, NOT a shared helper extracted from `main()`. Plan 25-01 explicitly forbade touching `main()`. The duplication is small (~30 lines) and the two paths have diverging needs (chat path also does backend creation, system-prompt warning, smart-startup match; print path doesn't). Phase 26 may unify if it chooses.
- `delay` parameter accepted by `print_md` but currently a no-op for rendering — passed through `merge_cli_flags` so the env-layer test (`CLAUDE_TELETYPE_DELAY=10`) proves `apply_env_overrides` ran end-to-end. Phase 26's speed dialog will wire `config.delay` into a paced wrapper around `driver.write` inside `_render_markdown_to_driver`. Single-callsite change.
- Helper-function shape: `_print_command_impl` (config + profile + path validation) is SEPARATE from `_render_markdown_to_driver` (driver lifecycle: discover_printer → render → flush → end_response → close in finally). Plan 25-02 reuses ONLY the latter; the picker callback skips path validation since the picker constrains its result to a real `Path` already. The locked contract for 25-02: `exit_code = _render_markdown_to_driver(path, config, all_profiles, resolved_profile)`.
- `getattr(driver, "end_response", None)` duck-test pattern for the 5 driver implementations: only `ProfilePrinterDriver` and `JukiPrinterDriver` implement `end_response()` (per-response paper cut on receipt printers). NullPrinterDriver, FilePrinterDriver, CupsPrinterDriver, UsbPrinterDriver don't. The getattr guard keeps the helper usable across all five without isinstance branching.
- `wrapper.flush()` placement: AFTER `renderer.render(text)` and BEFORE `driver.end_response()`. WordWrapper buffers the last word until `flush()`; without this, documents that don't end in whitespace would lose their trailing token. Locked by `test_print_calls_wrapper_flush_after_render` and `test_render_helper_call_order`.

Decisions added in 25-02:

- Closure-factory `_make_markdown_picker_app(config, all_profiles, resolved_profile, root)` rather than a constructor-arg App subclass. Captures the resolved print context as closure variables in the factory; the nested `class MarkdownPickerApp(App)` reads them by name. Keeps the App's `__init__` minimal (`super().__init__(); self._exit_code = 0`) and avoids overriding Textual's constructor signature. Pattern locked for future one-shot Textual launchers (confirmation dialogs, settings-edit apps): use a `_make_*_app()` factory + closure rather than threading args through `__init__`.
- `_resolve_print_context(delay, device, printer)` shared resolver extracted from `_print_command_impl` body. Both Typer branches (explicit path AND no-arg picker) now call it; on unknown-profile error returns `(None, None, None)` so callers detect failure uniformly without raising. Plan 25-01's `_render_markdown_to_driver` signature stays untouched -- the refactor only relocated code. Pattern: when sibling Typer branches share resolution but diverge in what they do AFTER, extract a `_resolve_<thing>_context()` helper that returns the resolved tuple OR a sentinel on error. Avoids the alternative of raising typer.Exit from inside the resolver, which makes unit-testing harder.
- `Path | None` (modern union) over `Optional[Path]` in `print_md`. Plan recommended `Optional` but ruff's UP045 lint prefers the modern syntax; Typer 0.23.1 handles both identically. Verified: `--help` shows `[PATH]` for the optional arg, dispatch fires correctly when path is omitted. Adjustment NOT counted as deviation -- following project lint preferences per `<project_context>` rules.
- App._exit_code attribute idiom for return-code propagation. The picker callback stores `_render_markdown_to_driver`'s return value on the app instance; the caller reads it via `getattr(picker_app, "_exit_code", 0)` after `.run()` returns. Mirrors the existing `TeletypeApp.session_id` pattern (set during `.run()`, read after). Pattern locked for one-shot Textual apps that need richer return-code semantics than `App.exit(result=...)` provides.
- Synchronous render inside `_on_pick` (NOT in a worker). Phase 25's print is non-paced -- file I/O + USB write fast enough that picker-dismiss → render → app.exit() is imperceptible. Phase 26 will need to refactor into a Textual worker when pacing lands so a speed dialog can run between dismiss and render-start. Locked in a docstring comment for future Phase 26 reference.
- Test option (a) (patch `app_inst.push_screen` BEFORE calling `app_inst.on_mount()`) worked first try for `test_picker_app_on_mount_pushes_filepicker`. Plan offered three test strategies (a: patch-pre-call, b: Pilot, c: inspect.getsource grep); option (a) succeeded because on_mount() only calls self.push_screen, which is now the mock -- Textual's compositor isn't touched. Bonus: the test asserts (1) push_screen called, (2) first positional arg is a real FilePickerScreen instance, AND (3) callback kwarg is the bound `_on_pick` method. Richer assertions than option (c) would have produced.
- Test patches the FACTORY (`claude_teletype.cli._make_markdown_picker_app`) at the dispatch level, AND patches `claude_teletype.cli._render_markdown_to_driver` directly for the callback unit tests. The factory IS the cli-side surface; the closure-captured `_render_markdown_to_driver` reference is patched at the cli module path because the factory's nested `class MarkdownPickerApp` body resolves the name through the cli module namespace, not through textual or file_picker_screen.

Decisions added in 26-01:

- `chunk_writes` is a free function in `printer.py` (not a method on `ProfilePrinterDriver`) — driver-agnostic, pure, trivially testable, accepts any `PrinterDriver` Protocol. Method-on-driver would have coupled it to one inner driver shape and made it harder to unit-test against `NullPrinterDriver` recorders.
- Sync `time.sleep` for typewriter pacing instead of converting `_render_markdown_to_driver` to `async`. Preserves Plan 25-02's locked sync `MarkdownPickerApp._on_pick` callback shape; the helper still runs in a sync context (Typer command body and picker callback). `pacer.pace_characters` (async) is bypassed but its `CHAR_DELAYS` dict + `classify_char` function are reused so per-char delay multipliers are identical to the chat path.
- `speed_mode` defaults to `"instant"` (not `"typewriter"`) so the two existing Phase 25 callers (`_print_command_impl`, `MarkdownPickerApp._on_pick`) keep working without modification. They passed 4 positional args before Phase 26 and inherit the no-pacer behaviour matching their pre-Phase-26 contract. The regression sentinel test (27 prior `test_cli_print.py` tests) verifies this.
- Style-channel chunking lives only on the instant path (not typewriter) because typewriter mode interleaves 1-char text writes with 3–6 byte ESC bursts that are always under any realistic `profile.buffer_bytes`. Adding chunking on the typewriter path would only add a no-op layer of overhead.
- Instant-mode generic-profile fallback uses `buffer_bytes=256` (defensive default). However, `resolve_style` returns `(b"", b"")` for `None` profile so `style_dest` is effectively unreachable for generic — belt-and-suspenders.
- `chunk_writes` patch target in tests is `claude_teletype.printer.chunk_writes` (source module) because `cli.py` imports it locally inside the function body. Matches the patch-target convention documented at the top of `tests/test_cli_print.py` for `discover_printer`/`MarkdownRenderer`/`WordWrapper`. Test patching `claude_teletype.cli.chunk_writes` raises `AttributeError` (no module-level attribute) — this is the canonical "import locally + patch at source" pattern in this project.
- `SpeedModeScreen.__init__` defensively coerces unknown `default_mode` values to `"typewriter"` rather than raising. Phase 26-02/26-03 callers will pass `"typewriter"` or `"instant"` derived from `profile.instant_output`, but a junk value (e.g. user-edited config) shouldn't crash the dialog. Locked by `test_invalid_default_mode_falls_back_to_typewriter`.
- Pattern locked for one-shot ModalScreen with two-option choice + Print/Cancel: `Vertical(id="<dialog>") -> Static(title) + RadioSet(id="<radio>") -> 2 RadioButton + Horizontal(id="button-row") -> Print + Cancel`. `on_button_pressed` dispatches by `event.button.id`; Print button reads `RadioSet.pressed_button.id`. `action_cancel` mapped to `escape` via `BINDINGS`. Mirrors `SettingsScreen`'s shape.
- TDD RED gate proven for both tasks: Task 1's tests failed with `ModuleNotFoundError: No module named 'claude_teletype.speed_mode_screen'` before implementation; Task 2's tests failed with `TypeError: _render_markdown_to_driver() got an unexpected keyword argument 'speed_mode'` before implementation. GREEN gate followed in each case with all tests passing.

Decisions added in 26-02:

- Public `MarkdownRenderer.close()` is a thin 1-line delegation to `_close_open_styles()` — Phase 23's helper stays the SINGLE source of truth for LIFO emit ordering (italic_off before bold_off) and the resolve_style fallback chain. Reimplementing the cleanup body inline would duplicate the LIFO order and the profile-fallback decision; every future fix would need to be applied in two places. Promote-private-helper-to-public-API pattern locked: when a private mechanic needs a public entry point (e.g. cancel handler in another module), add a thin documented wrapper that delegates 1:1.
- Cancel keybinding wiring deferred to Plan 26-03. Plan 26-02 ships only the renderer-side public API. The keybinding interaction with the speed-dialog → picker → render pipeline lives in 26-03 so the integration test there can exercise the full cancel pipeline as one piece. This split also keeps 26-02's surface area minimal (one public method, one docstring paragraph, 9 tests) which made TDD RED→GREEN sharp.
- close() takes no arguments and returns None. No `force=True` flag, no `flush=True` flag — the underlying `_close_open_styles` is already deterministic (closes whatever flags are open). Adding optional params would just expose private state. Idempotency is inherent: emit-then-clear semantics on the flags mean a second call sees False flags and emits nothing — no separate `_closed` boolean needed.
- profile=None safety inherited from Phase 23: `_emit_style_off` already short-circuits via `self._profile is None: return` (Phase 23-03), so close() does NOT need its own None guard. Test `test_close_with_profile_none_is_safe` documents this defensively.
- Document the contract in BOTH the class docstring (Cancel safety paragraph) AND the `close()` method docstring. Class docstring tells future readers WHY the API exists (printer state-leak hazard); method docstring tells callers HOW to use it (idempotent, profile=None safe, LIFO emit order). Both reference `_close_open_styles` by name to make the delegation discoverable. Sentinel test `test_close_docstring_documents_abort_contract` asserts "abort" or "cancel" appears in the docstring.
- TDD RED gate proven: 9 tests added in commit a0fd705 (test) all failed with `AttributeError: 'MarkdownRenderer' object has no attribute 'close'` before implementation. GREEN commit 938eb1d (feat) added the method body and all 9 passed first run; Phase 23's 17 emphasis/symmetry tests still green; full project went 675 → 684 (+9, zero regressions). REFACTOR phase skipped — implementation is one statement.

### Pending Todos

None — phase planning starts at Phase 21.

### Blockers/Concerns

- Juki 9100 control codes still extrapolated from 6100 (carried over from v1.4) — Phase 22 left Juki bold/italic intentionally empty (CAP-05 conservative-default rule), so the carry-forward concern shrinks to "underline ESC -1/-0 should be exercised on real hardware before claiming Juki underline works end-to-end". 23-03 wires the fallback chain end-to-end (juki bold/italic → underline ESC -1/-0 verified by TestStyleFallback) — the on-hardware verification of underline itself remains the open item.
- Phase 22 left intentionally-empty cells for OKI italic (ESC! mode-bit composite varies by firmware revision) and all three Citizen italics (thermal receipt does not support italic). Documented in 22-CONTEXT.md Deferred Ideas.
- Phase 23 narrow-columns: 23-02's `test_table_fits_within_columns` proves the renderer won't crash on Citizen 42-col thermal — but cells get truncated rather than wrapped. Acceptable for v1; in-cell wrap is in `<deferred>`. Closed.
- Phase 23 code-block visual indent: WordWrapper strips the renderer's 4-space leading indent on code-block lines. Content survives, indent doesn't. Out of scope for v1.5; a renderer-aware tab/non-space prefix could fix it later. 23-03's TestIntegration documents this nuance via the `code with *no italic*` substring assertion (no leading-space prefix asserted).
- Phase 26: per-profile `buffer_bytes` defaults need real-hardware validation for at least Juki and Epson before instant mode can be trusted.

## Session Continuity

Last session: 2026-04-28T22:35:08Z
Stopped at: Completed 26-02-PLAN.md (Wave 2 of Phase 26; FLOW-05 renderer-side closed; MarkdownRenderer.close() public abort hook; 9 new TestRendererCancelSafety tests = 684 total green)
Resume file: None
Next action: Execute Plan 26-03 (Wave 3). Wires `SpeedModeScreen` into both call sites (`tui.py::_handle_picker_result` replacing Phase 24's `notify()` stub; `cli.py::MarkdownPickerApp._on_pick` calling `_render_markdown_to_driver(..., speed_mode=choice)`), adds `transcript.write_printed_file(path, body)` per TXN-01..03, and wires the cancel keybinding handler that calls `renderer.close()` + `driver.end_response()` (FLOW-05 closure). Locked Phase 26-01 + 26-02 contracts: `SpeedModeScreen(default_mode: str = "typewriter")` dismissing with `"typewriter"|"instant"|None`; `chunk_writes(driver: PrinterDriver, data: bytes, chunk_size: int) -> None` (ValueError on chunk_size<=0); `_render_markdown_to_driver(path, config, all_profiles, resolved_profile, speed_mode: str = "instant") -> int`; `MarkdownRenderer.close() -> None` (idempotent, profile=None safe, LIFO emit order — delegates to `_close_open_styles`). Phase 25 contracts (4-arg shape, `_resolve_print_context`, `_make_markdown_picker_app` factory) remain locked and intact.
