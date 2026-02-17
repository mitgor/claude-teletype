"""Integration tests for LLM backend wiring in config, CLI, and TUI.

Verifies the full config-to-backend pipeline: config fields, env overrides,
create_backend factory from config, TUI backend storage, and CLI error paths.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from claude_teletype.bridge import StreamResult
from claude_teletype.config import (
    TeletypeConfig,
    apply_env_overrides,
    load_config,
)

runner = CliRunner()


class TestConfigBackendDefaults:
    """Config field defaults for LLM backend settings."""

    def test_config_backend_default(self) -> None:
        """TeletypeConfig().backend defaults to 'claude-cli'."""
        assert TeletypeConfig().backend == "claude-cli"

    def test_config_model_default(self) -> None:
        """TeletypeConfig().model defaults to empty string."""
        assert TeletypeConfig().model == ""

    def test_config_system_prompt_default(self) -> None:
        """TeletypeConfig().system_prompt defaults to empty string."""
        assert TeletypeConfig().system_prompt == ""


class TestConfigLoadLlmSection:
    """Config loading from TOML [llm] section."""

    def test_config_load_llm_section(self, tmp_path) -> None:
        """load_config reads backend/model/system_prompt from [llm] section."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[llm]\nbackend = "openai"\nmodel = "gpt-4o-mini"\n'
            'system_prompt = "You are helpful."\n',
            encoding="utf-8",
        )
        result = load_config(config_file)
        assert result.backend == "openai"
        assert result.model == "gpt-4o-mini"
        assert result.system_prompt == "You are helpful."


class TestConfigEnvOverrideBackend:
    """Env var override for backend field."""

    def test_config_env_override_backend(self, monkeypatch) -> None:
        """CLAUDE_TELETYPE_BACKEND env var overrides config."""
        monkeypatch.setenv("CLAUDE_TELETYPE_BACKEND", "openrouter")
        result = apply_env_overrides(TeletypeConfig())
        assert result.backend == "openrouter"

    def test_config_env_override_model(self, monkeypatch) -> None:
        """CLAUDE_TELETYPE_MODEL env var overrides config."""
        monkeypatch.setenv("CLAUDE_TELETYPE_MODEL", "gpt-4o-mini")
        result = apply_env_overrides(TeletypeConfig())
        assert result.model == "gpt-4o-mini"


class TestCreateBackendFromConfig:
    """Factory creates correct backend from config values."""

    def test_create_backend_from_config_openai(self) -> None:
        """create_backend with backend='openai', model='gpt-4o-mini' returns OpenAIBackend."""
        from claude_teletype.backends import create_backend
        from claude_teletype.backends.openai_backend import OpenAIBackend

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            backend = create_backend(
                backend="openai", model="gpt-4o-mini"
            )
        assert isinstance(backend, OpenAIBackend)
        assert backend._model == "gpt-4o-mini"


class TestTuiAcceptsBackend:
    """TUI stores backend parameter."""

    def test_tui_accepts_backend(self) -> None:
        """TeletypeApp(backend=mock_backend) stores it as _backend."""
        from claude_teletype.tui import TeletypeApp

        mock_backend = MagicMock()
        app = TeletypeApp(backend=mock_backend)
        assert app._backend is mock_backend


class TestCliChatAsyncUsesBackend:
    """_chat_async streams from backend.stream()."""

    @pytest.mark.asyncio
    async def test_cli_chat_async_uses_backend(self, tmp_path) -> None:
        """_chat_async consumes backend.stream() yielding text and StreamResult."""
        from claude_teletype.cli import _chat_async

        items = ["Hello", StreamResult(model="gpt-4o")]

        mock_backend = MagicMock()

        async def mock_stream(prompt):
            for item in items:
                yield item

        mock_backend.stream = mock_stream

        with patch(
            "claude_teletype.cli.pace_characters",
            new_callable=AsyncMock,
        ) as mock_pace, patch(
            "claude_teletype.cli.console",
        ) as mock_console, patch(
            "claude_teletype.transcript.make_transcript_output",
            return_value=(MagicMock(), MagicMock()),
        ):
            mock_console.status.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_console.status.return_value.__exit__ = MagicMock(
                return_value=False
            )

            await _chat_async(
                "test",
                base_delay_ms=0,
                no_audio=True,
                transcript_dir=str(tmp_path),
                backend=mock_backend,
            )

        # pace_characters should be called with "Hello" (str, not StreamResult)
        assert mock_pace.call_count >= 1
        first_arg = mock_pace.call_args_list[0][0][0]
        assert first_arg == "Hello"


class TestBackendValidationErrorExits:
    """Backend validation error causes CLI exit."""

    def test_backend_validation_error_exits(self) -> None:
        """BackendError from create_backend causes main() to exit with code 1."""
        from claude_teletype.backends import BackendError
        from claude_teletype.cli import app

        def raise_error(*args, **kwargs):
            raise BackendError("OPENAI_API_KEY not set")

        with patch(
            "claude_teletype.cli.create_backend", side_effect=raise_error
        ), patch("claude_teletype.cli.load_config"), patch(
            "claude_teletype.cli.apply_env_overrides"
        ) as mock_env, patch(
            "claude_teletype.cli.merge_cli_flags"
        ) as mock_merge:
            mock_cfg = TeletypeConfig(backend="openai")
            mock_env.return_value = mock_cfg
            mock_merge.return_value = mock_cfg

            result = runner.invoke(app, ["--no-tui", "hello"])

        assert result.exit_code == 1


class TestConfigShowLlmFields:
    """Config show displays LLM fields."""

    def test_config_show_displays_backend(self, tmp_path) -> None:
        """config show displays backend, model, system_prompt fields."""
        from claude_teletype.cli import app as cli_app

        fake_config = tmp_path / "nonexistent.toml"
        with patch("claude_teletype.cli.CONFIG_FILE", fake_config), patch(
            "claude_teletype.config.CONFIG_FILE", fake_config
        ):
            result = runner.invoke(cli_app, ["config", "show"])

        assert result.exit_code == 0
        assert "backend = claude-cli" in result.output
        assert "model = " in result.output
        assert "system_prompt = ''" in result.output
