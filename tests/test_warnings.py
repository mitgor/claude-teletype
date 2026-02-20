"""Tests for the warnings module."""

import pytest

from claude_teletype.warnings import (
    _reset_warned,
    check_system_prompt_warning,
    should_warn_startup,
)


@pytest.fixture(autouse=True)
def _clear_warned_state():
    """Reset warned combos before each test for isolation."""
    _reset_warned()
    yield
    _reset_warned()


class TestCheckSystemPromptWarning:
    """Tests for check_system_prompt_warning()."""

    def test_warning_when_system_prompt_and_claude_cli(self):
        """Returns warning when system_prompt is set with claude-cli backend."""
        result = check_system_prompt_warning("claude-cli", "You are helpful")
        assert result is not None
        assert "ignored" in result
        assert "claude-cli" in result
        assert "CLAUDE.md" in result
        assert "openai" in result or "openrouter" in result

    def test_no_warning_when_empty_system_prompt(self):
        """Returns None when system_prompt is empty."""
        assert check_system_prompt_warning("claude-cli", "") is None

    def test_no_warning_when_whitespace_system_prompt(self):
        """Returns None when system_prompt is only whitespace."""
        assert check_system_prompt_warning("claude-cli", "   ") is None

    def test_no_warning_when_openai_backend(self):
        """Returns None for openai backend even with system_prompt set."""
        assert check_system_prompt_warning("openai", "You are helpful") is None

    def test_no_warning_when_openrouter_backend(self):
        """Returns None for openrouter backend even with system_prompt set."""
        assert check_system_prompt_warning("openrouter", "You are helpful") is None

    def test_warning_message_includes_remediation(self):
        """Warning message includes suggestion to switch backends."""
        result = check_system_prompt_warning("claude-cli", "test prompt")
        assert result is not None
        assert "Settings" in result or "config" in result


class TestShouldWarnStartup:
    """Tests for should_warn_startup() once-per-config suppression."""

    def test_first_call_returns_true(self):
        """First call for a combo returns True."""
        assert should_warn_startup("claude-cli", "test") is True

    def test_second_call_returns_false(self):
        """Second call with same combo returns False."""
        should_warn_startup("claude-cli", "test")
        assert should_warn_startup("claude-cli", "test") is False

    def test_different_combo_returns_true(self):
        """Different combo returns True even after prior combo was warned."""
        should_warn_startup("claude-cli", "prompt A")
        assert should_warn_startup("claude-cli", "prompt B") is True

    def test_different_backend_returns_true(self):
        """Same prompt with different backend is a different combo."""
        should_warn_startup("claude-cli", "test")
        assert should_warn_startup("openai", "test") is True

    def test_reset_allows_re_warning(self):
        """After _reset_warned(), previously seen combos trigger again."""
        should_warn_startup("claude-cli", "test")
        assert should_warn_startup("claude-cli", "test") is False
        _reset_warned()
        assert should_warn_startup("claude-cli", "test") is True
