"""PHP: composer.json, with resolved versions from composer.lock."""

from __future__ import annotations

import json

from repolens.extractors.deps._common import dependency, folder_of, sibling
from repolens.repo import Repo


def composer(repo: Repo, path: str) -> dict | None:
    """composer.json; `resolved` versions come from composer.lock.

    The `php` requirement is reported as the runtime, and ext-* requirements are skipped."""
    try:
        data = json.loads(repo.read(path))
    except json.JSONDecodeError:
        return None
    lock_path = sibling(folder_of(path), "composer.lock")
    resolved = {}
    if repo.exists(lock_path):
        try:
            lock = json.loads(repo.read(lock_path))
            for pkg in (lock.get("packages") or []) + (lock.get("packages-dev") or []):
                resolved[pkg.get("name")] = str(pkg.get("version", "")).lstrip("v")
        except json.JSONDecodeError:
            pass
    deps = []
    php = None
    for section, scope in (("require", "runtime"), ("require-dev", "dev")):
        for name, declared in (data.get(section) or {}).items():
            if name == "php":
                php = declared
                continue
            if name.startswith("ext-"):
                continue
            deps.append(dependency(name, declared, resolved.get(name), scope))
    return {
        "ecosystem": "PHP (Composer)",
        "manifest": path,
        "lock": lock_path if resolved else None,
        "project": data.get("name"),
        "version": data.get("version"),
        "runtime": {"php": php},
        "dependencies": deps,
    }
