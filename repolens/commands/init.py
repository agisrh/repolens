"""`repolens init [folder]`: create a .repolens.yml template from what was detected.

The template lists every key as a commented example, and fills in the few things the scan
could not work out on its own: framework versions without a lock file, a missing version,
and the findings that need attention at the time the file was created.
"""

from __future__ import annotations

import re
from pathlib import Path

from repolens import coverage, projectconfig, ui
from repolens.commands._common import add_command, flag
from repolens.i18n import t
from repolens.scanner import is_git_url, scan

NAME = "init"
MAIN_FRAMEWORKS = coverage.BACKEND | coverage.FRONTEND | coverage.MOBILE


def register(subparsers, common):
    p = add_command(
        subparsers,
        NAME,
        common,
        "Create a .repolens.yml template from what is detected",
        "Buat template .repolens.yml berdasarkan hasil deteksi",
    )
    p.add_argument("source", nargs="?", default=".")
    flag(p, "--no-git", "Read the folder as plain files", "Baca folder sebagai file biasa")
    flag(p, "--force", "Overwrite an existing .repolens.yml", "Timpa .repolens.yml yang sudah ada")
    return p


def run(args) -> int:
    root = _local_root(args.source)
    names = projectconfig.FILENAMES + projectconfig.LEGACY_FILENAMES
    existing = next((root / name for name in names if (root / name).exists()), None)
    if existing and not args.force:
        ui.error(
            t(
                f"{existing} already exists. Use --force to overwrite.",
                f"{existing} sudah ada. Pakai --force untuk menimpa.",
            )
        )
        return 1
    ui.header("Init", str(root))
    with ui.out.status(t("Scanning…", "Memindai…")):
        source = {"type": "local", "location": str(root), "ref": None}
        facts = scan(root, source, use_git=not args.no_git)
    if existing:
        existing.unlink()  # also replaces a legacy .docgen.yml with .repolens.yml
    target = root / ".repolens.yml"
    target.write_text(template(facts), encoding="utf-8")
    ui.ok(t(f"Created {target}", f"Dibuat: {target}"))
    ui.hint(
        t(
            "Fill it in, then run `repolens doctor .` to check.",
            "Lengkapi isinya, lalu jalankan `repolens doctor .` untuk mengecek.",
        ),
        indent="  ",
    )
    return 0


def _local_root(source: str) -> Path:
    """.repolens.yml is written into the repository, so the source must be a local folder."""
    if is_git_url(source):
        raise RuntimeError(
            t(
                "`repolens init` needs a local folder, because .repolens.yml is written into "
                "the repository. Clone the repository first, then run `repolens init <folder>`.",
                "`repolens init` butuh folder lokal, karena .repolens.yml ditulis ke dalam "
                "repository. Clone repository-nya dulu, lalu jalankan `repolens init <folder>`.",
            )
        )
    root = Path(source).resolve()
    if not root.is_dir():
        raise FileNotFoundError(t("Folder not found: ", "Folder tidak ditemukan: ") + str(root))
    return root


# ---- the template -------------------------------------------------------------------------


def template(facts: dict) -> str:
    """The .repolens.yml text for these scan facts."""
    name = facts["project"]["name"]
    lines = [
        t(f"# repolens configuration for {name}.", f"# Konfigurasi repolens untuk {name}."),
        t(
            "# Every key is optional. Fill in only what cannot be detected automatically.",
            "# Semua key opsional. Isi hanya yang tidak bisa terdeteksi otomatis.",
        ),
        t("# Check the result with: repolens doctor .", "# Cek hasilnya dengan: repolens doctor ."),
    ]
    findings = [f"[{c['area']}] {c['message']}" for c in facts["coverage"] if c["level"] == "warn"]
    if findings:
        lines += [
            "#",
            t("# Findings when this file was created:", "# Temuan saat file ini dibuat:"),
        ]
        lines += [f"#   - {finding}" for finding in findings]
    lines += ["", f"name: {name}"]
    lines.append(
        t("# description: Short project description", "# description: Deskripsi singkat proyek")
    )
    lines += [_version_line(facts), _frameworks_block(facts)]
    lines += _commented_examples()
    return "\n".join(lines)


def _version_line(facts: dict) -> str:
    """A commented example when a manifest has the version, an empty key to fill in otherwise."""
    if facts["project"].get("version"):
        return "# version: 1.0.0"
    missing = t(
        "no version in any manifest, fill in manually", "tidak ada versi di manifest, isi manual"
    )
    return "version:              # " + missing


def _frameworks_block(facts: dict) -> str:
    """Main frameworks whose exact version is unknown (no lock file), ready to fill in."""
    unknown = [
        f
        for f in facts["frameworks"]
        if f["name"] in MAIN_FRAMEWORKS
        and (not f["version"] or re.match(r"^[\^~><=*]", f["version"]))  # a range, not a version
    ]
    if not unknown:
        return "# frameworks:\n#   - {name: CodeIgniter 4, version: 4.4.8}\n"
    lines = [
        t(
            "# Framework versions that could not be read from a lock file:",
            "# Versi framework yang tidak terbaca dari lock file:",
        ),
        "frameworks:",
    ]
    for framework in unknown:
        detected = framework["version"] or t("unknown", "tidak diketahui")
        lines += [
            f"  - name: {framework['name']}",
            f"    version:            # {t('detected', 'terdeteksi')}: {detected}",
        ]
    return "\n".join(lines) + "\n"


def _commented_examples() -> list[str]:
    """The remaining keys, as commented examples."""
    auto_routing = t("created through auto-routing", "dibuat lewat auto-routing")
    return [
        t(
            "# Route files outside the standard locations (Laravel, CodeIgniter 3/4 are recognised):",
            "# File route di luar lokasi standar (Laravel, CodeIgniter 3/4 dikenali otomatis):",
        ),
        "# routes:",
        "#   - app/Config/RoutesAdmin.php",
        "",
        t(
            "# Schema-only SQL dump (may be a git-ignored file):",
            "# SQL dump skema tanpa data (boleh file yang di-.gitignore):",
        ),
        "# schema:",
        "#   - database/schema.sql",
        "",
        t("# Folders that do not need scanning:", "# Folder yang tidak perlu dipindai:"),
        "# ignore:",
        "#   - public/assets/vendor",
        "",
        t(
            "# Endpoints created dynamically that cannot be detected:",
            "# Endpoint yang dibuat dinamis dan tidak terdeteksi:",
        ),
        "# endpoints:",
        "#   - {method: GET, path: /api/health, handler: Health::index, note: "
        + auto_routing
        + "}",
        "",
        t("# Notes shown in the document:", "# Catatan yang ditampilkan di dokumen:"),
        "# notes:",
        "#   - " + t("Auto-routing is enabled in production.", "Auto-routing aktif di production."),
        "",
    ]
