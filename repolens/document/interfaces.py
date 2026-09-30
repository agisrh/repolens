"""Sections about what the code exposes and stores: 6. endpoints and routes, 7. database."""

from __future__ import annotations

from collections import defaultdict

from repolens.document._blocks import Blocks, source, value
from repolens.i18n import t


def endpoints(doc: Blocks, facts: dict) -> None:
    """6. Endpoints served, APIs called, and UI pages, each with its source location."""
    found = facts["endpoints"]
    server, client, pages = found["server"], found["client"], found["pages"]
    doc.h1(t("Endpoints & Routes", "Endpoint & Route"))
    if not (server or client or pages):
        doc.p(
            t(
                "No endpoints or routes were detected for this stack.",
                "Tidak ada endpoint atau route yang terdeteksi untuk stack ini.",
            )
        )
    if server:
        doc.h2(
            t(f"Endpoints provided ({len(server)})", f"Endpoint yang disediakan ({len(server)})")
        )
        frameworks = ", ".join(sorted({e["framework"] for e in server if e.get("framework")}))
        doc.p(
            t(
                f"Detected from {frameworks} route definitions.",
                f"Terdeteksi dari definisi route {frameworks}.",
            )
        )
        _grouped_tables(doc, server)
    if client:
        doc.h2(
            t(
                f"APIs called by the app ({len(client)})",
                f"API yang dipanggil aplikasi ({len(client)})",
            )
        )
        doc.p(
            t(
                "HTTP calls from client code, grouped by base URL or file. "
                "Paths are relative to that base URL. `{name}` is a dynamic parameter.",
                "Panggilan HTTP dari kode klien, dikelompokkan per base URL atau file. "
                "Path relatif terhadap base URL tersebut. `{nama}` adalah parameter dinamis.",
            )
        )
        _grouped_tables(doc, client)
    if pages:
        doc.h2(t(f"UI pages / routes ({len(pages)})", f"Halaman / route UI ({len(pages)})"))
        rows = [[e["path"], value(e.get("framework")), source(e["file"], e["line"])] for e in pages]
        doc.table(["Path", "Router", t("Source", "Sumber")], rows, widths=[2.5, 1.5, 3.5])
    for note in found["notes"]:
        doc.note(note, level="warn")


def _grouped_tables(doc: Blocks, items: list[dict]) -> None:
    """One table per group (route file, controller, or base URL), with a heading when there
    is more than one group."""
    groups = defaultdict(list)
    for item in items:
        groups[item.get("group") or "-"].append(item)
    for group, members in groups.items():
        if len(groups) > 1:
            doc.h3(f"{group} ({len(members)})")
        rows = [
            [
                e["method"],
                e["path"],
                value(e.get("handler")) + (f" ({e['note']})" if e.get("note") else ""),
                source(e["file"], e["line"]),
            ]
            for e in members
        ]
        doc.table(
            ["Method", "Path", "Handler", t("Source", "Sumber")], rows, widths=[0.9, 3, 2.2, 3.2]
        )


def database(doc: Blocks, facts: dict) -> None:
    """7. Engines, an overview of all tables, then every table with its columns."""
    engines, tables = facts["database"]["engines"], facts["database"]["tables"]
    doc.h1("Database")
    if engines:
        headers = [t("Engine / storage", "Engine / penyimpanan"), t("Evidence", "Bukti")]
        doc.table(headers, [[e["engine"], e["evidence"]] for e in engines], widths=[1.5, 3])
    else:
        doc.p(t("No database engine detected.", "Engine database tidak terdeteksi."))
    if not tables:
        doc.p(
            t(
                "No schema definitions (SQL, migrations, ORM entities/models) were found "
                "in this repository.",
                "Tidak ada definisi skema (SQL, migration, entity/model ORM) yang ditemukan "
                "di repository ini.",
            )
        )
        return
    doc.h2(t(f"Schema ({len(tables)} tables/models)", f"Skema ({len(tables)} tabel/model)"))
    headers = [
        t("Table / model", "Tabel / model"),
        t("Defined by", "Sumber definisi"),
        t("Columns", "Kolom"),
        "File",
    ]
    rows = [
        [x["name"], x["source"], str(len(x["columns"])), source(x["file"], x["line"])]
        for x in tables
    ]
    doc.table(headers, rows, widths=[2, 2, 0.8, 3.5])
    for table in tables:
        doc.h3(table["name"])
        info = f"{table['source']} · `{source(table['file'], table['line'])}`"
        if table["notes"]:
            info += " · " + "; ".join(table["notes"])
        doc.p(info)
        if table["columns"]:
            headers = [t("Column", "Kolom"), t("Type", "Tipe"), t("Attributes", "Atribut")]
            rows = [[c["name"], c["type"], c["attrs"] or "-"] for c in table["columns"]]
            doc.table(headers, rows, widths=[2, 2, 2.5])
