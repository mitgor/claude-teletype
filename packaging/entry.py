"""Frozen entry point for the PyInstaller bundle.

Mirrors src/claude_teletype/__main__.py — PyInstaller needs a plain script
(not a -m module invocation) as the Analysis target.
"""

from claude_teletype.cli import app

app()
