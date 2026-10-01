"""Python: requirements.txt and pyproject.toml (PEP 621 [project] and Poetry).

Installed versions come from uv.lock or poetry.lock, next to the manifest or at the
repository root (a uv workspace keeps one lock file for all its members). Package names
are compared in their normalised form (PEP 503), so `Django` matches `django`.
"""

from __future__ import annotations

import json
import re

from repolens.extractors.deps._common import dependency, folder_of, sibling
from repolens.repo import Repo

# A PEP 508 requirement: the name, optional [extras], then the version constraint.
REQUIREMENT = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(.*)")
LOCK_FILES = ("uv.lock", "poetry.lock")


def normalized(name: str) -> str:
    """PEP 503 name: "Flask_SQLAlchemy" -> "flask-sqlalchemy"."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _lock_versions(repo: Repo, path: str) -> tuple[str | None, dict]:
    """(lock file, {normalised name: version}) from uv.lock / poetry.lock beside the manifest,
    else at the repository root; (None, {}) without one."""
    for folder in dict.fromkeys([folder_of(path), ""]):
        for name in LOCK_FILES:
            lock = sibling(folder, name)
            if repo.exists(lock):
                return lock, _read_lock(repo.read(lock))
    return None, {}


def _read_lock(text: str) -> dict:
    """Both uv.lock and poetry.lock are TOML with a [[package]] list of name/version."""
    try:
        data = _toml().loads(text)
    except Exception:
        return {}
    return {
        normalized(str(p["name"])): str(p["version"])
        for p in data.get("package") or []
        if p.get("name") and p.get("version")
    }


def _toml():
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib
    return tomllib


def requirements_txt(repo: Repo, path: str) -> dict:
    """requirements.txt; an exact pin (==1.2.3) also counts as the resolved version."""
    deps = []
    for line in repo.read(path).splitlines():
        line = line.split("#")[0].strip()
        if not line or line.startswith(("-", "git+")):
            continue
        m = REQUIREMENT.match(line)
        if m:
            spec = m.group(2).strip() or None
            pinned = spec[2:] if spec and spec.startswith("==") else None
            deps.append(dependency(m.group(1), spec, pinned))
    return {
        "ecosystem": "Python (pip)",
        "manifest": path,
        "lock": None,
        "project": None,
        "version": None,
        "runtime": {},
        "dependencies": deps,
    }


def pyproject(repo: Repo, path: str) -> dict | None:
    """pyproject.toml: PEP 621 [project] dependencies and Poetry's [tool.poetry]."""
    try:
        data = _toml().loads(repo.read(path))
    except Exception:
        return None
    project = data.get("project") or {}
    poetry = (data.get("tool") or {}).get("poetry") or {}
    lock, installed = _lock_versions(repo, path)
    deps = []
    for spec in project.get("dependencies") or []:
        m = REQUIREMENT.match(spec)
        if m:
            name = m.group(1)
            deps.append(dependency(name, m.group(2) or None, installed.get(normalized(name))))
    for name, spec in (poetry.get("dependencies") or {}).items():
        if name != "python":
            declared = spec if isinstance(spec, str) else json.dumps(spec)
            deps.append(dependency(name, declared, installed.get(normalized(name))))
    if not deps and not project and not poetry:
        return None
    python = project.get("requires-python") or (poetry.get("dependencies") or {}).get("python")
    return {
        "ecosystem": "Python (pyproject)",
        "manifest": path,
        "lock": lock,
        "project": project.get("name") or poetry.get("name"),
        "version": project.get("version") or poetry.get("version"),
        "runtime": {"python": python},
        "dependencies": deps,
    }
