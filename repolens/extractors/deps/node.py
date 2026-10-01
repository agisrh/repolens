"""Node.js: package.json, with installed versions from package-lock.json, yarn.lock,
or pnpm-lock.yaml."""

from __future__ import annotations

import json
import re

import yaml

from repolens.extractors.deps._common import dependency, folder_of, sibling
from repolens.repo import Repo


def _npm_lock_versions(repo: Repo, folder: str) -> tuple[str | None, dict]:
    """(lock file, {package: installed version}) from the first lock file found next to
    package.json, else at the repository root (npm, yarn, pnpm, and bun workspaces keep one
    lock file there for every member); (None, {}) without one."""
    for where in dict.fromkeys([folder, ""]):
        for name, read in LOCK_READERS:
            lock = sibling(where, name)
            if repo.exists(lock):
                # The member path only matters for a lock file shared from the root.
                return lock, read(repo.read(lock), folder if where != folder else "")
    return None, {}


def _package_lock(text: str, member: str = "") -> dict:
    """package-lock.json: v2/v3 "packages" (top level only), then v1 "dependencies"."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = {}
    versions = {}
    for key, info in (data.get("packages") or {}).items():
        if key.startswith("node_modules/") and key.count("node_modules/") == 1:
            versions[key[len("node_modules/") :]] = info.get("version")
    for name, info in (data.get("dependencies") or {}).items():
        versions.setdefault(name, info.get("version"))
    return versions


def _yarn_lock(text: str, member: str = "") -> dict:
    """yarn.lock: a `"name@range", "name@range2":` header line, then `version "1.2.3"`."""
    versions = {}
    current: list[str] = []  # package names of the entry being read
    for line in text.splitlines():
        if line and not line.startswith((" ", "#")):
            current = []
            for spec in line.rstrip(":").split(","):
                spec = spec.strip().strip('"')
                at = spec.rfind("@")  # the last @: scoped names start with one too
                if at > 0:
                    current.append(spec[:at])
        else:
            match = re.match(r'\s+version:?\s+"?([^"\s]+)"?', line)
            if match and current:
                for name in current:
                    versions.setdefault(name, match.group(1))
                current = []
    return versions


def _pnpm_lock(text: str, member: str = "") -> dict:
    """pnpm-lock.yaml: the dependencies of the importer for this package.json (its folder,
    "." at the root), "1.2.3(peer@4)" -> "1.2.3"."""
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        data = {}
    importer = (data.get("importers") or {}).get(member or ".") or data
    versions = {}
    for section in ("dependencies", "devDependencies"):
        for name, info in (importer.get(section) or {}).items():
            version = info.get("version") if isinstance(info, dict) else info
            versions[name] = str(version).split("(")[0] if version else None
    return versions


def _bun_lock(text: str, member: str = "") -> dict:
    """bun.lock: JSON with trailing commas; "packages" maps a name to ["name@version", ...].
    Nested entries ("parent/child") are other copies of a package and are skipped."""
    try:
        data = json.loads(re.sub(r",(\s*[}\]])", r"\1", text))
    except json.JSONDecodeError:
        return {}
    versions = {}
    for key, entry in (data.get("packages") or {}).items():
        spec = entry[0] if isinstance(entry, list) and entry else ""
        at = spec.rfind("@")  # the last @: scoped names start with one too
        if at > 0 and spec[:at] == key:
            versions[key] = spec[at + 1 :]
    return versions


LOCK_READERS = [
    ("package-lock.json", _package_lock),
    ("yarn.lock", _yarn_lock),
    ("pnpm-lock.yaml", _pnpm_lock),
    ("bun.lock", _bun_lock),
]


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
