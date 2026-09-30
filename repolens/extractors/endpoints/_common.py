"""Building blocks shared by the endpoint extractors.

Most extractors follow the same recipe: find route definitions with a regular expression,
read the text between the parentheses with `balanced()`, pick the string arguments with
`strings()`, and record each route with a `FileScan`.
"""

from __future__ import annotations

import re

from repolens.extractors._text import balanced, block_end, strings, uncommented
from repolens.repo import line_of

__all__ = ["balanced", "block_end", "strings", "uncommented"]  # re-exported for the extractors

HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD")


def endpoint(kind, method, path, handler, file, line, group=None, framework=None) -> dict:
    """One entry of the endpoint list. `kind` is "server", "client", or "page"."""
    return {
        "kind": kind,
        "method": method,
        "path": path,
        "handler": handler,
        "file": file,
        "line": line,
        "group": group,
        "framework": framework,
    }


class FileScan:
    """Endpoints found in one file.

    What every entry of the file shares (kind, file, framework, group) is given once, so each
    route found only needs its method, path, handler, and position:

        found = FileScan("routes/api.php", text, "Laravel")
        found.add("GET", "/users", "UserController@index", match.start())
        out += found.items
    """

    def __init__(self, file: str, text: str, framework: str, kind="server", group=None):
        self.file, self.text, self.framework = file, text, framework
        self.kind, self.group = kind, group
        self.items: list[dict] = []

    def add(self, method, path, handler, pos=0, *, line=None, group=None) -> None:
        """Record a route. `pos` is its offset in the text; `line` overrides the line number."""
        line = line if line is not None else line_of(self.text, pos)
        group = group if group is not None else self.group
        self.items.append(
            endpoint(self.kind, method, path, handler, self.file, line, group, self.framework)
        )


# ---- reading source text ------------------------------------------------------------------


def join_paths(*parts: str) -> str:
    """join_paths("/api", "users/", "{id}") -> "/api/users/{id}"; empty parts are skipped."""
    joined = "/".join(p.strip("/") for p in parts if p and p.strip("/"))
    return "/" + joined if joined else "/"


def scoped_prefixes(text: str, group_re: re.Pattern) -> list[tuple[int, int, str]]:
    """Find `group("prefix") ... { ... }` blocks: (start, end, prefix) for each.

    `group_re` must capture the prefix in group 1."""
    spans = []
    for match in group_re.finditer(text):
        brace = text.find("{", match.end())
        if brace >= 0:
            spans.append((brace, block_end(text, brace), match.group(1)))
    return spans


def prefix_at(spans: list[tuple[int, int, str]], pos: int) -> str:
    """The combined prefix of every group block that contains `pos`."""
    return join_paths(*[p for start, end, p in spans if start < pos < end]) if spans else ""


def php_handler(raw: str) -> str:
    """Short name of a PHP route handler.

    [UserController::class, 'index'] -> UserController@index; a closure -> Closure."""
    raw = " ".join(raw.split())
    match = re.search(r"\[\s*([\w\\]+)::class\s*,\s*['\"](\w+)['\"]\s*\]", raw)
    if match:
        return f"{match.group(1).split(chr(92))[-1]}@{match.group(2)}"
    match = re.search(r"['\"]([\w\\]+@\w+)['\"]", raw)
    if match:
        return match.group(1).split("\\")[-1]
    match = re.search(r"([\w\\]+)::class", raw)
    if match:
        return match.group(1).split("\\")[-1]
    if "function" in raw or "fn" in raw:
        return "Closure"
    return raw[:60]
