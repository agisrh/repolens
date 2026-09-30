"""Git metadata, project identity, folder tree, and language breakdown."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict

import yaml

from repolens.repo import Repo, strip_credentials

LANGUAGES = {
    ".dart": "Dart",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".php": "PHP",
    ".js": "JavaScript",
    ".jsx": "JavaScript (JSX)",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript (TSX)",
    ".py": "Python",
    ".go": "Go",
    ".rb": "Ruby",
    ".cs": "C#",
    ".swift": "Swift",
    ".m": "Objective-C",
    ".rs": "Rust",
    ".c": "C",
    ".h": "C/C++ Header",
    ".cpp": "C++",
    ".cc": "C++",
    ".scala": "Scala",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "Sass",
    ".less": "Less",
    ".sql": "SQL",
    ".sh": "Shell",
    ".groovy": "Groovy",
    ".xml": "XML",
    ".blade.php": "Blade",
}


SKELETON_NAMES = {
    "codeigniter4/framework",
    "codeigniter4/appstarter",
    "codeigniter/framework",
    "laravel/laravel",
    "laravel/lumen",
    "symfony/skeleton",
    "symfony/website-skeleton",
}


def git_info(repo: Repo) -> dict:
    if not repo.is_git:
        return {"is_git": False}
    head_tags = repo.git("tag", "--points-at", "HEAD").split()
    branch = repo.git("rev-parse", "--abbrev-ref", "HEAD")
    return {
        "is_git": True,
        "commit": repo.git("rev-parse", "HEAD"),
        "commit_short": repo.git("rev-parse", "--short", "HEAD"),
        "commit_date": repo.git("log", "-1", "--format=%cI"),
        "commit_subject": repo.git("log", "-1", "--format=%s"),
        "branch": None if branch == "HEAD" else branch,  # detached HEAD, e.g. a --ref scan of a tag
        "tags_at_head": head_tags,
        "describe": repo.git("describe", "--tags", "--always"),
        "remote": strip_credentials(repo.git("remote", "get-url", "origin")),
        "commit_count": int(repo.git("rev-list", "--count", "HEAD") or 0),
        "contributors": len(set(repo.git("log", "--format=%ae").splitlines())),
        "dirty": bool(repo.git("status", "--porcelain")),
    }


def identity(repo: Repo) -> dict:
    """Project name, version, and description from the first manifest that declares them."""
    name = version = description = None
    source = None

    def take(n, v, d, src):
        nonlocal name, version, description, source
        if n and not name:
            name, source = n, src
        if v and not version:
            version = v
        if d and not description:
            description = d

    if repo.exists("pubspec.yaml"):
        try:
            data = yaml.safe_load(repo.read("pubspec.yaml")) or {}
            take(
                data.get("name"),
                str(data.get("version") or "") or None,
                data.get("description"),
                "pubspec.yaml",
            )
        except yaml.YAMLError:
            pass
    if repo.exists("package.json"):
        try:
            data = json.loads(repo.read("package.json"))
            take(data.get("name"), data.get("version"), data.get("description"), "package.json")
        except json.JSONDecodeError:
            pass
    if repo.exists("composer.json"):
        try:
            data = json.loads(repo.read("composer.json"))
            take(data.get("name"), data.get("version"), data.get("description"), "composer.json")
        except json.JSONDecodeError:
            pass
    if repo.exists("pom.xml"):
        text = repo.read("pom.xml")
        body = re.sub(r"<parent>.*?</parent>", "", text, flags=re.S)
        body = re.sub(r"<dependencies>.*", "", body, flags=re.S)
        a = re.search(r"<artifactId>([^<]+)</artifactId>", body)
        v = re.search(r"<version>([^<]+)</version>", body)
        d = re.search(r"<description>([^<]+)</description>", body)
        take(a and a.group(1), v and v.group(1), d and d.group(1).strip(), "pom.xml")
    for gradle in ("build.gradle", "build.gradle.kts"):
        if repo.exists(gradle):
            v = re.search(r"^version\s*=?\s*['\"]([^'\"]+)['\"]", repo.read(gradle), re.M)
            take(None, v and v.group(1), None, gradle)
    if repo.exists("settings.gradle") or repo.exists("settings.gradle.kts"):
        s = repo.read("settings.gradle") or repo.read("settings.gradle.kts")
        n = re.search(r"rootProject\.name\s*=\s*['\"]([^'\"]+)['\"]", s)
        take(n and n.group(1), None, None, "settings.gradle")

    # Framework skeletons ship their own composer/package name; that is not the app's name.
    if name in SKELETON_NAMES:
        name, source = None, None
    return {
        "name": name or repo.root.name,
        "version": version,
        "description": description,
        "name_source": source or "folder",
        "folder": repo.root.name,
    }


def readme_excerpt(repo: Repo, limit: int = 6000) -> str:
    for candidate in (
        "README.md",
        "readme.md",
        "README.MD",
        "Readme.md",
        "README.rst",
        "README.txt",
        "README",
    ):
        if repo.exists(candidate):
            return repo.read(candidate)[:limit]
    return ""


def folder_tree(repo: Repo, max_depth: int = 3, max_children: int = 20) -> dict:
    """Directory tree (dirs to max_depth; files only at the root) plus per-folder file counts."""
    counts: Counter[str] = Counter()
    children: dict[str, set[str]] = defaultdict(set)
    root_files: list[str] = []
    for f in repo.files:
        parts = f.split("/")
        if len(parts) == 1:
            root_files.append(f)
        for depth in range(1, len(parts)):
            d = "/".join(parts[:depth])
            counts[d] += 1
            parent = "/".join(parts[: depth - 1])
            if depth <= max_depth:
                children[parent].add(d)

    lines = [repo.root.name + "/"]

    def walk(parent: str, prefix: str, depth: int):
        dirs = sorted(children.get(parent, ()))
        entries: list[tuple[str, bool]] = [(d, True) for d in dirs]
        if parent == "":
            entries += [(f, False) for f in root_files]
        hidden = max(0, len(entries) - max_children)
        entries = entries[:max_children]
        for i, (path, is_dir) in enumerate(entries):
            last = i == len(entries) - 1 and not hidden
            branch = "└── " if last else "├── "
            name = path.rsplit("/", 1)[-1]
            label = f"{name}/  ({counts[path]} file)" if is_dir else name
            lines.append(prefix + branch + label)
            if is_dir and depth < max_depth:
                walk(path, prefix + ("    " if last else "│   "), depth + 1)
        if hidden:
            lines.append(prefix + f"└── … (+{hidden} lainnya)")

    walk("", "", 1)
    dirs = sorted(d for d in counts if d.count("/") < 2)
    return {
        "text": "\n".join(lines),
        "max_depth": max_depth,
        "directories": [{"path": d, "files": counts[d]} for d in dirs],
        "total_files": len(repo.files),
    }


def languages(repo: Repo) -> list[dict]:
    files: Counter[str] = Counter()
    lines: Counter[str] = Counter()
    for f in repo.files:
        lang = None
        if f.endswith(".blade.php"):
            lang = "Blade"
        else:
            dot = f.rfind(".")
            if dot > f.rfind("/"):
                lang = LANGUAGES.get(f[dot:].lower())
        if not lang or "/gen/" in f or f.endswith((".g.dart", ".freezed.dart", ".min.js")):
            continue
        files[lang] += 1
        lines[lang] += repo.read(f).count("\n")
    total = sum(lines.values()) or 1
    return [
        {
            "language": lang,
            "files": files[lang],
            "lines": lines[lang],
            "percent": round(lines[lang] * 100 / total, 1),
        }
        for lang, _ in lines.most_common()
    ]
