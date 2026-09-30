"""The last sections: 11. security, 12. AI notes and recommendations, 13. scan coverage,
14. about this document."""

from __future__ import annotations

from repolens.document._blocks import Blocks, source, value
from repolens.i18n import code_of, label, t


def security(doc: Blocks, facts: dict) -> None:
    """11. Possible secrets in the current files, masked."""
    secrets = facts["security"]["secrets"]
    doc.h1(t("Security", "Keamanan"))
    if not secrets:
        doc.p(
            t(
                "No common secret patterns (GitHub/AWS/Slack/Stripe tokens, private keys, JWT, "
                "hardcoded passwords) were found in the current files.",
                "Tidak ditemukan pola rahasia yang umum (token GitHub/AWS/Slack/Stripe, private "
                "key, "
                "JWT, password hardcoded) di file saat ini.",
            )
        )
        return
    per_level = {
        level: sum(1 for s in secrets if code_of(s.get("severity") or "") == level)
        for level in ("high", "medium", "low")
    }
    counts = ", ".join(f"{per_level[level]} {label(level)}" for level in ("high", "medium", "low"))
    total = len(secrets)
    doc.p(
        t(
            f"Found {total} possible sensitive values in the scanned files ({counts}). "
            "Values are masked: tokens show only their first 4 characters, passwords are not "
            "shown at all. *Low* is used for findings in test files and Firebase client config "
            "API keys.",
            f"Ditemukan {total} kemungkinan data sensitif di file yang dipindai ({counts}). "
            "Nilai disamarkan: token hanya ditampilkan 4 karakter pertamanya, password tidak "
            "ditampilkan sama sekali. Tingkat *rendah* dipakai untuk temuan di file test dan "
            "API key config Firebase klien.",
        )
    )
    headers = [
        t("Level", "Tingkat"),
        t("Type", "Jenis"),
        t("Location", "Lokasi"),
        t("Preview", "Cuplikan"),
        t("In git", "Di git"),
    ]
    rows = [
        [
            label(s.get("severity")),
            label(s["type"]) + (f" ({s['note']})" if s.get("note") else ""),
            source(s["file"], s["line"]),
            s["preview"],
            value(s["committed"]),
        ]
        for s in secrets
    ]
    doc.table(headers, rows, widths=[0.9, 1.6, 3.5, 1.5, 0.7])
    doc.note(
        t(
            "This scan only checks the current files, not git history. A secret that was "
            "committed and later deleted is still in the history and must be revoked.",
            "Pemindaian ini hanya memeriksa isi file saat ini, bukan riwayat git. Rahasia yang "
            "pernah di-commit lalu dihapus tetap ada di riwayat dan harus dicabut (revoke).",
        ),
        level="warn",
    )


def recommendations(doc: Blocks, facts: dict) -> None:
    """12. Setup steps and observations written by the AI (left out without them)."""
    ai = facts.get("ai")
    if not ai or not (ai.get("setup_steps") or ai.get("observations")):
        return
    doc.h1(t("Notes & Recommendations", "Catatan & Rekomendasi"))
    if ai.get("setup_steps"):
        doc.h2(t("Running the project", "Menjalankan proyek"))
        doc.bullets(ai["setup_steps"])
    if ai.get("observations"):
        doc.h2(t("Observations", "Observasi"))
        doc.bullets(ai["observations"])


def coverage(doc: Blocks, facts: dict) -> None:
    """13. What is probably missing from this document and how to fill it in."""
    checks = facts.get("coverage")
    if checks is None:  # scans made before coverage existed
        return
    doc.h1(t("Scan Coverage", "Cakupan Pemindaian"))
    if not checks:
        doc.p(t("No sign of missing sections.", "Tidak ada indikasi bagian yang terlewat."))
    else:
        warnings = sum(1 for c in checks if c["level"] == "warn")
        others = len(checks) - warnings
        doc.p(
            t(
                f"{warnings} items may leave this document incomplete, plus {others} other notes. "
                "Most can be fixed with a `.repolens.yml` file in the repository "
                "(create one with `repolens init`).",
                f"{warnings} hal kemungkinan membuat dokumen ini belum lengkap, dan {others} "
                "catatan lainnya. Sebagian besar bisa diperbaiki lewat file `.repolens.yml` di "
                "repository (buat dengan `repolens init`).",
            )
        )
        headers = [
            t("Level", "Tingkat"),
            "Area",
            t("Finding", "Temuan"),
            t("How to complete", "Cara melengkapi"),
        ]
        rows = [[label(c["level"]), c["area"], c["message"], c.get("hint") or "-"] for c in checks]
        doc.table(headers, rows, widths=[1, 1.2, 4, 3.5])
    config = facts.get("project_config") or {}
    if config.get("file"):
        doc.bullets(_config_summary(config))


def _config_summary(config: dict) -> list[str]:
    """What .repolens.yml changed about this scan."""
    items = [
        t(
            f"Configuration read from `{config['file']}`.",
            f"Konfigurasi dibaca dari `{config['file']}`.",
        )
    ]
    items += [t(f"Applied: {a}", f"Diterapkan: {a}") for a in config.get("applied", [])]
    if config.get("routes"):
        items.append(
            t("Extra route files: ", "File route tambahan: ") + ", ".join(config["routes"])
        )
    if config.get("schema"):
        items.append(
            t("Extra schema files: ", "File skema tambahan: ") + ", ".join(config["schema"])
        )
    if config.get("ignore"):
        items.append(t("Excluded: ", "Dikecualikan: ") + ", ".join(config["ignore"]))
    return items


def about(doc: Blocks, facts: dict) -> None:
    """14. How the document was made and what it may miss."""
    doc.h1(t("About This Document", "Tentang Dokumen Ini"))
    items = [
        t(
            "Generated automatically by repolens by reading the files in the repository "
            "(static analysis). No code is executed.",
            "Dibuat otomatis oleh repolens dengan membaca file di repository (analisis statis). "
            "Kode tidak dijalankan.",
        ),
        t(
            "Endpoints, schema, and versions come straight from code, manifests, and lock files, "
            "with their source locations.",
            "Endpoint, skema, dan versi diambil langsung dari kode, manifest, dan lock file, "
            "lengkap dengan lokasi sumbernya.",
        ),
        t(
            "Routes built at runtime (e.g. auto-routing, routes from a database, or prefixes "
            "assembled at runtime) may not be detected.",
            "Route yang dibentuk secara dinamis (misalnya auto-routing, route dari database, atau "
            "prefix yang dirakit saat runtime) bisa tidak terdeteksi.",
        ),
    ]
    ai = facts.get("ai")
    if ai:
        model = ai.get("model")
        items.append(
            t(
                "The summary, architecture, folder descriptions, and observations were written by "
                f"AI ({model}) from the scan facts and should be reviewed by a person.",
                "Ringkasan, arsitektur, keterangan folder, dan observasi ditulis oleh AI "
                f"({model}) berdasarkan fakta hasil pemindaian, lalu perlu ditinjau manusia.",
            )
        )
    else:
        items.append(
            t(
                "The narrative (AI) sections are not included in this document.",
                "Bagian naratif (AI) tidak disertakan pada dokumen ini.",
            )
        )
    doc.bullets(items)
