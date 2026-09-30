"""`repolens scan <folder|git-url>`: scan a repository and write the documentation.

The command runs these steps in order, each in its own function below:
  1. read the source (a local folder, a folder at a git ref, or a git URL) into facts
  2. compare with an earlier scan or git ref, when asked
  3. ask the AI for the narrative sections, unless --no-ai / --dry-run
  4. write scan.json and the documents, unless --dry-run
  5. print a summary (or JSON with --json)
"""

from __future__ import annotations

import time
from contextlib import ExitStack
from pathlib import Path

from repolens import ai, credentials, diff, document, ui
from repolens.commands._common import (
    ALL_FORMATS,
    add_command,
    check_source_options,
    count_warnings,
    emit_json,
    flag,
    formats,
    option,
    positive_int,
    source_detail,
)
from repolens.i18n import LANGUAGES, get_lang, t
from repolens.output import display_path, format_list, load_scan, output_dir, write_documents
from repolens.scanner import is_git_url, prepared_source, scan

NAME = "scan"


def register(subparsers, common):
    p = add_command(
        subparsers,
        NAME,
        common,
        "Scan a repository and export documentation",
        "Pindai repository dan export dokumentasi",
    )
    option(
        p, "source", "Local folder or git URL (https/ssh)", "Folder lokal atau URL git (https/ssh)"
    )
    option(
        p,
        "--ref",
        "Tag, branch, or commit to scan (your working tree is not touched)",
        "Tag, branch, atau commit yang dipindai (working tree Anda tidak disentuh)",
    )
    flag(
        p,
        "--no-git",
        "Read the local folder as plain files: everything on disk, no .gitignore, no git info",
        "Baca folder lokal sebagai file biasa: semua file di disk, tanpa .gitignore dan info git",
    )
    compare = p.add_mutually_exclusive_group()
    option(
        compare,
        "--compare-ref",
        "Compare with another tag/commit, e.g. the previous release",
        "Bandingkan dengan tag/commit lain, misalnya rilis sebelumnya",
    )
    option(
        compare,
        "--compare",
        "Compare with a scan.json from an earlier scan",
        "Bandingkan dengan scan.json dari pemindaian sebelumnya",
    )
    option(
        p,
        "--format",
        "pdf,docx,md (default: all three)",
        "pdf,docx,md (default: ketiganya)",
        type=formats,
        default=ALL_FORMATS,
    )
    option(
        p,
        "--out",
        "Output folder (default: ./docs-output)",
        "Folder output (default: ./docs-output)",
        default="docs-output",
    )
    flag(
        p,
        "--no-ai",
        "No AI summary (nothing is sent anywhere)",
        "Tanpa ringkasan AI (tidak ada data yang dikirim keluar)",
    )
    option(
        p,
        "--model",
        f"Claude model (default: the one from `repolens auth login`, else {ai.DEFAULT_MODEL})",
        f"Model Claude (default: pilihan di `repolens auth login`, atau {ai.DEFAULT_MODEL})",
    )
    option(
        p,
        "--tree-depth",
        "Folder structure depth (default: 3, or tree_depth in .repolens.yml)",
        "Kedalaman struktur folder (default: 3, atau tree_depth di .repolens.yml)",
        type=positive_int,
    )
    flag(
        p,
        "--dry-run",
        "Scan and show the summary without writing files or calling AI",
        "Pindai dan tampilkan ringkasan tanpa menulis file atau memanggil AI",
    )
    flag(
        p,
        "--strict",
        "Exit code 1 when something needs attention (for CI)",
        "Exit code 1 jika ada temuan 'perlu dicek' (untuk CI)",
    )
    flag(
        p,
        "--force",
        "Overwrite the output folder even if it holds another project's documents",
        "Timpa folder output walaupun berisi dokumen proyek lain",
    )
    flag(
        p,
        "--json",
        "Print a JSON result instead of the human output",
        "Cetak hasil JSON, bukan tampilan biasa",
    )
    return p


def run(args) -> int:
    started = time.monotonic()
    check_source_options(args)
    args.model = args.model or credentials.default_model(ai.DEFAULT_MODEL)
    previous = load_scan(args.compare) if args.compare else None  # fail before a long scan
    ai_state = t("off", "mati") if args.no_ai or args.dry_run else args.model
    detail = [source_detail(args), format_list(args.format), f"AI: {ai_state}"]
    ui.header("Scan", "  ·  ".join(detail + [LANGUAGES[get_lang()]]))

    facts = _scan_source(args)
    _add_comparison(args, facts, previous)
    _add_ai_summary(args, facts)
    out_dir = output_dir(args.out, facts)
    written = _write(args, facts, out_dir)
    _report(args, facts, out_dir, written, time.monotonic() - started)
    warnings = count_warnings(facts.get("coverage") or [])
    return 1 if args.strict and warnings else 0


# ---- steps --------------------------------------------------------------------------------


def _scan_source(args) -> dict:
    """Step 1: collect the facts. A git URL or --ref is cloned to a temporary folder first."""
    use_git = not args.no_git
    with ExitStack() as stack:
        if is_git_url(args.source) or args.ref:
            with ui.task(
                t("Preparing source (git clone)", "Menyiapkan sumber (git clone)"),
                t("Source ready", "Sumber siap"),
            ):
                root, info = stack.enter_context(prepared_source(args.source, args.ref))
        else:
            root, info = stack.enter_context(prepared_source(args.source, None))
            if not use_git:
                info["no_git"] = True
        return scan(root, info, tree_depth=args.tree_depth, log=ui.log, use_git=use_git)


def _add_comparison(args, facts: dict, previous: dict | None) -> None:
    """Step 2: add facts["changes"] from --compare (a scan.json) or --compare-ref (a git ref)."""
    if previous:
        facts["changes"] = diff.compare(previous, facts)
        ui.ok(t(f"Compared with {args.compare}", f"Dibandingkan dengan {args.compare}"))
        return
    if not args.compare_ref:
        return
    ref = args.compare_ref
    with ui.task(
        t(f"Scanning comparison ref {ref}", f"Memindai pembanding {ref}"),
        t(f"Compared with {ref}", f"Dibandingkan dengan {ref}"),
    ):
        with prepared_source(args.source, ref) as (root, info):
            previous = scan(root, info, tree_depth=args.tree_depth)
        facts["changes"] = diff.compare(previous, facts)


def _add_ai_summary(args, facts: dict) -> None:
    """Step 3: add facts["ai"] with the narrative sections (None when the AI is unavailable)."""
    if args.dry_run:
        ui.skip(t("AI skipped (--dry-run)", "AI dilewati (--dry-run)"))
        return
    if args.no_ai:
        ui.skip(t("AI skipped (--no-ai)", "AI dilewati (--no-ai)"))
        return
    started = time.monotonic()
    with ui.out.status(
        t(
            f"Writing the summary with AI ({args.model})…",
            f"Menyusun ringkasan dengan AI ({args.model})…",
        )
    ):
        facts["ai"] = ai.generate(facts, model=args.model, log=ui.log)
    if facts["ai"]:
        elapsed = time.monotonic() - started
        ui.ok(t("AI summary written", "Ringkasan AI selesai") + f" [{elapsed:.1f}s]")


def _write(args, facts: dict, out_dir: Path) -> list[Path]:
    """Step 4: write scan.json and the documents; nothing with --dry-run."""
    if args.dry_run:
        ui.skip(
            t(
                f"Nothing written (--dry-run); would write to {out_dir}",
                f"Tidak ada yang ditulis (--dry-run); tujuan: {out_dir}",
            )
        )
        return []
    names = format_list(args.format)
    with ui.task(
        t(f"Rendering {names}", f"Membuat {names}"),
        t(f"Rendered {names}", f"Selesai membuat {names}"),
    ):
        return write_documents(facts, out_dir, args.format, force=args.force)


def _report(args, facts: dict, out_dir: Path, written: list[Path], elapsed: float) -> None:
    """Step 5: the closing summary, or the JSON result with --json."""
    if args.json:
        emit_json(_json_result(args, facts, out_dir, written, elapsed))
        return
    rows = _summary_rows(facts)
    if written:
        kinds = ", ".join("scan.json" if p.name == "scan.json" else p.suffix[1:] for p in written)
        rows.append(("Output", f"{display_path(out_dir)}/  ({kinds})"))
    if args.dry_run:
        title = t("Dry run complete", "Dry run selesai")
    else:
        title = t("Documentation ready", "Dokumentasi siap")
    release = document.release_label(facts)
    subtitle = f"{facts['project']['name']} {release}  ·  {elapsed:.1f}s"
    ui.summary(title, rows, subtitle=subtitle)
    _print_brief_coverage(facts.get("coverage") or [], args.source)


# ---- report helpers -----------------------------------------------------------------------


def _summary_rows(facts: dict) -> list[tuple[str, str]]:
    endpoints, tables = facts["endpoints"], len(facts["database"]["tables"])
    server, client, pages = (len(endpoints[k]) for k in ("server", "client", "pages"))
    secrets = facts["security"]["secrets"]
    high = sum(1 for s in secrets if s.get("severity") == "high")
    return [
        ("Stack", _stack_line(facts)),
        (
            t("Endpoints", "Endpoint"),
            t(
                f"{server} server · {client} client · {pages} pages",
                f"{server} server · {client} klien · {pages} halaman",
            ),
        ),
        ("Database", t(f"{tables} tables/models", f"{tables} tabel/model")),
        (
            t("Security", "Keamanan"),
            t(f"{len(secrets)} findings ({high} high)", f"{len(secrets)} temuan ({high} tinggi)"),
        ),
    ]


def _stack_line(facts: dict) -> str:
    """The first six frameworks with their versions: "Laravel 11.9.2, PHP ^8.2"."""
    names = (f["name"] + (" " + f["version"] if f["version"] else "") for f in facts["frameworks"])
    return ", ".join(list(names)[:6]) or "-"


def _json_result(args, facts: dict, out_dir: Path, written: list[Path], elapsed: float) -> dict:
    endpoints = facts["endpoints"]
    return {
        "project": facts["project"]["name"],
        "release": document.release_label(facts),
        "dry_run": args.dry_run,
        "output_dir": None if args.dry_run else str(out_dir),
        "files": [str(p) for p in written],
        "stats": {
            "files": facts["tree"]["total_files"],
            "server_endpoints": len(endpoints["server"]),
            "client_calls": len(endpoints["client"]),
            "pages": len(endpoints["pages"]),
            "tables": len(facts["database"]["tables"]),
            "security_findings": len(facts["security"]["secrets"]),
        },
        "frameworks": facts["frameworks"],
        "coverage": facts.get("coverage") or [],
        "seconds": round(elapsed, 2),
    }


def _print_brief_coverage(checks: list[dict], source: str) -> None:
    """After the summary: the findings that need attention, and where to read more."""
    warnings = [c for c in checks if c["level"] == "warn"]
    if not warnings:
        return
    ui.out.print()
    count = len(warnings)
    ui.warn(
        t(
            f"{count} items may leave the document incomplete:",
            f"{count} hal kemungkinan membuat dokumen belum lengkap:",
        ),
        indent="",
    )
    for check in warnings:
        ui.out.print(f"  - [{check['area']}] {check['message']}", markup=False)
    ui.hint(
        t(
            f"Details and fixes: repolens doctor {source}",
            f"Detail dan cara melengkapinya: repolens doctor {source}",
        ),
        indent="  ",
    )
