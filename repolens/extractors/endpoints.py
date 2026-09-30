"""HTTP endpoints defined by a backend, API calls made by a client, and UI routes.

Every entry records the file and line it came from so the document can cite it.
Kinds:
  server - an endpoint this codebase serves
  client - an API this codebase calls (mobile apps, SPAs)
  page   - a UI route / screen
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from repolens.i18n import t
from repolens.repo import Repo, line_of

HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD")


def _ep(kind, method, path, handler, file, line, group=None, framework=None):
    return {"kind": kind, "method": method, "path": path, "handler": handler, "file": file,
            "line": line, "group": group, "framework": framework}


def _join_paths(*parts: str) -> str:
    joined = "/".join(p.strip("/") for p in parts if p and p.strip("/"))
    return "/" + joined if joined else "/"


def _strings(args: str) -> list[str]:
    return re.findall(r"[\"']([^\"']*)[\"']", args or "")


def _balanced(text: str, start: int) -> tuple[str, int]:
    """Return the contents of the parenthesised group opening at text[start] == '('."""
    depth = 0
    in_str = None
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if c == in_str and text[i - 1] != "\\":
                in_str = None
            continue
        if c in "\"'`":
            in_str = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
    return text[start + 1:], len(text)


def _scoped_prefixes(text: str, group_re: re.Pattern) -> list[tuple[int, int, str]]:
    """Find `group(prefix) ... { ... }` blocks; return (start, end, prefix) spans."""
    spans = []
    for m in group_re.finditer(text):
        brace = text.find("{", m.end())
        if brace < 0:
            continue
        depth, i = 0, brace
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        spans.append((brace, i, m.group(1)))
    return spans


def _prefix_at(spans, pos) -> str:
    return _join_paths(*[p for s, e, p in spans if s < pos < e]) if spans else ""


# ---- Spring (Java/Kotlin) and NestJS (decorators) --------------------------

CLASS_DECL = re.compile(r"^[ \t]*(?:@\w+(?:\([^)]*\))?\s+)*(?:(?:public|protected|private|abstract|final|open|data|sealed|internal)\s+)*(class|interface)\s+(\w+)(?:<[^>]*>)?(?:\s+extends\s+(\w+))?", re.M)
MAPPING = re.compile(r"@(Get|Post|Put|Delete|Patch|Request)Mapping\b")
HANDLER_JAVA = re.compile(r"(?:public|protected|private|fun)\s+(?:[\w<>\[\],.?\s]+?\s+)?(\w+)\s*\(")


def spring(repo: Repo) -> list[dict]:
    out = []
    for path in repo.by_ext(".java", ".kt"):
        text = repo.read(path)
        if "Mapping" not in text or not re.search(r"@(Rest)?Controller\b", text):
            continue
        class_match = CLASS_DECL.search(text)
        # Position of the `class` keyword itself, so class-level annotations stay in the prefix region.
        class_pos = class_match.start(1) if class_match else 0
        class_name = class_match.group(2) if class_match else PurePosixPath(path).stem
        prefix = ""
        for m in MAPPING.finditer(text[:class_pos]):
            if text[m.end():m.end() + 1] == "(":
                args, _ = _balanced(text, m.end())
                s = _strings(re.sub(r"\b(produces|consumes|headers|params)\s*=\s*\{?[^,)]*\}?", "", args))
                prefix = s[0] if s else ""
        for m in MAPPING.finditer(text, class_pos):
            kind = m.group(1)
            args, end = ("", m.end())
            if text[m.end():m.end() + 1] == "(":
                args, end = _balanced(text, m.end())
            cleaned = re.sub(r"\b(produces|consumes|headers|params|name)\s*=\s*(\{[^}]*\}|\"[^\"]*\"|[\w.]+)", "", args)
            paths = _strings(cleaned) or [""]
            if kind == "Request":
                methods = re.findall(r"RequestMethod\.(\w+)", args) or ["ANY"]
            else:
                methods = [kind.upper()]
            h = HANDLER_JAVA.search(text, end)
            handler = f"{class_name}.{h.group(1)}()" if h else class_name
            for p in paths:
                for method in methods:
                    out.append(_ep("server", method, _join_paths(prefix, p), handler, path, line_of(text, m.start()),
                                   group=class_name, framework="Spring"))
    return out


NEST_METHOD = re.compile(r"@(Get|Post|Put|Delete|Patch|Options|Head|All)\(\s*([^)]*)\)")


def nestjs(repo: Repo) -> list[dict]:
    out = []
    for path in repo.by_ext(".ts"):
        text = repo.read(path)
        ctrl = re.search(r"@Controller\(\s*([^)]*)\)", text)
        if not ctrl:
            continue
        prefix = (_strings(ctrl.group(1)) or [""])[0]
        cls = re.search(r"class\s+(\w+)", text)
        for m in NEST_METHOD.finditer(text):
            h = re.search(r"(\w+)\s*\(", text[m.end():])
            out.append(_ep("server", m.group(1).upper(), _join_paths(prefix, (_strings(m.group(2)) or [""])[0]),
                           f"{cls.group(1) if cls else ''}.{h.group(1) if h else ''}()", path, line_of(text, m.start()),
                           group=cls.group(1) if cls else None, framework="NestJS"))
    return out


# ---- Laravel ----------------------------------------------------------------

LARAVEL_ROUTE = re.compile(r"Route::(get|post|put|patch|delete|options|any|match)\s*\(")
LARAVEL_RESOURCE = re.compile(r"Route::(apiResource|resource)\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*([^)]+)\)")
LARAVEL_GROUP = re.compile(
    r"(?:Route::prefix\(\s*['\"]([^'\"]*)['\"]\s*\)(?:->\w+\([^)]*\))*->group\s*\(|"
    r"Route::group\s*\(\s*\[[^\]]*['\"]prefix['\"]\s*=>\s*['\"]([^'\"]*)['\"])"
)


def _laravel_groups(text: str):
    spans = []
    for m in LARAVEL_GROUP.finditer(text):
        prefix = m.group(1) if m.group(1) is not None else m.group(2)
        brace = text.find("{", m.end())
        if brace < 0:
            continue
        depth, i = 0, brace
        while i < len(text):
            depth += (text[i] == "{") - (text[i] == "}")
            if depth == 0:
                break
            i += 1
        spans.append((brace, i, prefix))
    return spans


def _short_handler(raw: str) -> str:
    raw = " ".join(raw.split())
    m = re.search(r"\[\s*([\w\\]+)::class\s*,\s*['\"](\w+)['\"]\s*\]", raw)
    if m:
        return f"{m.group(1).split(chr(92))[-1]}@{m.group(2)}"
    m = re.search(r"['\"]([\w\\]+@\w+)['\"]", raw)
    if m:
        return m.group(1).split("\\")[-1]
    m = re.search(r"([\w\\]+)::class", raw)
    if m:
        return m.group(1).split("\\")[-1]
    if "function" in raw or "fn" in raw:
        return "Closure"
    return raw[:60]


def laravel(repo: Repo, extra: list[str] = ()) -> list[dict]:
    out = []
    files = repo.glob("routes/*.php") + [f for f in extra if "Route::" in repo.read(f)]
    for path in dict.fromkeys(files):
        text = repo.read(path)
        base = "/api" if path.endswith("routes/api.php") else ""
        spans = _laravel_groups(text)
        for m in LARAVEL_ROUTE.finditer(text):
            args, _ = _balanced(text, m.end() - 1)
            verb = m.group(1)
            if verb == "match":
                mm = re.match(r"\s*\[([^\]]*)\]\s*,\s*['\"]([^'\"]*)['\"]\s*,?(.*)", args, re.S)
                if not mm:
                    continue
                methods = [s.upper() for s in _strings(mm.group(1))]
                uri, rest = mm.group(2), mm.group(3)
            else:
                mm = re.match(r"\s*['\"]([^'\"]*)['\"]\s*,?(.*)", args, re.S)
                if not mm:
                    continue
                methods = ["ANY" if verb == "any" else verb.upper()]
                uri, rest = mm.group(1), mm.group(2)
            full = _join_paths(base, _prefix_at(spans, m.start()), uri)
            for method in methods:
                out.append(_ep("server", method, full, _short_handler(rest), path, line_of(text, m.start()),
                               group=PurePosixPath(path).name, framework="Laravel"))
        for m in LARAVEL_RESOURCE.finditer(text):
            name, ctrl = m.group(2), _short_handler(m.group(3))
            full = _join_paths(base, _prefix_at(spans, m.start()), name)
            param = "{" + name.rstrip("s").split(".")[-1] + "}"
            actions = [("GET", "", "index"), ("POST", "", "store"), ("GET", f"/{param}", "show"),
                       ("PUT", f"/{param}", "update"), ("DELETE", f"/{param}", "destroy")]
            if m.group(1) == "resource":
                actions += [("GET", "/create", "create"), ("GET", f"/{param}/edit", "edit")]
            for method, suffix, action in actions:
                out.append(_ep("server", method, full + suffix, f"{ctrl}@{action}", path, line_of(text, m.start()),
                               group=PurePosixPath(path).name, framework="Laravel"))
    return out


# ---- CodeIgniter ------------------------------------------------------------

CI4_ROUTE = re.compile(r"\$routes->(get|post|put|patch|delete|options|add|match|cli)\s*\(")
CI4_GROUP = re.compile(r"\$routes->group\(\s*['\"]([^'\"]*)['\"]")
CI4_RESOURCE = re.compile(r"\$routes->(resource|presenter)\(\s*['\"]([^'\"]+)['\"]")


def _uncommented(text: str) -> str:
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith(("//", "#", "*", "/*")))


def _ci4_auto_route_state(repo: Repo, routes_files: list[str]) -> tuple[str | None, str]:
    """Return (state, evidence): state is 'on', 'off', or 'env:<NAME>'; None when nothing says."""
    for path in routes_files:
        text = _uncommented(repo.read(path))
        m = re.search(r"\$routes->setAutoRoute\(\s*(.+?)\s*\)\s*;", text)
        if not m:
            continue
        arg = m.group(1)
        if arg.lower() == "true":
            return "on", path
        if arg.lower() == "false":
            return "off", path
        env = re.search(r"(?:env|getenv)\(\s*['\"](\w+)['\"]", arg)
        return (f"env:{env.group(1)}" if env else "env:?"), path
    for path in repo.glob("*app/Config/Routing.php"):
        m = re.search(r"\$autoRoute\s*=\s*(true|false)", _uncommented(repo.read(path)))
        if m:
            return ("on" if m.group(1) == "true" else "off"), path
    return None, ""


PHP_PUBLIC_METHOD = re.compile(r"^\s*(?:(public|protected|private)\s+)?(?:static\s+)?function\s+(\w+)\s*\(([^)]*)\)", re.M)
SKIP_METHODS = {"__construct", "initController", "_remap", "__destruct", "__get", "__set", "__call"}


def _controller_methods(text: str) -> list[tuple[str, list[str], int]]:
    """Public, routable methods: (name, param names, line)."""
    result = []
    for m in PHP_PUBLIC_METHOD.finditer(text):
        visibility, name = m.group(1), m.group(2)
        if visibility in ("protected", "private") or name in SKIP_METHODS or name.startswith("_"):
            continue
        params = [p.split("=")[0].strip().split()[-1].lstrip("&$") for p in m.group(3).split(",") if p.strip()]
        result.append((name, params, line_of(text, m.start())))
    return result


def _auto_routes(repo: Repo, controller_glob: str, base_dir: str, framework: str, improved: bool, group: str) -> list[dict]:
    out = []
    for path in repo.glob(controller_glob):
        if PurePosixPath(path).stem in ("BaseController", "Controller", "MY_Controller"):
            continue
        text = repo.read(path)
        if re.search(r"^\s*abstract\s+class", text, re.M) or not re.search(r"\bclass\s+\w+", text):
            continue
        rel = path.split(base_dir, 1)[1][:-4]  # Admin/Dashboard
        controller = rel.replace("/", "\\")
        for name, params, line in _controller_methods(text):
            http = "ANY"
            action = name
            if improved:
                verb = re.match(r"^(get|post|put|patch|delete|cli)([A-Z]\w*)$", name)
                if not verb:
                    continue  # improved auto-routing only exposes verb-prefixed methods
                http, action = verb.group(1).upper(), verb.group(2)[0].lower() + verb.group(2)[1:]
            segs = [rel] + ([] if action == "index" and not params else [action]) + [f"{{{p}}}" for p in params]
            out.append(_ep("server", http, _join_paths(*segs), f"{controller}::{name}", path, line,
                           group=group, framework=framework))
    return out


def codeigniter(repo: Repo, extra: list[str] = ()) -> tuple[list[dict], list[str]]:
    out, notes = [], []
    ci4_files = repo.glob("*app/Config/Routes.php", "*app/Config/Routes/*.php") + [f for f in extra if "$routes->" in repo.read(f)]
    for path in dict.fromkeys(ci4_files):
        text = _uncommented(repo.read(path))
        spans = _scoped_prefixes(text, CI4_GROUP)
        dynamic = 0
        for m in CI4_ROUTE.finditer(text):
            args, _ = _balanced(text, m.end() - 1)
            verb = m.group(1)
            if verb == "match":
                methods = [s.upper() for s in re.findall(r"['\"](\w+)['\"]", args.split("]")[0])]
                rest = args.split("]", 1)[1].lstrip(" ,") if "]" in args else ""
            else:
                methods = ["ANY" if verb == "add" else ("CLI" if verb == "cli" else verb.upper())]
                rest = args.lstrip()
            if not rest[:1] in ("'", '"'):
                dynamic += 1  # path built from a variable, e.g. inside a foreach
                continue
            strings = _strings(rest)
            handler = strings[1] if len(strings) > 1 else _short_handler(rest)
            for method in methods:
                out.append(_ep("server", method, _join_paths(_prefix_at(spans, m.start()), strings[0]),
                               handler.split("\\")[-1], path, line_of(text, m.start()), group="Routes.php",
                               framework="CodeIgniter 4"))
        if dynamic:
            notes.append(t(f"{path}: {dynamic} routes are built from variables (e.g. in a loop) and cannot be read statically.",
                           f"{path}: {dynamic} route dibuat dari variabel (misalnya dalam perulangan) dan tidak bisa dibaca statis."))
        for m in CI4_RESOURCE.finditer(text):
            name = m.group(2)
            full = _join_paths(_prefix_at(spans, m.start()), name)
            for method, suffix in (("GET", ""), ("GET", "/(:segment)"), ("POST", ""), ("PUT", "/(:segment)"), ("DELETE", "/(:segment)")):
                out.append(_ep("server", method, full + suffix, f"{m.group(1)}:{name}", path, line_of(text, m.start()),
                               group="Routes.php", framework="CodeIgniter 4"))

    if ci4_files:
        state, evidence = _ci4_auto_route_state(repo, ci4_files)
        improved = any(re.search(r"autoRoutesImproved\s*=\s*true", _uncommented(repo.read(f))) for f in repo.glob("*app/Config/Feature.php"))
        if state and state != "off":
            conditional = state.startswith("env:")
            label = "Auto-routing" + (t(f" (active when env {state[4:]} is true)", f" (aktif jika env {state[4:]} bernilai true)")
                                      if conditional else "")
            explicit = {e["handler"].split("/")[0].lower() for e in out}
            auto = [e for e in _auto_routes(repo, "*app/Controllers/*.php", "Controllers/", "CodeIgniter 4 (auto-routing)", improved, label)
                    if e["handler"].lower() not in explicit]
            out += auto
            mode = "improved" if improved else "legacy"
            status = t(f"depends on env `{state[4:]}`", f"bergantung env `{state[4:]}`") if conditional else t("enabled", "aktif")
            notes.append(t(f"{evidence}: auto-routing {status} (mode {mode}). {len(auto)} endpoints are derived from public controller methods. ",
                           f"{evidence}: auto-routing {status} (mode {mode}). {len(auto)} endpoint dibentuk dari method public controller. ")
                         + (t("URLs follow the class name (case-sensitive on Linux).",
                              "URL mengikuti nama class (huruf besar-kecil berpengaruh di Linux).") if not improved else ""))

    ci3_files = repo.glob("*application/config/routes.php") + [f for f in extra if "$route[" in repo.read(f)]
    for path in dict.fromkeys(ci3_files):
        text = _uncommented(repo.read(path))
        for m in re.finditer(r"\$route\[\s*['\"]([^'\"]+)['\"]\s*\](?:\[\s*['\"](\w+)['\"]\s*\])?\s*=\s*['\"]([^'\"]*)['\"]", text):
            key = m.group(1)
            if key in ("translate_uri_dashes", "404_override"):
                continue
            path_ = "/" if key == "default_controller" else _join_paths(key)
            out.append(_ep("server", (m.group(2) or "ANY").upper(), path_, m.group(3), path, line_of(text, m.start()),
                           group="routes.php", framework="CodeIgniter 3"))
        base = path.rsplit("config/routes.php", 1)[0]
        auto = _auto_routes(repo, f"{base}controllers/*.php", "controllers/", "CodeIgniter 3 (auto-routing)", False, "Auto-routing")
        for e in auto:  # CI3 URLs are lowercase by convention
            e["path"] = e["path"].lower() if "{" not in e["path"] else re.sub(r"^[^{]+", lambda m: m.group(0).lower(), e["path"])
        out += auto
        notes.append(t(f"{path}: CodeIgniter 3 always maps /controller/method automatically. {len(auto)} endpoints are derived from public controller methods.",
                       f"{path}: CodeIgniter 3 selalu memetakan /controller/method secara otomatis. {len(auto)} endpoint dibentuk dari method public controller."))
    return out, notes


# ---- Next.js / React / Express / Python / Go -------------------------------

def _next_route_path(rel: str, root_marker: str) -> str:
    inner = rel.split(root_marker, 1)[1]
    parts = [p for p in inner.split("/")[:-1] if not (p.startswith("(") and p.endswith(")")) and not p.startswith("@")]
    return _join_paths(*parts)


def nextjs(repo: Repo) -> list[dict]:
    out = []
    for path in repo.files:
        norm = "/" + path
        for marker in ("/src/app/", "/app/"):
            if marker in norm:
                rel = norm.split(marker, 1)[1]
                name = rel.rsplit("/", 1)[-1]
                if re.fullmatch(r"route\.(ts|js|tsx|jsx)", name):
                    text = repo.read(path)
                    methods = re.findall(r"export\s+(?:async\s+)?(?:function|const)\s+(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\b", text)
                    route = _next_route_path(marker + rel, marker)
                    for method in methods or ["ANY"]:
                        out.append(_ep("server", method, route, "route handler", path, 1, group="App Router", framework="Next.js"))
                elif re.fullmatch(r"page\.(tsx|jsx|ts|js|mdx)", name):
                    out.append(_ep("page", "VIEW", _next_route_path(marker + rel, marker), "page", path, 1,
                                   group="App Router", framework="Next.js"))
                break
        else:
            for marker in ("/src/pages/", "/pages/"):
                if marker in norm and repo.exists("package.json") and '"next"' in repo.read("package.json"):
                    rel = norm.split(marker, 1)[1]
                    if not re.search(r"\.(tsx|jsx|ts|js)$", rel):
                        break
                    route = "/" + re.sub(r"(/?index)?\.(tsx|jsx|ts|js)$", "", rel)
                    if rel.startswith("api/"):
                        text = repo.read(path)
                        methods = sorted(set(re.findall(r"req\.method\s*===?\s*['\"](\w+)['\"]", text))) or ["ANY"]
                        for method in methods:
                            out.append(_ep("server", method, route or "/", "api route", path, 1, group="Pages API", framework="Next.js"))
                    elif not PurePosixPath(rel).name.startswith("_"):
                        out.append(_ep("page", "VIEW", route or "/", "page", path, 1, group="Pages Router", framework="Next.js"))
                    break
    return out


EXPRESS = re.compile(r"\b(app|router|server|api|route)\.(get|post|put|patch|delete|all)\(\s*['\"`](/[^'\"`]*)['\"`]")
PY_DECORATOR = re.compile(r"@(\w+)\.(get|post|put|patch|delete|route|api_route)\(\s*['\"]([^'\"]*)['\"]([^)]*)\)")
DJANGO_PATH = re.compile(r"\b(?:re_)?path\(\s*r?['\"]([^'\"]*)['\"]\s*,\s*([\w.]+)")
GO_ROUTE = re.compile(r"\.(GET|POST|PUT|PATCH|DELETE|Get|Post|Put|Patch|Delete)\(\s*\"([^\"]+)\"\s*,\s*([\w.]+)")
REACT_ROUTE = re.compile(r"<Route\b[^>]*\bpath\s*=\s*[{]?['\"`]([^'\"`]+)['\"`]|\bpath\s*:\s*['\"`](/[^'\"`]*)['\"`]")


def node_python_go(repo: Repo) -> list[dict]:
    out = []
    for path in repo.by_ext(".js", ".ts", ".mjs", ".cjs"):
        if "/app/" in "/" + path and path.endswith(("route.ts", "route.js")):
            continue
        text = repo.read(path)
        if "express" not in text and "Router(" not in text and "fastify" not in text:
            continue
        for m in EXPRESS.finditer(text):
            out.append(_ep("server", m.group(2).upper().replace("ALL", "ANY"), m.group(3), m.group(1), path,
                           line_of(text, m.start()), group=PurePosixPath(path).name, framework="Express"))
    for path in repo.by_ext(".py"):
        text = repo.read(path)
        for m in PY_DECORATOR.finditer(text):
            verb = m.group(2)
            if verb in ("route", "api_route"):
                methods = re.findall(r"['\"](GET|POST|PUT|PATCH|DELETE)['\"]", m.group(4)) or ["GET"]
                fw = "Flask"
            else:
                methods, fw = [verb.upper()], "FastAPI"
            h = re.search(r"def\s+(\w+)", text[m.end():])
            for method in methods:
                out.append(_ep("server", method, m.group(3), h.group(1) if h else "", path, line_of(text, m.start()),
                               group=PurePosixPath(path).name, framework=fw))
        if path.endswith("urls.py"):
            for m in DJANGO_PATH.finditer(text):
                out.append(_ep("server", "ANY", "/" + m.group(1), m.group(2), path, line_of(text, m.start()),
                               group=path, framework="Django"))
    for path in repo.by_ext(".go"):
        text = repo.read(path)
        for m in GO_ROUTE.finditer(text):
            out.append(_ep("server", m.group(1).upper(), m.group(2), m.group(3), path, line_of(text, m.start()),
                           group=PurePosixPath(path).name, framework="Go"))
    return out


def react_routes(repo: Repo) -> list[dict]:
    out = []
    for path in repo.by_ext(".js", ".jsx", ".ts", ".tsx"):
        text = repo.read(path)
        if "react-router" not in text and "<Route" not in text:
            continue
        for m in REACT_ROUTE.finditer(text):
            route = m.group(1) or m.group(2)
            out.append(_ep("page", "VIEW", route if route.startswith("/") else "/" + route, "", path,
                           line_of(text, m.start()), group=PurePosixPath(path).name, framework="React Router"))
    return out


# ---- Client-side API calls --------------------------------------------------

JS_CALL = re.compile(r"\b(axios|api|http|client|request|requests|agent|\$http|fetcher|instance)\.(get|post|put|patch|del|delete)\(\s*[`'\"]([^`'\"]+)[`'\"]")
FETCH = re.compile(r"\bfetch\(\s*[`'\"]([^`'\"]+)[`'\"](?:\s*,\s*\{[^}]*?method\s*:\s*['\"](\w+)['\"])?")
DART_CALL = re.compile(r"\.call\(\s*([^,)]+)[\s\S]{0,600}?method:\s*MethodRequest\.(\w+)")
DART_HTTP = re.compile(r"\b(?:dio|_dio|http|client|_client|apiClient)\.(get|post|put|patch|delete)\(\s*(?:Uri\.parse\()?\s*['\"]([^'\"]+)['\"]")
DART_BASE = re.compile(r"baseUrl\s*:\s*([\w.]+(?:\(\))?)")


def _normalize_client_url(url: str) -> str:
    """Drop query strings and turn `$var` / `${expr}` interpolation into `{var}`."""
    url = url.split("?", 1)[0]
    url = re.sub(r"\$\{([^}]+)\}", lambda m: "{" + m.group(1).split(".")[-1].strip() + "}", url)
    return re.sub(r"\$(\w+)", r"{\1}", url)


def _resolve_dart_ident(ident: str, before: str, depth: int = 0) -> str | None:
    """Resolve a local variable holding a URL path, e.g. `const path = 'trucks'` or
    `final finalPath = q.isNotEmpty ? '$path?$q' : path` (first string literal, with nested vars substituted)."""
    if depth > 3 or not re.fullmatch(r"\w+", ident):
        return None
    decl = None
    for d in re.finditer(rf"(?:final|const|var|String)\s+{re.escape(ident)}\s*=\s*([^;]+);", before):
        decl = d
    if not decl:
        return None
    literal = re.search(r"['\"]([^'\"]*)['\"]", decl.group(1))
    if not literal:
        return None

    def sub(m):
        inner = _resolve_dart_ident(m.group(1), before[:decl.start()], depth + 1)
        return inner if inner is not None else m.group(0)

    return re.sub(r"\$(\w+)", sub, literal.group(1))


def client_calls(repo: Repo) -> list[dict]:
    out = []
    for path in repo.by_ext(".js", ".jsx", ".ts", ".tsx", ".vue"):
        if "/pages/api/" in "/" + path or re.search(r"(^|/)app/.*route\.(ts|js)$", path):
            continue
        text = repo.read(path)
        for m in JS_CALL.finditer(text):
            url = _normalize_client_url(m.group(3))
            if not (url.startswith(("/", "http", "${")) or "/" in url):
                continue
            method = {"del": "DELETE"}.get(m.group(2), m.group(2).upper())
            out.append(_ep("client", method, url, m.group(1), path, line_of(text, m.start()),
                           group=PurePosixPath(path).name, framework="HTTP client"))
        for m in FETCH.finditer(text):
            url = _normalize_client_url(m.group(1))
            if not url.startswith(("/", "http", "${")):
                continue
            out.append(_ep("client", (m.group(2) or "GET").upper(), url, "fetch", path, line_of(text, m.start()),
                           group=PurePosixPath(path).name, framework="fetch"))
    for path in repo.by_ext(".dart"):
        text = repo.read(path)
        if ".call(" not in text and not DART_HTTP.search(text):
            continue
        base = DART_BASE.search(text)
        group = base.group(1) if base else PurePosixPath(path).stem
        for m in DART_CALL.finditer(text):
            arg = m.group(1).strip()
            if arg[:1] in "'\"":
                url = arg.strip("'\"")
            else:
                url = _resolve_dart_ident(arg, text[:m.start()]) or f"<{arg}>"
            url = _normalize_client_url(url)
            handler = None
            fn = None
            for fn in re.finditer(r"(?:Future<[^>]*>|Future)\s+(\w+)\s*\(", text[:m.start()]):
                pass
            if fn:
                handler = fn.group(1)
            out.append(_ep("client", m.group(2).upper(), url, handler, path, line_of(text, m.start()),
                           group=group, framework="Dart"))
        for m in DART_HTTP.finditer(text):
            out.append(_ep("client", m.group(1).upper(), _normalize_client_url(m.group(2)), None, path,
                           line_of(text, m.start()), group=group, framework="Dart"))
    return out


def extract(repo: Repo, extra_routes: list[str] = ()) -> dict:
    """extra_routes: route files declared in .repolens.yml; parsed by whichever syntax they contain."""
    ci_eps, notes = codeigniter(repo, extra_routes)
    server = spring(repo) + nestjs(repo) + laravel(repo, extra_routes) + ci_eps + node_python_go(repo)
    next_eps = nextjs(repo)
    server += [e for e in next_eps if e["kind"] == "server"]
    pages = [e for e in next_eps if e["kind"] == "page"] + react_routes(repo)
    client = client_calls(repo)

    def dedupe(items):
        seen, result = set(), []
        for e in items:
            key = (e["method"], e["path"], e["file"], e["line"])
            if key not in seen:
                seen.add(key)
                result.append(e)
        return result

    return {"server": dedupe(server), "client": dedupe(client), "pages": dedupe(pages), "notes": notes}
