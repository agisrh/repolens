"""Ruby on Rails routes from config/routes.rb (and config/routes/*.rb).

The routes DSL nests blocks, so the file is read line by line with a stack of open blocks:
  resources :articles, only: [...], param: :slug   the standard actions; nested routes
                                                    get /articles/:article_slug/...
  resource :user                                    singular resource (no :id)
  namespace :admin / scope :api                     path prefixes
  member do / collection do, `on: :collection`      routes on one item or on the list
  get 'path' => 'controller#action', root 'c#a'     single routes
Routes added by gems (devise_for, mount) cannot be listed; they are reported as notes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from repolens.extractors.endpoints._common import FileScan, join_paths
from repolens.i18n import t
from repolens.repo import Repo

PLURAL_ACTIONS = [  # (action, method, path after /name, needs the :id)
    ("index", "GET", "", False),
    ("create", "POST", "", False),
    ("new", "GET", "/new", False),
    ("show", "GET", "", True),
    ("edit", "GET", "/edit", True),
    ("update", "PATCH", "", True),
    ("update", "PUT", "", True),
    ("destroy", "DELETE", "", True),
]
SINGULAR_ACTIONS = [
    ("show", "GET", ""),
    ("create", "POST", ""),
    ("new", "GET", "/new"),
    ("edit", "GET", "/edit"),
    ("update", "PATCH", ""),
    ("update", "PUT", ""),
    ("destroy", "DELETE", ""),
]
VERB = re.compile(r"^(get|post|put|patch|delete|match)\s+(.*)$")
RESOURCES = re.compile(r"^(resources|resource)\s+:(\w+)(.*)$")
PREFIX = re.compile(r"^(namespace|scope)\s*\(?\s*(?:[:\"'](\w[\w/]*)[\"']?)?(.*)$")


@dataclass
class _Block:
    """An open `... do` block: how it changes the path and controller of routes inside it."""

    path: str = ""  # path prefix for routes inside the block
    member_path: str = ""  # path for `on: :member` routes / member blocks (resources only)
    controller: str = ""  # controller of routes inside a resources block
    module: str = ""  # controller folder from a namespace
    kind: str = "other"  # resources, resource, member, collection, prefix, other


def rails(repo: Repo) -> tuple[list[dict], list[str]]:
    out, notes = [], []
    for path in repo.glob("config/routes.rb", "*/config/routes.rb", "config/routes/*.rb"):
        text = repo.read(path)
        found = FileScan(path, text, "Rails", group="routes.rb")
        _read_routes(text, found, notes, path)
        out += found.items
    return out, notes


def _statements(text: str):
    """(line number, statement) without comments; lines ending in `,` are joined."""
    pending, start = "", 0
    for number, line in enumerate(text.splitlines(), 1):
        line = re.sub(r"\s+#.*$", "", line).strip()
        if not line or line.startswith("#"):
            continue
        if not pending:
            start = number
        pending = f"{pending} {line}".strip()
        if not pending.endswith(","):
            yield start, pending
            pending = ""


def _read_routes(text: str, found: FileScan, notes: list[str], path: str) -> None:
    stack: list[_Block] = []
    for line, statement in _statements(text):
        opens = bool(re.search(r"\bdo(\s*\|[^|]*\|)?$", statement))
        statement = re.sub(r"\s*\bdo(\s*\|[^|]*\|)?$", "", statement)
        if statement == "end":
            if stack:
                stack.pop()
            continue
        block = _route(statement, stack, found, line, notes, path)
        if opens:
            stack.append(block or _Block(path=_prefix(stack), module=_module(stack)))


def _route(statement, stack, found, line, notes, path) -> _Block | None:
    """Record the routes of one statement; return the block it opens, if any."""
    resources = RESOURCES.match(statement)
    if resources:
        return _resources(resources, stack, found, line)
    prefix = PREFIX.match(statement)
    if prefix and statement.startswith(("namespace", "scope")):
        return _prefix_block(prefix, stack)
    if statement in ("member", "collection"):
        parent = stack[-1] if stack else _Block()
        where = parent.member_path if statement == "member" else parent.path
        return _Block(
            path=where, controller=parent.controller, module=parent.module, kind=statement
        )
    root = re.match(r"^root\s+(?:to:\s*)?[\"']([\w/]+#\w+)[\"']", statement)
    if root:
        found.add("GET", join_paths(_prefix(stack)), root.group(1), line=line)
        return None
    verb = VERB.match(statement)
    if verb:
        _single_route(verb.group(1), verb.group(2), stack, found, line)
        return None
    gem = re.match(r"^(devise_for|mount)\s+(\S+)", statement)
    if gem:
        notes.append(
            t(
                f"{path}: `{gem.group(1)} {gem.group(2).rstrip(',')}` adds routes from a gem "
                "that are not listed here.",
                f"{path}: `{gem.group(1)} {gem.group(2).rstrip(',')}` menambah route dari gem "
                "yang tidak tercantum di sini.",
            )
        )
    return None


def _resources(match, stack, found, line) -> _Block:
    """resources :articles (plural) or resource :user (singular), and the block they open."""
    plural, name, options = match.group(1) == "resources", match.group(2), match.group(3)
    base = join_paths(_prefix(stack), _option(options, "path") or name)
    controller = _module(stack) + (
        _option(options, "controller") or (name if plural else _plural(name))
    )
    wanted = _actions(options)
    if plural:
        param = _option(options, "param") or "id"
        item = f"{base}/:{param}"
        for action, method, suffix, needs_id in PLURAL_ACTIONS:
            if action in wanted:
                found.add(
                    method,
                    (item if needs_id else base) + suffix,
                    f"{controller}#{action}",
                    line=line,
                )
        nested = f"{base}/:{_singular(name)}_{param}"
        return _Block(
            path=nested,
            member_path=item,
            controller=controller,
            module=_module(stack),
            kind="resources",
        )
    for action, method, suffix in SINGULAR_ACTIONS:
        if action in wanted:
            found.add(method, base + suffix, f"{controller}#{action}", line=line)
    return _Block(
        path=base, member_path=base, controller=controller, module=_module(stack), kind="resource"
    )


def _single_route(verb, rest, stack, found, line) -> None:
    """get 'path' => 'c#a', get :feed (inside resources), get 'x', to: 'c#a', via: [...]"""
    parent = stack[-1] if stack else _Block()
    target = re.match(r"[:\"']([^\"',\s]+)[\"']?(?:\s*=>\s*[\"']([\w/]+#\w+)[\"'])?(.*)$", rest)
    if not target:
        return
    route, handler, options = target.group(1), target.group(2), target.group(3)
    handler = handler or _option(options, "to")
    if verb == "match":
        methods = [m.upper() for m in re.findall(r":(\w+)", _raw_option(options, "via") or "")] or [
            "ANY"
        ]
    else:
        methods = [verb.upper()]
    on = _option(options, "on")
    if on == "collection" or parent.kind == "collection":
        base = parent.path if parent.kind == "collection" else _collection_path(parent)
    elif on == "member" or parent.kind == "member":
        base = parent.path if parent.kind == "member" else parent.member_path
    else:
        base = _prefix(stack)
    if not handler:  # get :feed inside resources :articles -> articles#feed
        action = route.strip("/").split("/")[-1]
        handler = f"{parent.controller or _module(stack) + route.strip('/')}#{action}"
    for method in methods:
        found.add(method, join_paths(base, route), handler, line=line)


def _prefix_block(match, stack) -> _Block:
    """namespace :admin -> /admin and controllers in admin/; scope :api -> /api only."""
    kind, name, options = match.group(1), match.group(2), match.group(3)
    path = _option(options, "path") or name or ""
    module = _module(stack)
    if kind == "namespace" and name:
        module += f"{name}/"
    elif _option(options, "module"):
        module += f"{_option(options, 'module')}/"
    return _Block(path=join_paths(_prefix(stack), path), module=module, kind="prefix")


# ---- helpers ----------------------------------------------------------------------------


def _prefix(stack: list[_Block]) -> str:
    return stack[-1].path if stack else ""


def _module(stack: list[_Block]) -> str:
    return stack[-1].module if stack else ""


def _collection_path(block: _Block) -> str:
    """/articles/:article_slug -> /articles (routes `on: :collection` of a resources block)."""
    return block.member_path.rsplit("/:", 1)[0] if block.kind == "resources" else block.path


def _raw_option(options: str, key: str) -> str | None:
    match = re.search(rf"\b{key}:\s*(\[[^\]]*\]|[:\"']?[\w/#.-]+[\"']?)", options)
    return match.group(1) if match else None


def _option(options: str, key: str) -> str | None:
    """Value of `key: :value` / `key: 'value'` in the options of a statement."""
    raw = _raw_option(options, key)
    return raw.strip(":\"'") if raw else None


def _actions(options: str) -> set[str]:
    """The actions kept by only: / except: (all seven when neither is given)."""
    every = {"index", "create", "new", "show", "edit", "update", "destroy"}
    only, exclude = _raw_option(options, "only"), _raw_option(options, "except")
    if only:
        return set(re.findall(r"\w+", only)) & every
    if exclude:
        return every - set(re.findall(r"\w+", exclude))
    return every


def _plural(word: str) -> str:
    if re.search(r"[^aeiou]y$", word):
        return word[:-1] + "ies"
    if re.search(r"(s|x|z|ch|sh)$", word):
        return word + "es"
    return word + "s"


def _singular(word: str) -> str:
    if word.endswith("ies"):
        return word[:-3] + "y"
    if re.search(r"(s|x|z|ch|sh)es$", word):
        return word[:-2]
    return word[:-1] if word.endswith("s") else word
