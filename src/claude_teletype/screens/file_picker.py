"""Markdown file picker screen for the Textual TUI.

Full-screen DirectoryTree rooted at cwd, filtered to markdown files and
non-noisy directories. Dismisses with the absolute Path of the selected
file or None if cancelled. Caller is responsible for any file I/O beyond
DirectoryTree's tree-loading -- the picker is pure UI.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DirectoryTree, Footer, Header, Static

# Directories that are pure noise in a markdown picker -- hidden globally.
# Per CONTEXT.md "File filtering" decision: filter via name list, not
# extension or callback chains. Easy to extend, easy to grep.
HIDDEN_DIRS: frozenset[str] = frozenset(
    {".git", ".venv", "__pycache__", "node_modules", ".planning"}
)

# Visible markdown extensions (PICK-03).
MARKDOWN_SUFFIXES: frozenset[str] = frozenset({".md", ".markdown"})


class MarkdownDirectoryTree(DirectoryTree):
    """DirectoryTree subclass that filters children to markdown + non-noisy dirs.

    Override filter_paths so the same instance can be reused without per-instance
    callable wiring. Returns directories that aren't in HIDDEN_DIRS plus files
    whose suffix (case-insensitive) is in MARKDOWN_SUFFIXES.
    """

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        for p in paths:
            if p.is_dir():
                if p.name in HIDDEN_DIRS:
                    continue
                yield p
            elif p.suffix.lower() in MARKDOWN_SUFFIXES:
                yield p
            # else: skip non-markdown files


class FilePickerScreen(Screen[Path | None]):
    """Full-screen markdown file picker rooted at cwd.

    Dismisses with the absolute Path of the selected file (enter on a file
    node), or None if the user cancels (escape or q). Matches the full-Screen
    pattern of PrinterSetupScreen and TypewriterScreen (not a modal overlay)
    per the CONTEXT.md "TUI architecture" decision.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("q", "cancel", "Cancel", show=False),
    ]

    CSS = """
    #picker-container {
        padding: 1 2;
    }
    #picker-title {
        text-style: bold;
        text-align: center;
        width: 100%;
    }
    #picker-tree {
        height: 1fr;
        border: solid $surface-darken-1;
    }
    #picker-path {
        dock: bottom;
        height: 1;
        padding: 0 1;
        background: $surface;
        color: $text-muted;
    }
    """

    def __init__(self, root: Path | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # Resolve root at construction so tests with monkeypatched cwd see
        # the right tree. Default = Path.cwd() (PICK-02).
        self._root = (root if root is not None else Path.cwd()).resolve()

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="picker-container"):
            yield Static(
                "Pick a Markdown file (enter to print, escape to cancel)",
                id="picker-title",
            )
            yield MarkdownDirectoryTree(str(self._root), id="picker-tree")
        yield Static("Highlight a file to see its path", id="picker-path")
        yield Footer()

    def on_mount(self) -> None:
        """Focus the tree so arrow keys and enter work without an extra Tab."""
        self.query_one("#picker-tree", DirectoryTree).focus()

    # ------------------------------------------------------------------
    # DirectoryTree event handlers
    # ------------------------------------------------------------------

    def on_directory_tree_node_highlighted(self, event: Any) -> None:
        """Update the path display whenever the cursor moves (PICK-05).

        The DirectoryTree's TreeNode carries `data` of type DirEntry whose
        `path` attribute is the underlying Path. Falls back to no-op when
        data is missing (defensive -- root collapsed state has no data).
        """
        node = event.node
        data = getattr(node, "data", None)
        path = getattr(data, "path", None)
        display = self.query_one("#picker-path", Static)
        if path is None:
            display.update("Highlight a file to see its path")
        else:
            # Always show resolved absolute (PICK-05 contract: user sees
            # exactly what they're about to print). DirectoryTree path
            # objects are already absolute when the tree is rooted at an
            # absolute path, but resolve() is the canonical idempotent
            # form and is safe on directories too.
            display.update(str(Path(path).resolve()))

    def on_directory_tree_file_selected(self, event: Any) -> None:
        """User activated a file (enter). Dismiss with the absolute Path (PICK-05)."""
        self.dismiss(Path(event.path).resolve())

    # ------------------------------------------------------------------
    # Cancel bindings
    # ------------------------------------------------------------------

    def action_cancel(self) -> None:
        """Escape / q -- dismiss with None so caller returns to chat (PICK-04)."""
        self.dismiss(None)
