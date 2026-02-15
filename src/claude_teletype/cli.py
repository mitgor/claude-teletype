"""CLI entry point for Claude Teletype.

Wires together the bridge (Claude Code subprocess streaming) and pacer
(character-by-character typewriter output) with a Rich thinking indicator.

Default mode: launches the Textual split-screen TUI.
Fallback: --no-tui flag or piped stdin preserves Phase 1 stdout behavior.
"""

import asyncio
import sys

import typer
from rich.console import Console

from claude_teletype.bridge import stream_claude_response
from claude_teletype.pacer import pace_characters

app = typer.Typer()
console = Console()


async def _chat_async(
    prompt: str, base_delay_ms: float, printer=None
) -> None:
    """Send prompt to Claude Code and display response with typewriter pacing.

    Shows a thinking spinner while waiting for the first token, then
    outputs characters one at a time with variable delays.

    Args:
        prompt: The user prompt to send to Claude.
        base_delay_ms: Base delay between characters in milliseconds.
        printer: Optional PrinterDriver instance for hardware output.
    """
    from claude_teletype.output import make_output_fn

    destinations = [sys.stdout.write]

    if printer is not None and printer.is_connected:
        from claude_teletype.printer import make_printer_output

        destinations.append(make_printer_output(printer))

    output_fn = make_output_fn(*destinations)
    first_token = True

    try:
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
) -> None:
    """Send a prompt to Claude and watch the response appear character by character."""
    # Auto-detect piped stdin -- fall back to non-TUI mode
    if not sys.stdin.isatty():
        no_tui = True

    # Discover printer (lazy import to avoid loading printer module when unused)
    from claude_teletype.printer import discover_printer

    printer = discover_printer(device_override=device)

    if no_tui:
        if not prompt:
            console.print("[bold red]Error: prompt required with --no-tui or piped input")
            raise typer.Exit(1)
        asyncio.run(_chat_async(prompt, delay, printer=printer))
    else:
        from claude_teletype.tui import TeletypeApp

        tui_app = TeletypeApp(base_delay_ms=delay, printer=printer)
        tui_app.run()
