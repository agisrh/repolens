"""`repolens doctor [folder]`: what was detected, and what is probably missing.

Nothing is written. The output has one block per area (project, tech stack, dependencies,
endpoints, database) and ends with the coverage findings and how to fix them. With
--strict the exit code is 1 when a finding needs attention, which makes it usable in CI.
"""

from __future__ import annotations

from repolens import ui
from repolens.commands._common import (
    add_command,
    check_source_options,
    count_warnings,
    emit_json,
    flag,
    option,
    source_detail,
)
from repolens.i18n import t
from repolens.scanner import prepared_source, scan

NAME = "doctor"


def register(subparsers, common):
    p = add_command(
        subparsers,
        NAME,
        common,
        "Check what is detected and what is missing, without writing documents",
        "Cek apa yang terdeteksi dan apa yang terlewat, tanpa membuat dokumen",
    )
    p.add_argument("source", nargs="?", default=".")
    option(p, "--ref", "Tag, branch, or commit to check", "Tag, branch, atau commit yang dicek")
    flag(p, "--no-git", "Read the folder as plain files", "Baca folder sebagai file biasa")
    flag(
        p,
        "--strict",
        "Exit code 1 when something needs attention (for CI)",
        "Exit code 1 jika ada temuan 'perlu dicek' (untuk CI)",
    )
    flag(p, "--json", "Print a JSON result", "Cetak hasil JSON")
    return p


def run(args) -> int:
    check_source_options(args)
    ui.header("Doctor", source_detail(args))
    scanning = ui.out.status(t("Scanning…", "Memindai…"))
    with scanning, prepared_source(args.source, args.ref) as (root, info):
        facts = scan(root, info, use_git=not args.no_git)
    checks = facts["coverage"]
    warnings = count_warnings(checks)
    exit_code = 1 if args.strict and warnings else 0
    if args.json:
        emit_json(
            {
                "project": facts["project"],
                "git": facts["git"],
                "frameworks": facts["frameworks"],
                "project_config": facts.get("project_config"),
                "coverage": checks,
            }
        )
        return exit_code

    _print_overview(facts)
    _print_stack(facts)
    _print_dependencies(facts)
    _print_endpoints(facts)
    _print_database(facts)
    _print_coverage(checks)
    ui.summary(
        t("Doctor complete", "Doctor selesai"),
        [
            (t("Needs attention", "Perlu dicek"), str(warnings)),
            ("Info", str(len(checks) - warnings)),
        ],
        subtitle=facts["project"]["name"],
    )
    return exit_code


# ---- one function per block of the output -------------------------------------------------


def _print_overview(facts: dict) -> None:
    """Project name and where it came from, git state, config file, file count."""
    project, git = facts["project"], facts["git"]
    config = facts.get("project_config") or {}
    name = f"{project['name']} ({t('from', 'dari')} {project['name_source']})"
    if project.get("version"):
        name += f", {t('version', 'versi')} {project['version']}"
    rows = [[t("Project", "Proyek"), name]]
    if git.get("is_git"):
        state = f"{git['commit_short']} · {git.get('branch') or 'detached'}"
        if git.get("dirty"):
            state += t(" · uncommitted changes", " · ada perubahan belum di-commit")
        rows.append(["Git", state])
    elif git.get("disabled"):
        rows.append(["Git", t("not used (--no-git)", "tidak dipakai (--no-git)")])
    no_config = t("no .repolens.yml", "tidak ada .repolens.yml")
    rows.append([t("Config", "Konfigurasi"), config.get("file") or no_config])
    rows += [["", f"↳ {applied}"] for applied in config.get("applied", [])]
    languages = ", ".join(f"{x['language']} {x['percent']}%" for x in facts["languages"][:3])
    rows.append(["File", f"{facts['tree']['total_files']} ({languages})"])
    ui.table([], rows, indent=0)


def _print_stack(facts: dict) -> None:
    """Detected frameworks with version and where each came from."""
    ui.section("Tech stack")
    if not facts["frameworks"]:
        ui.skip(t("nothing recognised", "tidak ada yang dikenali"))
        return
    ui.table(
        [], [[f["name"], f["version"] or "?", f"← {f['source']}"] for f in facts["frameworks"]]
    )


def _print_dependencies(facts: dict) -> None:
    """One line per manifest: package count and lock file."""
    ui.section("Dependency")
    if not facts["dependencies"]:
        ui.skip(t("none", "tidak ada"))
        return
    rows = []
    for manifest in facts["dependencies"]:
        count = len(manifest["dependencies"])
        lock = manifest.get("lock") or t("none", "tidak ada")
        rows.append(
            [manifest["manifest"], t(f"{count} packages", f"{count} package"), f"lock: {lock}"]
        )
    ui.table([], rows)


def _print_endpoints(facts: dict) -> None:
    """Endpoint counts per kind (server, client, pages) and framework."""
    ui.section("Endpoints")
    kinds = {"server": "server", "client": t("client", "klien"), "pages": t("pages", "halaman")}
    counts: dict[tuple[str, str], int] = {}
    for kind in kinds:
        for endpoint in facts["endpoints"][kind]:
            key = (kind, endpoint.get("framework") or "-")
            counts[key] = counts.get(key, 0) + 1
    if not counts:
        ui.skip(t("none", "tidak ada"))
        return
    ui.table([], [[kinds[kind], fw, str(n)] for (kind, fw), n in sorted(counts.items())])


def _print_database(facts: dict) -> None:
    """Database engines, and how many tables came from each source."""
    ui.section("Database")
    database = facts["database"]
    engines = ", ".join(e["engine"] for e in database["engines"]) or "-"
    per_source: dict[str, int] = {}
    for table in database["tables"]:
        per_source[table["source"]] = per_source.get(table["source"], 0) + 1
    rows = [["Engine", engines]]
    rows += [[source, t(f"{n} tables", f"{n} tabel")] for source, n in per_source.items()]
    ui.table([], rows)


def _print_coverage(checks: list[dict]) -> None:
    """Findings that need attention first, then the informational ones, each with its fix."""
    ui.section(t("Coverage", "Cakupan"))
    if not checks:
        ui.ok(t("No sign of missing sections.", "Tidak ada indikasi bagian yang terlewat."))
    for check in sorted(checks, key=lambda c: c["level"] != "warn"):
        show = ui.warn if check["level"] == "warn" else ui.info
        show(f"[{check['area']}] {check['message']}")
        if check.get("hint"):
            ui.hint(check["hint"])
