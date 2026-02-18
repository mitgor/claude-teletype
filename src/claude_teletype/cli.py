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
    """Show effective merged configuration."""
    config = load_config()
    config = apply_env_overrides(config)

    config_loaded = CONFIG_FILE.exists()
    typer.echo(f"Config file: {CONFIG_FILE}")
    typer.echo(f"File loaded: {config_loaded}")
    typer.echo("")

    typer.echo(f"delay = {config.delay}")
    typer.echo(f"no_audio = {config.no_audio}")
    typer.echo(f"no_tui = {config.no_tui}")
    typer.echo(f"transcript_dir = {config.transcript_dir}")
    typer.echo(f"device = {config.device}")
    typer.echo(f"printer_profile = {config.printer_profile}")
    typer.echo(f"juki = {config.juki}")
    typer.echo(f"backend = {config.backend}")
    typer.echo(f"model = {config.model}")
    typer.echo(f"system_prompt = {config.system_prompt!r}")


@config_app.command("init")
def init_config() -> None:
    """Create a config file with default settings."""
    if CONFIG_FILE.exists():
        typer.echo(f"Config file already exists: {CONFIG_FILE}")
        typer.echo("Delete it first if you want to regenerate.")
        raise typer.Exit(0)

    path = write_default_config()
    typer.echo(f"Config file created: {path}")


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
        help="Printer profile name (e.g., juki, escp, pcl)",
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

    # Create and validate backend; fall back to claude-cli if configured
    # backend fails (e.g., missing API key for openrouter/openai)
    try:
        llm_backend = create_backend(
            backend=config.backend,
            model=config.model or None,
            system_prompt=config.system_prompt or None,
            session_id=resume,
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

    # Discover printer (lazy import to avoid loading printer module when unused)
    from claude_teletype.printer import discover_printer

    printer_driver = discover_printer(device_override=config.device, profile=resolved_profile)

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
        )
        tui_app.run()

        if tui_app.session_id:
            Console(stderr=True).print(
                f"To resume: claude-teletype --resume {tui_app.session_id}",
                style="dim",
            )
