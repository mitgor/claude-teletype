"""Textual split-screen TUI application for Claude Teletype.

Provides an interactive terminal simulator with a scrollable output pane (Log)
showing Claude's responses with typewriter pacing, and an input pane (Input)
for submitting prompts.
"""

import asyncio

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Input, Log


class TeletypeApp(App):
    """Split-screen terminal simulator for Claude Teletype."""

    TITLE = "Claude Teletype"

    CSS = """
    #output {
        height: 1fr;
    }
    #prompt {
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("ctrl+d", "quit", "Quit"),
    ]

    def __init__(self, base_delay_ms: float = 75.0, **kwargs) -> None:
        super().__init__(**kwargs)
        self.base_delay_ms = base_delay_ms

    def compose(self) -> ComposeResult:
        yield Header()
        yield Log(id="output", auto_scroll=True)
        yield Input(id="prompt", placeholder="Type a prompt and press Enter...")
        yield Footer()

    def on_mount(self) -> None:
        """Focus the input widget on app start."""
        self.query_one("#prompt", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user pressing Enter in the input field."""
        prompt = event.value.strip()
        if not prompt:
            return

        event.input.clear()
        log = self.query_one("#output", Log)
        log.write(f"\n> {prompt}\n\n")

        # Indicate thinking state
        self.query_one("#prompt", Input).placeholder = "Thinking..."

        self.stream_response(prompt)

    @work(exclusive=True)
    async def stream_response(self, prompt: str) -> None:
        """Background worker: stream Claude response with typewriter pacing."""
        from claude_teletype.bridge import stream_claude_response
        from claude_teletype.output import make_output_fn
        from claude_teletype.pacer import pace_characters

        log = self.query_one("#output", Log)
        output_fn = make_output_fn(log.write)
        input_widget = self.query_one("#prompt", Input)

        try:
            async for chunk in stream_claude_response(prompt):
                await pace_characters(
                    chunk,
                    base_delay_ms=self.base_delay_ms,
                    output_fn=output_fn,
                )
            log.write("\n")
        except asyncio.CancelledError:
            log.write_line("\n[Cancelled]")
        except Exception as exc:
            log.write_line(f"\n[Error: {exc}]")
        finally:
            input_widget.placeholder = "Type a prompt and press Enter..."
