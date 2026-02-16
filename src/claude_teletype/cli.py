"""CLI entry point for Claude Teletype.

Wires together the bridge (Claude Code subprocess streaming) and pacer
(character-by-character typewriter output) with a Rich thinking indicator.

Default mode: launches the Textual split-screen TUI.
Fallback: --no-tui flag or piped stdin preserves Phase 1 stdout behavior.
"""

import asyncio
import sys
from pathlib import Path

import typer
from rich.console import Console

from claude_teletype.bridge import stream_claude_response
from claude_teletype.pacer import pace_characters

app = typer.Typer()
console = Console()


async def _chat_async(
    prompt: str,
    base_delay_ms: float,
    printer=None,
    no_audio: bool = False,
    transcript_dir: str | None = None,
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
            async for text_chunk in stream_claude_response(prompt):
                if first_token:
                    status.stop()
                    first_token = False

                await pace_characters(
                    text_chunk,
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


@app.command()
def chat(
    prompt: str = typer.Argument(None, help="Prompt (omit for interactive TUI)"),
    delay: float = typer.Option(
        75.0,
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
    juki: bool = typer.Option(
        False,
        "--juki",
        help="Enable Juki 6100 impact printer mode",
    ),
    teletype: bool = typer.Option(
        False,
        "--teletype",
        help="Raw teletype mode: keyboard to printer, char by char",
    ),
) -> None:
    """Send a prompt to Claude and watch the response appear character by character."""
    # Auto-detect piped stdin -- fall back to non-TUI mode
    if not sys.stdin.isatty():
        no_tui = True

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
            run_teletype(usb_driver, juki=juki)
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
        if device:
            console.print(f"[yellow]Falling back to device file: {device}")
            run_teletype(FilePrinterDriver(device), juki=juki)
            return

        console.print("[bold red]No USB printer available for teletype mode.")
        raise typer.Exit(1)

    # Discover printer (lazy import to avoid loading printer module when unused)
    from claude_teletype.printer import discover_printer

    printer = discover_printer(device_override=device, juki=juki)

    if no_tui:
        if not prompt:
            console.print("[bold red]Error: prompt required with --no-tui or piped input")
            raise typer.Exit(1)
        asyncio.run(
            _chat_async(
                prompt,
                delay,
                printer=printer,
                no_audio=no_audio,
                transcript_dir=transcript_dir,
            )
        )
    else:
        from claude_teletype.tui import TeletypeApp

        tui_app = TeletypeApp(
            base_delay_ms=delay,
            printer=printer,
            no_audio=no_audio,
            transcript_dir=transcript_dir,
            resume_session_id=resume,
        )
        tui_app.run()

        if tui_app.session_id:
            console.print(
                f"To resume: claude-teletype --resume {tui_app.session_id}",
                style="dim",
                stderr=True,
            )
