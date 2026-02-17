"""OpenAI and OpenRouter streaming backends.

Uses the openai SDK's AsyncOpenAI client to stream chat completions,
yielding text chunks and a final StreamResult for pipeline consumption.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from claude_teletype.backends import BackendError, LLMBackend
from claude_teletype.bridge import StreamResult


class OpenAIBackend(LLMBackend):
    """Backend that streams via the OpenAI API.

    Uses AsyncOpenAI with chat.completions.create(stream=True) and
    manages conversation history in-memory for multi-turn conversations.
    """

    def __init__(
        self,
        api_key: str | None,
        model: str,
        system_prompt: str | None = None,
        base_url: str | None = None,
    ) -> None:
        # Defer openai import to avoid hard dependency at module level
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=0)
        self._model = model
        self._system_prompt = system_prompt
        self._history: list[dict[str, str]] = []

    def validate(self) -> None:
        """Check that the API key is set.

        Raises:
            BackendError: If the API key is not configured.
        """
        if not self._client.api_key:
            raise BackendError(
                "OPENAI_API_KEY environment variable not set. "
                "Set it with: export OPENAI_API_KEY=your-key"
            )

    def add_to_history(self, role: str, content: str) -> None:
        """Append a message to conversation history."""
        self._history.append({"role": role, "content": content})

    def _build_messages(self) -> list[dict[str, str]]:
        """Build the messages list including optional system prompt."""
        messages: list[dict[str, str]] = []
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})
        messages.extend(self._history)
        return messages

    async def stream(self, prompt: str) -> AsyncIterator[str | StreamResult]:
        """Stream a chat completion response from the OpenAI API.

        Yields text chunks as they arrive, followed by a final StreamResult.
        Catches SDK exceptions and yields error StreamResults with messages
        matching existing ERROR_PATTERNS for classification.

        Args:
            prompt: The user message to send.

        Yields:
            Text strings followed by a single StreamResult.
        """
        import openai

        self.add_to_history("user", prompt)
        messages = self._build_messages()
        assistant_content: list[str] = []

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                stream=True,
            )
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    assistant_content.append(content)
                    yield content

            self.add_to_history("assistant", "".join(assistant_content))
            yield StreamResult(model=self._model, is_error=False)

        except openai.AuthenticationError as e:
            yield StreamResult(
                is_error=True,
                error_message=f"Authentication failed: {e}",
            )
        except openai.RateLimitError as e:
            yield StreamResult(
                is_error=True,
                error_message=f"Rate limit exceeded: {e}",
            )
        except openai.APIConnectionError as e:
            yield StreamResult(
                is_error=True,
                error_message=f"Network error - connection failed: {e}",
            )
        except openai.APIError as e:
            yield StreamResult(
                is_error=True,
                error_message=str(e),
            )


class OpenRouterBackend(OpenAIBackend):
    """Backend that streams via the OpenRouter API.

    Inherits from OpenAIBackend with a different base_url and API key.
    """

    def __init__(
        self,
        api_key: str | None,
        model: str,
        system_prompt: str | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            base_url="https://openrouter.ai/api/v1",
        )

    def validate(self) -> None:
        """Check that the OpenRouter API key is set.

        Raises:
            BackendError: If the API key is not configured.
        """
        if not self._client.api_key:
            raise BackendError(
                "OPENROUTER_API_KEY environment variable not set. "
                "Set it with: export OPENROUTER_API_KEY=your-key"
            )
