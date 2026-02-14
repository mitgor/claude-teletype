"""CLI entry point for Claude Teletype.

Wires together the bridge (Claude Code subprocess streaming) and pacer
(character-by-character typewriter output) with a Rich thinking indicator.
"""

import asyncio

import typer
from rich.console import Console

from claude_teletype.bridge import stream_claude_response
from claude_teletype.pacer import pace_characters

app = typer.Typer()
console = Console()


async def _chat_async(prompt: str, base_delay_ms: float) -> None:
    """Send prompt to Claude Code and display response with typewriter pacing.

    Shows a thinking spinner while waiting for the first token, then
    outputs characters one at a time with variable delays.
    """
    first_token = True

    try:
        with console.status("[bold cyan]Thinking...", spinner="dots") as status:
            async for text_chunk in stream_claude_response(prompt):
                if first_token:
                    status.stop()
                    first_token = False

                await pace_characters(text_chunk, base_delay_ms=base_delay_ms)

        print()

        if first_token:
            console.print("[bold red]No response received from Claude.")
    except KeyboardInterrupt:
        print("\n[Interrupted]")


@app.command()
def chat(
    prompt: str = typer.Argument(..., help="Prompt to send to Claude"),
    delay: float = typer.Option(
        75.0,
        "--delay",
        "-d",
        help="Base delay between characters in milliseconds (50-100 recommended)",
    ),
) -> None:
    """Send a prompt to Claude and watch the response appear character by character."""
    asyncio.run(_chat_async(prompt, delay))
