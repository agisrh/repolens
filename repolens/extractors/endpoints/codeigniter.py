"""CodeIgniter 3 and 4 routes, including routes created by auto-routing.

CodeIgniter 4: explicit routes in app/Config/Routes.php and in every other *Routes.php under
  a Config/ folder (modules, themes, extra route files loaded with require()), with groups and
  resources. When auto-routing is on (or depends on an env variable), every public method
  of a controller is reachable too, so those are added as endpoints of their own.
CodeIgniter 3: application/config/routes.php, plus /controller/method, which CI3 always
  maps automatically.

Returns notes next to the endpoints: things the document should mention, such as routes
built in a loop that cannot be read statically.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from repolens.extractors.endpoints._common import (
    FileScan,
    balanced,
    endpoint,
    join_paths,
    php_handler,
    prefix_at,
    scoped_prefixes,
    strings,
    uncommented,
)
from repolens.i18n import t
from repolens.repo import Repo, line_of

CI4_ROUTE = re.compile(r"\$routes->(get|post|put|patch|delete|options|add|match|cli)\s*\(")
CI4_GROUP = re.compile(r"\$routes->group\(\s*['\"]([^'\"]*)['\"]")
# Route files of modules and themes, usually loaded from app/Config/Routes.php with require():
# modules/Blog/Config/Routes.php, app/Config/templates/default/Routes.php, ...
CI4_MODULE_ROUTES = ("*Config/*Routes.php", "*Config/Routes/*.php")
CI4_404 = re.compile(r"\$routes->set404Override\(\s*['\"]([^'\"]+)['\"]")
CI4_RESOURCE = re.compile(r"\$routes->(resource|presenter)\(\s*['\"]([^'\"]+)['\"]")
CI3_ROUTE = re.compile(
    r"\$route\[\s*['\"]([^'\"]+)['\"]\s*\]"  # $route['uri']
    r"(?:\[\s*['\"](\w+)['\"]\s*\])?"  # optional ['post']
    r"\s*=\s*['\"]([^'\"]*)['\"]"  # = 'controller/method'
)
PHP_METHOD = re.compile(
    r"^\s*(?:(public|protected|private)\s+)?(?:static\s+)?function\s+(\w+)\s*\(([^)]*)\)", re.M
)
NOT_ROUTABLE = {"__construct", "initController", "_remap", "__destruct", "__get", "__set", "__call"}
BASE_CONTROLLERS = ("BaseController", "Controller", "MY_Controller")


def codeigniter(repo: Repo, extra: list[str] = ()) -> tuple[list[dict], list[str]]:
    """(endpoints, notes) for CodeIgniter 4 and 3."""
    out, notes = [], []
    ci4_files = repo.glob("*app/Config/Routes.php", "*app/Config/Routes/*.php")
    ci4_files += [f for f in repo.glob(*CI4_MODULE_ROUTES) if "$routes->" in repo.read(f)]
    ci4_files += [f for f in extra if "$routes->" in repo.read(f)]
    for path in dict.fromkeys(ci4_files):
        out += _ci4_routes(repo, path, notes)
    if ci4_files:
        out += _ci4_auto_routes(repo, ci4_files, out, notes)
    ci3_files = repo.glob("*application/config/routes.php")
    ci3_files += [f for f in extra if "$route[" in repo.read(f)]
    for path in dict.fromkeys(ci3_files):
        out += _ci3_routes(repo, path, notes)
    return out, notes


# ---- CodeIgniter 4 ------------------------------------------------------------------------


def _ci4_routes(repo: Repo, path: str, notes: list[str]) -> list[dict]:
    """Explicit $routes->get(...), ->match(...), ->resource(...) in one routes file."""
    text = uncommented(repo.read(path))
    spans = scoped_prefixes(text, CI4_GROUP)
    # Routes of the app itself are one group; a module's routes are grouped by their file.
    group = "Routes.php" if "app/Config/" in "/" + path else path
    found = FileScan(path, text, "CodeIgniter 4", group=group)
    dynamic = 0
    for match in CI4_ROUTE.finditer(text):
        args, _ = balanced(text, match.end() - 1)
        verb = match.group(1)
        if verb == "match":
            methods = [s.upper() for s in re.findall(r"['\"](\w+)['\"]", args.split("]")[0])]
            rest = args.split("]", 1)[1].lstrip(" ,") if "]" in args else ""
        else:
            methods = [{"add": "ANY", "cli": "CLI"}.get(verb, verb.upper())]
            rest = args.lstrip()
        if rest[:1] not in ("'", '"'):
            dynamic += 1  # the path is a variable, e.g. inside a foreach
            continue
        values = strings(rest)
        handler = values[1] if len(values) > 1 else php_handler(rest)
        route = join_paths(prefix_at(spans, match.start()), values[0])
        for method in methods:
            found.add(method, route, handler.split("\\")[-1], match.start())
    for match in CI4_404.finditer(text):  # the controller that shows "page not found"
        found.add("ANY", "(404)", match.group(1).split("\\")[-1], match.start())
    if dynamic:
        notes.append(
            t(
                f"{path}: {dynamic} routes are built from variables (e.g. in a loop) "
                "and cannot be read statically.",
                f"{path}: {dynamic} route dibuat dari variabel (misalnya dalam perulangan) "
                "dan tidak bisa dibaca statis.",
            )
        )
    for match in CI4_RESOURCE.finditer(text):
        name = match.group(2)
        full = join_paths(prefix_at(spans, match.start()), name)
        for method, suffix in (
            ("GET", ""),
            ("GET", "/(:segment)"),
            ("POST", ""),
            ("PUT", "/(:segment)"),
            ("DELETE", "/(:segment)"),
        ):
            found.add(method, full + suffix, f"{match.group(1)}:{name}", match.start())
    return found.items


def _ci4_auto_routes(
    repo: Repo, routes_files: list[str], explicit: list[dict], notes
) -> list[dict]:
    """Controller methods reachable through auto-routing, minus those with an explicit route."""
    state, evidence = _ci4_auto_route_state(repo, routes_files)
    if not state or state == "off":
        return []
    improved = any(
        re.search(r"autoRoutesImproved\s*=\s*true", uncommented(repo.read(f)))
        for f in repo.glob("*app/Config/Feature.php")
    )
    env = state[4:] if state.startswith("env:") else None
    group = "Auto-routing"
    if env:
        group += t(f" (active when env {env} is true)", f" (aktif jika env {env} bernilai true)")
    handled = {e["handler"].split("/")[0].lower() for e in explicit}
    framework = "CodeIgniter 4 (auto-routing)"
    derived = _auto_routes(
        repo, "*app/Controllers/*.php", "Controllers/", framework, improved, group
    )
    auto = [e for e in derived if e["handler"].lower() not in handled]

    mode = "improved" if improved else "legacy"
    if env:
        status = t(f"depends on env `{env}`", f"bergantung env `{env}`")
    else:
        status = t("enabled", "aktif")
    note = t(
        f"{evidence}: auto-routing {status} (mode {mode}). "
        f"{len(auto)} endpoints are derived from public controller methods. ",
        f"{evidence}: auto-routing {status} (mode {mode}). "
        f"{len(auto)} endpoint dibentuk dari method public controller. ",
    )
    if not improved:
        note += t(
            "URLs follow the class name (case-sensitive on Linux).",
            "URL mengikuti nama class (huruf besar-kecil berpengaruh di Linux).",
        )
    notes.append(note)
    return auto


def _ci4_auto_route_state(repo: Repo, routes_files: list[str]) -> tuple[str | None, str]:
    """(state, file that says so). state: "on", "off", "env:<NAME>", or None when nothing says."""
    for path in routes_files:
        text = uncommented(repo.read(path))
        match = re.search(r"\$routes->setAutoRoute\(\s*(.+?)\s*\)\s*;", text)
        if not match:
            continue
        arg = match.group(1)
        if arg.lower() == "true":
            return "on", path
        if arg.lower() == "false":
            return "off", path
        env = re.search(r"(?:env|getenv)\(\s*['\"](\w+)['\"]", arg)
        return (f"env:{env.group(1)}" if env else "env:?"), path
    for path in repo.glob("*app/Config/Routing.php"):
        match = re.search(r"\$autoRoute\s*=\s*(true|false)", uncommented(repo.read(path)))
        if match:
            return ("on" if match.group(1) == "true" else "off"), path
    return None, ""


# ---- CodeIgniter 3 ------------------------------------------------------------------------


def _ci3_routes(repo: Repo, path: str, notes: list[str]) -> list[dict]:
    """$route['uri'] = 'controller/method', plus the automatic /controller/method routes."""
    text = uncommented(repo.read(path))
    found = FileScan(path, text, "CodeIgniter 3", group="routes.php")
    for match in CI3_ROUTE.finditer(text):
        key = match.group(1)
        if key in ("translate_uri_dashes", "404_override"):  # settings, not routes
            continue
        route = "/" if key == "default_controller" else join_paths(key)
        found.add((match.group(2) or "ANY").upper(), route, match.group(3), match.start())
    base = path.rsplit("config/routes.php", 1)[0]
    framework = "CodeIgniter 3 (auto-routing)"
    auto = _auto_routes(
        repo, f"{base}controllers/*.php", "controllers/", framework, False, "Auto-routing"
    )
    for item in auto:  # CI3 URLs are lowercase by convention; {params} keep their case
        item["path"] = re.sub(r"^[^{]+", lambda m: m.group(0).lower(), item["path"])
    notes.append(
        t(
            f"{path}: CodeIgniter 3 always maps /controller/method automatically. "
            f"{len(auto)} endpoints are derived from public controller methods.",
            f"{path}: CodeIgniter 3 selalu memetakan /controller/method secara otomatis. "
            f"{len(auto)} endpoint dibentuk dari method public controller.",
        )
    )
    return found.items + auto


# ---- auto-routing (both versions) ---------------------------------------------------------


def _auto_routes(repo: Repo, controller_glob, base_dir, framework, improved, group) -> list[dict]:
    """One endpoint per public controller method: /<Controller>/<method>/{param}.

    With CI4's improved auto-routing only verb-prefixed methods count: getList -> GET /x/list."""
    out = []
    for path in repo.glob(controller_glob):
        if PurePosixPath(path).stem in BASE_CONTROLLERS:
            continue
        text = repo.read(path)
        if re.search(r"^\s*abstract\s+class", text, re.M) or not re.search(r"\bclass\s+\w+", text):
            continue
        relative = path.split(base_dir, 1)[1][:-4]  # "Admin/Dashboard"
        controller = relative.replace("/", "\\")
        for name, params, line in _public_methods(text):
            http, action = "ANY", name
            if improved:
                verb = re.match(r"^(get|post|put|patch|delete|cli)([A-Z]\w*)$", name)
                if not verb:
                    continue
                http, action = verb.group(1).upper(), verb.group(2)[0].lower() + verb.group(2)[1:]
            segments = [relative]
            if not (action == "index" and not params):
                segments.append(action)
            segments += [f"{{{p}}}" for p in params]
            handler = f"{controller}::{name}"
            out.append(
                endpoint(
                    "server", http, join_paths(*segments), handler, path, line, group, framework
                )
            )
    return out


def _public_methods(text: str) -> list[tuple[str, list[str], int]]:
    """Routable methods of a controller: (name, parameter names, line)."""
    result = []
    for match in PHP_METHOD.finditer(text):
        visibility, name = match.group(1), match.group(2)
        if visibility in ("protected", "private") or name in NOT_ROUTABLE or name.startswith("_"):
            continue
        params = [
            p.split("=")[0].strip().split()[-1].lstrip("&$")
            for p in match.group(3).split(",")
            if p.strip()
        ]
        result.append((name, params, line_of(text, match.start())))
    return result
