"""Turn scan facts into a format-neutral list of blocks that every renderer understands.

Block types:
  title      {title, subtitle, meta: [(label, value)]}
  h1/h2/h3   {text}
  p          {text}            inline `code` and **bold** are supported
  bullets    {items}
  table      {headers, rows, widths}   widths are relative column weights
  code       {text}
  note       {text, level: info|warn}
  pagebreak  {}

Text follows the current output language (repolens.i18n). Strings produced during the scan
(coverage messages, extractor notes) keep the language the scan ran in.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from repolens.diff import is_empty
from repolens.i18n import code_of, date_time, label, number, signed, t


def _v(value) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, bool):
        return t("yes", "ya") if value else t("no", "tidak")
    if isinstance(value, (list, tuple)):
        return ", ".join(map(str, value)) if value else "-"
    return str(value)


def _src(file: str, line: int | None) -> str:
    return f"{file}:{line}" if line and line > 1 else file


def release_label(facts: dict) -> str:
    git = facts.get("git") or {}
    return (facts["source"].get("ref") or (git.get("tags_at_head") or [None])[0]
            or facts["project"].get("version") or git.get("commit_short") or "snapshot")


def build(facts: dict) -> list[dict]:
    b: list[dict] = []
    add = b.append
    p, git, ai = facts["project"], facts.get("git") or {}, facts.get("ai")
    scanned = date_time(datetime.fromisoformat(facts["scanned_at"]).astimezone())

    meta = [(t("Version", "Versi"), _v(p.get("version"))), (t("Release / ref", "Rilis / ref"), release_label(facts))]
    if git.get("is_git"):
        meta += [("Commit", f"{git['commit_short']} ({git['commit_date'][:10]})"), ("Branch", _v(git.get("branch")))]
        if git.get("remote"):
            meta.append(("Repository", git["remote"]))
    meta += [(t("Scanned", "Dipindai"), scanned), ("Generator", f"repolens {facts['repolens_version']}")]
    add({"t": "title", "title": p["name"], "subtitle": t("Technical Documentation", "Dokumentasi Teknis"), "meta": meta})
    if git.get("dirty"):
        add({"t": "note", "level": "warn", "text": t(
            "The repository was scanned with uncommitted changes. This document does not fully represent the commit above.",
            "Repository dipindai dengan perubahan yang belum di-commit. Dokumen ini tidak sepenuhnya mewakili commit di atas.")})

    eps = facts["endpoints"]
    n_server, n_client, n_pages = len(eps["server"]), len(eps["client"]), len(eps["pages"])
    n_files, n_tables = facts["tree"]["total_files"], len(facts["database"]["tables"])

    # 1. Summary
    add({"t": "h1", "text": t("Summary", "Ringkasan")})
    if ai:
        for para in ai["summary"].split("\n\n"):
            add({"t": "p", "text": para.strip()})
    else:
        if p.get("description"):
            add({"t": "p", "text": p["description"]})
        fw = ", ".join(f"{f['name']} {f['version'] or ''}".strip() for f in facts["frameworks"] if "framework" in f["category"].lower())
        langs = ", ".join(l["language"] for l in facts["languages"][:3])
        built = fw or langs or t("a stack that was not detected", "stack yang tidak terdeteksi")
        add({"t": "p", "text": t(
            f"**{p['name']}** is built with {built}. It has {number(n_files)} files, {n_server} server endpoints, "
            f"{n_client} client API calls, {n_pages} UI pages/routes, and {n_tables} table/data model definitions.",
            f"Proyek **{p['name']}** dibangun dengan {built}. Terdapat {number(n_files)} file, {n_server} endpoint server, "
            f"{n_client} panggilan API klien, {n_pages} halaman/route UI, dan {n_tables} definisi tabel/model data.")})
        add({"t": "note", "level": "info", "text": t(
            "The narrative summary is written by AI. Run the scan without `--no-ai` (and with Anthropic credentials) to include it.",
            "Ringkasan naratif dibuat oleh AI. Jalankan scan tanpa `--no-ai` (dan dengan kredensial Anthropic) untuk menambahkannya.")})
    stats = [
        [t("Total files", "Total file"), number(n_files)],
        [t("Lines of code", "Baris kode"), number(sum(l["lines"] for l in facts["languages"]))],
        [t("Server endpoints", "Endpoint server"), str(n_server)],
        [t("Client API calls", "Panggilan API klien"), str(n_client)],
        [t("UI pages / routes", "Halaman / route UI"), str(n_pages)],
        [t("Tables / data models", "Tabel / model data"), str(n_tables)],
        [t("Security findings", "Temuan keamanan"), str(len(facts["security"]["secrets"]))],
    ]
    add({"t": "table", "headers": [t("Metric", "Metrik"), t("Count", "Jumlah")], "rows": stats, "widths": [3, 1]})
    if ai and ai.get("architecture"):
        add({"t": "h2", "text": t("Architecture", "Arsitektur")})
        for para in ai["architecture"].split("\n\n"):
            add({"t": "p", "text": para.strip()})
    if ai and ai.get("modules"):
        add({"t": "h2", "text": t("Functional Modules", "Modul Fungsional")})
        add({"t": "table", "headers": [t("Module", "Modul"), t("Description", "Deskripsi")],
             "rows": [[m["name"], m["description"]] for m in ai["modules"]], "widths": [1, 3]})

    pcfg = facts.get("project_config") or {}
    if pcfg.get("notes"):
        add({"t": "h2", "text": t("Project owner notes", "Catatan pemilik proyek")})
        add({"t": "bullets", "items": pcfg["notes"]})

    # 2. Changes since previous release
    changes = facts.get("changes")
    if changes:
        add({"t": "h1", "text": t(f"Changes {changes['from']} → {changes['to']}", f"Perubahan {changes['from']} → {changes['to']}")})
        if is_empty(changes):
            add({"t": "p", "text": t("No changes to the stack, dependencies, endpoints, database, env, or platforms.",
                                     "Tidak ada perubahan pada stack, dependency, endpoint, database, env, atau platform.")})
        f0, f1 = changes["stats"]["files"]
        l0, l1 = changes["stats"]["lines"]
        summary = t(f"Files: {number(f0)} → {number(f1)} ({signed(f1 - f0)}). Lines of code: {number(l0)} → {number(l1)} ({signed(l1 - l0)}).",
                    f"File: {number(f0)} → {number(f1)} ({signed(f1 - f0)}). Baris kode: {number(l0)} → {number(l1)} ({signed(l1 - l0)}).")
        if changes.get("commits"):
            summary += f" Commit: {changes['commits']['from']} → {changes['commits']['to']}."
        add({"t": "p", "text": summary})
        change, before, after = t("Change", "Perubahan"), t("Before", "Sebelum"), t("After", "Sesudah")
        if changes["frameworks"]:
            add({"t": "h2", "text": "Tech stack"})
            add({"t": "table", "headers": [t("Component", "Komponen"), change, before, after],
                 "rows": [[c["name"], label(c["change"]), _v(c["old"]), _v(c["new"])] for c in changes["frameworks"]], "widths": [3, 2, 2, 2]})
        if changes["platforms"]:
            add({"t": "h2", "text": "Platform"})
            add({"t": "table", "headers": [t("Setting", "Pengaturan"), before, after],
                 "rows": [[c["setting"], _v(c["old"]), _v(c["new"])] for c in changes["platforms"]], "widths": [3, 2, 2]})
        if changes["endpoints"]:
            add({"t": "h2", "text": t("Endpoints & routes", "Endpoint & route")})
            kinds = {"server": "server", "client": t("client", "klien"), "pages": t("page", "halaman")}
            add({"t": "table", "headers": [change, t("Kind", "Jenis"), "Method", "Path", "File"],
                 "rows": [[label(c["change"]), kinds[c["kind"]], c["method"], c["path"], c["file"]] for c in changes["endpoints"]],
                 "widths": [1.2, 1, 1, 3.5, 3.5]})
        if changes["database"]:
            add({"t": "h2", "text": "Database"})
            add({"t": "table", "headers": [t("Table", "Tabel"), change, "Detail"],
                 "rows": [[c["table"], label(c["change"]), c["detail"] or "-"] for c in changes["database"]], "widths": [2, 1.5, 4]})
        if changes["env"]:
            add({"t": "h2", "text": "Environment"})
            add({"t": "table", "headers": ["Key", change], "rows": [[c["key"], label(c["change"])] for c in changes["env"]], "widths": [3, 1]})
        if changes["dependencies"]:
            add({"t": "h2", "text": "Dependency"})
            add({"t": "table", "headers": ["Package", t("Ecosystem", "Ekosistem"), change, before, after],
                 "rows": [[c["name"], c["ecosystem"], label(c["change"]), _v(c["old"]), _v(c["new"])] for c in changes["dependencies"]],
                 "widths": [3, 2, 1.3, 1.6, 1.6]})

    # 3. Release info
    add({"t": "h1", "text": t("Release & Repository", "Informasi Rilis & Repository")})
    rows = [[t("Project name", "Nama proyek"), p["name"]], [t("Version (manifest)", "Versi (manifest)"), _v(p.get("version"))],
            [t("Name source", "Sumber nama"), p.get("name_source")]]
    if git.get("is_git"):
        rows += [["Commit", git["commit"]], [t("Commit date", "Tanggal commit"), git["commit_date"]],
                 [t("Commit message", "Pesan commit"), _v(git.get("commit_subject"))],
                 ["Branch", _v(git.get("branch"))], [t("Tags on this commit", "Tag pada commit ini"), _v(git.get("tags_at_head"))],
                 ["git describe", _v(git.get("describe"))], ["Remote", _v(git.get("remote"))],
                 [t("Commit count", "Jumlah commit"), str(git.get("commit_count"))],
                 [t("Contributors (unique emails)", "Kontributor (email unik)"), str(git.get("contributors"))]]
    elif git.get("disabled"):
        rows.append(["Git", t("Not read (scanned with --no-git)", "Tidak dibaca (dipindai dengan --no-git)")])
    else:
        rows.append(["Git", t("This folder is not a git repository", "Folder ini bukan repository git")])
    add({"t": "table", "headers": ["Item", t("Value", "Nilai")], "rows": rows, "widths": [1.3, 3]})
    ref = facts["source"].get("ref")
    if git.get("is_git") and ref and ref not in (git.get("tags_at_head") or []) and not ref.startswith(git.get("commit_short", "~")):
        add({"t": "note", "level": "info", "text": t(f"Scanned at ref `{ref}`.", f"Dipindai pada ref `{ref}`.")})

    # 4. Tech stack
    add({"t": "h1", "text": "Tech Stack"})
    if facts["frameworks"]:
        add({"t": "table", "headers": [t("Component", "Komponen"), t("Category", "Kategori"), t("Version", "Versi"), t("Source", "Sumber")],
             "rows": [[f["name"], f["category"], _v(f["version"]), f["source"]] for f in facts["frameworks"]], "widths": [2, 2, 1.5, 3]})
        add({"t": "p", "text": t(
            "Versions come from lock files when present (the version actually installed). Without a lock file, the manifest constraint is shown (e.g. `^8.1`).",
            "Versi diambil dari lock file jika ada (versi yang benar-benar terpasang). Jika tidak ada lock file, yang tercatat adalah constraint di manifest (misalnya `^8.1`).")})
    else:
        add({"t": "p", "text": t("No framework was detected automatically. See the Languages and Dependency sections.",
                                 "Framework tidak terdeteksi otomatis. Lihat bagian Bahasa dan Dependency.")})
    add({"t": "h2", "text": t("Programming languages", "Bahasa pemrograman")})
    add({"t": "table", "headers": [t("Language", "Bahasa"), "File", t("Lines", "Baris"), "%"],
         "rows": [[l["language"], number(l["files"]), number(l["lines"]), f"{l['percent']}"] for l in facts["languages"][:15]],
         "widths": [3, 1, 1.3, 1]})

    # 5. Folder structure
    add({"t": "h1", "text": t("Folder Structure", "Struktur Folder")})
    depth = facts["tree"]["max_depth"]
    add({"t": "p", "text": t(
        f"Structure up to depth {depth}. Build output, dependencies (e.g. `node_modules`, `vendor`), and caches are not shown.",
        f"Struktur hingga kedalaman {depth}. Folder hasil build, dependency (misalnya `node_modules`, `vendor`), dan cache tidak ditampilkan.")})
    add({"t": "code", "text": facts["tree"]["text"]})
    if ai and ai.get("folder_descriptions"):
        add({"t": "h2", "text": t("Folder descriptions", "Keterangan folder")})
        add({"t": "table", "headers": ["Folder", t("Description", "Keterangan")],
             "rows": [[f"`{f['path']}`", f["description"]] for f in ai["folder_descriptions"]], "widths": [1.4, 3]})

    # 6. Endpoints
    add({"t": "h1", "text": t("Endpoints & Routes", "Endpoint & Route")})
    if not (eps["server"] or eps["client"] or eps["pages"]):
        add({"t": "p", "text": t("No endpoints or routes were detected for this stack.", "Tidak ada endpoint atau route yang terdeteksi untuk stack ini.")})

    def ep_tables(items, with_group_heading: bool):
        groups = defaultdict(list)
        for e in items:
            groups[e.get("group") or "-"].append(e)
        for group, rows in groups.items():
            if with_group_heading and len(groups) > 1:
                add({"t": "h3", "text": f"{group} ({len(rows)})"})
            add({"t": "table", "headers": ["Method", "Path", "Handler", t("Source", "Sumber")],
                 "rows": [[e["method"], e["path"], _v(e.get("handler")) + (f" ({e['note']})" if e.get("note") else ""),
                           _src(e["file"], e["line"])] for e in rows],
                 "widths": [0.9, 3, 2.2, 3.2]})

    if eps["server"]:
        add({"t": "h2", "text": t(f"Endpoints provided ({n_server})", f"Endpoint yang disediakan ({n_server})")})
        fws = ", ".join(sorted({e["framework"] for e in eps["server"] if e.get("framework")}))
        add({"t": "p", "text": t(f"Detected from {fws} route definitions.", f"Terdeteksi dari definisi route {fws}.")})
        ep_tables(eps["server"], True)
    if eps["client"]:
        add({"t": "h2", "text": t(f"APIs called by the app ({n_client})", f"API yang dipanggil aplikasi ({n_client})")})
        add({"t": "p", "text": t(
            "HTTP calls from client code, grouped by base URL or file. Paths are relative to that base URL. `{name}` is a dynamic parameter.",
            "Panggilan HTTP dari kode klien, dikelompokkan per base URL atau file. Path relatif terhadap base URL tersebut. `{nama}` adalah parameter dinamis.")})
        ep_tables(eps["client"], True)
    if eps["pages"]:
        add({"t": "h2", "text": t(f"UI pages / routes ({n_pages})", f"Halaman / route UI ({n_pages})")})
        add({"t": "table", "headers": ["Path", "Router", t("Source", "Sumber")],
             "rows": [[e["path"], _v(e.get("framework")), _src(e["file"], e["line"])] for e in eps["pages"]], "widths": [2.5, 1.5, 3.5]})
    for note in eps["notes"]:
        add({"t": "note", "level": "warn", "text": note})

    # 7. Database
    db = facts["database"]
    add({"t": "h1", "text": "Database"})
    if db["engines"]:
        add({"t": "table", "headers": [t("Engine / storage", "Engine / penyimpanan"), t("Evidence", "Bukti")],
             "rows": [[e["engine"], e["evidence"]] for e in db["engines"]], "widths": [1.5, 3]})
    else:
        add({"t": "p", "text": t("No database engine detected.", "Engine database tidak terdeteksi.")})
    if db["tables"]:
        add({"t": "h2", "text": t(f"Schema ({n_tables} tables/models)", f"Skema ({n_tables} tabel/model)")})
        add({"t": "table", "headers": [t("Table / model", "Tabel / model"), t("Defined by", "Sumber definisi"), t("Columns", "Kolom"), "File"],
             "rows": [[tbl["name"], tbl["source"], str(len(tbl["columns"])), _src(tbl["file"], tbl["line"])] for tbl in db["tables"]],
             "widths": [2, 2, 0.8, 3.5]})
        for tbl in db["tables"]:
            add({"t": "h3", "text": tbl["name"]})
            info = f"{tbl['source']} · `{_src(tbl['file'], tbl['line'])}`"
            if tbl["notes"]:
                info += " · " + "; ".join(tbl["notes"])
            add({"t": "p", "text": info})
            if tbl["columns"]:
                add({"t": "table", "headers": [t("Column", "Kolom"), t("Type", "Tipe"), t("Attributes", "Atribut")],
                     "rows": [[c["name"], c["type"], c["attrs"] or "-"] for c in tbl["columns"]], "widths": [2, 2, 2.5]})
    else:
        add({"t": "p", "text": t("No schema definitions (SQL, migrations, ORM entities/models) were found in this repository.",
                                 "Tidak ada definisi skema (SQL, migration, entity/model ORM) yang ditemukan di repository ini.")})

    # 8. Config
    cfg = facts["config"]
    add({"t": "h1", "text": t("Configuration & Environment", "Konfigurasi & Environment")})
    add({"t": "p", "text": t("Only **key names** are recorded. Values are never read into this document.",
                             "Hanya **nama key** yang dicatat. Nilai tidak pernah dibaca ke dalam dokumen.")})
    if cfg["env_files"]:
        all_keys = sorted({k for e in cfg["env_files"] for k in e["keys"]})
        files = [e["file"] for e in cfg["env_files"]]
        rows = [[k] + ["✓" if k in e["keys"] else "" for e in cfg["env_files"]] for k in all_keys]
        add({"t": "table", "headers": ["Key"] + files, "rows": rows, "widths": [2.5] + [1] * len(files)})
        committed = [e["file"] for e in cfg["env_files"] if e["committed"] and not e["template"]]
        if committed:
            listed = ", ".join(committed)
            add({"t": "note", "level": "warn", "text": t(f"These env files are committed to git: {listed}. Make sure they hold no secrets.",
                                                          f"File env berikut ikut di-commit ke git: {listed}. Pastikan isinya bukan rahasia.")})
    else:
        add({"t": "p", "text": t("No `.env` files were found.", "Tidak ada file `.env` yang ditemukan.")})
    for sc in cfg["spring_config"]:
        add({"t": "h3", "text": sc["file"]})
        add({"t": "p", "text": ", ".join(f"`{k}`" for k in sc["keys"]) or "-"})

    # 9. Platforms & infra
    plat, infra = facts["platforms"], facts["infrastructure"]
    setting, value = t("Setting", "Pengaturan"), t("Value", "Nilai")
    if plat or infra["dockerfiles"] or infra["compose_services"] or infra["ci"]:
        add({"t": "h1", "text": t("Platforms, Build & Infrastructure", "Platform, Build & Infrastruktur")})
        if plat.get("android"):
            a = plat["android"]
            add({"t": "h2", "text": "Android"})
            add({"t": "table", "headers": [setting, value], "rows": [
                ["Application ID", _v(a["application_id"])], ["minSdk", _v(a["min_sdk"])], ["targetSdk", _v(a["target_sdk"])],
                ["compileSdk", _v(a["compile_sdk"])], ["Flavor", _v(a["flavors"])], ["JVM target", _v(a["jvm_target"])],
                ["File", a["file"]]], "widths": [1.3, 3]})
        if plat.get("ios"):
            i = plat["ios"]
            add({"t": "h2", "text": "iOS"})
            add({"t": "table", "headers": [setting, value], "rows": [
                [t("Deployment target (min iOS)", "Deployment target (min iOS)"), _v(i["deployment_target"])],
                ["Podfile platform", _v(i["podfile_platform"])], ["Bundle ID", _v(i["bundle_ids"])], ["File", i["file"]]],
                "widths": [1.3, 3]})
        if plat.get("other"):
            others = ", ".join(plat["other"])
            add({"t": "p", "text": t(f"Other platforms with a folder: {others}.", f"Platform lain yang ada foldernya: {others}.")})
        if infra["dockerfiles"]:
            add({"t": "h2", "text": "Docker"})
            add({"t": "table", "headers": ["File", "Base image"], "rows": [[d["file"], _v(d["base_images"])] for d in infra["dockerfiles"]],
                 "widths": [2, 3]})
        if infra["compose_services"]:
            add({"t": "h2", "text": "Docker Compose"})
            add({"t": "table", "headers": ["Service", "Image", "Port", "File"],
                 "rows": [[s["service"], _v(s["image"]), _v(s["ports"]), s["file"]] for s in infra["compose_services"]], "widths": [1.5, 2, 1.5, 2]})
        if infra["ci"]:
            add({"t": "h2", "text": "CI/CD"})
            add({"t": "table", "headers": [t("System", "Sistem"), t("Name", "Nama"), "Trigger", "File"],
                 "rows": [[c["system"], _v(c["name"]), _v(c["triggers"]), c["file"]] for c in infra["ci"]], "widths": [1.5, 2.5, 1.5, 2.5]})

    # 10. Dependencies
    add({"t": "h1", "text": "Dependency"})
    if not facts["dependencies"]:
        add({"t": "p", "text": t("No recognised dependency manifest.", "Tidak ada manifest dependency yang dikenali.")})
    for m in facts["dependencies"]:
        add({"t": "h2", "text": f"{m['manifest']} · {m['ecosystem']}"})
        lock = (t(f"Lock file: `{m['lock']}`.", f"Lock file: `{m['lock']}`.") if m.get("lock") else
                t("No lock file, so the *installed* column is empty unless the manifest pins a version.",
                  "Tidak ada lock file, jadi kolom *terpasang* kosong kecuali versi dipatok di manifest."))
        runtime = ", ".join(f"{k}: {v}" for k, v in (m.get("runtime") or {}).items() if v)
        add({"t": "p", "text": lock + (f" Runtime: {runtime}." if runtime else "")})
        add({"t": "table", "headers": ["Package", t("Declared", "Dideklarasikan"), t("Installed", "Terpasang"), "Scope", t("Note", "Keterangan")],
             "rows": [[d["name"], _v(d["declared"]), _v(d["resolved"]), d["scope"], _v(d.get("source"))] for d in m["dependencies"]],
             "widths": [3, 1.6, 1.4, 1, 2.2]})

    # 11. Security
    secrets = facts["security"]["secrets"]
    add({"t": "h1", "text": t("Security", "Keamanan")})
    if secrets:
        by_level = {lvl: sum(1 for s in secrets if code_of(s.get("severity") or "") == lvl) for lvl in ("high", "medium", "low")}
        counts = f"{by_level['high']} {label('high')}, {by_level['medium']} {label('medium')}, {by_level['low']} {label('low')}"
        add({"t": "p", "text": t(
            f"Found {len(secrets)} possible sensitive values in the scanned files ({counts}). Values are masked: tokens show only "
            "their first 4 characters, passwords are not shown at all. *Low* is used for findings in test files and Firebase client config API keys.",
            f"Ditemukan {len(secrets)} kemungkinan data sensitif di file yang dipindai ({counts}). Nilai disamarkan: token hanya ditampilkan "
            "4 karakter pertamanya, password tidak ditampilkan sama sekali. Tingkat *rendah* dipakai untuk temuan di file test dan API key config Firebase klien.")})
        add({"t": "table", "headers": [t("Level", "Tingkat"), t("Type", "Jenis"), t("Location", "Lokasi"), t("Preview", "Cuplikan"), t("In git", "Di git")],
             "rows": [[label(s.get("severity")), label(s["type"]) + (f" ({s['note']})" if s.get("note") else ""), _src(s["file"], s["line"]),
                       s["preview"], _v(s["committed"])] for s in secrets],
             "widths": [0.9, 1.6, 3.5, 1.5, 0.7]})
        add({"t": "note", "level": "warn", "text": t(
            "This scan only checks the current files, not git history. A secret that was committed and later deleted is still in the history and must be revoked.",
            "Pemindaian ini hanya memeriksa isi file saat ini, bukan riwayat git. Rahasia yang pernah di-commit lalu dihapus tetap ada di riwayat dan harus dicabut (revoke).")})
    else:
        add({"t": "p", "text": t(
            "No common secret patterns (GitHub/AWS/Slack/Stripe tokens, private keys, JWT, hardcoded passwords) were found in the current files.",
            "Tidak ditemukan pola rahasia yang umum (token GitHub/AWS/Slack/Stripe, private key, JWT, password hardcoded) di file saat ini.")})

    # 12. AI observations + setup
    if ai and (ai.get("setup_steps") or ai.get("observations")):
        add({"t": "h1", "text": t("Notes & Recommendations", "Catatan & Rekomendasi")})
        if ai.get("setup_steps"):
            add({"t": "h2", "text": t("Running the project", "Menjalankan proyek")})
            add({"t": "bullets", "items": ai["setup_steps"]})
        if ai.get("observations"):
            add({"t": "h2", "text": t("Observations", "Observasi")})
            add({"t": "bullets", "items": ai["observations"]})

    # 13. Coverage
    checks = facts.get("coverage")
    if checks is not None:
        add({"t": "h1", "text": t("Scan Coverage", "Cakupan Pemindaian")})
        warns = [c for c in checks if c["level"] == "warn"]
        if not checks:
            add({"t": "p", "text": t("No sign of missing sections.", "Tidak ada indikasi bagian yang terlewat.")})
        else:
            others = len(checks) - len(warns)
            add({"t": "p", "text": t(
                f"{len(warns)} items may leave this document incomplete, plus {others} other notes. "
                "Most can be fixed with a `.repolens.yml` file in the repository (create one with `repolens init`).",
                f"{len(warns)} hal kemungkinan membuat dokumen ini belum lengkap, dan {others} catatan lainnya. "
                "Sebagian besar bisa diperbaiki lewat file `.repolens.yml` di repository (buat dengan `repolens init`).")})
            add({"t": "table", "headers": [t("Level", "Tingkat"), t("Area", "Area"), t("Finding", "Temuan"), t("How to complete", "Cara melengkapi")],
                 "rows": [[label(c["level"]), c["area"], c["message"], c.get("hint") or "-"] for c in checks],
                 "widths": [1, 1.2, 4, 3.5]})
        if pcfg.get("file"):
            items = [t(f"Configuration read from `{pcfg['file']}`.", f"Konfigurasi dibaca dari `{pcfg['file']}`.")]
            items += [t(f"Applied: {a}", f"Diterapkan: {a}") for a in pcfg.get("applied", [])]
            if pcfg.get("routes"):
                items.append(t("Extra route files: ", "File route tambahan: ") + ", ".join(pcfg["routes"]))
            if pcfg.get("schema"):
                items.append(t("Extra schema files: ", "File skema tambahan: ") + ", ".join(pcfg["schema"]))
            if pcfg.get("ignore"):
                items.append(t("Excluded: ", "Dikecualikan: ") + ", ".join(pcfg["ignore"]))
            add({"t": "bullets", "items": items})

    # 14. About this document
    add({"t": "h1", "text": t("About This Document", "Tentang Dokumen Ini")})
    items = [
        t("Generated automatically by repolens by reading the files in the repository (static analysis). No code is executed.",
          "Dibuat otomatis oleh repolens dengan membaca file di repository (analisis statis). Kode tidak dijalankan."),
        t("Endpoints, schema, and versions come straight from code, manifests, and lock files, with their source locations.",
          "Endpoint, skema, dan versi diambil langsung dari kode, manifest, dan lock file, lengkap dengan lokasi sumbernya."),
        t("Routes built at runtime (e.g. auto-routing, routes from a database, or prefixes assembled at runtime) may not be detected.",
          "Route yang dibentuk secara dinamis (misalnya auto-routing, route dari database, atau prefix yang dirakit saat runtime) bisa tidak terdeteksi."),
    ]
    if ai:
        model = ai.get("model")
        items.append(t(f"The summary, architecture, folder descriptions, and observations were written by AI ({model}) from the scan facts and should be reviewed by a person.",
                       f"Ringkasan, arsitektur, keterangan folder, dan observasi ditulis oleh AI ({model}) berdasarkan fakta hasil pemindaian, lalu perlu ditinjau manusia."))
    else:
        items.append(t("The narrative (AI) sections are not included in this document.", "Bagian naratif (AI) tidak disertakan pada dokumen ini."))
    add({"t": "bullets", "items": items})
    return b
