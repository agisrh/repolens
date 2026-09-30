"""`repolens export <scan.json>`: render the documents again from an earlier scan.

Useful for another format or language without scanning again. The documents are written
next to the scan.json unless --out is given.
"""

from __future__ import annotations

from pathlib import Path

from repolens import ui
from repolens.commands._common import ALL_FORMATS, add_command, formats
from repolens.i18n import LANGUAGES, get_lang, set_lang, t
from repolens.output import format_list, load_scan, write_documents

NAME = "export"


def register(subparsers, common):
    p = add_command(
        subparsers,
        NAME,
        common,
        "Render documents again from scan.json without scanning",
        "Render ulang dokumen dari scan.json tanpa memindai lagi",
    )
    p.add_argument("scan")
    p.add_argument("--format", type=formats, default=ALL_FORMATS)
    p.add_argument("--out")
    return p


def run(args) -> int:
    facts = load_scan(args.scan)
    if not args.lang_given:
        # Use the scan's language; scans made before `lang` existed were written in Indonesian.
        set_lang(facts.get("lang") or "id")
    out_dir = Path(args.out) if args.out else Path(args.scan).parent
    names = format_list(args.format)
    ui.header("Export", f"{args.scan}  ·  {names}  ·  {LANGUAGES[get_lang()]}")
    if facts.get("lang") and facts["lang"] != get_lang():
        ui.info(
            t(
                "Findings and notes produced during the scan stay in the scan's language. "
                "Scan again for a full translation.",
                "Temuan dan catatan hasil scan tetap dalam bahasa saat scan. "
                "Scan ulang untuk terjemahan penuh.",
            )
        )
    with ui.task(t(f"Rendering {names}", f"Membuat {names}")):
        written = write_documents(facts, out_dir, args.format)
    for path in written:
        ui.out.print(f"    {path}", markup=False)
    return 0
