"""Sections about the project itself: 3. release and repository, 4. tech stack, 5. folders."""

from __future__ import annotations

from repolens.document._blocks import Blocks, value
from repolens.i18n import number, t


def release(doc: Blocks, facts: dict) -> None:
    """3. Name, version, and everything git knows about the scanned commit."""
    project, git = facts["project"], facts.get("git") or {}
    doc.h1(t("Release & Repository", "Informasi Rilis & Repository"))
    rows = [
        [t("Project name", "Nama proyek"), project["name"]],
        [t("Version (manifest)", "Versi (manifest)"), value(project.get("version"))],
        [t("Name source", "Sumber nama"), project.get("name_source")],
    ]
    if git.get("is_git"):
        rows += [
            ["Commit", git["commit"]],
            [t("Commit date", "Tanggal commit"), git["commit_date"]],
            [t("Commit message", "Pesan commit"), value(git.get("commit_subject"))],
            ["Branch", value(git.get("branch"))],
            [t("Tags on this commit", "Tag pada commit ini"), value(git.get("tags_at_head"))],
            ["git describe", value(git.get("describe"))],
            ["Remote", value(git.get("remote"))],
            [t("Commit count", "Jumlah commit"), str(git.get("commit_count"))],
            [
                t("Contributors (unique emails)", "Kontributor (email unik)"),
                str(git.get("contributors")),
            ],
        ]
    elif git.get("disabled"):
        rows.append(
            [
                "Git",
                t("Not read (scanned with --no-git)", "Tidak dibaca (dipindai dengan --no-git)"),
            ]
        )
    else:
        rows.append(
            ["Git", t("This folder is not a git repository", "Folder ini bukan repository git")]
        )
    doc.table(["Item", t("Value", "Nilai")], rows, widths=[1.3, 3])
    ref = facts["source"].get("ref")
    # Mention the ref only when the table does not already show it (as a tag or the commit).
    if (
        git.get("is_git")
        and ref
        and ref not in (git.get("tags_at_head") or [])
        and not ref.startswith(git.get("commit_short", "~"))
    ):
        doc.note(t(f"Scanned at ref `{ref}`.", f"Dipindai pada ref `{ref}`."))


def tech_stack(doc: Blocks, facts: dict) -> None:
    """4. Frameworks with versions and where each came from, then the languages."""
    doc.h1("Tech Stack")
    if facts["frameworks"]:
        headers = [
            t("Component", "Komponen"),
            t("Category", "Kategori"),
            t("Version", "Versi"),
            t("Source", "Sumber"),
        ]
        rows = [
            [f["name"], f["category"], value(f["version"]), f["source"]]
            for f in facts["frameworks"]
        ]
        doc.table(headers, rows, widths=[2, 2, 1.5, 3])
        doc.p(
            t(
                "Versions come from lock files when present (the version actually installed). "
                "Without a lock file, the manifest constraint is shown (e.g. `^8.1`).",
                "Versi diambil dari lock file jika ada (versi yang benar-benar terpasang). "
                "Jika tidak ada lock file, yang tercatat adalah constraint di manifest "
                "(misalnya `^8.1`).",
            )
        )
    else:
        doc.p(
            t(
                "No framework was detected automatically. See the Languages and Dependency sections.",
                "Framework tidak terdeteksi otomatis. Lihat bagian Bahasa dan Dependency.",
            )
        )
    doc.h2(t("Programming languages", "Bahasa pemrograman"))
    rows = [
        [x["language"], number(x["files"]), number(x["lines"]), f"{x['percent']}"]
        for x in facts["languages"][:15]
    ]
    doc.table(
        [t("Language", "Bahasa"), "File", t("Lines", "Baris"), "%"], rows, widths=[3, 1, 1.3, 1]
    )


def folders(doc: Blocks, facts: dict) -> None:
    """5. The folder tree, plus a description per folder when the AI wrote them."""
    doc.h1(t("Folder Structure", "Struktur Folder"))
    depth = facts["tree"]["max_depth"]
    doc.p(
        t(
            f"Structure up to depth {depth}. Build output, dependencies "
            "(e.g. `node_modules`, `vendor`), and caches are not shown.",
            f"Struktur hingga kedalaman {depth}. Folder hasil build, dependency "
            "(misalnya `node_modules`, `vendor`), dan cache tidak ditampilkan.",
        )
    )
    doc.code(facts["tree"]["text"])
    ai = facts.get("ai")
    if ai and ai.get("folder_descriptions"):
        doc.h2(t("Folder descriptions", "Keterangan folder"))
        rows = [[f"`{f['path']}`", f["description"]] for f in ai["folder_descriptions"]]
        doc.table(["Folder", t("Description", "Keterangan")], rows, widths=[1.4, 3])
