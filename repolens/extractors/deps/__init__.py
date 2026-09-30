"""Dependency manifests and lock files for every common ecosystem.

Each manifest yields the declared version constraint of every dependency and, when a lock
file is present, the version actually installed. One module per ecosystem; a reader takes
(repo, path) and returns a manifest dict, or None when the file cannot be read.

To support another ecosystem, add a reader and list its file name in READERS below.
"""

from __future__ import annotations

from repolens.extractors.deps.dart import pubspec
from repolens.extractors.deps.jvm import gradle, maven_pom
from repolens.extractors.deps.node import package_json
from repolens.extractors.deps.other import csproj, gemfile_lock, go_mod
from repolens.extractors.deps.php import composer
from repolens.extractors.deps.python import pyproject, requirements_txt
from repolens.repo import Repo

# manifest file name -> reader, in the order manifests are listed
READERS = [
    ("pubspec.yaml", pubspec),
    ("package.json", package_json),
    ("composer.json", composer),
    ("pom.xml", maven_pom),
    ("build.gradle", gradle),
    ("build.gradle.kts", gradle),
    ("go.mod", go_mod),
    ("requirements.txt", requirements_txt),
    ("pyproject.toml", pyproject),
    ("Gemfile.lock", gemfile_lock),
]


def extract(repo: Repo) -> list[dict]:
    """Every recognised manifest that lists dependencies (or at least a project name)."""
    manifests = []
    for filename, read in READERS:
        for path in repo.by_name(filename):
            # Flutter's android/ and ios/ Gradle files are platform shells, reported under
            # platforms rather than as a separate set of dependencies.
            if (
                filename.startswith("build.gradle")
                and path.split("/")[0] in ("android", "ios")
                and repo.exists("pubspec.yaml")
            ):
                continue
            result = read(repo, path)
            if result and (
                result["dependencies"] or result.get("project") or result.get("plugins")
            ):
                manifests.append(result)
    for path in repo.by_ext(".csproj"):
        manifests.append(csproj(repo, path))
    return manifests
