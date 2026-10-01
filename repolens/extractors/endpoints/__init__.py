"""HTTP endpoints a backend serves, API calls a client makes, and UI routes.

Every entry records the file and line it came from, so the document can cite it:
  {"kind", "method", "path", "handler", "file", "line", "group", "framework"}
Kinds:
  server - an endpoint this codebase serves
  client - an API this codebase calls (mobile apps, single-page apps)
  page   - a UI route or screen

One module per stack. To support a new framework, add a function `(repo) -> list[dict]` in
the matching module (or a new one), build entries with `_common.FileScan`, call it from
`extract()` below, and add a fixture plus a test in tests/test_fixtures.py.
"""

from __future__ import annotations

from repolens.extractors.endpoints.client import client_calls
from repolens.extractors.endpoints.codeigniter import codeigniter
from repolens.extractors.endpoints.java_nest import nestjs, spring
from repolens.extractors.endpoints.javascript import express, nextjs, react_routes
from repolens.extractors.endpoints.laravel import laravel
from repolens.extractors.endpoints.python_go import go, python
from repolens.extractors.endpoints.rails import rails
from repolens.repo import Repo


def extract(repo: Repo, extra_routes: list[str] = ()) -> dict:
    """{"server", "client", "pages", "notes"}.

    extra_routes: route files listed in .repolens.yml; each is read with whichever syntax
    (Laravel, CodeIgniter 3 or 4) it contains."""
    codeigniter_endpoints, notes = codeigniter(repo, extra_routes)
    rails_endpoints, rails_notes = rails(repo)
    notes += rails_notes
    next_endpoints = nextjs(repo)
    server = (
        spring(repo)
        + nestjs(repo)
        + laravel(repo, extra_routes)
        + codeigniter_endpoints
        + express(repo)
        + python(repo)
        + go(repo)
        + rails_endpoints
        + [e for e in next_endpoints if e["kind"] == "server"]
    )
    pages = [e for e in next_endpoints if e["kind"] == "page"] + react_routes(repo)
    return {
        "server": _unique(server),
        "client": _unique(client_calls(repo)),
        "pages": _unique(pages),
        "notes": notes,
    }


def _unique(items: list[dict]) -> list[dict]:
    """Drop repeats of the same method + path at the same place (keeps the first)."""
    seen, result = set(), []
    for item in items:
        key = (item["method"], item["path"], item["file"], item["line"])
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
