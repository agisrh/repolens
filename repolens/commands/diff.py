"""`repolens diff <old.json> <new.json>`: what changed between two scans.

The comparison itself lives in repolens/diff.py (it is also used by `scan --compare-ref`);
this module only prints it.
"""

from __future__ import annotations

from repolens import diff, ui
from repolens.commands._common import add_command, emit_json, flag
from repolens.i18n import label, t
from repolens.output import load_scan

NAME = "diff"
MAX_ROWS = 50  # per section; --json always has the full list

SECTION_TITLES = {
    "frameworks": "Tech stack",
    "platforms": "Platform",
    "endpoints": "Endpoints",
    "database": "Database",
    "env": "Environment",
    "dependencies": "Dependency",
}


def register(subparsers, common):
    p = add_command(
        subparsers,
        NAME,
        common,
        "Show the changes between two scan.json files",
        "Tampilkan perubahan antara dua scan.json",
    )
    p.add_argument("old")
    p.add_argument("new")
    flag(p, "--json", "Print the changes as JSON", "Cetak perubahan sebagai JSON")
    return p


def run(args) -> int:
    changes = diff.compare(load_scan(args.old), load_scan(args.new))
    if args.json:
        emit_json(changes)
        return 0
    ui.header("Diff", f"{changes['from']} → {changes['to']}")
    if diff.is_empty(changes):
        ui.ok(t("No changes.", "Tidak ada perubahan."))
        return 0
    for section, title in SECTION_TITLES.items():
        if changes[section]:
            _print_section(title, changes[section])
    return 0


def _print_section(title: str, items: list[dict]) -> None:
    """One table per section: the kind of change first, then the changed values."""
    ui.section(f"{title} ({len(items)})")
    rows = []
    for item in items[:MAX_ROWS]:
        row = [label(item["change"])] if "change" in item else []
        row += [str(value) for key, value in item.items() if key != "change" and value is not None]
        rows.append(row)
    width = max(len(row) for row in rows)
    ui.table([], [row + [""] * (width - len(row)) for row in rows])
    if len(items) > MAX_ROWS:
        more = len(items) - MAX_ROWS
        ui.skip(
            t(
                f"… {more} more (use --json for the full list)",
                f"… {more} lagi (pakai --json untuk daftar lengkap)",
            )
        )
