"""The start of the document: the title block and the summary section."""

from __future__ import annotations

from datetime import datetime

from repolens.document._blocks import Blocks, value
from repolens.i18n import date_time, number, t


def release_label(facts: dict) -> str:
    """The release a document describes: the scanned ref, a tag on the commit, the manifest
    version, the short commit hash, or "snapshot", whichever is found first."""
    git = facts.get("git") or {}
    return (
        facts["source"].get("ref")
        or (git.get("tags_at_head") or [None])[0]
        or facts["project"].get("version")
        or git.get("commit_short")
        or "snapshot"
    )


def title(doc: Blocks, facts: dict) -> None:
    """Project name, release, commit, and when and by what the document was made."""
    project, git = facts["project"], facts.get("git") or {}
    meta = [
        (t("Version", "Versi"), value(project.get("version"))),
        (t("Release / ref", "Rilis / ref"), release_label(facts)),
    ]
    if git.get("is_git"):
        meta.append(("Commit", f"{git['commit_short']} ({git['commit_date'][:10]})"))
        meta.append(("Branch", value(git.get("branch"))))
        if git.get("remote"):
            meta.append(("Repository", git["remote"]))
    scanned = date_time(datetime.fromisoformat(facts["scanned_at"]).astimezone())
    meta.append((t("Scanned", "Dipindai"), scanned))
    meta.append(("Generator", f"repolens {facts['repolens_version']}"))
    doc.title(project["name"], t("Technical Documentation", "Dokumentasi Teknis"), meta)
    if git.get("dirty"):
        doc.note(
            t(
                "The repository was scanned with uncommitted changes. "
                "This document does not fully represent the commit above.",
                "Repository dipindai dengan perubahan yang belum di-commit. "
                "Dokumen ini tidak sepenuhnya mewakili commit di atas.",
            ),
            level="warn",
        )


def summary(doc: Blocks, facts: dict) -> None:
    """1. What the project is (AI narrative, or a one-line fallback) and key numbers."""
    ai = facts.get("ai")
    counts = _counts(facts)
    doc.h1(t("Summary", "Ringkasan"))
    if ai:
        doc.paragraphs(ai["summary"])
    else:
        _summary_without_ai(doc, facts, counts)
    doc.table(
        [t("Metric", "Metrik"), t("Count", "Jumlah")],
        [
            [t("Total files", "Total file"), number(counts["files"])],
            [t("Lines of code", "Baris kode"), number(sum(x["lines"] for x in facts["languages"]))],
            [t("Server endpoints", "Endpoint server"), str(counts["server"])],
            [t("Client API calls", "Panggilan API klien"), str(counts["client"])],
            [t("UI pages / routes", "Halaman / route UI"), str(counts["pages"])],
            [t("Tables / data models", "Tabel / model data"), str(counts["tables"])],
            [t("Security findings", "Temuan keamanan"), str(len(facts["security"]["secrets"]))],
        ],
        widths=[3, 1],
    )
    if ai and ai.get("architecture"):
        doc.h2(t("Architecture", "Arsitektur"))
        doc.paragraphs(ai["architecture"])
    if ai and ai.get("modules"):
        doc.h2(t("Functional Modules", "Modul Fungsional"))
        rows = [[m["name"], m["description"]] for m in ai["modules"]]
        doc.table([t("Module", "Modul"), t("Description", "Deskripsi")], rows, widths=[1, 3])
    notes = (facts.get("project_config") or {}).get("notes")
    if notes:
        doc.h2(t("Project owner notes", "Catatan pemilik proyek"))
        doc.bullets(notes)


def _counts(facts: dict) -> dict:
    """Numbers used in the summary sentence and table."""
    endpoints = facts["endpoints"]
    return {
        "files": facts["tree"]["total_files"],
        "server": len(endpoints["server"]),
        "client": len(endpoints["client"]),
        "pages": len(endpoints["pages"]),
        "tables": len(facts["database"]["tables"]),
    }


def _summary_without_ai(doc: Blocks, facts: dict, counts: dict) -> None:
    """The description from the manifest, one sentence built from the facts, and a hint."""
    project = facts["project"]
    if project.get("description"):
        doc.p(project["description"])
    frameworks = ", ".join(
        f"{f['name']} {f['version'] or ''}".strip()
        for f in facts["frameworks"]
        if "framework" in f["category"].lower()
    )
    languages = ", ".join(x["language"] for x in facts["languages"][:3])
    built = (
        frameworks or languages or t("a stack that was not detected", "stack yang tidak terdeteksi")
    )
    name, files = project["name"], number(counts["files"])
    server, client, pages, tables = (
        counts["server"],
        counts["client"],
        counts["pages"],
        counts["tables"],
    )
    doc.p(
        t(
            f"**{name}** is built with {built}. It has {files} files, {server} server endpoints, "
            f"{client} client API calls, {pages} UI pages/routes, "
            f"and {tables} table/data model definitions.",
            f"Proyek **{name}** dibangun dengan {built}. Terdapat {files} file, "
            f"{server} endpoint server, {client} panggilan API klien, {pages} halaman/route UI, "
            f"dan {tables} definisi tabel/model data.",
        )
    )
    doc.note(
        t(
            "The narrative summary is written by AI. Run the scan without `--no-ai` "
            "(and with Anthropic credentials) to include it.",
            "Ringkasan naratif dibuat oleh AI. Jalankan scan tanpa `--no-ai` "
            "(dan dengan kredensial Anthropic) untuk menambahkannya.",
        )
    )
