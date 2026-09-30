"""Command line interface.

  repolens                         interactive menu (in a terminal)
  repolens scan <folder|git-url> [--ref v1.2.0] [--compare-ref v1.1.0] [--no-git] [--format pdf,docx,md]
  repolens doctor <folder>         what was detected and what is probably missing, without writing documents
  repolens init <folder>           create a .repolens.yml template from what was detected
  repolens export <scan.json>      render documents again from a previous scan
  repolens diff <old.json> <new.json>
  repolens auth login|status|logout   your own Anthropic API key and model for the AI summary
  repolens update [--check]      install the newest release
  repolens completion bash|zsh|fish

Every command takes --lang en|id (default: REPOLENS_LANG or en) and --debug.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from contextlib import ExitStack
from pathlib import Path

from repolens import __version__, ai, auth, completion, coverage, credentials, diff, document, projectconfig, selfupdate, ui
from repolens.i18n import LANGUAGES, get_lang, label, set_lang, t
from repolens.render import docx_out, markdown, pdf_out
from repolens.scanner import is_git_url, prepared_source, scan

RENDERERS = {"md": (markdown.render, ".md"), "docx": (docx_out.render, ".docx"), "pdf": (pdf_out.render, ".pdf")}
FORMAT_NAMES = {"pdf": "PDF", "docx": "Word", "md": "Markdown"}


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-").lower() or "project"


def _formats(value: str) -> list[str]:
    fmts = [f.strip().lower() for f in value.split(",") if f.strip()]
    unknown = [f for f in fmts if f not in RENDERERS]
    if unknown or not fmts:
        raise argparse.ArgumentTypeError(t(f"unknown format: {', '.join(unknown) or '-'} (choose: pdf, docx, md)",
                                           f"format tidak dikenal: {', '.join(unknown) or '-'} (pilihan: pdf, docx, md)"))
    return list(dict.fromkeys(fmts))


def _positive_int(value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        n = 0
    if n < 1:
        raise argparse.ArgumentTypeError(t(f"must be a whole number of 1 or more, not `{value}`",
                                           f"harus bilangan bulat 1 atau lebih, bukan `{value}`"))
    return n


REQUIRED_KEYS = ("repolens_version", "scanned_at", "source", "project", "tree", "languages", "frameworks", "dependencies",
                 "endpoints", "database", "config", "security")


def load_scan(path: str) -> dict:
    """Read a scan.json produced by `repolens scan`, with a readable error instead of a traceback."""
    file = Path(path)
    if not file.is_file():
        raise FileNotFoundError(t("File not found: ", "File tidak ditemukan: ") + str(file))
    try:
        facts = json.loads(file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError(t(f"{file} is not valid JSON: {exc}", f"{file} bukan JSON yang valid: {exc}")) from None
    if isinstance(facts, dict) and "docgen_version" in facts:  # written before the rename to repolens
        facts.setdefault("repolens_version", facts.pop("docgen_version"))
    missing = [k for k in REQUIRED_KEYS if not isinstance(facts, dict) or k not in facts]
    if missing:
        keys = ", ".join(missing)
        raise RuntimeError(t(f"{file} is not a `repolens scan` result (missing: {keys}).",
                             f"{file} bukan hasil `repolens scan` (tidak ada: {keys})."))
    return facts


def _identity(facts: dict) -> str | None:
    """What makes two scans the same project: the git remote, or the scanned folder when there is none."""
    remote = (facts.get("git") or {}).get("remote")
    if remote:
        return re.sub(r"\.git$", "", remote.rstrip("/")).lower()
    return (facts.get("source") or {}).get("location")


def _check_output(facts: dict, out_dir: Path, force: bool) -> str | None:
    """Refuse to overwrite another project's documents that share the same name and release label.

    Returns a note when the same project is overwritten at a different commit."""
    previous_file = out_dir / "scan.json"
    if force or not previous_file.is_file():
        return None
    try:
        previous = json.loads(previous_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    old_id, new_id = _identity(previous), _identity(facts)
    if old_id and new_id and old_id != new_id:
        project = facts["project"]
        name, release = project["name"], document.release_label(facts)
        origin = t(f"from {project['name_source']}", f"dari {project['name_source']}")
        unique = _slug(project.get("folder") or "") or "my-app"
        raise RuntimeError(t(
            f"Two different projects are both called {name} {release} ({origin}), so their documents would overwrite each other.\n"
            f"  already in {_display_path(out_dir)}:  {old_id}\n"
            f"  scanned now:  {new_id}\n"
            "Fix it with one of:\n"
            f"  → give this project its own name: add `name: {unique}` to its .repolens.yml\n"
            f"  → write somewhere else:  --out {_display_path(out_dir.parent / unique)}\n"
            "  → overwrite anyway:  --force",
            f"Dua proyek berbeda sama-sama bernama {name} {release} ({origin}), jadi dokumennya akan saling menimpa.\n"
            f"  sudah ada di {_display_path(out_dir)}:  {old_id}\n"
            f"  yang dipindai sekarang:  {new_id}\n"
            "Perbaiki dengan salah satu:\n"
            f"  → beri nama sendiri untuk proyek ini: tambahkan `name: {unique}` di .repolens.yml-nya\n"
            f"  → tulis ke folder lain:  --out {_display_path(out_dir.parent / unique)}\n"
            "  → tetap timpa:  --force"))
    old_commit, new_commit = (previous.get("git") or {}).get("commit_short"), (facts.get("git") or {}).get("commit_short")
    if old_commit and new_commit and old_commit != new_commit:
        return t(f"Replaced the previous result (commit {old_commit} → {new_commit})",
                 f"Menimpa hasil sebelumnya (commit {old_commit} → {new_commit})")
    return None


def export(facts: dict, out_dir: Path, formats: list[str], force: bool = True) -> list[Path]:
    note = _check_output(facts, out_dir, force)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"{_slug(facts['project']['name'])}-{_slug(document.release_label(facts))}"
    (out_dir / "scan.json").write_text(json.dumps(facts, indent=2, ensure_ascii=False), encoding="utf-8")
    blocks = document.build(facts)
    written = [out_dir / "scan.json"]
    for fmt in formats:
        render, ext = RENDERERS[fmt]
        written.append(render(blocks, out_dir / f"{base}{ext}"))
    if note:
        ui.info(note)
    return written


def _display_path(path: Path) -> str:
    """Relative to the current folder when that is shorter (docs-output/app-1.0 instead of /Users/…)."""
    try:
        rel = os.path.relpath(path)
    except ValueError:  # different drive on Windows
        return str(path)
    return rel if len(rel) < len(str(path)) else str(path)


def _emit_json(data: dict) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _stack_line(facts: dict) -> str:
    return ", ".join(f["name"] + (" " + f["version"] if f["version"] else "") for f in facts["frameworks"][:6]) or "-"


def _print_brief_coverage(checks: list[dict], source: str) -> None:
    warns = [c for c in checks if c["level"] == "warn"]
    if not warns:
        return
    ui.out.print()
    ui.warn(t(f"{len(warns)} items may leave the document incomplete:", f"{len(warns)} hal kemungkinan membuat dokumen belum lengkap:"), indent="")
    for c in warns:
        ui.out.print(f"  - [{c['area']}] {c['message']}", markup=False)
    ui.hint(t(f"Details and fixes: repolens doctor {source}", f"Detail dan cara melengkapinya: repolens doctor {source}"), indent="  ")


# ---- scan -------------------------------------------------------------------

def _check_source_options(args) -> None:
    if not is_git_url(args.source) and not Path(args.source).expanduser().is_dir():
        raise FileNotFoundError(t("Folder not found: ", "Folder tidak ditemukan: ") + args.source)
    if getattr(args, "no_git", False):
        if is_git_url(args.source):
            raise RuntimeError(t("--no-git only works with a local folder; a git URL has to be cloned with git.",
                                 "--no-git hanya untuk folder lokal; URL git harus di-clone dengan git."))
        if getattr(args, "ref", None) or getattr(args, "compare_ref", None):
            raise RuntimeError(t("--no-git cannot be combined with --ref or --compare-ref, which read from git history.",
                                 "--no-git tidak bisa digabung dengan --ref atau --compare-ref, yang membaca riwayat git."))


def _source_detail(args) -> str:
    source = args.source
    if args.ref:
        source += f" @ {args.ref}"
    elif getattr(args, "no_git", False):
        source += t(" (plain folder, no git)", " (folder biasa, tanpa git)")
    elif not is_git_url(args.source):
        source += t(" (working tree)", " (working tree)")
    return source


def cmd_scan(args) -> int:
    started = time.monotonic()
    _check_source_options(args)
    args.model = args.model or credentials.default_model(ai.DEFAULT_MODEL)
    previous = load_scan(args.compare) if args.compare else None  # fail before a long scan, not after
    formats = ", ".join(FORMAT_NAMES[f] for f in args.format)
    ai_state = t("off", "mati") if args.no_ai or args.dry_run else args.model
    ui.header("Scan", f"{_source_detail(args)}  ·  {formats}  ·  AI: {ai_state}  ·  {LANGUAGES[get_lang()]}")

    use_git = not args.no_git
    with ExitStack() as stack:
        if is_git_url(args.source) or args.ref:
            with ui.task(t("Preparing source (git clone)", "Menyiapkan sumber (git clone)"),
                         t("Source ready", "Sumber siap")):
                root, info = stack.enter_context(prepared_source(args.source, args.ref))
        else:
            root, info = stack.enter_context(prepared_source(args.source, None))
            if not use_git:
                info["no_git"] = True
        facts = scan(root, info, tree_depth=args.tree_depth, log=ui.log, use_git=use_git)

    if previous:
        facts["changes"] = diff.compare(previous, facts)
        ui.ok(t(f"Compared with {args.compare}", f"Dibandingkan dengan {args.compare}"))
    elif args.compare_ref:
        with ui.task(t(f"Scanning comparison ref {args.compare_ref}", f"Memindai pembanding {args.compare_ref}"),
                     t(f"Compared with {args.compare_ref}", f"Dibandingkan dengan {args.compare_ref}")):
            with prepared_source(args.source, args.compare_ref) as (root, info):
                previous = scan(root, info, tree_depth=args.tree_depth)
            facts["changes"] = diff.compare(previous, facts)

    if args.dry_run:
        ui.skip(t("AI skipped (--dry-run)", "AI dilewati (--dry-run)"))
    elif args.no_ai:
        ui.skip(t("AI skipped (--no-ai)", "AI dilewati (--no-ai)"))
    else:
        ai_started = time.monotonic()
        with ui.out.status(t(f"Writing the summary with AI ({args.model})…", f"Menyusun ringkasan dengan AI ({args.model})…")):
            facts["ai"] = ai.generate(facts, model=args.model, log=ui.log)
        if facts["ai"]:
            ui.ok(t("AI summary written", "Ringkasan AI selesai") + f" [{time.monotonic() - ai_started:.1f}s]")

    release = document.release_label(facts)
    out_dir = Path(args.out) / f"{_slug(facts['project']['name'])}-{_slug(release)}"
    written: list[Path] = []
    if args.dry_run:
        ui.skip(t(f"Nothing written (--dry-run); would write to {out_dir}", f"Tidak ada yang ditulis (--dry-run); tujuan: {out_dir}"))
    else:
        with ui.task(t(f"Rendering {formats}", f"Membuat {formats}"), t(f"Rendered {formats}", f"Selesai membuat {formats}")):
            written = export(facts, out_dir, args.format, force=args.force)

    eps, checks = facts["endpoints"], facts.get("coverage") or []
    warns = sum(1 for c in checks if c["level"] == "warn")
    secrets = facts["security"]["secrets"]
    high = sum(1 for s in secrets if s.get("severity") == "high")
    elapsed = time.monotonic() - started
    if args.json:
        _emit_json({
            "project": facts["project"]["name"], "release": release, "dry_run": args.dry_run,
            "output_dir": None if args.dry_run else str(out_dir), "files": [str(p) for p in written],
            "stats": {"files": facts["tree"]["total_files"], "server_endpoints": len(eps["server"]),
                      "client_calls": len(eps["client"]), "pages": len(eps["pages"]),
                      "tables": len(facts["database"]["tables"]), "security_findings": len(secrets)},
            "frameworks": facts["frameworks"], "coverage": checks, "seconds": round(elapsed, 2),
        })
    else:
        rows = [
            ("Stack", _stack_line(facts)),
            (t("Endpoints", "Endpoint"), t(f"{len(eps['server'])} server · {len(eps['client'])} client · {len(eps['pages'])} pages",
                            f"{len(eps['server'])} server · {len(eps['client'])} klien · {len(eps['pages'])} halaman")),
            ("Database", t(f"{len(facts['database']['tables'])} tables/models", f"{len(facts['database']['tables'])} tabel/model")),
            (t("Security", "Keamanan"), t(f"{len(secrets)} findings ({high} high)", f"{len(secrets)} temuan ({high} tinggi)")),
        ]
        if written:
            files = ", ".join(p.suffix.lstrip(".") if p.name != "scan.json" else "scan.json" for p in written)
            rows.append(("Output", f"{_display_path(out_dir)}/  ({files})"))
        title = t("Dry run complete", "Dry run selesai") if args.dry_run else t("Documentation ready", "Dokumentasi siap")
        ui.summary(title, rows, subtitle=f"{facts['project']['name']} {release}  ·  {elapsed:.1f}s")
        _print_brief_coverage(checks, args.source)
    return 1 if args.strict and warns else 0


# ---- doctor -----------------------------------------------------------------

def cmd_doctor(args) -> int:
    _check_source_options(args)
    use_git = not args.no_git
    ui.header("Doctor", _source_detail(args))
    with ui.out.status(t("Scanning…", "Memindai…")):
        with prepared_source(args.source, args.ref) as (root, info):
            facts = scan(root, info, use_git=use_git)
    checks = facts["coverage"]
    warns = sum(1 for c in checks if c["level"] == "warn")
    if args.json:
        _emit_json({"project": facts["project"], "git": facts["git"], "frameworks": facts["frameworks"],
                    "project_config": facts.get("project_config"), "coverage": checks})
        return 1 if args.strict and warns else 0

    p, eps, db, git = facts["project"], facts["endpoints"], facts["database"], facts["git"]
    pcfg = facts.get("project_config") or {}
    langs = ", ".join(f"{lng['language']} {lng['percent']}%" for lng in facts["languages"][:3])
    rows = [[t("Project", "Proyek"), f"{p['name']} ({t('from', 'dari')} {p['name_source']})" + (f", {t('version', 'versi')} {p['version']}" if p.get("version") else "")]]
    if git.get("is_git"):
        rows.append(["Git", f"{git['commit_short']} · {git.get('branch') or 'detached'}"
                     + (t(" · uncommitted changes", " · ada perubahan belum di-commit") if git.get("dirty") else "")])
    elif git.get("disabled"):
        rows.append(["Git", t("not used (--no-git)", "tidak dipakai (--no-git)")])
    rows.append([t("Config", "Konfigurasi"), pcfg.get("file") or t("no .repolens.yml", "tidak ada .repolens.yml")])
    rows += [["", f"↳ {a}"] for a in pcfg.get("applied", [])]
    rows.append(["File", f"{facts['tree']['total_files']} ({langs})"])
    ui.table([], rows, indent=0)

    ui.section("Tech stack")
    if facts["frameworks"]:
        ui.table([], [[f["name"], f["version"] or "?", f"← {f['source']}"] for f in facts["frameworks"]])
    else:
        ui.skip(t("nothing recognised", "tidak ada yang dikenali"))

    ui.section("Dependency")
    if facts["dependencies"]:
        ui.table([], [[m["manifest"], t(f"{len(m['dependencies'])} packages", f"{len(m['dependencies'])} package"),
                       "lock: " + (m.get("lock") or t("none", "tidak ada"))] for m in facts["dependencies"]])
    else:
        ui.skip(t("none", "tidak ada"))

    ui.section("Endpoints")
    kinds = {"server": "server", "client": t("client", "klien"), "pages": t("pages", "halaman")}
    counts: dict[tuple[str, str], int] = {}
    for kind in kinds:
        for e in eps[kind]:
            counts[(kind, e.get("framework") or "-")] = counts.get((kind, e.get("framework") or "-"), 0) + 1
    if counts:
        ui.table([], [[kinds[k], fw, str(n)] for (k, fw), n in sorted(counts.items())])
    else:
        ui.skip(t("none", "tidak ada"))

    ui.section("Database")
    engines = ", ".join(e["engine"] for e in db["engines"]) or "-"
    by_src: dict[str, int] = {}
    for tbl in db["tables"]:
        by_src[tbl["source"]] = by_src.get(tbl["source"], 0) + 1
    ui.table([], [["Engine", engines]] + [[src, t(f"{n} tables", f"{n} tabel")] for src, n in by_src.items()])

    ui.section(t("Coverage", "Cakupan"))
    if not checks:
        ui.ok(t("No sign of missing sections.", "Tidak ada indikasi bagian yang terlewat."))
    for c in sorted(checks, key=lambda c: c["level"] != "warn"):
        (ui.warn if c["level"] == "warn" else ui.info)(f"[{c['area']}] {c['message']}")
        if c.get("hint"):
            ui.hint(c["hint"])
    ui.summary(t("Doctor complete", "Doctor selesai"), [
        (t("Needs attention", "Perlu dicek"), str(warns)),
        ("Info", str(len(checks) - warns)),
    ], subtitle=f"{p['name']}")
    return 1 if args.strict and warns else 0


# ---- init -------------------------------------------------------------------

def _init_template(name: str, findings: list[str], version_line: str, frameworks: str) -> str:
    lines = [
        t(f"# repolens configuration for {name}.", f"# Konfigurasi repolens untuk {name}."),
        t("# Every key is optional. Fill in only what cannot be detected automatically.",
          "# Semua key opsional. Isi hanya yang tidak bisa terdeteksi otomatis."),
        t("# Check the result with: repolens doctor .", "# Cek hasilnya dengan: repolens doctor ."),
    ]
    if findings:
        lines += ["#", t("# Findings when this file was created:", "# Temuan saat file ini dibuat:")]
        lines += [f"#   - {f}" for f in findings]
    lines += [
        "", f"name: {name}", t("# description: Short project description", "# description: Deskripsi singkat proyek"),
        version_line, frameworks,
        t("# Route files outside the standard locations (Laravel, CodeIgniter 3/4 are recognised):",
          "# File route di luar lokasi standar (Laravel, CodeIgniter 3/4 dikenali otomatis):"),
        "# routes:", "#   - app/Config/RoutesAdmin.php", "",
        t("# Schema-only SQL dump (may be a git-ignored file):", "# SQL dump skema tanpa data (boleh file yang di-.gitignore):"),
        "# schema:", "#   - database/schema.sql", "",
        t("# Folders that do not need scanning:", "# Folder yang tidak perlu dipindai:"),
        "# ignore:", "#   - public/assets/vendor", "",
        t("# Endpoints created dynamically that cannot be detected:", "# Endpoint yang dibuat dinamis dan tidak terdeteksi:"),
        "# endpoints:",
        "#   - {method: GET, path: /api/health, handler: Health::index, note: " + t("created through auto-routing", "dibuat lewat auto-routing") + "}",
        "", t("# Notes shown in the document:", "# Catatan yang ditampilkan di dokumen:"),
        "# notes:", "#   - " + t("Auto-routing is enabled in production.", "Auto-routing aktif di production."), "",
    ]
    return "\n".join(lines)


def cmd_init(args) -> int:
    if is_git_url(args.source):
        raise RuntimeError(t("`repolens init` needs a local folder, because .repolens.yml is written into the repository. "
                             "Clone the repository first, then run `repolens init <folder>`.",
                             "`repolens init` butuh folder lokal, karena .repolens.yml ditulis ke dalam repository. "
                             "Clone repository-nya dulu, lalu jalankan `repolens init <folder>`."))
    root = Path(args.source).resolve()
    if not root.is_dir():
        raise FileNotFoundError(t("Folder not found: ", "Folder tidak ditemukan: ") + str(root))
    existing = next((root / n for n in projectconfig.FILENAMES + projectconfig.LEGACY_FILENAMES if (root / n).exists()), None)
    if existing and not args.force:
        ui.error(t(f"{existing} already exists. Use --force to overwrite.", f"{existing} sudah ada. Pakai --force untuk menimpa."))
        return 1
    ui.header("Init", str(root))
    with ui.out.status(t("Scanning…", "Memindai…")):
        facts = scan(root, {"type": "local", "location": str(root), "ref": None}, use_git=not args.no_git)
    findings = [f"[{c['area']}] {c['message']}" for c in facts["coverage"] if c["level"] == "warn"]
    main_fw = coverage.BACKEND | coverage.FRONTEND | coverage.MOBILE
    missing = [f for f in facts["frameworks"] if f["name"] in main_fw and (not f["version"] or re.match(r"^[\^~><=*]", f["version"]))]
    if missing:
        fw_lines = [t("# Framework versions that could not be read from a lock file:", "# Versi framework yang tidak terbaca dari lock file:"),
                    "frameworks:"]
        for f in missing:
            detected = f["version"] or t("unknown", "tidak diketahui")
            fw_lines += [f"  - name: {f['name']}", f"    version:            # {t('detected', 'terdeteksi')}: {detected}"]
        frameworks = "\n".join(fw_lines) + "\n"
    else:
        frameworks = "# frameworks:\n#   - {name: CodeIgniter 4, version: 4.4.8}\n"
    version_line = ("# version: 1.0.0" if facts["project"].get("version") else
                    "version:              # " + t("no version in any manifest, fill in manually", "tidak ada versi di manifest, isi manual"))
    if existing:
        existing.unlink()
    target = root / ".repolens.yml"
    target.write_text(_init_template(facts["project"]["name"], findings, version_line, frameworks), encoding="utf-8")
    ui.ok(t(f"Created {target}", f"Dibuat: {target}"))
    ui.hint(t("Fill it in, then run `repolens doctor .` to check.", "Lengkapi isinya, lalu jalankan `repolens doctor .` untuk mengecek."), indent="  ")
    return 0


# ---- export & diff ----------------------------------------------------------

def cmd_export(args) -> int:
    facts = load_scan(args.scan)
    if not args.lang_given:
        set_lang(facts.get("lang") or "id")  # scans made before `lang` existed were written in Indonesian
    out_dir = Path(args.out) if args.out else Path(args.scan).parent
    formats = ", ".join(FORMAT_NAMES[f] for f in args.format)
    ui.header("Export", f"{args.scan}  ·  {formats}  ·  {LANGUAGES[get_lang()]}")
    if facts.get("lang") and facts["lang"] != get_lang():
        ui.info(t("Findings and notes produced during the scan stay in the scan's language. Scan again for a full translation.",
                  "Temuan dan catatan hasil scan tetap dalam bahasa saat scan. Scan ulang untuk terjemahan penuh."))
    with ui.task(t(f"Rendering {formats}", f"Membuat {formats}")):
        written = export(facts, out_dir, args.format)
    for path in written:
        ui.out.print(f"    {path}", markup=False)
    return 0


def cmd_diff(args) -> int:
    old, new = load_scan(args.old), load_scan(args.new)
    changes = diff.compare(old, new)
    if args.json:
        _emit_json(changes)
        return 0
    ui.header("Diff", f"{changes['from']} → {changes['to']}")
    if diff.is_empty(changes):
        ui.ok(t("No changes.", "Tidak ada perubahan."))
        return 0
    titles = {"frameworks": "Tech stack", "platforms": "Platform", "endpoints": "Endpoints", "database": "Database",
              "env": "Environment", "dependencies": "Dependency"}
    for section, title in titles.items():
        items = changes[section]
        if not items:
            continue
        ui.section(f"{title} ({len(items)})")
        rows = []
        for c in items[:50]:
            row = [label(c["change"])] if "change" in c else []
            row += [str(v) for k, v in c.items() if k != "change" and v is not None]
            rows.append(row)
        width = max(len(r) for r in rows)
        ui.table([], [r + [""] * (width - len(r)) for r in rows])
        if len(items) > 50:
            ui.skip(t(f"… {len(items) - 50} more (use --json for the full list)", f"… {len(items) - 50} lagi (pakai --json untuk daftar lengkap)"))
    return 0


# ---- auth -------------------------------------------------------------------

def cmd_auth(args) -> int:
    if args.action == "login":
        return auth.login(model=args.model, verify=not args.no_verify)
    if args.action == "logout":
        return auth.logout()
    return auth.status(as_json=args.json, verify=not args.offline)


def cmd_update(args) -> int:
    return selfupdate.run(check_only=args.check)


def cmd_completion(args) -> int:
    sys.stdout.write(completion.script(args.shell, build_parser()))
    return 0


# ---- parser & entry point ---------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--lang", choices=sorted(LANGUAGES), help=t("Output language: en or id (default: REPOLENS_LANG or en)",
                                                                   "Bahasa output: en atau id (default: REPOLENS_LANG atau en)"))
    common.add_argument("--debug", action="store_true", help=t("Show the full traceback on unexpected errors", "Tampilkan traceback lengkap saat error tak terduga"))

    parser = argparse.ArgumentParser(prog="repolens", parents=[common],
                                     description=t("Generate technical documentation from a repository. Run without arguments for the interactive menu.",
                                                   "Buat dokumentasi teknis dari repository. Jalankan tanpa argumen untuk menu interaktif."))
    parser.add_argument("--version", action="version", version=f"repolens {__version__}")
    sub = parser.add_subparsers(dest="command")

    s = sub.add_parser("scan", parents=[common], help=t("Scan a repository and export documentation", "Pindai repository dan export dokumentasi"))
    s.add_argument("source", help=t("Local folder or git URL (https/ssh)", "Folder lokal atau URL git (https/ssh)"))
    s.add_argument("--ref", help=t("Tag, branch, or commit to scan (your working tree is not touched)",
                                   "Tag, branch, atau commit yang dipindai (working tree Anda tidak disentuh)"))
    s.add_argument("--no-git", action="store_true", help=t("Read the local folder as plain files: everything on disk, no .gitignore, no git info",
                                                           "Baca folder lokal sebagai file biasa: semua file di disk, tanpa .gitignore dan info git"))
    cmp = s.add_mutually_exclusive_group()
    cmp.add_argument("--compare-ref", help=t("Compare with another tag/commit, e.g. the previous release",
                                             "Bandingkan dengan tag/commit lain, misalnya rilis sebelumnya"))
    cmp.add_argument("--compare", help=t("Compare with a scan.json from an earlier scan", "Bandingkan dengan scan.json dari pemindaian sebelumnya"))
    s.add_argument("--format", type=_formats, default=["pdf", "docx", "md"], help=t("pdf,docx,md (default: all three)", "pdf,docx,md (default: ketiganya)"))
    s.add_argument("--out", default="docs-output", help=t("Output folder (default: ./docs-output)", "Folder output (default: ./docs-output)"))
    s.add_argument("--no-ai", action="store_true", help=t("No AI summary (nothing is sent anywhere)", "Tanpa ringkasan AI (tidak ada data yang dikirim keluar)"))
    s.add_argument("--model", help=t(f"Claude model (default: the one from `repolens auth login`, else {ai.DEFAULT_MODEL})",
                                     f"Model Claude (default: pilihan di `repolens auth login`, atau {ai.DEFAULT_MODEL})"))
    s.add_argument("--tree-depth", type=_positive_int, help=t("Folder structure depth (default: 3, or tree_depth in .repolens.yml)",
                                                              "Kedalaman struktur folder (default: 3, atau tree_depth di .repolens.yml)"))
    s.add_argument("--dry-run", action="store_true", help=t("Scan and show the summary without writing files or calling AI",
                                                            "Pindai dan tampilkan ringkasan tanpa menulis file atau memanggil AI"))
    s.add_argument("--strict", action="store_true", help=t("Exit code 1 when something needs attention (for CI)", "Exit code 1 jika ada temuan 'perlu dicek' (untuk CI)"))
    s.add_argument("--force", action="store_true", help=t("Overwrite the output folder even if it holds another project's documents",
                                                          "Timpa folder output walaupun berisi dokumen proyek lain"))
    s.add_argument("--json", action="store_true", help=t("Print a JSON result instead of the human output", "Cetak hasil JSON, bukan tampilan biasa"))
    s.set_defaults(func=cmd_scan)

    doc = sub.add_parser("doctor", parents=[common], help=t("Check what is detected and what is missing, without writing documents",
                                                            "Cek apa yang terdeteksi dan apa yang terlewat, tanpa membuat dokumen"))
    doc.add_argument("source", nargs="?", default=".")
    doc.add_argument("--ref", help=t("Tag, branch, or commit to check", "Tag, branch, atau commit yang dicek"))
    doc.add_argument("--no-git", action="store_true", help=t("Read the folder as plain files", "Baca folder sebagai file biasa"))
    doc.add_argument("--strict", action="store_true", help=t("Exit code 1 when something needs attention (for CI)", "Exit code 1 jika ada temuan 'perlu dicek' (untuk CI)"))
    doc.add_argument("--json", action="store_true", help=t("Print a JSON result", "Cetak hasil JSON"))
    doc.set_defaults(func=cmd_doctor)

    ini = sub.add_parser("init", parents=[common], help=t("Create a .repolens.yml template from what is detected", "Buat template .repolens.yml berdasarkan hasil deteksi"))
    ini.add_argument("source", nargs="?", default=".")
    ini.add_argument("--no-git", action="store_true", help=t("Read the folder as plain files", "Baca folder sebagai file biasa"))
    ini.add_argument("--force", action="store_true", help=t("Overwrite an existing .repolens.yml", "Timpa .repolens.yml yang sudah ada"))
    ini.set_defaults(func=cmd_init)

    e = sub.add_parser("export", parents=[common], help=t("Render documents again from scan.json without scanning", "Render ulang dokumen dari scan.json tanpa memindai lagi"))
    e.add_argument("scan")
    e.add_argument("--format", type=_formats, default=["pdf", "docx", "md"])
    e.add_argument("--out")
    e.set_defaults(func=cmd_export)

    d = sub.add_parser("diff", parents=[common], help=t("Show the changes between two scan.json files", "Tampilkan perubahan antara dua scan.json"))
    d.add_argument("old")
    d.add_argument("new")
    d.add_argument("--json", action="store_true", help=t("Print the changes as JSON", "Cetak perubahan sebagai JSON"))
    d.set_defaults(func=cmd_diff)

    a = sub.add_parser("auth", parents=[common], help=t("Set your own Anthropic API key and model for the AI summary",
                                                        "Atur API key Anthropic dan model Anda sendiri untuk ringkasan AI"))
    actions = a.add_subparsers(dest="action")
    login = actions.add_parser("login", parents=[common], help=t("Save an API key (asked for, or read from stdin), after checking it",
                                                                 "Simpan API key (ditanyakan, atau dibaca dari stdin) setelah dicek"))
    login.add_argument("--model", help=t(f"Default model for scans (e.g. {', '.join(ai.MODELS)})",
                                         f"Model default untuk scan (mis. {', '.join(ai.MODELS)})"))
    login.add_argument("--no-verify", action="store_true", help=t("Save without checking the key with Anthropic", "Simpan tanpa mengecek key ke Anthropic"))
    status = actions.add_parser("status", parents=[common], help=t("Show which key and model are used, and check them",
                                                                   "Tampilkan key dan model yang dipakai, lalu cek"))
    status.add_argument("--offline", action="store_true", help=t("Do not contact Anthropic", "Tanpa menghubungi Anthropic"))
    status.add_argument("--json", action="store_true", help=t("Print a JSON result", "Cetak hasil JSON"))
    actions.add_parser("logout", parents=[common], help=t("Remove the saved key", "Hapus key yang disimpan"))
    a.set_defaults(func=cmd_auth, action="status", offline=False, json=False)

    u = sub.add_parser("update", parents=[common], help=t("Install the newest RepoLens release", "Pasang rilis RepoLens terbaru"))
    u.add_argument("--check", action="store_true", help=t("Only report whether a newer release exists", "Hanya cek apakah ada rilis yang lebih baru"))
    u.set_defaults(func=cmd_update)

    c = sub.add_parser("completion", parents=[common], help=t("Print a shell completion script", "Cetak script tab-completion untuk shell"))
    c.add_argument("shell", choices=completion.SHELLS)
    c.set_defaults(func=cmd_completion)
    return parser


def _initial_lang(argv: list[str]) -> str:
    """The language is needed before argparse runs (help texts are translated too)."""
    for i, arg in enumerate(argv):
        if arg == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--lang="):
            return arg.split("=", 1)[1]
    return os.environ.get("REPOLENS_LANG") or os.environ.get("DOCGEN_LANG") or "en"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    lang = _initial_lang(argv)
    set_lang(lang if lang in LANGUAGES else "en")
    debug = "--debug" in argv or bool(os.environ.get("REPOLENS_DEBUG") or os.environ.get("DOCGEN_DEBUG"))
    ui.set_quiet(False)
    try:
        if not argv:
            if not (sys.stdin.isatty() and sys.stdout.isatty()):
                build_parser().print_help()
                return 0
            from repolens import menu
            argv = menu.run()
            if not argv:
                return 0
            set_lang(_initial_lang(argv))
        args = build_parser().parse_args(argv)
        if not getattr(args, "func", None):
            build_parser().print_help()
            return 0
        args.lang_given = args.lang is not None
        if args.lang:
            set_lang(args.lang)
        ui.set_quiet(getattr(args, "json", False))
        return args.func(args)
    except (RuntimeError, OSError) as exc:
        if debug:
            raise
        ui.error(str(exc))
        return 1
    except KeyboardInterrupt:
        ui.error(t("Cancelled.", "Dibatalkan."))
        return 130
    except Exception as exc:  # a bug in repolens: short message by default, full traceback with --debug
        if debug:
            raise
        ui.error(t(f"Unexpected error ({type(exc).__name__}): {exc}\nRun again with --debug for details, and report it to the repolens maintainers.",
                   f"Error tak terduga ({type(exc).__name__}): {exc}\nJalankan ulang dengan --debug untuk detail, lalu laporkan ke pengelola repolens."))
        return 2
