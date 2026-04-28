"""CLI entry point for Claude Teletype.

Wires together the bridge (Claude Code subprocess streaming) and pacer
(character-by-character typewriter output) with a Rich thinking indicator.

Default mode: launches the Textual split-screen TUI.
Fallback: --no-tui flag or piped stdin preserves Phase 1 stdout behavior.
"""

import asyncio
import shutil
import sys
from pathlib import Path

import typer
from rich.console import Console

from claude_teletype.backends import BackendError, create_backend
from claude_teletype.bridge import StreamResult
from claude_teletype.config import (
    CONFIG_FILE,
    apply_env_overrides,
    load_config,
    merge_cli_flags,
    resolve_sources,
    write_default_config,
)
from claude_teletype.pacer import pace_characters


class _PromptFriendlyGroup(typer.core.TyperGroup):
    """Give subcommand names priority over the positional prompt argument.

    Without this, Typer/Click consumes ``config`` in ``claude-teletype config show``
    as the ``prompt`` positional argument and then fails to find a ``show`` command.
    This override detects when the first non-option arg is a known subcommand and
    temporarily hides the ``prompt`` parameter so Click routes correctly.
    """

    def parse_args(self, ctx, args):
        first_non_option = None
        for a in args:
            if not a.startswith("-"):
                first_non_option = a
                break

        if first_non_option and first_non_option in self.list_commands(ctx):
            original_params = list(self.params)
            self.params = [p for p in self.params if p.name != "prompt"]
            try:
                return super().parse_args(ctx, args)
            finally:
                self.params = original_params

        return super().parse_args(ctx, args)


app = typer.Typer(cls=_PromptFriendlyGroup)
config_app = typer.Typer(help="Manage configuration")
app.add_typer(config_app, name="config")
console = Console()

CLAUDE_INSTALL_URL = "https://claude.ai/install.sh"
CLAUDE_DOCS_URL = "https://code.claude.com/docs/en/quickstart"


def check_claude_installed() -> None:
    """Verify Claude Code CLI is installed and on PATH.

    Prints install instructions and exits with code 1 if 'claude' binary
    is not found via shutil.which().
    """
    if shutil.which("claude") is None:
        console.print(
            "[bold red]Claude Code CLI is not installed.[/bold red]\n\n"
            "Install it with:\n"
            f"  curl -fsSL {CLAUDE_INSTALL_URL} | bash\n\n"
            f"Or visit: {CLAUDE_DOCS_URL}",
        )
        raise typer.Exit(1)


async def _chat_async(
    prompt: str,
    base_delay_ms: float,
    printer=None,
    no_audio: bool = False,
    transcript_dir: str | None = None,
    backend=None,
) -> None:
    """Send prompt to Claude Code and display response with typewriter pacing.

    Shows a thinking spinner while waiting for the first token, then
    outputs characters one at a time with variable delays.

    Args:
        prompt: The user prompt to send to Claude.
        base_delay_ms: Base delay between characters in milliseconds.
        printer: Optional PrinterDriver instance for hardware output.
        no_audio: If True, disable bell sound on line breaks.
        transcript_dir: Directory for transcript files (default: ./transcripts).
        backend: LLM backend to use for streaming.
    """
    from claude_teletype.output import make_output_fn

    destinations = [sys.stdout.write]

    printer_write = None
    if printer is not None and printer.is_connected:
        from claude_teletype.printer import make_printer_output

        printer_write = make_printer_output(printer)
        destinations.append(printer_write)

    if not no_audio:
        from claude_teletype.audio import make_bell_output

        destinations.append(make_bell_output())

    from claude_teletype.transcript import make_transcript_output

    transcript_write, transcript_close = make_transcript_output(
        Path(transcript_dir) if transcript_dir else None
    )
    destinations.append(transcript_write)

    output_fn = make_output_fn(*destinations)
    first_token = True

    try:
        # Write user prompt to transcript and printer before streaming
        for ch in f"\n> {prompt}\n\n":
            transcript_write(ch)
            if printer_write:
                printer_write(ch)

        with console.status("[bold cyan]Thinking...", spinner="dots") as status:
            async for item in backend.stream(prompt):
                if isinstance(item, StreamResult):
                    if item.is_error:
                        if first_token:
                            status.stop()
                        console.print(
                            f"\n[bold red]Error: {item.error_message}"
                        )
                    break  # StreamResult is always the final yield
                if first_token:
                    status.stop()
                    first_token = False
                await pace_characters(
                    item,
                    base_delay_ms=base_delay_ms,
                    output_fn=output_fn,
                )

        print()

        if first_token:
            console.print("[bold red]No response received from Claude.")
    except KeyboardInterrupt:
        print("\n[Interrupted]")
    finally:
        transcript_close()
        if printer is not None:
            printer.close()


@config_app.command()
def show() -> None:
    """Show effective merged configuration with source annotations."""
    config = load_config()
    config = apply_env_overrides(config)
    sources = resolve_sources()

    config_loaded = CONFIG_FILE.exists()
    typer.echo(f"Config file: {CONFIG_FILE}")
    typer.echo(f"File loaded: {config_loaded}")
    typer.echo("")

    # Field groupings for sectioned output
    _sections: list[tuple[str, list[str]]] = [
        ("[general]", ["delay", "no_audio", "no_tui", "transcript_dir"]),
        ("[printer]", ["device", "printer_profile"]),
        ("[llm]", ["backend", "model", "system_prompt"]),
        ("[keys]", ["openai_api_key", "openrouter_api_key"]),
    ]

    _secret_fields = {"openai_api_key", "openrouter_api_key"}

    for section_header, field_names in _sections:
        typer.echo(section_header)
        for name in field_names:
            value = getattr(config, name)
            source = sources.get(name, "default")
            if name in _secret_fields:
                display_value = "***" if value else ""
            elif isinstance(value, str):
                display_value = repr(value) if name == "system_prompt" else value
            else:
                display_value = value
            typer.echo(f"{name} = {display_value}  # {source}")
        typer.echo("")


@config_app.command("init")
def init_config() -> None:
    """Create a config file with default settings."""
    if CONFIG_FILE.exists():
        typer.echo(f"Config file already exists: {CONFIG_FILE}")
        typer.echo("Delete it first if you want to regenerate.")
        raise typer.Exit(0)

    path = write_default_config()
    typer.echo(f"Config file created: {path}")


@app.command()
def diagnose() -> None:
    """Show printer diagnostics: USB devices, CUPS queues, pyusb and libusb status."""
    from claude_teletype.diagnose import run_diagnose

    run_diagnose()


def _render_markdown_to_driver(
    path: Path,
    config,
    all_profiles: dict,
    resolved_profile,
    speed_mode: str = "instant",
    transcript_write=None,
) -> int:
    """Render a markdown file through the configured printer driver chain.

    Reused by Plan 25-02's picker-mode launcher (the picker hands a Path
    to this function and exits when it returns).

    Phase 25 contract (default speed_mode="instant"): NO pacer, NO
    transcript, NO chat session — preserved verbatim so the existing
    Phase 25 callers keep working unchanged.

    Phase 26 extension (FLOW-03, FLOW-04):
    - speed_mode="typewriter" routes the text channel through a per-char
      pacer (same delay multipliers as pacer.classify_char) and plays the
      audio bell on '\\n' (unless config.no_audio). Sync time.sleep is used
      so this helper stays sync-only — Plan 25-02's MarkdownPickerApp._on_pick
      callback is sync, and the locked architecture per CONTEXT.md keeps
      it that way.
    - speed_mode="instant" routes the style channel through chunk_writes
      using profile.buffer_bytes, preventing CH341 USB-LPT byte-fragility
      on impact printers (Juki/OKI buffer_bytes=64).

    Phase 26 Plan 03 extension (TXN-01, TXN-02, TXN-03): when
    ``transcript_write`` is provided, the renderer's text channel is fanned
    out into a list collector; after a successful render the captured
    plain-text body is written via ``transcript.write_printed_file``. Style
    ESC bytes are NOT captured (TXN-02 byte-cleanliness — the parallel
    collector taps ONLY the renderer's text_output_fn, never the
    style_output_fn). When ``transcript_write`` is None, no transcript
    entry is created (TXN-03).

    Args:
        path: Path to a regular UTF-8 text file (already validated).
        config: Resolved TeletypeConfig (defaults < TOML < env < CLI flags).
        all_profiles: Built-in + custom profile registry (lookup by name).
        resolved_profile: PrinterProfile or None (None = generic).
        speed_mode: "typewriter" (paced + bell) or "instant" (no pacing,
            chunked style writes). Defaults to "instant" for Phase 25
            backward compat — Plan 25-01/25-02 callers keep working.
        transcript_write: Optional per-character transcript writer. When
            provided, the rendered plain-text body is fanned out via this
            callable in addition to the printer; after a successful render,
            ``write_printed_file`` is called once with the joined body.
            Defaults to None (Phase 25 backward compat — no transcript fan-out).

    Returns:
        Exit code: 0 on success, 1 on read error or invalid speed_mode.
    """
    import time

    from claude_teletype.markdown import MarkdownRenderer
    from claude_teletype.pacer import CHAR_DELAYS, classify_char
    from claude_teletype.printer import chunk_writes, discover_printer
    from claude_teletype.transcript import write_printed_file
    from claude_teletype.wordwrap import WordWrapper

    if speed_mode not in ("typewriter", "instant"):
        typer.echo(
            f"Error: invalid speed_mode {speed_mode!r}; "
            "expected 'typewriter' or 'instant'",
            err=True,
        )
        return 1

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        typer.echo(f"Error: cannot read {path}: {e}", err=True)
        return 1

    driver = discover_printer(
        device_override=config.device,
        profile=resolved_profile,
    )

    # Plan 26-03 (TXN-02): parallel collector captures the renderer's
    # text channel for the transcript. Initialised even when transcript
    # is unused — appending to a list with no consumer is cheap.
    transcript_buffer: list[str] = []

    try:
        # Columns: profile.columns when present, else 80 (matches
        # MarkdownRenderer's own fallback inside __init__).
        columns = (
            resolved_profile.columns
            if resolved_profile is not None and resolved_profile.columns
            else 80
        )

        # Build text + style destinations based on speed_mode.
        if speed_mode == "typewriter":
            # FLOW-03: pacer + bell. Reuses pacer.classify_char + CHAR_DELAYS
            # for delay multipliers identical to the chat path. Sync
            # time.sleep — this helper runs sync-only per Phase 25 locked
            # architecture.
            base_delay = (config.delay or 0.0) / 1000.0

            from claude_teletype.audio import make_bell_output

            bell_fn = (
                (lambda ch: None)
                if config.no_audio
                else make_bell_output()
            )

            def text_dest(char: str) -> None:
                driver.write(char)
                bell_fn(char)
                if base_delay > 0:
                    multiplier = CHAR_DELAYS[classify_char(char)]
                    time.sleep(base_delay * multiplier)

            wrapper = WordWrapper(columns, text_dest)
            # Style channel: bytes go straight to driver — no chunking
            # needed in typewriter mode (style bursts are tiny ESC seqs,
            # always well under any realistic profile.buffer_bytes).
            style_dest = driver.write_bytes
        else:
            # FLOW-04: instant mode. No per-char delay; split style writes
            # at profile.buffer_bytes to avoid CH341 byte-fragility.
            wrapper = WordWrapper(columns, driver.write)

            buffer_bytes = (
                resolved_profile.buffer_bytes
                if resolved_profile is not None and resolved_profile.buffer_bytes
                else 256
            )

            def style_dest(data: bytes) -> None:
                # chunk_writes raises ValueError on chunk_size<=0; we
                # guarantee buffer_bytes > 0 above via the conditional.
                chunk_writes(driver, data, buffer_bytes)

        # Plan 26-03: text channel fan-out for transcript.
        # When transcript_write is provided, text_dest_with_capture writes
        # to BOTH the wrapper (-> printer) AND the transcript buffer.
        # Style channel is NOT routed through the buffer (TXN-02).
        if transcript_write is not None:
            def text_dest_with_capture(char: str) -> None:
                wrapper.feed(char)
                transcript_buffer.append(char)
            renderer_text_fn = text_dest_with_capture
        else:
            renderer_text_fn = wrapper.feed

        renderer = MarkdownRenderer(
            text_output_fn=renderer_text_fn,
            style_output_fn=style_dest,
            profile=resolved_profile,
            columns=columns,
        )
        renderer.render(text)
        # WordWrapper buffers the last word until flush() -- without this,
        # documents that don't end in whitespace would lose their trailing
        # token. flush() must run BEFORE end_response() so the cut/paper-eject
        # happens after every visible character has reached the driver.
        wrapper.flush()
        # ProfilePrinterDriver has end_response (per-response paper cut on
        # receipt printers). Plain drivers don't. Use getattr-then-call so
        # this helper works across all driver implementations.
        end_response = getattr(driver, "end_response", None)
        if end_response is not None:
            end_response()

        # Plan 26-03 (TXN-01): write transcript entry after successful render.
        # write_printed_file guards None internally (TXN-03), but we only
        # reach this branch when transcript_write is non-None anyway.
        if transcript_write is not None:
            write_printed_file(
                transcript_write, path, "".join(transcript_buffer),
            )
    finally:
        # close() runs in finally so partial-render exceptions still close
        # the device handle cleanly.
        driver.close()

    return 0


def _resolve_print_context(
    delay: float | None,
    device: str | None,
    printer: str | None,
):
    """Build (config, all_profiles, resolved_profile) for the print path.

    Shared by both the explicit-path branch (`_print_command_impl`) and the
    picker-mode branch (`_print_command_impl_picker`). Mirrors `main()`'s
    profile-resolution chain (per Plan 25-01 D-03) without touching it
    -- the chat path stays in its lane.

    Returns a 3-tuple on success. On unknown-profile error, emits the error
    message via typer.echo(err=True) and returns ``(None, None, None)`` so
    callers can detect failure uniformly without raising.
    """
    # Config: defaults < TOML < env < CLI flags. Same chain as main() per
    # Plan 25-01 D-02 (CLI-03 requirement). delay is accepted but currently
    # unused for rendering -- merging it still proves the env/CLI layer was
    # applied (Phase 26 will wire it into the speed dialog).
    config = load_config()
    config = apply_env_overrides(config)
    config = merge_cli_flags(config, delay=delay, device=device)

    # Profile resolution -- mirrors main() lines ~325-371 (per Plan 25-01 D-03).
    from claude_teletype.profiles import (
        BUILTIN_PROFILES,
        PrinterProfile,
        auto_detect_profile,
        load_custom_profiles,
    )

    custom_profiles_dict = (
        load_custom_profiles({"printer": {"profiles": config.custom_profiles}})
        if config.custom_profiles
        else {}
    )
    all_profiles = dict(BUILTIN_PROFILES)
    all_profiles.update(custom_profiles_dict)

    resolved_profile: PrinterProfile | None = None
    if printer is not None:
        key = printer.lower().strip()
        if key not in all_profiles:
            available = ", ".join(sorted(all_profiles))
            typer.echo(
                f"Error: unknown printer profile {printer!r}. "
                f"Available: {available}",
                err=True,
            )
            return None, None, None
        resolved_profile = all_profiles[key]
    elif config.printer_profile and config.printer_profile != "generic":
        key = config.printer_profile.lower().strip()
        if key in all_profiles:
            resolved_profile = all_profiles[key]
    else:
        detected = auto_detect_profile(
            extra_profiles=custom_profiles_dict or None,
        )
        if detected is not None:
            resolved_profile = detected

    return config, all_profiles, resolved_profile


def _print_command_impl(
    path: Path,
    delay: float | None,
    device: str | None,
    printer: str | None,
) -> int:
    """Resolve config + profile, validate path, then render to driver.

    Returns the exit code: 0 on success, 1 on path validation failure or any
    clean error. Per Phase 25 CONTEXT.md decisions:

    - Honors TOML < env < CLI flag chain (CLI-03)
    - Non-zero exit on missing or non-regular file (CLI-04)
    - No pacer (Phase 26 wires the speed dialog)
    - No transcript (Phase 26 territory)
    """
    # Path validation (CLI-04). Use absolute path in error messages so users
    # see exactly what we tried to read.
    try:
        resolved_path = path.expanduser().resolve()
    except OSError as e:
        typer.echo(f"Error: cannot resolve path {path!r}: {e}", err=True)
        return 1
    if not resolved_path.exists():
        typer.echo(f"Error: file not found: {resolved_path}", err=True)
        return 1
    if not resolved_path.is_file():
        typer.echo(
            f"Error: not a regular file: {resolved_path}",
            err=True,
        )
        return 1

    config, all_profiles, resolved_profile = _resolve_print_context(
        delay, device, printer,
    )
    if config is None:
        # _resolve_print_context already emitted the error message.
        return 1

    # Plan 26-03 (TXN-01 CLI side): if a transcript directory is configured,
    # build a transcript writer and pass it to the renderer so a "Printed
    # file: <path>\n<body>\n" entry is appended to the session transcript.
    # No transcript_dir = None writer = TXN-03 no-op inside write_printed_file.
    transcript_write_fn = None
    transcript_close_fn = None
    if config.transcript_dir:
        from claude_teletype.transcript import make_transcript_output

        transcript_write_fn, transcript_close_fn = make_transcript_output(
            Path(config.transcript_dir),
        )

    try:
        return _render_markdown_to_driver(
            resolved_path, config, all_profiles, resolved_profile,
            transcript_write=transcript_write_fn,
        )
    finally:
        if transcript_close_fn is not None:
            transcript_close_fn()


def _make_markdown_picker_app(
    config,
    all_profiles: dict,
    resolved_profile,
    root: Path | None = None,
):
    """Build a minimal Textual App that runs the markdown picker and exits.

    Lazily imports textual so cli.py top-level remains lightweight when the
    user invokes only the explicit-path branch or non-interactive commands
    like ``config show`` or ``diagnose``. Plan 25-02 (CLI-02): the no-path
    branch of ``claude-teletype print`` calls this factory, runs the
    returned app, and reads ``app._exit_code`` after ``run()`` returns.

    Closure captures ``config``, ``all_profiles``, ``resolved_profile``,
    and ``root`` so the picker callback has everything it needs to call
    ``_render_markdown_to_driver`` on the selected path.
    """
    from textual.app import App

    from claude_teletype.file_picker_screen import FilePickerScreen

    class MarkdownPickerApp(App):
        """Minimal one-shot picker launcher for `claude-teletype print` (CLI-02).

        Pushes FilePickerScreen on mount; the dismiss callback either prints
        the selected file via the Plan 25-01 helper or exits cleanly on
        cancel. No chat tree, no input prompt, no transcript -- the app
        exists only to bridge the no-arg CLI to the picker.
        """

        CSS = ""  # no chrome

        def __init__(self) -> None:
            super().__init__()
            self._exit_code: int = 0

        def on_mount(self) -> None:
            self.push_screen(
                FilePickerScreen(root=root),
                callback=self._on_pick,
            )

        def _on_pick(self, result) -> None:
            """Handle picker dismiss.

            None -> cancel: exit 0, no print started.
            Path -> render then exit with the helper's return code.
            """
            if result is None:
                self._exit_code = 0
                self.exit()
                return
            # result is a Path. Render synchronously (blocks the picker
            # until print completes) then exit. Phase 26 will refactor
            # this into a worker when the speed dialog lands.
            self._exit_code = _render_markdown_to_driver(
                result, config, all_profiles, resolved_profile,
            )
            self.exit()

    return MarkdownPickerApp()


def _print_command_impl_picker(
    delay: float | None,
    device: str | None,
    printer: str | None,
) -> int:
    """No-path branch: launch picker app, return its exit code (CLI-02).

    Mirrors `_print_command_impl`'s config + profile resolution (TOML <
    env < CLI flags, --printer override, auto-detect) via the shared
    `_resolve_print_context` helper but skips the path-validation block
    (no path) and ends with the picker launcher instead of a direct
    render call. The launcher's callback calls `_render_markdown_to_driver`
    after the user picks a file.

    Returns 0 on cancel or successful render, the helper's non-zero
    exit code on render failure, or 1 if config/profile resolution
    fails up front.
    """
    config, all_profiles, resolved_profile = _resolve_print_context(
        delay, device, printer,
    )
    if config is None:
        return 1

    picker_app = _make_markdown_picker_app(
        config, all_profiles, resolved_profile, root=None,
    )
    picker_app.run()
    return getattr(picker_app, "_exit_code", 0)


@app.command("print")
def print_md(
    path: Path | None = typer.Argument(
        None,
        exists=False,  # we validate manually so we can give a clean error
        help=(
            "Path to a Markdown (or UTF-8 text) file to print. "
            "Omit to launch the file picker."
        ),
    ),
    delay: float = typer.Option(
        None,
        "--delay",
        "-d",
        help=(
            "Base delay between characters (Phase 25 ignores this; "
            "Phase 26 wires the speed dialog)."
        ),
    ),
    device: str = typer.Option(
        None,
        "--device",
        help="Printer device path (e.g., /dev/usb/lp0)",
    ),
    printer: str = typer.Option(
        None,
        "--printer",
        "-p",
        help="Printer profile name (e.g., juki-6100, escp, ppds, pcl).",
    ),
) -> None:
    """Print a Markdown file in one shot.

    With a path: render and exit. Without a path: launch the file picker
    (escape to cancel without printing), render the chosen file, and
    exit. No chat session is started either way.
    """
    if path is None:
        rc = _print_command_impl_picker(delay, device, printer)
    else:
        rc = _print_command_impl(path, delay, device, printer)
    raise typer.Exit(rc)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    prompt: str = typer.Argument(None, help="Prompt (omit for interactive TUI)"),
    delay: float = typer.Option(
        None,
        "--delay",
        "-d",
        help="Base delay between characters in milliseconds (50-100 recommended)",
    ),
    no_tui: bool = typer.Option(
        False,
        "--no-tui",
        help="Disable TUI, use plain stdout (Phase 1 mode)",
    ),
    device: str = typer.Option(
        None,
        "--device",
        help="Printer device path (e.g., /dev/usb/lp0)",
    ),
    no_audio: bool = typer.Option(
        False,
        "--no-audio",
        help="Disable bell sound on line breaks",
    ),
    transcript_dir: str = typer.Option(
        None,
        "--transcript-dir",
        help="Directory for transcript files (default: ./transcripts)",
    ),
    resume: str = typer.Option(
        None,
        "--resume",
        help="Resume a previous session by ID",
    ),
    printer: str = typer.Option(
        None,
        "--printer",
        "-p",
        help="Printer profile name (e.g., juki-6100, juki-2200, oki-3390, escp, ppds/ibm, pcl)",
    ),
    juki: bool = typer.Option(
        False,
        "--juki",
        help="[deprecated] Use --printer juki instead",
    ),
    backend: str = typer.Option(
        None,
        "--backend",
        "-b",
        help="LLM backend: claude-cli, openai, openrouter",
    ),
    model: str = typer.Option(
        None,
        "--model",
        "-m",
        help="Model name (e.g., gpt-4o, anthropic/claude-3.5-sonnet)",
    ),
    teletype: bool = typer.Option(
        False,
        "--teletype",
        help="Raw teletype mode: keyboard to printer, char by char",
    ),
    init_config_flag: bool = typer.Option(
        False,
        "--init-config",
        help="Create config file with defaults",
    ),
    setup_printer: bool = typer.Option(
        False,
        "--setup-printer",
        help="Force the printer setup screen on launch (bypass smart-startup)",
    ),
) -> None:
    """Send a prompt to Claude and watch the response appear character by character."""
    # If a subcommand was invoked (e.g., `config show`), let it handle things
    if ctx.invoked_subcommand is not None:
        return

    # Handle --init-config shortcut
    if init_config_flag:
        if CONFIG_FILE.exists():
            typer.echo(f"Config file already exists: {CONFIG_FILE}")
        else:
            path = write_default_config()
            typer.echo(f"Config file created: {path}")
        raise typer.Exit()

    # Load and merge configuration: defaults < TOML file < env vars < CLI flags
    config = load_config()
    config = apply_env_overrides(config)
    config = merge_cli_flags(
        config, delay=delay, device=device, transcript_dir=transcript_dir,
        backend=backend, model=model,
    )

    # Boolean flags: CLI flag wins if True, otherwise config value wins
    effective_no_audio = no_audio or config.no_audio
    effective_no_tui = no_tui or config.no_tui

    # Profile resolution: --printer flag > --juki flag > config.printer_profile > config.juki > auto-detect > generic
    from claude_teletype.profiles import (
        PrinterProfile,
        auto_detect_profile,
        get_profile,
        load_custom_profiles,
    )

    # Load custom profiles from config
    custom_profiles_dict = load_custom_profiles(
        {"printer": {"profiles": config.custom_profiles}}
    ) if config.custom_profiles else {}

    # Merge built-in + custom for lookup
    from claude_teletype.profiles import BUILTIN_PROFILES

    all_profiles = dict(BUILTIN_PROFILES)
    all_profiles.update(custom_profiles_dict)

    resolved_profile: PrinterProfile | None = None
    if printer is not None:
        # --printer flag set explicitly
        key = printer.lower().strip()
        if key not in all_profiles:
            available = ", ".join(sorted(all_profiles))
            typer.echo(f"Error: unknown printer profile {printer!r}. Available: {available}", err=True)
            raise typer.Exit(1)
        resolved_profile = all_profiles[key]
    elif juki:
        # --juki flag (deprecated)
        typer.echo("Warning: --juki is deprecated, use --printer juki", err=True)
        resolved_profile = get_profile("juki")
    elif config.printer_profile != "generic":
        # Config file [printer] profile = "..."
        key = config.printer_profile.lower().strip()
        if key in all_profiles:
            resolved_profile = all_profiles[key]
    elif config.juki:
        # Old config juki = true backward compat
        resolved_profile = get_profile("juki")
    else:
        # Try USB auto-detection
        detected = auto_detect_profile(extra_profiles=custom_profiles_dict or None)
        if detected is not None:
            resolved_profile = detected

    # resolved_profile is None means generic (no wrapping)

    # Resolve API key from config for the chosen backend
    def _api_key_for(backend_name: str) -> str | None:
        key_map = {"openai": config.openai_api_key, "openrouter": config.openrouter_api_key}
        return key_map.get(backend_name) or None

    # Create and validate backend; fall back to claude-cli if configured
    # backend fails (e.g., missing API key for openrouter/openai)
    try:
        llm_backend = create_backend(
            backend=config.backend,
            model=config.model or None,
            system_prompt=config.system_prompt or None,
            session_id=resume,
            api_key=_api_key_for(config.backend),
        )
        llm_backend.validate()
    except BackendError as e:
        if config.backend != "claude-cli":
            console.print(
                f"[yellow]{e}[/yellow]\n"
                "[dim]Falling back to claude-cli backend. "
                "Change backend in Settings (Ctrl+,).[/dim]",
                highlight=False,
            )
            config.backend = "claude-cli"
            config.model = ""
            try:
                llm_backend = create_backend(
                    backend="claude-cli", session_id=resume,
                )
                llm_backend.validate()
            except BackendError as fallback_err:
                console.print(f"[bold red]{fallback_err}")
                raise typer.Exit(1)
        else:
            console.print(f"[bold red]{e}")
            raise typer.Exit(1)

    # Check for system_prompt + claude-cli conflict at startup
    from claude_teletype.warnings import check_system_prompt_warning, should_warn_startup

    startup_warning = check_system_prompt_warning(config.backend, config.system_prompt)
    if startup_warning and should_warn_startup(config.backend, config.system_prompt):
        console.print(f"[yellow]{startup_warning}[/yellow]", highlight=False)

    # Auto-detect piped stdin -- fall back to non-TUI mode
    if not sys.stdin.isatty():
        effective_no_tui = True

    if teletype:
        from claude_teletype.printer import (
            FilePrinterDriver,
            discover_cups_printers,
            discover_macos_usb_printers,
            discover_usb_device_verbose,
        )
        from claude_teletype.teletype import run_teletype

        usb_driver, diagnostics = discover_usb_device_verbose()

        if usb_driver is not None:
            run_teletype(usb_driver, profile=resolved_profile)
            return

        # Discovery failed — show diagnostics
        for msg in diagnostics:
            console.print(f"[yellow]  {msg}", highlight=False)

        # macOS IOKit fallback
        if sys.platform == "darwin":
            iokit_printers = discover_macos_usb_printers()
            if iokit_printers:
                console.print("[cyan]macOS IOKit sees:")
                for p in iokit_printers:
                    vid = p.get("vid", 0)
                    pid = p.get("pid", 0)
                    console.print(
                        f"[cyan]  {p['name']} (0x{vid:04x}:0x{pid:04x})", highlight=False
                    )

        # CUPS fallback info
        cups_printers = discover_cups_printers()
        usb_cups = [p for p in cups_printers if p["uri"].startswith("usb://")]
        if usb_cups:
            console.print("[cyan]CUPS sees USB printers:")
            for p in usb_cups:
                console.print(
                    f"[cyan]  {p['name']} ({p['uri']}) "
                    "— but teletype needs direct USB access.",
                    highlight=False,
                )
            console.print("[cyan]  Ensure pyusb is installed: uv sync --extra usb")

        # --device fallback
        if config.device:
            console.print(f"[yellow]Falling back to device file: {config.device}")
            run_teletype(FilePrinterDriver(config.device), profile=resolved_profile)
            return

        console.print("[bold red]No USB printer available for teletype mode.")
        raise typer.Exit(1)

    # Discover printer: use discover_all() for TUI (setup screen handles selection)
    # or discover_printer() for --no-tui mode (direct selection)
    from claude_teletype.printer import create_driver_for_selection, discover_all, discover_printer

    if effective_no_tui:
        # --no-tui mode: use existing direct discovery (no setup screen)
        printer_driver = discover_printer(device_override=config.device, profile=resolved_profile)
        discovery = None
    else:
        # TUI mode: run lightweight discovery, pass to setup screen
        # If user specified --device, use direct discovery (skip setup screen)
        if config.device:
            printer_driver = discover_printer(device_override=config.device, profile=resolved_profile)
            discovery = None  # No setup screen needed
        else:
            discovery = discover_all()
            printer_driver = None  # Setup screen will create the driver

            # Smart startup: check if saved printer is still connected (CFG-02).
            # --setup-printer bypasses this so the user can re-pick a connection.
            if (
                not setup_printer
                and config.saved_printer_type
                and config.saved_printer_type != "skip"
            ):
                from claude_teletype.printer import match_saved_printer
                saved_match = match_saved_printer(
                    config.saved_printer_type,
                    config.saved_printer_id,
                    discovery,
                )
                if saved_match is not None:
                    # Saved printer found -- create driver, skip setup screen
                    saved_match.profile_name = config.saved_printer_profile or "generic"
                    printer_driver = create_driver_for_selection(
                        saved_match, discovery, all_profiles=all_profiles,
                    )
                    discovery = None  # Signal: no setup screen needed
                    # Also resolve the profile for status bar display
                    if config.saved_printer_profile and config.saved_printer_profile in all_profiles:
                        resolved_profile = all_profiles[config.saved_printer_profile]
                # else: saved printer not found -- discovery stays set, setup screen will show

    if effective_no_tui:
        if not prompt:
            console.print("[bold red]Error: prompt required with --no-tui or piped input")
            raise typer.Exit(1)
        asyncio.run(
            _chat_async(
                prompt,
                config.delay,
                printer=printer_driver,
                no_audio=effective_no_audio,
                transcript_dir=config.transcript_dir,
                backend=llm_backend,
            )
        )
    else:
        from claude_teletype.tui import TeletypeApp

        tui_app = TeletypeApp(
            base_delay_ms=config.delay,
            printer=printer_driver,
            no_audio=effective_no_audio,
            transcript_dir=config.transcript_dir,
            resume_session_id=resume,
            backend=llm_backend,
            backend_name=config.backend,
            model_config=config.model,
            system_prompt=config.system_prompt,
            profile_name=resolved_profile.name if resolved_profile else "generic",
            all_profiles=all_profiles,
            openai_api_key=config.openai_api_key,
            openrouter_api_key=config.openrouter_api_key,
            discovery=discovery,
        )
        tui_app.run()

        if tui_app.session_id:
            Console(stderr=True).print(
                f"To resume: claude-teletype --resume {tui_app.session_id}",
                style="dim",
            )
