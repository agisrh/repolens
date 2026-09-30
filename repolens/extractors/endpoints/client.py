"""API calls a client makes: web front ends (axios, fetch, ...) and Flutter/Dart apps.

URLs are normalised so the same endpoint looks the same everywhere: the query string is
dropped and interpolation (`${id}`, `$id`) becomes `{id}`.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from repolens.extractors.endpoints._common import FileScan
from repolens.repo import Repo

JS_CALL = re.compile(
    r"\b(axios|api|http|client|request|requests|agent|\$http|fetcher|instance)"
    r"\.(get|post|put|patch|del|delete)\(\s*[`'\"]([^`'\"]+)[`'\"]"
)
FETCH = re.compile(
    r"\bfetch\(\s*[`'\"]([^`'\"]+)[`'\"](?:\s*,\s*\{[^}]*?method\s*:\s*['\"](\w+)['\"])?"
)
# Project-specific Dart wrapper: api.call(path, ..., method: MethodRequest.get)
DART_CALL = re.compile(r"\.call\(\s*([^,)]+)[\s\S]{0,600}?method:\s*MethodRequest\.(\w+)")
DART_HTTP = re.compile(
    r"\b(?:dio|_dio|http|client|_client|apiClient)\.(get|post|put|patch|delete)"
    r"\(\s*(?:Uri\.parse\()?\s*['\"]([^'\"]+)['\"]"
)
DART_BASE = re.compile(r"baseUrl\s*:\s*([\w.]+(?:\(\))?)")
DART_FUNCTION = re.compile(r"(?:Future<[^>]*>|Future)\s+(\w+)\s*\(")


def client_calls(repo: Repo) -> list[dict]:
    return _javascript_calls(repo) + _dart_calls(repo)


def _javascript_calls(repo: Repo) -> list[dict]:
    out = []
    for path in repo.by_ext(".js", ".jsx", ".ts", ".tsx", ".vue"):
        if "/pages/api/" in "/" + path or re.search(r"(^|/)app/.*route\.(ts|js)$", path):
            continue  # server code of a Next.js app
        text = repo.read(path)
        group = PurePosixPath(path).name
        found = FileScan(path, text, "HTTP client", kind="client", group=group)
        for match in JS_CALL.finditer(text):
            url = _normalize_url(match.group(3))
            if not (url.startswith(("/", "http", "${")) or "/" in url):
                continue
            method = {"del": "DELETE"}.get(match.group(2), match.group(2).upper())
            found.add(method, url, match.group(1), match.start())
        fetches = FileScan(path, text, "fetch", kind="client", group=group)
        for match in FETCH.finditer(text):
            url = _normalize_url(match.group(1))
            if url.startswith(("/", "http", "${")):
                fetches.add((match.group(2) or "GET").upper(), url, "fetch", match.start())
        out += found.items + fetches.items
    return out


def _dart_calls(repo: Repo) -> list[dict]:
    out = []
    for path in repo.by_ext(".dart"):
        text = repo.read(path)
        if ".call(" not in text and not DART_HTTP.search(text):
            continue
        base = DART_BASE.search(text)
        group = base.group(1) if base else PurePosixPath(path).stem
        found = FileScan(path, text, "Dart", kind="client", group=group)
        for match in DART_CALL.finditer(text):
            arg = match.group(1).strip()
            if arg[:1] in "'\"":
                url = arg.strip("'\"")
            else:
                url = _resolve_dart_variable(arg, text[: match.start()]) or f"<{arg}>"
            functions = list(DART_FUNCTION.finditer(text[: match.start()]))
            handler = functions[-1].group(1) if functions else None  # the enclosing Future method
            found.add(match.group(2).upper(), _normalize_url(url), handler, match.start())
        for match in DART_HTTP.finditer(text):
            found.add(match.group(1).upper(), _normalize_url(match.group(2)), None, match.start())
        out += found.items
    return out


def _normalize_url(url: str) -> str:
    """Drop the query string and turn `$var` / `${expr}` interpolation into `{var}`."""
    url = url.split("?", 1)[0]
    url = re.sub(r"\$\{([^}]+)\}", lambda m: "{" + m.group(1).split(".")[-1].strip() + "}", url)
    return re.sub(r"\$(\w+)", r"{\1}", url)


def _resolve_dart_variable(name: str, before: str, depth: int = 0) -> str | None:
    """The URL held by a local variable, e.g. `const path = 'trucks'`.

    For `final p = q.isNotEmpty ? '$path?$q' : path` the first string literal is used, with
    variables inside it resolved the same way (up to three levels deep)."""
    if depth > 3 or not re.fullmatch(r"\w+", name):
        return None
    declarations = list(
        re.finditer(rf"(?:final|const|var|String)\s+{re.escape(name)}\s*=\s*([^;]+);", before)
    )
    if not declarations:
        return None
    declaration = declarations[-1]  # the closest one before the call
    literal = re.search(r"['\"]([^'\"]*)['\"]", declaration.group(1))
    if not literal:
        return None

    def resolve(match: re.Match) -> str:
        inner = _resolve_dart_variable(match.group(1), before[: declaration.start()], depth + 1)
        return inner if inner is not None else match.group(0)

    return re.sub(r"\$(\w+)", resolve, literal.group(1))
