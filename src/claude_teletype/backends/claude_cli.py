"""Claude Code CLI backend wrapping bridge.py.

Delegates streaming to the existing stream_claude_response subprocess bridge,
providing the same AsyncIterator[str | StreamResult] interface as all backends.
"""

from __future__ import annotations

import shutil
from collections.abc import AsyncIterator

from claude_teletype.backends import BackendError, LLMBackend
from claude_teletype.bridge import StreamResult, stream_claude_response


class ClaudeCliBackend(LLMBackend):
    """Backend that streams via the Claude Code CLI subprocess.

    Wraps stream_claude_response from bridge.py, managing session ID
    for multi-turn resume and proc_holder for subprocess lifecycle.
    """

    def __init__(self, session_id: str | None = None) -> None:
        self._session_id = session_id
        self._proc_holder: list = []

    @property
    def session_id(self) -> str | None:
        """Current session ID for multi-turn resume."""
        return self._session_id

    @property
    def proc_holder(self) -> list:
        """Subprocess reference list for external lifecycle management."""
        return self._proc_holder

    def validate(self) -> None:
        """Check that the Claude Code CLI binary is on PATH.

        Raises:
            BackendError: If the claude binary is not found.
        """
        if shutil.which("claude") is None:
            raise BackendError(
                "Claude Code CLI is not installed. "
                "Install it from https://docs.anthropic.com/en/docs/claude-code/overview"
            )

    def add_to_history(self, role: str, content: str) -> None:
        """No-op: Claude CLI manages its own conversation state via --resume."""

    async def stream(self, prompt: str) -> AsyncIterator[str | StreamResult]:
        """Stream a response via the Claude Code CLI subprocess.

        Delegates to stream_claude_response, yielding each item.
        Updates session_id from the final StreamResult for multi-turn resume.

        Args:
            prompt: The prompt to send to Claude Code.

        Yields:
            Text strings followed by a single StreamResult.
        """
        async for item in stream_claude_response(
            prompt, session_id=self._session_id, proc_holder=self._proc_holder
        ):
            if isinstance(item, StreamResult) and item.session_id is not None:
                self._session_id = item.session_id
            yield item
