"""Dart and Flutter: pubspec.yaml, with resolved versions from pubspec.lock."""

from __future__ import annotations

import re

import yaml

from repolens.extractors.deps._common import dependency, folder_of, sibling
from repolens.repo import Repo


def pubspec(repo: Repo, path: str) -> dict | None:
    """pubspec.yaml; `resolved` versions come from pubspec.lock next to it."""
    try:
        data = yaml.safe_load(repo.read(path)) or {}
    except yaml.YAMLError:
        return None
    lock_path = sibling(folder_of(path), "pubspec.lock")
    lock = {}
    if repo.exists(lock_path):
        try:
            lock = yaml.safe_load(repo.read(lock_path)) or {}
        except yaml.YAMLError:
            lock = {}
    packages = lock.get("packages") or {}

    def describe(spec):
        if isinstance(spec, dict):
            if "sdk" in spec:
                return None, f"sdk: {spec['sdk']}"
            if "path" in spec:
                return None, f"path: {spec['path']}"
            if "git" in spec:
                git = spec["git"]
                url = git.get("url") if isinstance(git, dict) else git
                ref = git.get("ref") if isinstance(git, dict) else None
                return None, f"git: {re.sub(r'//[^/@]+@', '//', str(url))}" + (
                    f" @ {ref}" if ref else ""
                )
            if "version" in spec:
                return str(spec["version"]), None
        return (str(spec) if spec is not None else None), None

    deps = []
    for section, scope in (
        ("dependencies", "runtime"),
        ("dev_dependencies", "dev"),
        ("dependency_overrides", "override"),
    ):
        for name, spec in (data.get(section) or {}).items():
            declared, src = describe(spec)
            if name == "flutter" and src and src.startswith("sdk"):
                continue
            resolved = (packages.get(name) or {}).get("version")
            deps.append(dependency(name, declared, resolved, scope, src))
    return {
        "ecosystem": "Dart (pub)",
        "manifest": path,
        "lock": lock_path if lock else None,
        "project": data.get("name"),
        "version": str(data.get("version")) if data.get("version") is not None else None,
        "runtime": {
            "dart_sdk": (data.get("environment") or {}).get("sdk"),
            "flutter_sdk_locked": (lock.get("sdks") or {}).get("flutter"),
        },
        "dependencies": deps,
    }
