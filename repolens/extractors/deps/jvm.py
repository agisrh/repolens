"""Java and Kotlin: Maven pom.xml and Gradle build files.

Maven ${property} placeholders are resolved from <properties> and the parent version.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from repolens.extractors.deps._common import dependency
from repolens.i18n import t
from repolens.repo import Repo


def _without_namespaces(tree: ET.Element) -> ET.Element:
    for el in tree.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return tree


def maven_pom(repo: Repo, path: str) -> dict | None:
    """pom.xml; dependencyManagement entries are skipped (they only pin versions)."""
    try:
        root = _without_namespaces(ET.fromstring(repo.read(path)))
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
        note = (
            t("version from parent/BOM", "versi dari parent/BOM") if not v and parent_info else None
        )
        deps.append(dependency(f"{g}:{a}", v, v, scope, note))
    return {
        "ecosystem": "Java (Maven)",
        "manifest": path,
        "lock": None,
        "project": root.findtext("artifactId"),
        "version": resolve(root.findtext("version")),
        "parent": parent_info,
        "runtime": {
            "java": props.get("java.version")
            or props.get("maven.compiler.source")
            or props.get("maven.compiler.release")
        },
        "dependencies": deps,
    }


GRADLE_DEP = re.compile(
    r"^\s*(implementation|api|compileOnly|runtimeOnly|testImplementation|annotationProcessor|kapt|ksp|developmentOnly|testRuntimeOnly)"
    r"\s*\(?\s*(?:platform\()?['\"]([^'\"]+)['\"]",
    re.M,
)


def gradle(repo: Repo, path: str) -> dict | None:
    """build.gradle(.kts): dependency lines, plugins, and the Java version."""
    text = repo.read(path)
    deps = []
    for m in GRADLE_DEP.finditer(text):
        coord = m.group(2)
        parts = coord.split(":")
        name = ":".join(parts[:2]) if len(parts) >= 2 else coord
        version = parts[2] if len(parts) >= 3 else None
        scope = "dev" if m.group(1).startswith("test") else m.group(1)
        deps.append(dependency(name, version, version, scope))
    plugins = [
        {"id": m.group(1), "version": m.group(2)}
        for m in re.finditer(
            r"id\s*\(?\s*['\"]([\w.\-]+)['\"]\s*\)?\s*(?:version\s*['\"]([^'\"]+)['\"])?", text
        )
    ]
    java = re.search(
        r"(?:sourceCompatibility|languageVersion)\s*[=(]?\s*(?:JavaVersion\.VERSION_|JavaLanguageVersion\.of\()?['\"]?([\d._]+)",
        text,
    )
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
