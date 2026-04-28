"""Tests for FilePickerScreen: mount, filter, path display, dismiss contracts."""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.app import App
from textual.screen import ModalScreen, Screen
from textual.widgets import DirectoryTree, Static

from claude_teletype.file_picker_screen import (
    HIDDEN_DIRS,
    FilePickerScreen,
    MarkdownDirectoryTree,
)


@pytest.fixture
def md_tree(tmp_path: Path) -> Path:
    """Build a small markdown tree:

        tmp_path/
            README.md
            notes.markdown
            script.py            (filtered out)
            data.json            (filtered out)
            docs/
                intro.md
                image.png        (filtered out)
            .git/                (filtered out)
                HEAD
            .venv/               (filtered out)
            node_modules/        (filtered out)
            .planning/           (filtered out)
            __pycache__/         (filtered out)
    """
    (tmp_path / "README.md").write_text("# Readme\n")
    (tmp_path / "notes.markdown").write_text("# Notes\n")
    (tmp_path / "script.py").write_text("print('hi')\n")
    (tmp_path / "data.json").write_text("{}\n")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "intro.md").write_text("# Intro\n")
    (docs / "image.png").write_bytes(b"\x89PNG\r\n")
    for hidden in (".git", ".venv", "node_modules", ".planning", "__pycache__"):
        d = tmp_path / hidden
        d.mkdir()
        (d / "ignored").write_text("ignored\n")
    return tmp_path


class PickerTestApp(App):
    """Minimal test app that pushes a FilePickerScreen on mount.

    Mirrors SetupTestApp from test_printer_setup_screen.py. The
    applied_result sentinel "NOT_SET" lets us distinguish the
    "callback never fired" state from a legitimate None dismiss.
    """

    def __init__(self, root: Path) -> None:
        super().__init__()
        self._root = root
        self.applied_result: object = "NOT_SET"

    def on_mount(self) -> None:
        self.push_screen(
            FilePickerScreen(root=self._root),
            callback=self._on_result,
        )

    def _on_result(self, result: Path | None) -> None:
        self.applied_result = result


# ------------------------------------------------------------------
# Structural / unit-level tests (no Pilot needed)
# ------------------------------------------------------------------

def test_screen_is_full_screen_not_modal():
    """CONTEXT.md decision: full Screen, NOT ModalScreen (carry-forward)."""
    s = FilePickerScreen()
    assert isinstance(s, Screen)
    assert not isinstance(s, ModalScreen)


def test_filter_paths_keeps_md_files(tmp_path: Path):
    """PICK-03: .md and .markdown files survive filter_paths."""
    readme = tmp_path / "README.md"
    notes = tmp_path / "notes.markdown"
    for p in (readme, notes):
        p.write_text("# x\n")
    tree = MarkdownDirectoryTree(str(tmp_path))
    kept = list(tree.filter_paths([readme, notes]))
    assert readme in kept
    assert notes in kept


def test_filter_paths_hides_non_markdown_files(tmp_path: Path):
    """PICK-03: .py / .txt / .json files do not survive filter_paths."""
    script = tmp_path / "script.py"
    notes = tmp_path / "notes.txt"
    data = tmp_path / "data.json"
    for p in (script, notes, data):
        p.write_text("x\n")
    tree = MarkdownDirectoryTree(str(tmp_path))
    kept = list(tree.filter_paths([script, notes, data]))
    assert kept == []


def test_filter_paths_hides_noisy_dirs(tmp_path: Path):
    """PICK-03 noise reduction: hidden / build / cache dirs are filtered out."""
    for name in HIDDEN_DIRS:
        (tmp_path / name).mkdir()
    tree = MarkdownDirectoryTree(str(tmp_path))
    kept = list(tree.filter_paths([tmp_path / n for n in HIDDEN_DIRS]))
    assert kept == []


def test_filter_paths_keeps_normal_dirs(tmp_path: Path):
    """PICK-02: regular subdirectories survive filter_paths so users can navigate."""
    docs = tmp_path / "docs"
    notes = tmp_path / "notes"
    for d in (docs, notes):
        d.mkdir()
    tree = MarkdownDirectoryTree(str(tmp_path))
    kept = list(tree.filter_paths([docs, notes]))
    assert docs in kept
    assert notes in kept


def test_filter_paths_case_insensitive_extensions(tmp_path: Path):
    """PICK-03: .MD and .Markdown (mixed case) also match -- defensive normalization."""
    upper = tmp_path / "READ.MD"
    mixed = tmp_path / "Notes.Markdown"
    for p in (upper, mixed):
        p.write_text("x\n")
    tree = MarkdownDirectoryTree(str(tmp_path))
    kept = list(tree.filter_paths([upper, mixed]))
    assert upper in kept
    assert mixed in kept


# ------------------------------------------------------------------
# Pilot-driven integration tests (Textual Pilot pattern)
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_picker_mounts_with_directory_tree(md_tree: Path):
    """PICK-02: Picker mounts; DirectoryTree present and rooted at given path."""
    app = PickerTestApp(root=md_tree)
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        tree = app.screen.query_one("#picker-tree", DirectoryTree)
        # DirectoryTree.path is a Path on modern Textual; coerce for safety.
        assert Path(tree.path).resolve() == md_tree.resolve()


@pytest.mark.asyncio
async def test_path_display_initial_placeholder(md_tree: Path):
    """PICK-05: Path display shows placeholder before user navigates."""
    app = PickerTestApp(root=md_tree)
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        display = app.screen.query_one("#picker-path", Static)
        # Static.render() returns a Textual Content object whose str()
        # is the displayed text. Avoids relying on private attrs.
        text = str(display.render())
        # Either the literal placeholder or the root path itself is acceptable
        # initial state (depends on whether DirectoryTree fires
        # NodeHighlighted on mount). Both satisfy PICK-05.
        assert (
            "Highlight a file" in text
            or str(md_tree.resolve()) in text
        )


@pytest.mark.asyncio
async def test_escape_dismisses_with_none(md_tree: Path):
    """PICK-04: escape returns None to caller (cancel-back semantics)."""
    app = PickerTestApp(root=md_tree)
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.applied_result is None


@pytest.mark.asyncio
async def test_q_dismisses_with_none(md_tree: Path):
    """PICK-04: q is the alternate cancel binding."""
    app = PickerTestApp(root=md_tree)
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.press("q")
        await pilot.pause()
        assert app.applied_result is None


@pytest.mark.asyncio
async def test_file_selected_dismisses_with_path(md_tree: Path):
    """PICK-05: selecting a file dismisses with its resolved absolute Path.

    Synthesizes a DirectoryTree.FileSelected event rather than relying on
    Pilot keyboard navigation (which depends on tree-expansion timing).
    Mirrors the test_printer_setup_screen.py pattern of driving the
    screen's event handlers directly when needed.
    """
    app = PickerTestApp(root=md_tree)
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        target = (md_tree / "README.md").resolve()

        # Build a minimal FileSelected event. DirectoryTree.FileSelected
        # exposes a `path` attribute and a `node` attribute. We only need
        # path for the handler, but pass node to satisfy the dataclass.
        class _StubNode:
            pass

        event = DirectoryTree.FileSelected(
            node=_StubNode(),  # type: ignore[arg-type]
            path=target,
        )
        screen.on_directory_tree_file_selected(event)
        await pilot.pause()
        assert app.applied_result == target
        assert isinstance(app.applied_result, Path)
