"""Dependency manifests and lock files for every common ecosystem.

Each manifest yields the declared version constraint and, when a lock file is
present, the version actually resolved.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath

import yaml

from repolens.i18n import t
from repolens.repo import Repo


def _dir(path: str) -> str:
    parent = str(PurePosixPath(path).parent)
    return "" if parent == "." else parent


def _join(d: str, name: str) -> str:
    return f"{d}/{name}" if d else name


def _dep(name, declared=None, resolved=None, scope="runtime", source=None):
    return {"name": name, "declared": declared, "resolved": resolved, "scope": scope, "source": source}


# ---- Dart / Flutter ---------------------------------------------------------

def _pubspec(repo: Repo, path: str) -> dict | None:
    try:
        data = yaml.safe_load(repo.read(path)) or {}
    except yaml.YAMLError:
        return None
    lock_path = _join(_dir(path), "pubspec.lock")
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
                return None, f"git: {re.sub(r'//[^/@]+@', '//', str(url))}" + (f" @ {ref}" if ref else "")
            if "version" in spec:
                return str(spec["version"]), None
        return (str(spec) if spec is not None else None), None

    deps = []
    for section, scope in (("dependencies", "runtime"), ("dev_dependencies", "dev"), ("dependency_overrides", "override")):
        for name, spec in (data.get(section) or {}).items():
            declared, src = describe(spec)
            if name == "flutter" and src and src.startswith("sdk"):
                continue
            resolved = (packages.get(name) or {}).get("version")
            deps.append(_dep(name, declared, resolved, scope, src))
    return {
        "ecosystem": "Dart (pub)",
        "manifest": path,
        "lock": lock_path if lock else None,
        "project": data.get("name"),
        "version": str(data.get("version")) if data.get("version") is not None else None,
        "runtime": {"dart_sdk": (data.get("environment") or {}).get("sdk"),
                    "flutter_sdk_locked": (lock.get("sdks") or {}).get("flutter")},
        "dependencies": deps,
    }


# ---- JavaScript / TypeScript ----------------------------------------------

def _npm_resolved(repo: Repo, d: str) -> tuple[str | None, dict]:
    lock = _join(d, "package-lock.json")
    if repo.exists(lock):
        try:
            data = json.loads(repo.read(lock))
        except json.JSONDecodeError:
            data = {}
        resolved = {}
        for key, info in (data.get("packages") or {}).items():
            if key.startswith("node_modules/") and key.count("node_modules/") == 1:
                resolved[key[len("node_modules/"):]] = info.get("version")
        for name, info in (data.get("dependencies") or {}).items():
            resolved.setdefault(name, info.get("version"))
        return lock, resolved
    lock = _join(d, "yarn.lock")
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
    lock = _join(d, "pnpm-lock.yaml")
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


def _package_json(repo: Repo, path: str) -> dict | None:
    try:
        data = json.loads(repo.read(path))
    except json.JSONDecodeError:
        return None
    lock, resolved = _npm_resolved(repo, _dir(path))
    deps = []
    for section, scope in (("dependencies", "runtime"), ("devDependencies", "dev"), ("peerDependencies", "peer")):
        for name, declared in (data.get(section) or {}).items():
            deps.append(_dep(name, declared, resolved.get(name), scope))
    return {
        "ecosystem": "Node.js (npm)",
        "manifest": path,
        "lock": lock,
        "project": data.get("name"),
        "version": data.get("version"),
        "runtime": {"node": (data.get("engines") or {}).get("node"),
                    "package_manager": data.get("packageManager")},
        "scripts": data.get("scripts") or {},
        "dependencies": deps,
    }


# ---- PHP --------------------------------------------------------------------

def _composer(repo: Repo, path: str) -> dict | None:
    try:
        data = json.loads(repo.read(path))
    except json.JSONDecodeError:
        return None
    lock_path = _join(_dir(path), "composer.lock")
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
            deps.append(_dep(name, declared, resolved.get(name), scope))
    return {
        "ecosystem": "PHP (Composer)",
        "manifest": path,
        "lock": lock_path if resolved else None,
        "project": data.get("name"),
        "version": data.get("version"),
        "runtime": {"php": php},
        "dependencies": deps,
    }


# ---- Java / Kotlin ----------------------------------------------------------

def _strip_ns(tree: ET.Element) -> ET.Element:
    for el in tree.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return tree


def _pom(repo: Repo, path: str) -> dict | None:
    try:
        root = _strip_ns(ET.fromstring(repo.read(path)))
    except ET.ParseError:
        return None
    props = {}
    p = root.find("properties")
    if p is not None:
        for child in p:
            props[child.tag] = (child.text or "").strip()
    parent = root.find("parent")
    parent_info = None
    if parent is not None:
        parent_info = {
            "group": parent.findtext("groupId"),
            "artifact": parent.findtext("artifactId"),
            "version": parent.findtext("version"),
        }
    props.setdefault("project.version", root.findtext("version") or "")
    if parent_info and parent_info["version"]:
        props.setdefault("project.parent.version", parent_info["version"])

    def resolve(value):
        if not value:
            return value
        return re.sub(r"\$\{([^}]+)\}", lambda m: props.get(m.group(1), m.group(0)), value)

    deps = []
    managed = root.find("dependencyManagement")
    managed_ids = set()
    if managed is not None:
        for d in managed.iter("dependency"):
            managed_ids.add(id(d))
    for d in root.iter("dependency"):
        if id(d) in managed_ids:
            continue
        g, a = d.findtext("groupId"), d.findtext("artifactId")
        v = resolve(d.findtext("version"))
        scope = d.findtext("scope") or "runtime"
        note = t("version from parent/BOM", "versi dari parent/BOM") if not v and parent_info else None
        deps.append(_dep(f"{g}:{a}", v, v, scope, note))
    return {
        "ecosystem": "Java (Maven)",
        "manifest": path,
        "lock": None,
        "project": root.findtext("artifactId"),
        "version": resolve(root.findtext("version")),
        "parent": parent_info,
        "runtime": {"java": props.get("java.version") or props.get("maven.compiler.source")
                    or props.get("maven.compiler.release")},
        "dependencies": deps,
    }


GRADLE_DEP = re.compile(
    r"^\s*(implementation|api|compileOnly|runtimeOnly|testImplementation|annotationProcessor|kapt|ksp|developmentOnly|testRuntimeOnly)"
    r"\s*\(?\s*(?:platform\()?['\"]([^'\"]+)['\"]",
    re.M,
)


def _gradle(repo: Repo, path: str) -> dict | None:
    text = repo.read(path)
    deps = []
    for m in GRADLE_DEP.finditer(text):
        coord = m.group(2)
        parts = coord.split(":")
        name = ":".join(parts[:2]) if len(parts) >= 2 else coord
        version = parts[2] if len(parts) >= 3 else None
        scope = "dev" if m.group(1).startswith("test") else m.group(1)
        deps.append(_dep(name, version, version, scope))
    plugins = [
        {"id": m.group(1), "version": m.group(2)}
        for m in re.finditer(r"id\s*\(?\s*['\"]([\w.\-]+)['\"]\s*\)?\s*(?:version\s*['\"]([^'\"]+)['\"])?", text)
    ]
    java = re.search(r"(?:sourceCompatibility|languageVersion)\s*[=(]?\s*(?:JavaVersion\.VERSION_|JavaLanguageVersion\.of\()?['\"]?([\d._]+)", text)
    if not deps and not plugins:
        return None
    return {
        "ecosystem": "Java/Kotlin (Gradle)",
        "manifest": path,
        "lock": None,
        "project": None,
        "version": None,
        "plugins": plugins,
        "runtime": {"java": java.group(1).replace("_", ".") if java else None},
        "dependencies": deps,
    }


# ---- Others -----------------------------------------------------------------

def _go_mod(repo: Repo, path: str) -> dict:
    text = repo.read(path)
    module = re.search(r"^module\s+(\S+)", text, re.M)
    go = re.search(r"^go\s+(\S+)", text, re.M)
    deps = []
    for block in re.findall(r"require\s*\((.*?)\)", text, re.S) + re.findall(r"^require\s+(\S+\s+\S+)", text, re.M):
        for line in block.splitlines():
            parts = line.split("//")[0].split()
            if len(parts) >= 2:
                scope = "indirect" if "// indirect" in line else "runtime"
                deps.append(_dep(parts[0], parts[1], parts[1], scope))
    return {"ecosystem": "Go (modules)", "manifest": path, "lock": None,
            "project": module and module.group(1), "version": None,
            "runtime": {"go": go and go.group(1)}, "dependencies": deps}


def _requirements(repo: Repo, path: str) -> dict:
    deps = []
    for line in repo.read(path).splitlines():
        line = line.split("#")[0].strip()
        if not line or line.startswith(("-", "git+")):
            continue
        m = re.match(r"([A-Za-z0-9_.\-\[\]]+)\s*(.*)", line)
        if m:
            spec = m.group(2).strip() or None
            pinned = spec[2:] if spec and spec.startswith("==") else None
            deps.append(_dep(m.group(1), spec, pinned))
    return {"ecosystem": "Python (pip)", "manifest": path, "lock": None, "project": None,
            "version": None, "runtime": {}, "dependencies": deps}


def _pyproject(repo: Repo, path: str) -> dict | None:
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
            deps.append(_dep(m.group(1), m.group(2) or None))
    for name, spec in (poetry.get("dependencies") or {}).items():
        if name != "python":
            deps.append(_dep(name, spec if isinstance(spec, str) else json.dumps(spec)))
    if not deps and not project and not poetry:
        return None
    python = project.get("requires-python") or (poetry.get("dependencies") or {}).get("python")
    return {"ecosystem": "Python (pyproject)", "manifest": path, "lock": None,
            "project": project.get("name") or poetry.get("name"),
            "version": project.get("version") or poetry.get("version"),
            "runtime": {"python": python}, "dependencies": deps}


def _csproj(repo: Repo, path: str) -> dict:
    text = repo.read(path)
    deps = [
        _dep(m.group(1), m.group(2), m.group(2))
        for m in re.finditer(r'<PackageReference\s+Include="([^"]+)"\s+Version="([^"]+)"', text)
    ]
    fw = re.search(r"<TargetFrameworks?>([^<]+)<", text)
    return {"ecosystem": ".NET (NuGet)", "manifest": path, "lock": None, "project": None,
            "version": None, "runtime": {"dotnet": fw and fw.group(1)}, "dependencies": deps}


def _gemfile_lock(repo: Repo, path: str) -> dict:
    deps = []
    in_specs = False
    for line in repo.read(path).splitlines():
        if line.strip() == "specs:":
            in_specs = True
            continue
        if in_specs:
            m = re.match(r"^    ([\w\-.]+) \(([^)]+)\)$", line)
            if m:
                deps.append(_dep(m.group(1), None, m.group(2)))
            elif line and not line.startswith(" "):
                in_specs = False
    return {"ecosystem": "Ruby (Bundler)", "manifest": path, "lock": path, "project": None,
            "version": None, "runtime": {}, "dependencies": deps}


def extract(repo: Repo) -> list[dict]:
    handlers = [
        ("pubspec.yaml", _pubspec), ("package.json", _package_json), ("composer.json", _composer),
        ("pom.xml", _pom), ("build.gradle", _gradle), ("build.gradle.kts", _gradle),
        ("go.mod", _go_mod), ("requirements.txt", _requirements), ("pyproject.toml", _pyproject),
        ("Gemfile.lock", _gemfile_lock),
    ]
    manifests = []
    for filename, handler in handlers:
        for path in repo.by_name(filename):
            # Skip platform shells generated by frameworks (e.g. Flutter's android/ gradle files
            # are reported under platforms, not as a separate dependency set).
            if filename.startswith("build.gradle") and path.split("/")[0] in ("android", "ios") and repo.exists("pubspec.yaml"):
                continue
            result = handler(repo, path)
            if result and (result["dependencies"] or result.get("project") or result.get("plugins")):
                manifests.append(result)
    for path in repo.by_ext(".csproj"):
        manifests.append(_csproj(repo, path))
    return manifests
