"""Python: requirements.txt and pyproject.toml (PEP 621 [project] and Poetry)."""

from __future__ import annotations

import json
import re

from repolens.extractors.deps._common import dependency
from repolens.repo import Repo


def requirements_txt(repo: Repo, path: str) -> dict:
    """requirements.txt; an exact pin (==1.2.3) also counts as the resolved version."""
    deps = []
    for line in repo.read(path).splitlines():
        line = line.split("#")[0].strip()
        if not line or line.startswith(("-", "git+")):
            continue
        m = re.match(r"([A-Za-z0-9_.\-\[\]]+)\s*(.*)", line)
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
        try:
            import tomllib
        except ModuleNotFoundError:  # Python 3.10
            import tomli as tomllib
        data = tomllib.loads(repo.read(path))
    except Exception:
        return None
    project = data.get("project") or {}
    poetry = (data.get("tool") or {}).get("poetry") or {}
    deps = []
    for spec in project.get("dependencies") or []:
        m = re.match(r"([A-Za-z0-9_.\-\[\]]+)\s*(.*)", spec)
        if m:
            deps.append(dependency(m.group(1), m.group(2) or None))
    for name, spec in (poetry.get("dependencies") or {}).items():
        if name != "python":
            deps.append(dependency(name, spec if isinstance(spec, str) else json.dumps(spec)))
    if not deps and not project and not poetry:
        return None
    python = project.get("requires-python") or (poetry.get("dependencies") or {}).get("python")
    return {
        "ecosystem": "Python (pyproject)",
        "manifest": path,
        "lock": None,
        "project": project.get("name") or poetry.get("name"),
        "version": project.get("version") or poetry.get("version"),
        "runtime": {"python": python},
        "dependencies": deps,
    }
