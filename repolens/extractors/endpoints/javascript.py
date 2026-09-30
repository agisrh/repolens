"""Server endpoints and pages in JavaScript/TypeScript projects: Next.js, Express, React Router.

Next.js routes come from the file layout: app/**/route.ts and pages/api/** are endpoints,
app/**/page.tsx and pages/** are pages. Route groups "(name)" and parallel slots "@name"
do not appear in the URL.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from repolens.extractors.endpoints._common import FileScan, endpoint, join_paths
from repolens.repo import Repo

APP_ROUTER_MARKERS = ("/src/app/", "/app/")
PAGES_ROUTER_MARKERS = ("/src/pages/", "/pages/")
ROUTE_EXPORT = re.compile(
    r"export\s+(?:async\s+)?(?:function|const)\s+(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\b"
)
EXPRESS = re.compile(
    r"\b(app|router|server|api|route)\.(get|post|put|patch|delete|all)\(\s*['\"`](/[^'\"`]*)['\"`]"
)
REACT_ROUTE = re.compile(
    r"<Route\b[^>]*\bpath\s*=\s*[{]?['\"`]([^'\"`]+)['\"`]"  # <Route path="/x">
    r"|\bpath\s*:\s*['\"`](/[^'\"`]*)['\"`]"  # { path: "/x" }
)


# ---- Next.js ------------------------------------------------------------------------------


def nextjs(repo: Repo) -> list[dict]:
    """Endpoints and pages of both the App Router and the Pages Router."""
    out = []
    uses_next = None  # read package.json only when a pages/ file shows up
    for path in repo.files:
        normalized = "/" + path
        marker = next((m for m in APP_ROUTER_MARKERS if m in normalized), None)
        if marker:
            out += _app_router(repo, path, normalized, marker)
            continue
        marker = next((m for m in PAGES_ROUTER_MARKERS if m in normalized), None)
        if marker:
            if uses_next is None:
                uses_next = repo.exists("package.json") and '"next"' in repo.read("package.json")
            if uses_next:
                out += _pages_router(repo, path, normalized, marker)
    return out


def _route_path(relative: str) -> str:
    """URL of a file under app/: folders only, without "(group)" and "@slot" segments."""
    folders = relative.split("/")[:-1]
    visible = [
        p for p in folders if not (p.startswith("(") and p.endswith(")")) and not p.startswith("@")
    ]
    return join_paths(*visible)


def _app_router(repo: Repo, path: str, normalized: str, marker: str) -> list[dict]:
    relative = normalized.split(marker, 1)[1]
    name = relative.rsplit("/", 1)[-1]
    if re.fullmatch(r"route\.(ts|js|tsx|jsx)", name):
        methods = ROUTE_EXPORT.findall(repo.read(path)) or ["ANY"]
        route = _route_path(relative)
        return [
            endpoint("server", m, route, "route handler", path, 1, "App Router", "Next.js")
            for m in methods
        ]
    if re.fullmatch(r"page\.(tsx|jsx|ts|js|mdx)", name):
        return [
            endpoint(
                "page", "VIEW", _route_path(relative), "page", path, 1, "App Router", "Next.js"
            )
        ]
    return []


def _pages_router(repo: Repo, path: str, normalized: str, marker: str) -> list[dict]:
    relative = normalized.split(marker, 1)[1]
    if not re.search(r"\.(tsx|jsx|ts|js)$", relative):
        return []
    route = "/" + re.sub(r"(/?index)?\.(tsx|jsx|ts|js)$", "", relative) or "/"
    if relative.startswith("api/"):
        found = set(re.findall(r"req\.method\s*===?\s*['\"](\w+)['\"]", repo.read(path)))
        methods = sorted(found) or ["ANY"]
        return [
            endpoint("server", m, route, "api route", path, 1, "Pages API", "Next.js")
            for m in methods
        ]
    if PurePosixPath(relative).name.startswith("_"):  # _app.tsx, _document.tsx
        return []
    return [endpoint("page", "VIEW", route, "page", path, 1, "Pages Router", "Next.js")]


# ---- Express and React Router -------------------------------------------------------------


def express(repo: Repo) -> list[dict]:
    """app.get("/x", ...), router.post("/y", ...) in Express/Fastify-style servers."""
    out = []
    for path in repo.by_ext(".js", ".ts", ".mjs", ".cjs"):
        if "/app/" in "/" + path and path.endswith(("route.ts", "route.js")):
            continue  # Next.js route handlers
        text = repo.read(path)
        if "express" not in text and "Router(" not in text and "fastify" not in text:
            continue
        found = FileScan(path, text, "Express", group=PurePosixPath(path).name)
        for match in EXPRESS.finditer(text):
            method = match.group(2).upper().replace("ALL", "ANY")
            found.add(method, match.group(3), match.group(1), match.start())
        out += found.items
    return out


def react_routes(repo: Repo) -> list[dict]:
    """Pages from <Route path="..."> elements and { path: "..." } route objects."""
    out = []
    for path in repo.by_ext(".js", ".jsx", ".ts", ".tsx"):
        text = repo.read(path)
        if "react-router" not in text and "<Route" not in text:
            continue
        found = FileScan(path, text, "React Router", kind="page", group=PurePosixPath(path).name)
        for match in REACT_ROUTE.finditer(text):
            route = match.group(1) or match.group(2)
            found.add("VIEW", route if route.startswith("/") else "/" + route, "", match.start())
        out += found.items
    return out
