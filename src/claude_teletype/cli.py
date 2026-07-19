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
from claude_teletype.rendering.pacer import pace_characters


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
    from claude_teletype.rendering.output import make_output_fn

    destinations = [sys.stdout.write]

    printer_write = None
    if printer is not None and printer.is_connected:
        from claude_teletype.printing.drivers import make_printer_output

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
    resolved_profile,
    driver,
    speed_mode: str = "instant",
    transcript_write=None,
    close_driver: bool = True,
) -> int:
    """Thin CLI adapter over the shared print pipeline (Phase 33, ARCH-01).

    The pipeline body (pacer, word wrapping, chunked style writes,
    transcript collector, end_response epilogue, style-close-in-finally)
    lives in ``printing/pipeline.py::render_document`` — the ONE
    implementation shared with the TUI. This adapter owns only what
    differs per consumer: file reading, error surfacing (typer.echo +
    exit codes), and driver lifetime.

    Driver ownership (single-owner contract): the caller acquires the
    driver (via ``discover_printer``) and passes it in. By default THIS
    adapter closes it in a ``finally`` — a fresh driver per explicit-path
    invocation. The picker flow passes ``close_driver=False`` because
    ``_print_command_impl_picker`` owns the close (the driver must
    survive a cancel, where this adapter is never called).
    render_document itself never closes drivers.

    The CLI-only path keeps synchronous ``time.sleep`` pacing via
    render_document's default ``sleep_fn`` (locked v1.5 sync shape).

    Args:
        path: Path to a regular UTF-8 text file (already validated).
        config: Resolved TeletypeConfig (defaults < TOML < env < CLI flags).
        resolved_profile: PrinterProfile or None (None = generic).
        driver: PrinterDriver acquired by the caller; closed here.
        speed_mode: "typewriter" (paced + bell) or "instant" (chunked
            style writes). Defaults to "instant" (Phase 25 backward compat).
        transcript_write: Optional per-character transcript writer
            (TXN-01..03); None = no transcript entry.
        close_driver: When True (default), close the driver in a finally.
            The picker flow passes False — its launcher owns the close.

    Returns:
        Exit code: 0 on success, 1 on read error or invalid speed_mode.
    """
    from claude_teletype.printing.pipeline import render_document

    try:
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

        render_document(
            driver,
            resolved_profile,
            text,
            speed_mode=speed_mode,
            base_delay_ms=(config.delay or 0.0),
            no_audio=config.no_audio,
            transcript_write=transcript_write,
            source_path=path,
        )
    finally:
        # close() runs in finally so partial-render exceptions still close
        # the device handle cleanly (single-owner contract: see docstring).
        if close_driver:
            driver.close()

    return 0


class _UnknownProfileError(ValueError):
    """``--printer`` named a profile that is not in the registry.

    The exception message is display-ready; callers decide how to exit
    (the print path returns an error code, ``main()`` raises typer.Exit).
    """


def _resolve_profile_selection(
    config,
    printer: str | None,
    *,
    juki_flag: bool = False,
    honor_config_juki: bool = False,
):
    """THE shared load-custom -> registry -> resolve chain (REF-05).

    Single source of the profile-resolution logic previously duplicated
    between ``_resolve_print_context`` and ``main()``. Builds ONE
    ``ProfileRegistry`` (built-ins merged with custom TOML profiles,
    REF-02) and resolves the active profile by precedence:

        --printer > --juki (deprecated, chat path only)
        > config.printer_profile > config.juki (backward compat,
        chat path only) > USB auto-detect

    Args:
        config: Resolved TeletypeConfig (defaults < TOML < env < CLI).
        printer: The --printer flag value, or None.
        juki_flag: The deprecated --juki flag (main() only). Emits the
            deprecation warning when it wins resolution.
        honor_config_juki: Apply the old ``config.juki = true`` backward
            compat branch (main() only — the print path never honored it).

    Returns:
        ``(registry, resolved_profile)``. ``resolved_profile`` is None
        for generic (no profile wrapping).

    Raises:
        _UnknownProfileError: when ``printer`` names an unknown profile.
    """
    from claude_teletype.printing.detection import detect_native_profile
    from claude_teletype.printing.profiles import (
        BUILTIN_PROFILES,
        PrinterProfile,
        load_custom_profiles,
    )
    from claude_teletype.printing.registry import ProfileRegistry

    custom_profiles_dict = (
        load_custom_profiles({"printer": {"profiles": config.custom_profiles}})
        if config.custom_profiles
        else {}
    )
    registry = ProfileRegistry(BUILTIN_PROFILES, custom_profiles_dict or None)

    resolved_profile: PrinterProfile | None = None
    if printer is not None:
        try:
            resolved_profile = registry.get(printer)
        except ValueError:
            available = ", ".join(sorted(registry.names()))
            raise _UnknownProfileError(
                f"Error: unknown printer profile {printer!r}. "
                f"Available: {available}"
            ) from None
    elif juki_flag:
        # --juki flag (deprecated)
        typer.echo("Warning: --juki is deprecated, use --printer juki", err=True)
        resolved_profile = registry.get("juki")
    elif config.printer_profile and config.printer_profile != "generic":
        try:
            resolved_profile = registry.get(config.printer_profile)
        except ValueError:
            # Unknown config profile falls through to generic (None) --
            # same forgiving behavior as the pre-registry blocks.
            resolved_profile = None
    elif honor_config_juki and config.juki:
        # Old config juki = true backward compat
        resolved_profile = registry.get("juki")
    else:
        # USB auto-detect through classify() — same detection seam as the
        # setup screen, so a bridge VID can never auto-suggest a profile.
        resolved_profile = detect_native_profile(registry)

    return registry, resolved_profile


def _resolve_print_context(
    delay: float | None,
    device: str | None,
    printer: str | None,
):
    """Build (config, registry, resolved_profile) for the print path.

    Shared by both the explicit-path branch (`_print_command_impl`) and the
    picker-mode branch (`_print_command_impl_picker`). Profile resolution
    goes through `_resolve_profile_selection`, the same registry-backed
    helper `main()` uses (REF-05).

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

    try:
        registry, resolved_profile = _resolve_profile_selection(config, printer)
    except _UnknownProfileError as e:
        typer.echo(str(e), err=True)
        return None, None, None

    return config, registry, resolved_profile


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

    config, _, resolved_profile = _resolve_print_context(
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

    # Driver acquisition lives here (not in the render adapter) — this is
    # a real terminal, so interactive multi-queue selection is acceptable.
    from claude_teletype.printing.selection import discover_printer

    driver = discover_printer(
        device_override=config.device,
        profile=resolved_profile,
    )

    try:
        return _render_markdown_to_driver(
            resolved_path, config, resolved_profile, driver,
            transcript_write=transcript_write_fn,
        )
    finally:
        if transcript_close_fn is not None:
            transcript_close_fn()


def _make_markdown_picker_app(
    config,
    resolved_profile,
    driver,
    root: Path | None = None,
):
    """Build a minimal Textual App that runs the markdown picker and exits.

    Lazily imports textual so cli.py top-level remains lightweight when the
    user invokes only the explicit-path branch or non-interactive commands
    like ``config show`` or ``diagnose``. Plan 25-02 (CLI-02): the no-path
    branch of ``claude-teletype print`` calls this factory, runs the
    returned app, and reads ``app._exit_code`` after ``run()`` returns.

    Closure captures ``config``, ``resolved_profile``, ``driver``, and
    ``root`` so the picker callback has everything it needs to call
    ``_render_markdown_to_driver`` on the selected path.

    WR-04 (Phase 33): the ``driver`` is resolved by the CALLER before this
    app ever runs — no printer-resolution code (and therefore no
    interactive multi-queue ``input()`` prompt) is reachable from inside
    the app while Textual owns the terminal. The caller also owns
    ``driver.close()``; the render callback passes ``close_driver=False``.
    """
    from textual.app import App

    from claude_teletype.screens.file_picker import FilePickerScreen

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
            # until print completes) then exit. The driver was resolved
            # before this app started (WR-04); the launcher owns its
            # close, so close_driver=False here.
            self._exit_code = _render_markdown_to_driver(
                result, config, resolved_profile, driver,
                close_driver=False,
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

    WR-04 (Phase 33): the printer driver is resolved HERE, before
    ``picker_app.run()`` puts Textual in the alternate screen. With >= 2
    CUPS queues, ``select_printer``'s interactive ``input()`` prompt runs
    on the real terminal, where the user can actually see and answer it.
    This launcher owns ``driver.close()`` on every path (cancel, success,
    render error) — the render callback inside the app passes
    ``close_driver=False`` (single-owner contract).
    """
    config, _, resolved_profile = _resolve_print_context(
        delay, device, printer,
    )
    if config is None:
        return 1

    from claude_teletype.printing.selection import discover_printer

    driver = discover_printer(
        device_override=config.device,
        profile=resolved_profile,
    )

    try:
        picker_app = _make_markdown_picker_app(
            config, resolved_profile, driver, root=None,
        )
        picker_app.run()
        return getattr(picker_app, "_exit_code", 0)
    finally:
        driver.close()


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
    # Single registry-backed chain shared with the print path (REF-02/REF-05).
    try:
        registry, resolved_profile = _resolve_profile_selection(
            config, printer, juki_flag=juki, honor_config_juki=True,
        )
    except _UnknownProfileError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)

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
        from claude_teletype.printing.discovery import (
            discover_cups_printers,
            discover_macos_usb_printers,
            discover_usb_device_verbose,
        )
        from claude_teletype.printing.drivers import FilePrinterDriver
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
    from claude_teletype.printing.discovery import discover_all
    from claude_teletype.printing.selection import create_driver_for_selection, discover_printer
    from claude_teletype.setup_decision import SetupDecision

    # REF-04: each path sets an explicit SetupDecision instead of overloading
    # discovery=None; discovery carries the DiscoveryResult only for SHOW_SETUP.
    if effective_no_tui:
        # --no-tui mode: use existing direct discovery (no setup screen)
        printer_driver = discover_printer(device_override=config.device, profile=resolved_profile)
        discovery = None
        setup_decision = SetupDecision.SKIP_NO_TUI
    else:
        # TUI mode: run lightweight discovery, pass to setup screen
        # If user specified --device, use direct discovery (skip setup screen)
        if config.device:
            printer_driver = discover_printer(device_override=config.device, profile=resolved_profile)
            discovery = None
            setup_decision = SetupDecision.SKIP_DEVICE_OVERRIDE
        else:
            discovery = discover_all()
            printer_driver = None  # Setup screen will create the driver
            setup_decision = SetupDecision.SHOW_SETUP

            # Smart startup: check if saved printer is still connected (CFG-02).
            # --setup-printer bypasses this so the user can re-pick a connection.
            if (
                not setup_printer
                and config.saved_printer_type
                and config.saved_printer_type != "skip"
            ):
                from claude_teletype.printing.selection import match_saved_printer
                saved_match = match_saved_printer(
                    config.saved_printer_type,
                    config.saved_printer_id,
                    discovery,
                    profile_name=config.saved_printer_profile or "generic",
                )
                if saved_match is not None:
                    # Saved printer found -- create driver, skip setup screen
                    printer_driver = create_driver_for_selection(
                        saved_match, discovery, registry=registry,
                    )
                    discovery = None
                    setup_decision = SetupDecision.SKIP_SAVED_MATCH
                    # Also resolve the profile for status bar display
                    if config.saved_printer_profile:
                        try:
                            resolved_profile = registry.get(config.saved_printer_profile)
                        except ValueError:
                            # IN-03: status bar must not claim a profile the
                            # driver doesn't wear.
                            resolved_profile = None
                # else: saved printer not found -- decision stays SHOW_SETUP

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
            registry=registry,
            openai_api_key=config.openai_api_key,
            openrouter_api_key=config.openrouter_api_key,
            discovery=discovery,
            setup_decision=setup_decision,
        )
        tui_app.run()

        if tui_app.session_id:
            Console(stderr=True).print(
                f"To resume: claude-teletype --resume {tui_app.session_id}",
                style="dim",
            )
