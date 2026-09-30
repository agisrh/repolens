"""Shapes and path helpers shared by the manifest readers."""

from __future__ import annotations

from pathlib import PurePosixPath


def dependency(name, declared=None, resolved=None, scope="runtime", source=None) -> dict:
    """One dependency: the declared constraint and, when a lock file says, the resolved version."""
    return {
        "name": name,
        "declared": declared,
        "resolved": resolved,
        "scope": scope,
        "source": source,
    }


def folder_of(path: str) -> str:
    """Folder of a path: "app/package.json" -> "app", "package.json" -> "" (the root)."""
    parent = str(PurePosixPath(path).parent)
    return "" if parent == "." else parent


def sibling(folder: str, name: str) -> str:
    """Path of `name` in `folder` (the repository root when folder is "")."""
    return f"{folder}/{name}" if folder else name
