"""Coverage checks: results that look complete but probably are not, each with a concrete fix.

Each finding is {level, area, message, hint}, where level is:
  warn - something is likely missing from the document
  info - worth knowing; the document is still correct

The checks run in the order of CHECKS below; each takes (repo, facts) and returns findings.
To add a check, write such a function and add it to CHECKS.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from repolens import projectconfig
from repolens.i18n import t
from repolens.repo import Repo

BACKEND = {
    "Spring Boot",
    "Laravel",
    "Lumen",
    "CodeIgniter 3",
    "CodeIgniter 4",
    "Symfony",
    "Express",
    "NestJS",
    "Fastify",
    "Django",
    "Flask",
    "FastAPI",
    "Gin",
    "Echo",
    "Fiber",
    "Ruby on Rails",
}
FRONTEND = {"React", "Next.js", "Vue", "Nuxt", "Angular", "Svelte", "Remix"}
MOBILE = {"Flutter", "React Native", "Expo"}
# Extensions of application source code (as opposed to config, docs, or assets).
SOURCE_EXT = tuple(
    ".java .kt .php .js .jsx .ts .tsx .py .go .rb .dart .cs .vue .swift .ex .exs .rs .scala"
    " .clj .erl .lua .pl .cpp .c .fs .vb .groovy".split()
)
CONFIG = "`.repolens.yml`"


def check(repo: Repo, facts: dict) -> list[dict]:
    """All findings for these scan facts."""
    findings: list[dict] = []
    for run in CHECKS:
        findings += run(repo, facts)
    return findings


def _finding(level: str, area: str, message: str, hint: str | None = None) -> dict:
    return {"level": level, "area": area, "message": message, "hint": hint}


# ---- tech stack and dependencies ----------------------------------------------------------


def _stack(repo: Repo, facts: dict) -> list[dict]:
    """No main framework recognised, or its version is unknown or only a range."""
    out = []
    names = {f["name"] for f in facts["frameworks"]}
    main = BACKEND | FRONTEND | MOBILE
    if any(f.endswith(SOURCE_EXT) for f in repo.files) and not (names & main):
        languages = ", ".join(x["language"] for x in facts["languages"][:3]) or "-"
        out.append(
            _finding(
                "warn",
                "Tech stack",
                t(
                    f"Main framework not recognised (languages: {languages}). "
                    "Endpoints and schema are probably missing.",
                    f"Framework utama tidak dikenali (bahasa: {languages}). "
                    "Endpoint dan skema kemungkinan tidak terdeteksi.",
                ),
                t(
                    f"Fill in `frameworks`, `routes` and `schema` in {CONFIG}, "
                    "and report this stack so an extractor can be added.",
                    f"Isi `frameworks`, `routes`, dan `schema` di {CONFIG}, "
                    "lalu laporkan stack ini supaya extractor-nya bisa ditambahkan.",
                ),
            )
        )
    for framework in facts["frameworks"]:
        if framework["name"] in main:
            out += _framework_version(framework)
    return out


def _framework_version(framework: dict) -> list[dict]:
    """A main framework without a version, or with only a range such as ^8.1."""
    name, version, source = framework["name"], framework["version"], framework["source"]
    if not version:
        if "vendor" in source:
            fix = t(
                "run `composer install` before scanning", "jalankan `composer install` sebelum scan"
            )
        else:
            fix = t("commit the lock file", "commit lock file")
        example = "`frameworks: [{name: " + name + ", version: ...}]`"
        return [
            _finding(
                "warn",
                "Tech stack",
                t(
                    f"{name} version unknown ({source}).",
                    f"Versi {name} tidak diketahui ({source}).",
                ),
                t(
                    f"Set {example} in {CONFIG}, or {fix}.",
                    f"Isi {example} di {CONFIG}, atau {fix}.",
                ),
            )
        ]
    if re.match(r"^[\^~><=*]", version):  # a range such as ^8.1, not an installed version
        return [
            _finding(
                "info",
                "Tech stack",
                t(
                    f"{name} is only recorded as the constraint `{version}`, not the installed "
                    "version.",
                    f"{name} hanya tercatat sebagai constraint `{version}`, bukan versi terpasang.",
                ),
                t(
                    "Commit the lock file (composer.lock / package-lock.json / pubspec.lock) "
                    "so the exact version can be read.",
                    "Commit lock file (composer.lock / package-lock.json / pubspec.lock) "
                    "agar versi pastinya terbaca.",
                ),
            )
        ]
    return []


def _dependencies(repo: Repo, facts: dict) -> list[dict]:
    """Manifests of ecosystems that normally commit a lock file, without one."""
    out = []
    for manifest in facts["dependencies"]:
        ecosystem = manifest["ecosystem"].split()[0]
        if (
            manifest["dependencies"]
            and not manifest.get("lock")
            and ecosystem in ("PHP", "Node.js", "Dart", "Ruby")
        ):
            path = manifest["manifest"]
            out.append(
                _finding(
                    "info",
                    "Dependency",
                    t(
                        f"`{path}` has no lock file, so installed versions are unknown.",
                        f"`{path}` tidak punya lock file, jadi versi terpasang tidak diketahui.",
                    ),
                    t("Commit the lock file to the repository.", "Commit lock file ke repository."),
                )
            )
    return out


# ---- endpoints ----------------------------------------------------------------------------


def _endpoints(repo: Repo, facts: dict) -> list[dict]:
    """A backend without routes, controllers no route points to, an app without API calls."""
    out = []
    names = {f["name"] for f in facts["frameworks"]}
    endpoints = facts["endpoints"]
    backend = names & BACKEND
    if backend and not endpoints["server"]:
        listed = ", ".join(sorted(backend))
        out.append(
            _finding(
                "warn",
                "Endpoint",
                t(
                    f"{listed} detected, but no server endpoints were found.",
                    f"{listed} terdeteksi, tapi tidak ada endpoint server yang ditemukan.",
                ),
                t(
                    f"If routes live in other files, list them under `routes` in {CONFIG}. "
                    "Dynamic endpoints can go under `endpoints`.",
                    f"Jika route ada di file lain, daftarkan di `routes` pada {CONFIG}. "
                    "Endpoint dinamis bisa ditulis di `endpoints`.",
                ),
            )
        )
    out += _unrouted_controllers(repo, endpoints["server"])
    if names & MOBILE and not endpoints["client"]:
        out.append(
            _finding(
                "warn",
                "Endpoint",
                t(
                    "Mobile app detected, but no API calls were found.",
                    "Aplikasi mobile terdeteksi, tapi tidak ada panggilan API yang ditemukan.",
                ),
                t(
                    "The HTTP client may use a pattern that is not recognised yet. "
                    "Report an example call so it can be added.",
                    "HTTP client-nya mungkin memakai pola yang belum dikenali. "
                    "Laporkan contoh pemanggilannya supaya bisa ditambahkan.",
                ),
            )
        )
    if names & FRONTEND and not (endpoints["client"] or endpoints["pages"] or endpoints["server"]):
        out.append(
            _finding(
                "info",
                "Endpoint",
                t(
                    "Frontend app detected, but no UI routes or API calls were found.",
                    "Aplikasi frontend terdeteksi, tapi tidak ada route UI atau panggilan API "
                    "yang ditemukan.",
                ),
            )
        )
    unresolved = [e for e in endpoints["client"] if e["path"].startswith("<")]
    if unresolved:
        count, where = len(unresolved), f"{unresolved[0]['file']}:{unresolved[0]['line']}"
        out.append(
            _finding(
                "info",
                "Endpoint",
                t(
                    f"{count} API call paths are built from variables and cannot be read "
                    f"statically (e.g. {where}).",
                    f"{count} panggilan API path-nya dirakit dari variabel dan tidak bisa dibaca "
                    f"statis (contoh: {where}).",
                ),
            )
        )
    out += [_finding("info", "Endpoint", note) for note in endpoints["notes"]]
    return out


def _unrouted_controllers(repo: Repo, server: list[dict]) -> list[dict]:
    """PHP controllers whose name appears in no route handler."""
    controllers = _php_controllers(repo)
    if not controllers or not server:
        return []
    handlers = " ".join(str(e.get("handler") or "") for e in server).lower()
    unrouted = [
        c
        for c in controllers
        if c.lower().replace("_", "") not in handlers.replace("_", "")
        and c.lower().removesuffix("controller") not in handlers
    ]
    if not unrouted:
        return []
    listed = ", ".join(sorted(unrouted)[:8]) + (" …" if len(unrouted) > 8 else "")
    count, total = len(unrouted), len(controllers)
    return [
        _finding(
            "warn",
            "Endpoint",
            t(
                f"{count} of {total} controllers do not appear in any route: {listed}.",
                f"{count} dari {total} controller tidak muncul di route mana pun: {listed}.",
            ),
            t(
                "They may be reached through auto-routing or dynamically built routes. "
                f"Add their endpoints under `endpoints` in {CONFIG}, or ignore this if they "
                "are unused.",
                "Controller ini mungkin diakses lewat auto-routing atau route yang dirakit "
                f"dinamis. Tulis endpoint-nya di `endpoints` pada {CONFIG}, atau abaikan jika "
                "memang tidak dipakai.",
            ),
        )
    ]


def _php_controllers(repo: Repo) -> list[str]:
    """Names of the PHP controllers (base controllers left out)."""
    names = []
    pattern = re.compile(
        r"(^|/)(app|application)/(Controllers|controllers|Http/Controllers)/.+\.php$"
    )
    for path in repo.files:
        if pattern.search(path):
            name = PurePosixPath(path).stem
            if name not in ("BaseController", "Controller", "MY_Controller"):
                names.append(name)
    return list(dict.fromkeys(names))


# ---- database -----------------------------------------------------------------------------


def _database(repo: Repo, facts: dict) -> list[dict]:
    """A database or backend without any schema, or a schema that is only inferred."""
    database = facts["database"]
    # "lokal" / "disimpulkan" keep scans made before the local/inferred flags existed working.
    engines = [
        e["engine"]
        for e in database["engines"]
        if not (e.get("local") or "lokal" in e["engine"]) and "Redis" not in e["engine"]
    ]
    tables = database["tables"]
    inferred = [x for x in tables if x.get("inferred") or "disimpulkan" in x["source"]]
    defined = [x for x in tables if x not in inferred]
    backend = {f["name"] for f in facts["frameworks"]} & BACKEND
    if (engines or backend) and not tables:
        what = "Database " + ", ".join(engines) if engines else "Backend"
        return [
            _finding(
                "warn",
                "Database",
                t(
                    f"{what} detected, but no schema definition was found (SQL, migration, "
                    "entity).",
                    f"{what} terdeteksi, tapi tidak ada definisi skema (SQL, migration, entity).",
                ),
                t(
                    "Put a schema-only SQL dump in the repository and list it under `schema` in "
                    f"{CONFIG}.",
                    f"Taruh SQL dump skema di repository lalu daftarkan di `schema` pada {CONFIG}.",
                ),
            )
        ]
    if inferred and not defined:
        count = len(inferred)
        return [
            _finding(
                "warn",
                "Database",
                t(
                    f"{count} tables are only inferred from queries in code, "
                    "so their column lists are incomplete.",
                    f"{count} tabel hanya disimpulkan dari query di kode, "
                    "jadi daftar kolomnya belum lengkap.",
                ),
                t(
                    "For a complete schema, add a schema-only SQL dump and list it under "
                    f"`schema` in {CONFIG}.",
                    "Untuk skema lengkap, tambahkan SQL dump (tanpa data) dan daftarkan di "
                    f"`schema` pada {CONFIG}.",
                ),
            )
        ]
    return []


# ---- repository and configuration ---------------------------------------------------------


def _repository(repo: Repo, facts: dict) -> list[dict]:
    """How the release was read (no git, not a repository, uncommitted changes) and the name."""
    out = []
    git = facts.get("git") or {}
    if git.get("disabled"):
        message = t(
            "Scanned as a plain folder (--no-git): files on disk as they are, "
            "without release info (commit, tag).",
            "Dipindai sebagai folder biasa (--no-git): file di disk apa adanya, "
            "tanpa informasi rilis (commit, tag).",
        )
        out.append(_finding("info", "Repository", message))
    elif not git.get("is_git"):
        message = t(
            "This folder is not a git repository, so release info (commit, tag) is not available.",
            "Folder ini bukan repository git, jadi informasi rilis (commit, tag) tidak tersedia.",
        )
        out.append(_finding("info", "Repository", message))
    elif git.get("dirty"):
        message = t(
            "There are uncommitted changes. Use `--ref <tag>` for a clean release document.",
            "Ada perubahan yang belum di-commit. Gunakan `--ref <tag>` untuk dokumen rilis "
            "yang bersih.",
        )
        out.append(_finding("info", "Repository", message))
    if facts["project"].get("name_source") == "folder":
        name = facts["project"]["name"]
        out.append(
            _finding(
                "info",
                t("Project", "Proyek"),
                t(
                    f"Project name taken from the folder name (`{name}`).",
                    f"Nama proyek diambil dari nama folder (`{name}`).",
                ),
                t(
                    f"Set `name` in {CONFIG} for the official name.",
                    f"Isi `name` di {CONFIG} untuk nama resmi.",
                ),
            )
        )
    return out


def _config_file(repo: Repo, facts: dict) -> list[dict]:
    """Problems in .repolens.yml, and a hint to rename a legacy .docgen.yml."""
    config = facts.get("project_config") or {}
    out = [_finding("warn", ".repolens.yml", warning) for warning in config.get("warnings", [])]
    legacy = config.get("file")
    if legacy in projectconfig.LEGACY_FILENAMES:
        out.append(
            _finding(
                "info",
                ".repolens.yml",
                t(
                    f"Read from the old file name `{legacy}`.",
                    f"Dibaca dari nama file lama `{legacy}`.",
                ),
                t("Rename it to `.repolens.yml`.", "Ganti namanya menjadi `.repolens.yml`."),
            )
        )
    return out


CHECKS = [_stack, _dependencies, _endpoints, _database, _repository, _config_file]
