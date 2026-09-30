"""Read-only view of a repository on disk: file listing, safe text reads, git metadata."""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from functools import cached_property
from pathlib import Path

from repolens.i18n import t

# Directories that never hold hand-written source worth documenting.
IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "vendor",
    "build",
    "dist",
    "out",
    "target",
    ".dart_tool",
    ".pub-cache",
    ".fvm",
    ".gradle",
    ".idea",
    ".vscode",
    ".next",
    ".nuxt",
    ".svelte-kit",
    "coverage",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".tox",
    "Pods",
    ".symlinks",
    "obj",
    ".terraform",
    ".cache",
    ".turbo",
    ".expo",
    "DerivedData",
    ".ruby-lsp",
    ".kotlin",
    ".plugin_symlinks",
    "ephemeral",
    "xcuserdata",
}

MAX_READ_BYTES = 1_500_000


class Repo:
    def __init__(self, root: str | Path, ignore: list[str] = (), use_git: bool = True):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise FileNotFoundError(
                t("Folder not found: ", "Folder tidak ditemukan: ") + str(self.root)
            )
        # use_git=False: read the folder as plain files on disk (no .gitignore, no git metadata).
        self.use_git = use_git
        # Extra glob patterns to exclude (from .repolens.yml `ignore`). A bare folder name
        # matches the whole folder.
        self.ignore = [p.rstrip("/") for p in ignore]

    def _ignored(self, rel: str) -> bool:
        return any(fnmatch.fnmatch(rel, p) or rel.startswith(p + "/") for p in self.ignore)

    @cached_property
    def files(self) -> list[str]:
        """All files (POSIX paths relative to root), excluding ignored directories.

        In a git repository this follows .gitignore (tracked + untracked-but-not-ignored files),
        so local build output and generated folders never leak into the document. Without git
        (or with use_git=False) every file on disk is listed, minus IGNORE_DIRS and `ignore`.
        """
        if self.is_git:
            listed = self.git("ls-files", "--cached", "--others", "--exclude-standard", "-z")
            if listed:
                keep = []
                for f in listed.split("\0"):
                    if not f or any(part in IGNORE_DIRS for part in f.split("/")[:-1]):
                        continue
                    if (self.root / f).is_file() and not self._ignored(f):
                        keep.append(f)
                return sorted(keep)
        result: list[str] = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(
                d for d in dirnames if d not in IGNORE_DIRS and not d.endswith(".egg-info")
            )
            rel_dir = Path(dirpath).relative_to(self.root)
            for name in sorted(filenames):
                rel = (rel_dir / name).as_posix()
                if not self._ignored(rel):
                    result.append(rel)
        return result

    @cached_property
    def file_set(self) -> set[str]:
        return set(self.files)

    def exists(self, rel: str) -> bool:
        return rel in self.file_set

    def glob(self, *patterns: str) -> list[str]:
        return [f for f in self.files if any(fnmatch.fnmatch(f, p) for p in patterns)]

    def by_name(self, *names: str) -> list[str]:
        wanted = set(names)
        return [f for f in self.files if f.rsplit("/", 1)[-1] in wanted]

    def by_ext(self, *exts: str) -> list[str]:
        return [f for f in self.files if f.endswith(exts)]

    def read(self, rel: str) -> str:
        path = self.root / rel
        try:
            if path.stat().st_size > MAX_READ_BYTES:
                return ""
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    # ---- git -------------------------------------------------------------

    def git(self, *args: str) -> str:
        try:
            out = subprocess.run(
                ["git", *args],
                cwd=self.root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return out.stdout.strip() if out.returncode == 0 else ""

    @cached_property
    def is_git(self) -> bool:
        return self.use_git and self.git("rev-parse", "--is-inside-work-tree") == "true"

    @cached_property
    def tracked_files(self) -> set[str]:
        if not self.is_git:
            return set()
        # -z: without it git quotes non-ASCII paths ("\303\251"), which then never match repo.files.
        return {f for f in self.git("ls-files", "-z").split("\0") if f}


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def strip_credentials(url: str) -> str:
    """Remove user:token@ from remote URLs so tokens never reach the document."""
    return re.sub(r"(//)[^/@\s]+@", r"\1", url)
