"""Coverage checks: flag results that look complete but probably are not, with a concrete fix.

Each check is {level, area, message, hint} where level is:
  warn - something is likely missing from the document
  info - worth knowing, the document is still correct
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from repolens import projectconfig
from repolens.i18n import t
from repolens.repo import Repo

BACKEND = {"Spring Boot", "Laravel", "Lumen", "CodeIgniter 3", "CodeIgniter 4", "Symfony", "Express", "NestJS", "Fastify",
           "Django", "Flask", "FastAPI", "Gin", "Echo", "Fiber", "Ruby on Rails"}
FRONTEND = {"React", "Next.js", "Vue", "Nuxt", "Angular", "Svelte", "Remix"}
MOBILE = {"Flutter", "React Native", "Expo"}
SOURCE_EXT = (".java", ".kt", ".php", ".js", ".jsx", ".ts", ".tsx", ".py", ".go", ".rb", ".dart", ".cs", ".vue", ".swift",
              ".ex", ".exs", ".rs", ".scala", ".clj", ".erl", ".lua", ".pl", ".cpp", ".c", ".fs", ".vb", ".groovy")


def _check(level, area, message, hint=None):
    return {"level": level, "area": area, "message": message, "hint": hint}


def _controllers(repo: Repo) -> list[str]:
    names = []
    for f in repo.files:
        if re.search(r"(^|/)(app|application)/(Controllers|controllers|Http/Controllers)/.+\.php$", f):
            name = PurePosixPath(f).stem
            if name not in ("BaseController", "Controller", "MY_Controller"):
                names.append(name)
    return list(dict.fromkeys(names))


def check(repo: Repo, facts: dict) -> list[dict]:
    out: list[dict] = []
    fw_names = {f["name"] for f in facts["frameworks"]}
    eps, db = facts["endpoints"], facts["database"]
    has_source = any(f.endswith(SOURCE_EXT) for f in repo.files)
    cfg = "`.repolens.yml`"

    # Stack
    if has_source and not (fw_names & (BACKEND | FRONTEND | MOBILE)):
        langs = ", ".join(l["language"] for l in facts["languages"][:3]) or "-"
        out.append(_check("warn", "Tech stack",
                          t(f"Main framework not recognised (languages: {langs}). Endpoints and schema are probably missing.",
                            f"Framework utama tidak dikenali (bahasa: {langs}). Endpoint dan skema kemungkinan tidak terdeteksi."),
                          t(f"Fill in `frameworks`, `routes` and `schema` in {cfg}, and report this stack so an extractor can be added.",
                            f"Isi `frameworks`, `routes`, dan `schema` di {cfg}, lalu laporkan stack ini supaya extractor-nya bisa ditambahkan.")))
    for f in facts["frameworks"]:
        if f["name"] in BACKEND | FRONTEND | MOBILE:
            name, version, source = f["name"], f["version"], f["source"]
            if not version:
                alt = (t("run `composer install` before scanning", "jalankan `composer install` sebelum scan") if "vendor" in source
                       else t("commit the lock file", "commit lock file"))
                example = "`frameworks: [{name: " + name + ", version: ...}]`"
                out.append(_check("warn", "Tech stack", t(f"{name} version unknown ({source}).", f"Versi {name} tidak diketahui ({source})."),
                                  t(f"Set {example} in {cfg}, or {alt}.", f"Isi {example} di {cfg}, atau {alt}.")))
            elif re.match(r"^[\^~><=*]", version):
                out.append(_check("info", "Tech stack",
                                  t(f"{name} is only recorded as the constraint `{version}`, not the installed version.",
                                    f"{name} hanya tercatat sebagai constraint `{version}`, bukan versi terpasang."),
                                  t("Commit the lock file (composer.lock / package-lock.json / pubspec.lock) so the exact version can be read.",
                                    "Commit lock file (composer.lock / package-lock.json / pubspec.lock) agar versi pastinya terbaca.")))
    for m in facts["dependencies"]:
        if m["dependencies"] and not m.get("lock") and m["ecosystem"].split()[0] in ("PHP", "Node.js", "Dart", "Ruby"):
            manifest = m["manifest"]
            out.append(_check("info", "Dependency",
                              t(f"`{manifest}` has no lock file, so installed versions are unknown.",
                                f"`{manifest}` tidak punya lock file, jadi versi terpasang tidak diketahui."),
                              t("Commit the lock file to the repository.", "Commit lock file ke repository.")))

    # Endpoints
    backend = fw_names & BACKEND
    if backend and not eps["server"]:
        names = ", ".join(sorted(backend))
        out.append(_check("warn", "Endpoint",
                          t(f"{names} detected, but no server endpoints were found.",
                            f"{names} terdeteksi, tapi tidak ada endpoint server yang ditemukan."),
                          t(f"If routes live in other files, list them under `routes` in {cfg}. Dynamic endpoints can go under `endpoints`.",
                            f"Jika route ada di file lain, daftarkan di `routes` pada {cfg}. Endpoint dinamis bisa ditulis di `endpoints`.")))
    controllers = _controllers(repo)
    if controllers and eps["server"]:
        handlers = " ".join(str(e.get("handler") or "") for e in eps["server"]).lower()
        unrouted = [c for c in controllers if c.lower().replace("_", "") not in handlers.replace("_", "")
                    and c.lower().removesuffix("controller") not in handlers]
        if unrouted:
            listed = ", ".join(sorted(unrouted)[:8]) + (" …" if len(unrouted) > 8 else "")
            n, total = len(unrouted), len(controllers)
            out.append(_check("warn", "Endpoint",
                              t(f"{n} of {total} controllers do not appear in any route: {listed}.",
                                f"{n} dari {total} controller tidak muncul di route mana pun: {listed}."),
                              t(f"They may be reached through auto-routing or dynamically built routes. Add their endpoints under `endpoints` in {cfg}, or ignore this if they are unused.",
                                f"Controller ini mungkin diakses lewat auto-routing atau route yang dirakit dinamis. Tulis endpoint-nya di `endpoints` pada {cfg}, atau abaikan jika memang tidak dipakai.")))
    if fw_names & MOBILE and not eps["client"]:
        out.append(_check("warn", "Endpoint",
                          t("Mobile app detected, but no API calls were found.", "Aplikasi mobile terdeteksi, tapi tidak ada panggilan API yang ditemukan."),
                          t("The HTTP client may use a pattern that is not recognised yet. Report an example call so it can be added.",
                            "HTTP client-nya mungkin memakai pola yang belum dikenali. Laporkan contoh pemanggilannya supaya bisa ditambahkan.")))
    if fw_names & FRONTEND and not (eps["client"] or eps["pages"] or eps["server"]):
        out.append(_check("info", "Endpoint", t("Frontend app detected, but no UI routes or API calls were found.",
                                                "Aplikasi frontend terdeteksi, tapi tidak ada route UI atau panggilan API yang ditemukan.")))
    unresolved = [e for e in eps["client"] if e["path"].startswith("<")]
    if unresolved:
        n, where = len(unresolved), f"{unresolved[0]['file']}:{unresolved[0]['line']}"
        out.append(_check("info", "Endpoint",
                          t(f"{n} API call paths are built from variables and cannot be read statically (e.g. {where}).",
                            f"{n} panggilan API path-nya dirakit dari variabel dan tidak bisa dibaca statis (contoh: {where}).")))
    for note in eps["notes"]:
        out.append(_check("info", "Endpoint", note))

    # Database ("lokal"/"disimpulkan" keep scans made before these flags existed working)
    engines = [e["engine"] for e in db["engines"]
               if not (e.get("local") or "lokal" in e["engine"]) and "Redis" not in e["engine"]]
    inferred = [tbl for tbl in db["tables"] if tbl.get("inferred") or "disimpulkan" in tbl["source"]]
    real = [tbl for tbl in db["tables"] if tbl not in inferred]
    if (engines or backend) and not db["tables"]:
        what = "Database " + ", ".join(engines) if engines else "Backend"
        out.append(_check("warn", "Database",
                          t(f"{what} detected, but no schema definition was found (SQL, migration, entity).",
                            f"{what} terdeteksi, tapi tidak ada definisi skema (SQL, migration, entity)."),
                          t(f"Put a schema-only SQL dump in the repository and list it under `schema` in {cfg}.",
                            f"Taruh SQL dump skema di repository lalu daftarkan di `schema` pada {cfg}.")))
    elif inferred and not real:
        n = len(inferred)
        out.append(_check("warn", "Database",
                          t(f"{n} tables are only inferred from queries in code, so their column lists are incomplete.",
                            f"{n} tabel hanya disimpulkan dari query di kode, jadi daftar kolomnya belum lengkap."),
                          t(f"For a complete schema, add a schema-only SQL dump and list it under `schema` in {cfg}.",
                            f"Untuk skema lengkap, tambahkan SQL dump (tanpa data) dan daftarkan di `schema` pada {cfg}.")))

    # Repository state
    git = facts.get("git") or {}
    if git.get("disabled"):
        out.append(_check("info", "Repository", t("Scanned as a plain folder (--no-git): files on disk as they are, without release info (commit, tag).",
                                                  "Dipindai sebagai folder biasa (--no-git): file di disk apa adanya, tanpa informasi rilis (commit, tag).")))
    elif not git.get("is_git"):
        out.append(_check("info", "Repository", t("This folder is not a git repository, so release info (commit, tag) is not available.",
                                                  "Folder ini bukan repository git, jadi informasi rilis (commit, tag) tidak tersedia.")))
    elif git.get("dirty"):
        out.append(_check("info", "Repository", t("There are uncommitted changes. Use `--ref <tag>` for a clean release document.",
                                                  "Ada perubahan yang belum di-commit. Gunakan `--ref <tag>` untuk dokumen rilis yang bersih.")))
    if facts["project"].get("name_source") == "folder":
        name = facts["project"]["name"]
        out.append(_check("info", t("Project", "Proyek"), t(f"Project name taken from the folder name (`{name}`).", f"Nama proyek diambil dari nama folder (`{name}`)."),
                          t(f"Set `name` in {cfg} for the official name.", f"Isi `name` di {cfg} untuk nama resmi.")))

    # Config file problems
    for w in (facts.get("project_config") or {}).get("warnings", []):
        out.append(_check("warn", ".repolens.yml", w))
    legacy = (facts.get("project_config") or {}).get("file")
    if legacy in projectconfig.LEGACY_FILENAMES:
        out.append(_check("info", ".repolens.yml", t(f"Read from the old file name `{legacy}`.", f"Dibaca dari nama file lama `{legacy}`."),
                          t("Rename it to `.repolens.yml`.", "Ganti namanya menjadi `.repolens.yml`.")))
    return out
