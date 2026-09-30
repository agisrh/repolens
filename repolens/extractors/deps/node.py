"""Node.js: package.json, with installed versions from package-lock.json, yarn.lock,
or pnpm-lock.yaml."""

from __future__ import annotations

import json
import re

import yaml

from repolens.extractors.deps._common import dependency, folder_of, sibling
from repolens.repo import Repo


def _npm_lock_versions(repo: Repo, d: str) -> tuple[str | None, dict]:
    """(lock file, {package: installed version}) from package-lock.json, yarn.lock,
    or pnpm-lock.yaml; (None, {}) without a lock file."""
    lock = sibling(d, "package-lock.json")
    if repo.exists(lock):
        try:
            data = json.loads(repo.read(lock))
        except json.JSONDecodeError:
            data = {}
        resolved = {}
        for key, info in (data.get("packages") or {}).items():
            if key.startswith("node_modules/") and key.count("node_modules/") == 1:
                resolved[key[len("node_modules/") :]] = info.get("version")
        for name, info in (data.get("dependencies") or {}).items():
            resolved.setdefault(name, info.get("version"))
        return lock, resolved
    lock = sibling(d, "yarn.lock")
    if repo.exists(lock):
        resolved = {}
        current: list[str] = []
        for line in repo.read(lock).splitlines():
            if line and not line.startswith((" ", "#")):
                current = []
                for spec in line.rstrip(":").split(","):
                    spec = spec.strip().strip('"')
                    at = spec.rfind("@")
                    if at > 0:
                        current.append(spec[:at])
            else:
                m = re.match(r'\s+version:?\s+"?([^"\s]+)"?', line)
                if m and current:
                    for n in current:
                        resolved.setdefault(n, m.group(1))
                    current = []
        return lock, resolved
    lock = sibling(d, "pnpm-lock.yaml")
    if repo.exists(lock):
        try:
            data = yaml.safe_load(repo.read(lock)) or {}
        except yaml.YAMLError:
            data = {}
        resolved = {}
        importer = (data.get("importers") or {}).get(".") or data
        for section in ("dependencies", "devDependencies"):
            for name, info in (importer.get(section) or {}).items():
                v = info.get("version") if isinstance(info, dict) else info
                resolved[name] = str(v).split("(")[0] if v else None
        return lock, resolved
    return None, {}


def package_json(repo: Repo, path: str) -> dict | None:
    """package.json; `resolved` versions come from the lock file next to it."""
    try:
        data = json.loads(repo.read(path))
    except json.JSONDecodeError:
        return None
    lock, resolved = _npm_lock_versions(repo, folder_of(path))
    deps = []
    for section, scope in (
        ("dependencies", "runtime"),
        ("devDependencies", "dev"),
        ("peerDependencies", "peer"),
    ):
        for name, declared in (data.get(section) or {}).items():
            deps.append(dependency(name, declared, resolved.get(name), scope))
    return {
        "ecosystem": "Node.js (npm)",
        "manifest": path,
        "lock": lock,
        "project": data.get("name"),
        "version": data.get("version"),
        "runtime": {
            "node": (data.get("engines") or {}).get("node"),
            "package_manager": data.get("packageManager"),
        },
        "scripts": data.get("scripts") or {},
        "dependencies": deps,
    }
