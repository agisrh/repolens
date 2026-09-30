"""Reading and writing scan results on disk.

A scan is written to `<out>/<project>-<release>/`: the raw facts as `scan.json`, plus one
document per requested format. `load_scan()` reads such a `scan.json` back for `export`
and `diff`.

To add an output format, write a `render(blocks, path) -> Path` function in
`repolens/render/` and add it to RENDERERS and FORMAT_NAMES below.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from repolens import document, ui
from repolens.i18n import t
from repolens.render import docx_out, markdown, pdf_out

# format name -> (render function, file extension)
RENDERERS = {
    "md": (markdown.render, ".md"),
    "docx": (docx_out.render, ".docx"),
    "pdf": (pdf_out.render, ".pdf"),
}
FORMAT_NAMES = {"pdf": "PDF", "docx": "Word", "md": "Markdown"}

# Keys every scan.json has; used to recognise one.
REQUIRED_KEYS = (
    "repolens_version",
    "scanned_at",
    "source",
    "project",
    "tree",
    "languages",
    "frameworks",
    "dependencies",
    "endpoints",
    "database",
    "config",
    "security",
)


def slug(text: str) -> str:
    """Safe file-name part: "My App 1.0" -> "my-app-1.0"."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-").lower() or "project"


def format_list(formats: list[str]) -> str:
    """["pdf", "md"] -> "PDF, Markdown"."""
    return ", ".join(FORMAT_NAMES[f] for f in formats)


def output_dir(out: str, facts: dict) -> Path:
    """Folder that holds one project release: <out>/<project>-<release>."""
    release = document.release_label(facts)
    return Path(out) / f"{slug(facts['project']['name'])}-{slug(release)}"


def display_path(path: Path) -> str:
    """Relative to the current folder when that is shorter (docs-output/app-1.0, not /Users/…)."""
    try:
        relative = os.path.relpath(path)
    except ValueError:  # a different drive on Windows
        return str(path)
    return relative if len(relative) < len(str(path)) else str(path)


def load_scan(path: str) -> dict:
    """Read a scan.json produced by `repolens scan`.

    Raises a readable error (not a traceback) for a missing, invalid, or unrelated file."""
    file = Path(path)
    if not file.is_file():
        raise FileNotFoundError(t("File not found: ", "File tidak ditemukan: ") + str(file))
    try:
        facts = json.loads(file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError(
            t(f"{file} is not valid JSON: {exc}", f"{file} bukan JSON yang valid: {exc}")
        ) from None
    # Scans written before the rename to RepoLens call the version key `docgen_version`.
    if isinstance(facts, dict) and "docgen_version" in facts:
        facts.setdefault("repolens_version", facts.pop("docgen_version"))
    missing = [k for k in REQUIRED_KEYS if not isinstance(facts, dict) or k not in facts]
    if missing:
        keys = ", ".join(missing)
        raise RuntimeError(
            t(
                f"{file} is not a `repolens scan` result (missing: {keys}).",
                f"{file} bukan hasil `repolens scan` (tidak ada: {keys}).",
            )
        )
    return facts


def write_documents(
    facts: dict, out_dir: Path, formats: list[str], force: bool = True
) -> list[Path]:
    """Write scan.json and the documents; returns the files written, scan.json first."""
    note = _check_overwrite(facts, out_dir, force)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"{slug(facts['project']['name'])}-{slug(document.release_label(facts))}"
    scan_file = out_dir / "scan.json"
    scan_file.write_text(json.dumps(facts, indent=2, ensure_ascii=False), encoding="utf-8")
    blocks = document.build(facts)
    written = [scan_file]
    for fmt in formats:
        render, extension = RENDERERS[fmt]
        written.append(render(blocks, out_dir / f"{base}{extension}"))
    if note:
        ui.info(note)
    return written


# ---- protecting another project's documents -----------------------------------------------


def _identity(facts: dict) -> str | None:
    """What makes two scans the same project: the git remote, or the folder when there is none."""
    remote = (facts.get("git") or {}).get("remote")
    if remote:
        return re.sub(r"\.git$", "", remote.rstrip("/")).lower()
    return (facts.get("source") or {}).get("location")


def _check_overwrite(facts: dict, out_dir: Path, force: bool) -> str | None:
    """Refuse to overwrite another project's documents that share the same name and release.

    Returns a note when the same project is overwritten at a different commit."""
    previous_file = out_dir / "scan.json"
    if force or not previous_file.is_file():
        return None
    try:
        previous = json.loads(previous_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    old_id, new_id = _identity(previous), _identity(facts)
    if old_id and new_id and old_id != new_id:
        raise RuntimeError(_name_clash_message(facts, out_dir, old_id, new_id))
    old_commit = (previous.get("git") or {}).get("commit_short")
    new_commit = (facts.get("git") or {}).get("commit_short")
    if old_commit and new_commit and old_commit != new_commit:
        return t(
            f"Replaced the previous result (commit {old_commit} → {new_commit})",
            f"Menimpa hasil sebelumnya (commit {old_commit} → {new_commit})",
        )
    return None


def _name_clash_message(facts: dict, out_dir: Path, old_id: str, new_id: str) -> str:
    """Explain which two projects clash, where the shared name comes from, and the fixes."""
    project = facts["project"]
    name, release = project["name"], document.release_label(facts)
    origin = t(f"from {project['name_source']}", f"dari {project['name_source']}")
    unique = slug(project.get("folder") or "") or "my-app"
    here, elsewhere = display_path(out_dir), display_path(out_dir.parent / unique)
    return t(
        f"Two different projects are both called {name} {release} ({origin}), "
        "so their documents would overwrite each other.\n"
        f"  already in {here}:  {old_id}\n"
        f"  scanned now:  {new_id}\n"
        "Fix it with one of:\n"
        f"  → give this project its own name: add `name: {unique}` to its .repolens.yml\n"
        f"  → write somewhere else:  --out {elsewhere}\n"
        "  → overwrite anyway:  --force",
        f"Dua proyek berbeda sama-sama bernama {name} {release} ({origin}), "
        "jadi dokumennya akan saling menimpa.\n"
        f"  sudah ada di {here}:  {old_id}\n"
        f"  yang dipindai sekarang:  {new_id}\n"
        "Perbaiki dengan salah satu:\n"
        f"  → beri nama sendiri untuk proyek ini: tambahkan `name: {unique}` di .repolens.yml-nya\n"
        f"  → tulis ke folder lain:  --out {elsewhere}\n"
        "  → tetap timpa:  --force",
    )
