"""2. Changes since the previous release (only when the scan was compared with one)."""

from __future__ import annotations

from repolens.diff import is_empty
from repolens.document._blocks import Blocks, value
from repolens.i18n import label, number, signed, t


def changes(doc: Blocks, facts: dict) -> None:
    diff = facts.get("changes")
    if not diff:
        return
    doc.h1(t(f"Changes {diff['from']} → {diff['to']}", f"Perubahan {diff['from']} → {diff['to']}"))
    if is_empty(diff):
        doc.p(
            t(
                "No changes to the stack, dependencies, endpoints, database, env, or platforms.",
                "Tidak ada perubahan pada stack, dependency, endpoint, database, env, atau platform.",
            )
        )
    doc.p(_totals(diff))
    change, before, after = t("Change", "Perubahan"), t("Before", "Sebelum"), t("After", "Sesudah")
    if diff["frameworks"]:
        doc.h2("Tech stack")
        rows = [
            [c["name"], label(c["change"]), value(c["old"]), value(c["new"])]
            for c in diff["frameworks"]
        ]
        doc.table([t("Component", "Komponen"), change, before, after], rows, widths=[3, 2, 2, 2])
    if diff["platforms"]:
        doc.h2("Platform")
        rows = [[c["setting"], value(c["old"]), value(c["new"])] for c in diff["platforms"]]
        doc.table([t("Setting", "Pengaturan"), before, after], rows, widths=[3, 2, 2])
    if diff["endpoints"]:
        doc.h2(t("Endpoints & routes", "Endpoint & route"))
        kinds = {"server": "server", "client": t("client", "klien"), "pages": t("page", "halaman")}
        rows = [
            [label(c["change"]), kinds[c["kind"]], c["method"], c["path"], c["file"]]
            for c in diff["endpoints"]
        ]
        headers = [change, t("Kind", "Jenis"), "Method", "Path", "File"]
        doc.table(headers, rows, widths=[1.2, 1, 1, 3.5, 3.5])
    if diff["database"]:
        doc.h2("Database")
        rows = [[c["table"], label(c["change"]), c["detail"] or "-"] for c in diff["database"]]
        doc.table([t("Table", "Tabel"), change, "Detail"], rows, widths=[2, 1.5, 4])
    if diff["env"]:
        doc.h2("Environment")
        rows = [[c["key"], label(c["change"])] for c in diff["env"]]
        doc.table(["Key", change], rows, widths=[3, 1])
    if diff["dependencies"]:
        doc.h2("Dependency")
        rows = [
            [c["name"], c["ecosystem"], label(c["change"]), value(c["old"]), value(c["new"])]
            for c in diff["dependencies"]
        ]
        headers = ["Package", t("Ecosystem", "Ekosistem"), change, before, after]
        doc.table(headers, rows, widths=[3, 2, 1.3, 1.6, 1.6])


def _totals(diff: dict) -> str:
    """ "Files: 120 → 131 (+11). Lines of code: ..." plus the commit range when known."""
    f0, f1 = diff["stats"]["files"]
    l0, l1 = diff["stats"]["lines"]
    text = t(
        f"Files: {number(f0)} → {number(f1)} ({signed(f1 - f0)}). "
        f"Lines of code: {number(l0)} → {number(l1)} ({signed(l1 - l0)}).",
        f"File: {number(f0)} → {number(f1)} ({signed(f1 - f0)}). "
        f"Baris kode: {number(l0)} → {number(l1)} ({signed(l1 - l0)}).",
    )
    if diff.get("commits"):
        text += f" Commit: {diff['commits']['from']} → {diff['commits']['to']}."
    return text
