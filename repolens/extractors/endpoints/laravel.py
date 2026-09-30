"""Laravel routes from routes/*.php (and extra route files listed in .repolens.yml).

Understands Route::get/post/..., Route::match([...]), Route::any, prefix groups
(`Route::prefix('x')->group(...)` and `Route::group(['prefix' => 'x'], ...)`), and
Route::resource / Route::apiResource, which expand into their standard actions.
Routes in routes/api.php get Laravel's automatic /api prefix.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from repolens.extractors.endpoints._common import (
    FileScan,
    balanced,
    block_end,
    join_paths,
    php_handler,
    prefix_at,
    strings,
)
from repolens.repo import Repo

ROUTE = re.compile(r"Route::(get|post|put|patch|delete|options|any|match)\s*\(")
RESOURCE = re.compile(r"Route::(apiResource|resource)\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*([^)]+)\)")
GROUP = re.compile(
    r"(?:Route::prefix\(\s*['\"]([^'\"]*)['\"]\s*\)(?:->\w+\([^)]*\))*->group\s*\(|"
    r"Route::group\s*\(\s*\[[^\]]*['\"]prefix['\"]\s*=>\s*['\"]([^'\"]*)['\"])"
)


def laravel(repo: Repo, extra: list[str] = ()) -> list[dict]:
    """Routes from routes/*.php and from extra route files that use Route::."""
    out = []
    files = repo.glob("routes/*.php") + [f for f in extra if "Route::" in repo.read(f)]
    for path in dict.fromkeys(files):
        text = repo.read(path)
        base = "/api" if path.endswith("routes/api.php") else ""
        spans = _groups(text)
        found = FileScan(path, text, "Laravel", group=PurePosixPath(path).name)
        _routes(found, text, base, spans)
        _resources(found, text, base, spans)
        out += found.items
    return out


def _groups(text: str) -> list[tuple[int, int, str]]:
    """(start, end, prefix) of every prefix group block."""
    spans = []
    for match in GROUP.finditer(text):
        prefix = match.group(1) if match.group(1) is not None else match.group(2)
        brace = text.find("{", match.end())
        if brace >= 0:
            spans.append((brace, block_end(text, brace), prefix))
    return spans


def _routes(found: FileScan, text: str, base: str, spans) -> None:
    """Route::get('uri', handler), Route::match(['get', 'post'], 'uri', handler), ..."""
    for match in ROUTE.finditer(text):
        args, _ = balanced(text, match.end() - 1)
        verb = match.group(1)
        if verb == "match":
            parts = re.match(r"\s*\[([^\]]*)\]\s*,\s*['\"]([^'\"]*)['\"]\s*,?(.*)", args, re.S)
            if not parts:
                continue
            methods = [s.upper() for s in strings(parts.group(1))]
            uri, rest = parts.group(2), parts.group(3)
        else:
            parts = re.match(r"\s*['\"]([^'\"]*)['\"]\s*,?(.*)", args, re.S)
            if not parts:
                continue
            methods = ["ANY" if verb == "any" else verb.upper()]
            uri, rest = parts.group(1), parts.group(2)
        full = join_paths(base, prefix_at(spans, match.start()), uri)
        for method in methods:
            found.add(method, full, php_handler(rest), match.start())


def _resources(found: FileScan, text: str, base: str, spans) -> None:
    """Route::resource('photos', PhotoController::class) -> index, store, show, update, ..."""
    for match in RESOURCE.finditer(text):
        name, controller = match.group(2), php_handler(match.group(3))
        full = join_paths(base, prefix_at(spans, match.start()), name)
        param = "{" + name.rstrip("s").split(".")[-1] + "}"
        actions = [
            ("GET", "", "index"),
            ("POST", "", "store"),
            ("GET", f"/{param}", "show"),
            ("PUT", f"/{param}", "update"),
            ("DELETE", f"/{param}", "destroy"),
        ]
        if match.group(1) == "resource":  # apiResource has no HTML forms
            actions += [("GET", "/create", "create"), ("GET", f"/{param}/edit", "edit")]
        for method, suffix, action in actions:
            found.add(method, full + suffix, f"{controller}@{action}", match.start())
