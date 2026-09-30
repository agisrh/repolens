"""Go (go.mod), .NET (*.csproj), and Ruby (Gemfile.lock)."""

from __future__ import annotations

import re

from repolens.extractors.deps._common import dependency
from repolens.repo import Repo


def go_mod(repo: Repo, path: str) -> dict:
    """go.mod: the module, the Go version, and every require line (// indirect is kept apart)."""
    text = repo.read(path)
    module = re.search(r"^module\s+(\S+)", text, re.M)
    go = re.search(r"^go\s+(\S+)", text, re.M)
    deps = []
    for block in re.findall(r"require\s*\((.*?)\)", text, re.S) + re.findall(
        r"^require\s+(\S+\s+\S+)", text, re.M
    ):
        for line in block.splitlines():
            parts = line.split("//")[0].split()
            if len(parts) >= 2:
                scope = "indirect" if "// indirect" in line else "runtime"
                deps.append(dependency(parts[0], parts[1], parts[1], scope))
    return {
        "ecosystem": "Go (modules)",
        "manifest": path,
        "lock": None,
        "project": module and module.group(1),
        "version": None,
        "runtime": {"go": go and go.group(1)},
        "dependencies": deps,
    }


def csproj(repo: Repo, path: str) -> dict:
    """*.csproj: PackageReference items and the target framework."""
    text = repo.read(path)
    deps = [
        dependency(m.group(1), m.group(2), m.group(2))
        for m in re.finditer(r'<PackageReference\s+Include="([^"]+)"\s+Version="([^"]+)"', text)
    ]
    fw = re.search(r"<TargetFrameworks?>([^<]+)<", text)
    return {
        "ecosystem": ".NET (NuGet)",
        "manifest": path,
        "lock": None,
        "project": None,
        "version": None,
        "runtime": {"dotnet": fw and fw.group(1)},
        "dependencies": deps,
    }


def gemfile_lock(repo: Repo, path: str) -> dict:
    """Gemfile.lock: the gems under `specs:` with their installed versions."""
    deps = []
    in_specs = False
    for line in repo.read(path).splitlines():
        if line.strip() == "specs:":
            in_specs = True
            continue
        if in_specs:
            m = re.match(r"^    ([\w\-.]+) \(([^)]+)\)$", line)
            if m:
                deps.append(dependency(m.group(1), None, m.group(2)))
            elif line and not line.startswith(" "):
                in_specs = False
    return {
        "ecosystem": "Ruby (Bundler)",
        "manifest": path,
        "lock": path,
        "project": None,
        "version": None,
        "runtime": {},
        "dependencies": deps,
    }
