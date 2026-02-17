"""LLM backend abstraction layer.

Provides LLMBackend ABC, BackendError exception, and create_backend factory
for creating streaming backends (Claude CLI, OpenAI, OpenRouter).
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from claude_teletype.bridge import StreamResult


class BackendError(Exception):
    """Raised when a backend fails validation or configuration."""


class LLMBackend(ABC):
    """Abstract base for all LLM streaming backends.

    All backends produce the same AsyncIterator[str | StreamResult] output:
    text chunks followed by a final StreamResult with session metadata.
    """

    @abstractmethod
    async def stream(self, prompt: str) -> AsyncIterator[str | StreamResult]:
        """Stream a response, yielding text chunks and a final StreamResult."""
        ...

    @abstractmethod
    def validate(self) -> None:
        """Check configuration at startup. Raise BackendError if misconfigured."""
        ...

    @abstractmethod
    def add_to_history(self, role: str, content: str) -> None:
        """Record a message in conversation history (no-op for Claude CLI)."""
        ...


def create_backend(
    backend: str,
    model: str | None = None,
    system_prompt: str | None = None,
    session_id: str | None = None,
) -> LLMBackend:
    """Create an LLM backend by name.

    Args:
        backend: Backend identifier: "claude-cli", "openai", or "openrouter".
        model: Model name override. Defaults vary by backend.
        system_prompt: System prompt for OpenAI/OpenRouter backends.
        session_id: Session ID for Claude CLI resume.

    Returns:
        An LLMBackend instance.

    Raises:
        BackendError: If the backend name is unknown.
    """
    if backend == "claude-cli":
        from claude_teletype.backends.claude_cli import ClaudeCliBackend

        return ClaudeCliBackend(session_id=session_id)

    if backend == "openai":
        from claude_teletype.backends.openai_backend import OpenAIBackend

        return OpenAIBackend(
            api_key=os.environ.get("OPENAI_API_KEY"),
            model=model or "gpt-4o",
            system_prompt=system_prompt,
        )

    if backend == "openrouter":
        from claude_teletype.backends.openai_backend import OpenRouterBackend

        return OpenRouterBackend(
            api_key=os.environ.get("OPENROUTER_API_KEY"),
            model=model or "openai/gpt-4o",
            system_prompt=system_prompt,
        )

    raise BackendError(f"Unknown backend: {backend!r}")
