"""Sections about running and building the project: 8. configuration, 9. platforms and
infrastructure, 10. dependencies."""

from __future__ import annotations

from repolens.document._blocks import Blocks, value
from repolens.i18n import t


def configuration(doc: Blocks, facts: dict) -> None:
    """8. Env keys per .env file (names only) and Spring configuration keys."""
    config = facts["config"]
    doc.h1(t("Configuration & Environment", "Konfigurasi & Environment"))
    doc.p(
        t(
            "Only **key names** are recorded. Values are never read into this document.",
            "Hanya **nama key** yang dicatat. Nilai tidak pernah dibaca ke dalam dokumen.",
        )
    )
    env_files = config["env_files"]
    if env_files:
        # One row per key, one column per file, ✓ where the file defines the key.
        keys = sorted({key for env in env_files for key in env["keys"]})
        files = [env["file"] for env in env_files]
        rows = [[key] + ["✓" if key in env["keys"] else "" for env in env_files] for key in keys]
        doc.table(["Key"] + files, rows, widths=[2.5] + [1] * len(files))
        committed = [env["file"] for env in env_files if env["committed"] and not env["template"]]
        if committed:
            listed = ", ".join(committed)
            doc.note(
                t(
                    f"These env files are committed to git: {listed}. Make sure they hold no secrets.",
                    f"File env berikut ikut di-commit ke git: {listed}. Pastikan isinya bukan rahasia.",
                ),
                level="warn",
            )
    else:
        doc.p(t("No `.env` files were found.", "Tidak ada file `.env` yang ditemukan."))
    for spring in config["spring_config"]:
        doc.h3(spring["file"])
        doc.p(", ".join(f"`{key}`" for key in spring["keys"]) or "-")


def platforms(doc: Blocks, facts: dict) -> None:
    """9. Android and iOS settings, Docker, Docker Compose, and CI/CD. Left out when empty."""
    platform, infra = facts["platforms"], facts["infrastructure"]
    if not (platform or infra["dockerfiles"] or infra["compose_services"] or infra["ci"]):
        return
    setting, setting_value = t("Setting", "Pengaturan"), t("Value", "Nilai")
    doc.h1(t("Platforms, Build & Infrastructure", "Platform, Build & Infrastruktur"))
    android = platform.get("android")
    if android:
        doc.h2("Android")
        rows = [
            ["Application ID", value(android["application_id"])],
            ["minSdk", value(android["min_sdk"])],
            ["targetSdk", value(android["target_sdk"])],
            ["compileSdk", value(android["compile_sdk"])],
            ["Flavor", value(android["flavors"])],
            ["JVM target", value(android["jvm_target"])],
            ["File", android["file"]],
        ]
        doc.table([setting, setting_value], rows, widths=[1.3, 3])
    ios = platform.get("ios")
    if ios:
        doc.h2("iOS")
        rows = [
            ["Deployment target (min iOS)", value(ios["deployment_target"])],
            ["Podfile platform", value(ios["podfile_platform"])],
            ["Bundle ID", value(ios["bundle_ids"])],
            ["File", ios["file"]],
        ]
        doc.table([setting, setting_value], rows, widths=[1.3, 3])
    if platform.get("other"):
        others = ", ".join(platform["other"])
        doc.p(
            t(
                f"Other platforms with a folder: {others}.",
                f"Platform lain yang ada foldernya: {others}.",
            )
        )
    if infra["dockerfiles"]:
        doc.h2("Docker")
        rows = [[d["file"], value(d["base_images"])] for d in infra["dockerfiles"]]
        doc.table(["File", "Base image"], rows, widths=[2, 3])
    if infra["compose_services"]:
        doc.h2("Docker Compose")
        rows = [
            [s["service"], value(s["image"]), value(s["ports"]), s["file"]]
            for s in infra["compose_services"]
        ]
        doc.table(["Service", "Image", "Port", "File"], rows, widths=[1.5, 2, 1.5, 2])
    if infra["ci"]:
        doc.h2("CI/CD")
        rows = [
            [c["system"], value(c["name"]), value(c["triggers"]), c["file"]] for c in infra["ci"]
        ]
        headers = [t("System", "Sistem"), t("Name", "Nama"), "Trigger", "File"]
        doc.table(headers, rows, widths=[1.5, 2.5, 1.5, 2.5])


def dependencies(doc: Blocks, facts: dict) -> None:
    """10. One table per manifest: declared constraint vs installed version."""
    doc.h1("Dependency")
    if not facts["dependencies"]:
        doc.p(
            t("No recognised dependency manifest.", "Tidak ada manifest dependency yang dikenali.")
        )
    for manifest in facts["dependencies"]:
        doc.h2(f"{manifest['manifest']} · {manifest['ecosystem']}")
        if manifest.get("lock"):
            lock = f"Lock file: `{manifest['lock']}`."
        else:
            lock = t(
                "No lock file, so the *installed* column is empty unless the manifest pins a version.",
                "Tidak ada lock file, jadi kolom *terpasang* kosong kecuali versi dipatok di manifest.",
            )
        runtime = ", ".join(f"{k}: {v}" for k, v in (manifest.get("runtime") or {}).items() if v)
        doc.p(lock + (f" Runtime: {runtime}." if runtime else ""))
        headers = [
            "Package",
            t("Declared", "Dideklarasikan"),
            t("Installed", "Terpasang"),
            "Scope",
            t("Note", "Keterangan"),
        ]
        rows = [
            [
                d["name"],
                value(d["declared"]),
                value(d["resolved"]),
                d["scope"],
                value(d.get("source")),
            ]
            for d in manifest["dependencies"]
        ]
        doc.table(headers, rows, widths=[3, 1.6, 1.4, 1, 2.2])
