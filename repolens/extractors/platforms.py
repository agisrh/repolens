"""Mobile platform settings (Android, iOS) and infrastructure (Docker, Compose, CI/CD)."""

from __future__ import annotations

import re

import yaml

from repolens.repo import Repo

# CI systems recognised by a single well-known file.
CI_FILES = (
    (".gitlab-ci.yml", "GitLab CI"),
    ("Jenkinsfile", "Jenkins"),
    ("bitbucket-pipelines.yml", "Bitbucket Pipelines"),
    ("azure-pipelines.yml", "Azure Pipelines"),
    (".circleci/config.yml", "CircleCI"),
    ("codemagic.yaml", "Codemagic"),
)
COMPOSE_FILES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")


# ---- mobile platforms ---------------------------------------------------------------------


def mobile_platforms(repo: Repo) -> dict:
    """{"android": {...}, "ios": {...}, "other": [...]}, with only the platforms present."""
    result = {}
    for gradle in ("android/app/build.gradle", "android/app/build.gradle.kts"):
        if repo.exists(gradle):
            result["android"] = _android(gradle, repo.read(gradle))
    project = "ios/Runner.xcodeproj/project.pbxproj"
    if repo.exists(project):
        result["ios"] = _ios(repo, project)
    for platform in ("web", "macos", "windows", "linux"):  # extra Flutter targets
        if any(f.startswith(platform + "/") for f in repo.files) and repo.exists("pubspec.yaml"):
            result.setdefault("other", []).append(platform)
    return result


def _android(file: str, text: str) -> dict:
    """Settings from android/app/build.gradle(.kts)."""
    return {
        "file": file,
        "application_id": _gradle_value(text, "applicationId"),
        "min_sdk": _gradle_value(text, "minSdk(?:Version)?"),
        "target_sdk": _gradle_value(text, "targetSdk(?:Version)?"),
        "compile_sdk": _gradle_value(text, "compileSdk(?:Version)?"),
        "flavors": _product_flavors(text),
        "jvm_target": _gradle_value(text, "jvmTarget"),
    }


def _gradle_value(text: str, key: str) -> str | None:
    """Value of a Gradle setting such as `minSdk = 21` or `targetSdkVersion 33`."""
    match = re.search(rf"{key}\s*[= ]\s*['\"]?([\w.]+)['\"]?", text)
    return match.group(1) if match else None


def _product_flavors(text: str) -> list[str]:
    """Names of the blocks directly inside `productFlavors { ... }` (Groovy or Kotlin DSL)."""
    start = re.search(r"productFlavors\s*\{", text)
    if not start:
        return []
    names = []
    depth, i = 1, start.end()
    while i < len(text) and depth:
        if text[i] == "{":
            if depth == 1:  # a flavor block opens: its name is just before the brace
                head = text[text.rfind("\n", 0, i) + 1 : i]
                name = re.search(r"(?:create\(\")?(\w+)\"?\)?\s*$", head)
                if name:
                    names.append(name.group(1))
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return names


def _ios(repo: Repo, project: str) -> dict:
    """Deployment target (the highest one set), Podfile platform, and bundle IDs."""
    text = repo.read(project)
    targets = sorted(
        set(re.findall(r"IPHONEOS_DEPLOYMENT_TARGET = ([\d.]+);", text)),
        key=lambda v: [int(x) for x in v.split(".")],
    )
    bundles = re.findall(r"PRODUCT_BUNDLE_IDENTIFIER = ([^;]+);", text)
    podfile = re.search(r"platform\s*:ios,\s*'([\d.]+)'", repo.read("ios/Podfile"))
    return {
        "file": project,
        "deployment_target": targets[-1] if targets else None,
        "podfile_platform": podfile.group(1) if podfile else None,
        "bundle_ids": sorted({b for b in bundles if "Tests" not in b}),
    }


# ---- infrastructure -----------------------------------------------------------------------


def infrastructure(repo: Repo) -> dict:
    return {
        "dockerfiles": _dockerfiles(repo),
        "compose_services": _compose_services(repo),
        "ci": _github_actions(repo) + _other_ci(repo),
    }


def _dockerfiles(repo: Repo) -> list[dict]:
    result = []
    for path in repo.glob("Dockerfile", "*/Dockerfile", "*.Dockerfile", "Dockerfile.*"):
        images = re.findall(r"^FROM\s+(\S+)", repo.read(path), re.M | re.I)
        result.append({"file": path, "base_images": images})
    return result


def _compose_services(repo: Repo) -> list[dict]:
    """Every service in docker-compose / compose files, with its image and ports."""
    services = []
    for path in repo.by_name(*COMPOSE_FILES):
        try:
            data = yaml.safe_load(repo.read(path)) or {}
        except yaml.YAMLError:
            continue
        for name, service in (data.get("services") or {}).items():
            service = service or {}
            image = service.get("image") or ("build" if service.get("build") else None)
            ports = [str(p) for p in service.get("ports") or []]
            services.append({"file": path, "service": name, "image": image, "ports": ports})
    return services


def _github_actions(repo: Repo) -> list[dict]:
    """Every GitHub Actions workflow with its name and triggers."""
    workflows = []
    for path in repo.glob(".github/workflows/*.yml", ".github/workflows/*.yaml"):
        try:
            data = yaml.safe_load(repo.read(path)) or {}
        except yaml.YAMLError:
            data = {}
        # YAML 1.1 reads the key `on:` as the boolean True.
        triggers = data.get(True) or data.get("on") or {}
        if isinstance(triggers, dict):
            names = list(triggers.keys())
        elif isinstance(triggers, str):
            names = [triggers]
        else:
            names = list(triggers)
        workflows.append(
            {
                "system": "GitHub Actions",
                "file": path,
                "name": data.get("name"),
                "triggers": [str(name) for name in names],
            }
        )
    return workflows


def _other_ci(repo: Repo) -> list[dict]:
    return [
        {"system": system, "file": name, "name": None, "triggers": []}
        for name, system in CI_FILES
        if repo.exists(name)
    ]
