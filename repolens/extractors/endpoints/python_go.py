"""Server endpoints in Python (FastAPI, Flask, Django) and Go (Gin, Echo, Fiber) projects."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from repolens.extractors.endpoints._common import FileScan
from repolens.repo import Repo

# @app.get("/x") (FastAPI) and @app.route("/x", methods=[...]) (Flask)
PY_DECORATOR = re.compile(
    r"@(\w+)\.(get|post|put|patch|delete|route|api_route)\(\s*['\"]([^'\"]*)['\"]([^)]*)\)"
)
DJANGO_PATH = re.compile(r"\b(?:re_)?path\(\s*r?['\"]([^'\"]*)['\"]\s*,\s*([\w.]+)")
GO_ROUTE = re.compile(
    r"\.(GET|POST|PUT|PATCH|DELETE|Get|Post|Put|Patch|Delete)\(\s*\"([^\"]+)\"\s*,\s*([\w.]+)"
)


def python(repo: Repo) -> list[dict]:
    out = []
    for path in repo.by_ext(".py"):
        text = repo.read(path)
        found = FileScan(path, text, "FastAPI", group=PurePosixPath(path).name)
        for match in PY_DECORATOR.finditer(text):
            verb = match.group(2)
            if verb in ("route", "api_route"):
                methods = re.findall(r"['\"](GET|POST|PUT|PATCH|DELETE)['\"]", match.group(4))
                methods, found.framework = methods or ["GET"], "Flask"
            else:
                methods, found.framework = [verb.upper()], "FastAPI"
            function = re.search(r"def\s+(\w+)", text[match.end() :])
            for method in methods:
                found.add(
                    method, match.group(3), function.group(1) if function else "", match.start()
                )
        if path.endswith("urls.py"):
            found.framework = "Django"
            for match in DJANGO_PATH.finditer(text):
                found.add("ANY", "/" + match.group(1), match.group(2), match.start(), group=path)
        out += found.items
    return out


def go(repo: Repo) -> list[dict]:
    out = []
    for path in repo.by_ext(".go"):
        text = repo.read(path)
        found = FileScan(path, text, "Go", group=PurePosixPath(path).name)
        for match in GO_ROUTE.finditer(text):
            found.add(match.group(1).upper(), match.group(2), match.group(3), match.start())
        out += found.items
    return out
