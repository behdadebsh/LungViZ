"""Dependency-free file browsing rendered with Polyscope's ImGui bindings."""

from __future__ import annotations

import fnmatch
import os
import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Sequence, Tuple


@dataclass(frozen=True)
class FileFilter:
    """A named collection of filename patterns displayed by the browser."""

    label: str
    patterns: Tuple[str, ...]


@dataclass(frozen=True)
class FileDialogRequest:
    """Description of a file-browser operation."""

    title: str
    mode: str
    initial_directory: Path = field(default_factory=Path.cwd)
    filters: Tuple[FileFilter, ...] = ()
    default_name: str = ""

    def __post_init__(self) -> None:
        valid_modes = {"open_files", "open_file", "select_directory", "save_file"}
        if self.mode not in valid_modes:
            raise ValueError(f"Unsupported file-dialog mode: {self.mode}")


@dataclass(frozen=True)
class FileDialogOutcome:
    """A completed browser operation; an empty path tuple means cancellation."""

    paths: Tuple[Path, ...]

    @property
    def accepted(self) -> bool:
        return bool(self.paths)


def available_filesystem_roots() -> List[Path]:
    """Return usable filesystem roots without platform-specific dependencies."""

    if os.name == "nt":
        return [
            Path(f"{letter}:\\")
            for letter in string.ascii_uppercase
            if Path(f"{letter}:\\").exists()
        ]
    return [Path("/")]


def nearest_existing_directory(path: Path) -> Path:
    """Resolve *path* to the nearest accessible existing directory."""

    candidate = Path(path).expanduser()
    if candidate.is_file():
        candidate = candidate.parent
    while not candidate.is_dir() and candidate != candidate.parent:
        candidate = candidate.parent
    if candidate.is_dir():
        try:
            return candidate.resolve()
        except OSError:
            return candidate.absolute()
    return Path.cwd().resolve()


class FileBrowser:
    """Stateful, non-blocking file browser drawn in the Polyscope callback."""

    popup_name = "LungViZ file browser"

    def __init__(self) -> None:
        self.request: FileDialogRequest | None = None
        self.directory = Path.cwd().resolve()
        self.path_input = str(self.directory)
        self.filename_input = ""
        self.filter_index = 0
        self.show_hidden = False
        self.selected: List[Path] = []
        self.error = ""
        self._entries: List[Path] = []
        self._open_popup = False
        self._overwrite_candidate: Path | None = None

    @property
    def active(self) -> bool:
        return self.request is not None

    def open(self, request: FileDialogRequest) -> bool:
        """Start a request, returning false when another request is already active."""

        if self.active:
            return False
        self.request = request
        self.directory = nearest_existing_directory(request.initial_directory)
        self.path_input = str(self.directory)
        self.filename_input = request.default_name
        self.filter_index = 0
        self.selected = []
        self.error = ""
        self._overwrite_candidate = None
        self._refresh()
        self._open_popup = True
        return True

    def cancel(self) -> FileDialogOutcome:
        self._reset()
        return FileDialogOutcome(())

    def navigate(self, path: str | Path) -> bool:
        """Navigate to a directory, retaining an actionable error on failure."""

        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.directory / candidate
        try:
            candidate = candidate.resolve()
            if not candidate.is_dir():
                raise NotADirectoryError(f"Not a directory: {candidate}")
            self.directory = candidate
            self.path_input = str(candidate)
            self.selected = []
            self.error = ""
            self._overwrite_candidate = None
            self._refresh()
            return True
        except (OSError, RuntimeError) as exc:
            self.error = f"Cannot open that location: {exc}"
            return False

    def go_to_input(self) -> bool:
        """Open a typed folder or select a typed file path."""

        request = self.request
        if request is None:
            return False
        candidate = Path(self.path_input).expanduser()
        if not candidate.is_absolute():
            candidate = self.directory / candidate
        try:
            candidate = candidate.resolve()
        except (OSError, RuntimeError) as exc:
            self.error = f"Cannot open that location: {exc}"
            return False
        if candidate.is_dir():
            return self.navigate(candidate)
        if request.mode == "save_file" and candidate.parent.is_dir():
            if not self.navigate(candidate.parent):
                return False
            self.filename_input = candidate.name
            return True
        if request.mode in {"open_file", "open_files"} and candidate.is_file():
            if not self._matches_filter(candidate):
                self.error = "That file does not match the selected file type."
                return False
            if not self.navigate(candidate.parent):
                return False
            self.select(candidate)
            return True
        self.error = f"Cannot find that location: {candidate}"
        return False

    def visible_entries(self) -> Sequence[Path]:
        return tuple(self._entries)

    def select(self, path: str | Path) -> None:
        """Select or toggle a visible file according to the request mode."""

        if self.request is None:
            return
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.directory / candidate
        candidate = candidate.resolve()
        if not candidate.is_file():
            return
        if self.request.mode == "save_file":
            self.filename_input = candidate.name
            self.selected = [candidate]
        elif self.request.mode == "open_files":
            if candidate in self.selected:
                self.selected.remove(candidate)
            else:
                self.selected.append(candidate)
        elif self.request.mode == "open_file":
            self.selected = [candidate]

    def confirm(self) -> FileDialogOutcome | None:
        """Validate the current choice and complete it when possible."""

        request = self.request
        if request is None:
            return None
        if request.mode == "select_directory":
            return self._finish((self.directory,))
        if request.mode in {"open_file", "open_files"}:
            if not self.selected:
                self.error = "Select at least one file."
                return None
            if request.mode == "open_file":
                return self._finish((self.selected[0],))
            return self._finish(tuple(self.selected))

        name = self.filename_input.strip()
        if not name:
            self.error = "Enter a filename."
            return None
        target = Path(name).expanduser()
        if not target.is_absolute():
            target = self.directory / target
        target = target.resolve()
        if target.is_dir():
            self.error = "The destination must include a filename."
            return None
        if (
            not target.suffix
            and request.filters
            and request.filters[self.filter_index].patterns
        ):
            pattern = request.filters[self.filter_index].patterns[0]
            suffix = pattern.removeprefix("*")
            if suffix.startswith("."):
                target = target.with_suffix(suffix)
        if target.exists() and self._overwrite_candidate != target:
            self._overwrite_candidate = target
            self.error = "That file already exists. Press Save again to replace it."
            return None
        return self._finish((target,))

    def draw(self, psim) -> FileDialogOutcome | None:
        """Render the active browser and return an outcome once it closes."""

        if self.request is None:
            return None
        if self._open_popup:
            psim.OpenPopup(self.popup_name)
            self._open_popup = False
        if not psim.BeginPopupModal(self.popup_name):
            return None

        outcome: FileDialogOutcome | None = None
        try:
            request = self.request
            psim.TextUnformatted(request.title)

            roots = available_filesystem_roots()
            if len(roots) > 1:
                current_root = self.directory.anchor.casefold()
                root_index = next(
                    (
                        index
                        for index, root in enumerate(roots)
                        if root.anchor.casefold() == current_root
                    ),
                    0,
                )
                changed, root_index = psim.Combo(
                    "Drive", root_index, [str(root) for root in roots]
                )
                if changed:
                    self.navigate(roots[root_index])

            changed, self.path_input = psim.InputTextWithHint(
                "Location", "Enter or paste a folder path", self.path_input
            )
            if changed:
                self._overwrite_candidate = None
            psim.SameLine()
            if psim.Button("Go"):
                self.go_to_input()
            psim.SameLine()
            if psim.Button("Up"):
                self.navigate(self.directory.parent)

            if request.filters:
                changed, index = psim.Combo(
                    "File type",
                    self.filter_index,
                    [item.label for item in request.filters],
                )
                if changed:
                    self.filter_index = index
                    self.selected = []
                    if request.mode == "save_file" and self.filename_input:
                        pattern = request.filters[index].patterns[0]
                        suffix = pattern.removeprefix("*")
                        if suffix.startswith("."):
                            current = Path(self.filename_input)
                            if current.suffix:
                                self.filename_input = str(current.with_suffix(suffix))
                    self._refresh()
            changed, show_hidden = psim.Checkbox("Show hidden files", self.show_hidden)
            if changed:
                self.show_hidden = show_hidden
                self._refresh()

            psim.BeginChild(
                "LungViZ file list",
                (0.0, 300.0),
                psim.ImGuiChildFlags_Borders,
            )
            try:
                for path in self._entries:
                    if path.is_dir():
                        if psim.Selectable(f"[Folder] {path.name}", False):
                            self.navigate(path)
                            break
                        continue
                    selected = path in self.selected
                    if psim.Selectable(path.name, selected):
                        self.select(path)
            finally:
                psim.EndChild()

            if request.mode == "save_file":
                changed, self.filename_input = psim.InputTextWithHint(
                    "Filename", "Enter a filename", self.filename_input
                )
                if changed:
                    self._overwrite_candidate = None
                    self.error = ""
            elif request.mode == "select_directory":
                psim.TextWrapped(f"Selected folder: {self.directory}")
            else:
                count = len(self.selected)
                psim.TextUnformatted(f"Selected file{'s' if count != 1 else ''}: {count}")

            if self.error:
                psim.TextWrapped(self.error)
            accept_label = {
                "open_files": "Open files",
                "open_file": "Open file",
                "select_directory": "Select folder",
                "save_file": "Save",
            }[request.mode]
            if psim.Button(accept_label):
                outcome = self.confirm()
                if outcome is not None:
                    psim.CloseCurrentPopup()
            psim.SameLine()
            if psim.Button("Cancel"):
                outcome = self.cancel()
                psim.CloseCurrentPopup()
        finally:
            psim.EndPopup()
        return outcome

    def _matches_filter(self, path: Path) -> bool:
        request = self.request
        if request is None or not request.filters:
            return True
        patterns = request.filters[self.filter_index].patterns
        if not patterns or "*" in patterns or "*.*" in patterns:
            return True
        name = path.name.casefold()
        return any(fnmatch.fnmatch(name, pattern.casefold()) for pattern in patterns)

    def _refresh(self) -> None:
        try:
            entries = list(self.directory.iterdir())
            entries = [
                path
                for path in entries
                if (self.show_hidden or not path.name.startswith("."))
                and (path.is_dir() or self._matches_filter(path))
            ]
            self._entries = sorted(
                entries, key=lambda path: (not path.is_dir(), path.name.casefold())
            )
            self.error = ""
        except OSError as exc:
            self._entries = []
            self.error = f"Cannot read this folder: {exc}"

    def _finish(self, paths: Tuple[Path, ...]) -> FileDialogOutcome:
        resolved = tuple(path.expanduser().resolve() for path in paths)
        self._reset()
        return FileDialogOutcome(resolved)

    def _reset(self) -> None:
        self.request = None
        self.selected = []
        self.error = ""
        self._overwrite_candidate = None
        self._open_popup = False
