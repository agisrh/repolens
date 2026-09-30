"""Interactive menu shown by `repolens` without arguments.

Every flow only builds the argument list for a regular command, shows the equivalent
command line (so it can be reused in scripts or CI), and runs it after confirmation.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

import questionary
from questionary import Choice, Separator, Style

from repolens import ui
from repolens.i18n import LANGUAGES, get_lang, t
from repolens.scanner import is_git_url

STYLE = Style([
    ("qmark", f"fg:{ui.BRAND} bold"),
    ("question", "bold"),
    ("pointer", f"fg:{ui.BRAND} bold"),
    ("highlighted", f"fg:{ui.BRAND} bold"),
    ("selected", f"fg:{ui.BRAND}"),
    ("answer", f"fg:{ui.BRAND}"),
    ("instruction", "fg:#888888"),
])
OTHER = "__other__"


class Cancelled(Exception):
    pass


def _ask(question):
    """Run a questionary prompt; Ctrl+C / Esc cancels the whole menu."""
    answer = question.ask()
    if answer is None:
        raise Cancelled
    return answer


def _select(message: str, choices: list, default=None):
    return _ask(questionary.select(message, choices=choices, default=default, pointer="➤", style=STYLE,
                                   instruction=t("(↑/↓, Enter)", "(↑/↓, Enter)")))


def _folder(message: str, default: str = ".") -> str:
    return _ask(questionary.path(message, default=default, only_directories=True, style=STYLE,
                                 validate=lambda p: Path(p).expanduser().is_dir() or t("Folder not found", "Folder tidak ditemukan")))


def _text(message: str, default: str = "", validate=None) -> str:
    return _ask(questionary.text(message, default=default, validate=validate, style=STYLE)).strip()


def _git(folder: str, *args: str) -> list[str]:
    try:
        result = subprocess.run(["git", "-C", folder, *args], capture_output=True, text=True, timeout=20,
                                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line for line in result.stdout.splitlines() if line.strip()] if result.returncode == 0 else []


def _is_git_repo(folder: str) -> bool:
    return _git(folder, "rev-parse", "--is-inside-work-tree") == ["true"]


def _pick_ref(folder: str, message: str, exclude: str | None = None, allow_none: bool = False) -> str | None:
    tags = [tag for tag in _git(folder, "tag", "--sort=-creatordate")[:25] if tag != exclude]
    branches = [b for b in _git(folder, "for-each-ref", "--format=%(refname:short)", "refs/heads")[:10] if b != exclude]
    choices: list = []
    if allow_none:
        choices.append(Choice(t("No comparison", "Tanpa pembanding"), None))
    if tags:
        choices += [Separator("── tags ──")] + [Choice(tag, tag) for tag in tags]
    if branches:
        choices += [Separator("── branches ──")] + [Choice(b, b) for b in branches]
    choices.append(Choice(t("Type a tag, branch, or commit…", "Ketik tag, branch, atau commit…"), OTHER))
    ref = _select(message, choices)
    if ref == OTHER:
        ref = _text(t("Ref:", "Ref:"), validate=lambda v: bool(v.strip()) or t("Required", "Wajib diisi"))
    return ref


def _recent_scans() -> list[Path]:
    return sorted(Path("docs-output").glob("*/scan.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]


def _pick_scan(message: str, exclude: Path | None = None) -> str:
    scans = [p for p in _recent_scans() if p != exclude]
    if scans:
        choice = _select(message, [Choice(str(p.parent.name), str(p)) for p in scans] + [Choice(t("Other file…", "File lain…"), OTHER)])
        if choice != OTHER:
            return choice
    return _ask(questionary.path(message, style=STYLE,
                                 validate=lambda p: Path(p).expanduser().is_file() or t("File not found", "File tidak ditemukan")))


def _formats() -> str:
    picked = _ask(questionary.checkbox(t("Formats", "Format"), style=STYLE, pointer="➤",
                                       choices=[Choice("PDF", "pdf", checked=True), Choice("Word (.docx)", "docx", checked=True),
                                                Choice("Markdown", "md", checked=True)],
                                       validate=lambda v: bool(v) or t("Pick at least one", "Pilih minimal satu")))
    return ",".join(picked)


def _language() -> str:
    return _select(t("Document language", "Bahasa dokumen"), [Choice(name, code) for code, name in LANGUAGES.items()], default=get_lang())


def _scan_flow() -> list[str]:
    argv = ["scan"]
    kind = _select(t("Source", "Sumber"), [Choice(t("Local folder", "Folder lokal"), "local"),
                                            Choice(t("Git repository URL", "URL repository git"), "url")])
    if kind == "url":
        url = _text(t("Git URL (https or ssh)", "URL git (https atau ssh)"),
                    validate=lambda v: is_git_url(v.strip()) or t("Not a git URL", "Bukan URL git"))
        argv.append(url)
        ref = _text(t("Tag / branch / commit (empty = default branch)", "Tag / branch / commit (kosong = branch utama)"))
        if ref:
            argv += ["--ref", ref]
        compare = _text(t("Compare with ref (empty = no comparison)", "Bandingkan dengan ref (kosong = tanpa pembanding)"))
        if compare:
            argv += ["--compare-ref", compare]
    else:
        folder = _folder(t("Folder", "Folder"))
        argv.append(folder)
        if _is_git_repo(folder):
            mode = _select(t("What to scan", "Yang dipindai"), [
                Choice(t("Current files, with git  (follows .gitignore, adds commit info)",
                         "File saat ini, dengan git  (mengikuti .gitignore, ada info commit)"), "git"),
                Choice(t("Current files as a plain folder  (everything on disk, no git)",
                         "File saat ini sebagai folder biasa  (semua file di disk, tanpa git)"), "plain"),
                Choice(t("A tag / branch / commit  (clean release, working tree untouched)",
                         "Tag / branch / commit  (rilis bersih, working tree tidak disentuh)"), "ref"),
            ])
            ref = None
            if mode == "plain":
                argv.append("--no-git")
            elif mode == "ref":
                ref = _pick_ref(folder, t("Release to scan", "Rilis yang dipindai"))
                argv += ["--ref", ref]
            if mode != "plain":
                compare = _pick_ref(folder, t("Compare with an earlier release?", "Bandingkan dengan rilis sebelumnya?"),
                                    exclude=ref, allow_none=True)
                if compare:
                    argv += ["--compare-ref", compare]
        else:
            ui.info(t("Not a git repository: scanned as a plain folder.", "Bukan repository git: dipindai sebagai folder biasa."))
    formats = _formats()
    if formats != "pdf,docx,md":
        argv += ["--format", formats]
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if not _ask(questionary.confirm(t("Write a narrative summary with AI? (sends scan facts, never source code, to Anthropic)",
                                      "Tulis ringkasan naratif dengan AI? (mengirim fakta hasil scan, bukan source code, ke Anthropic)"),
                                    default=has_key, style=STYLE)):
        argv.append("--no-ai")
    argv += ["--lang", _language()]
    out = _text(t("Output folder", "Folder output"), default="docs-output")
    if out != "docs-output":
        argv += ["--out", out]
    return argv


def _doctor_flow() -> list[str]:
    return ["doctor", _folder(t("Folder", "Folder"))]


def _init_flow() -> list[str]:
    return ["init", _folder(t("Folder", "Folder"))]


def _diff_flow() -> list[str]:
    old = _pick_scan(t("Older scan", "Scan lama"))
    new = _pick_scan(t("Newer scan", "Scan baru"), exclude=Path(old))
    return ["diff", old, new]


def _export_flow() -> list[str]:
    argv = ["export", _pick_scan("scan.json")]
    formats = _formats()
    if formats != "pdf,docx,md":
        argv += ["--format", formats]
    return argv + ["--lang", _language()]


FLOWS = {"scan": _scan_flow, "doctor": _doctor_flow, "init": _init_flow, "diff": _diff_flow, "export": _export_flow}


def run() -> list[str] | None:
    """Ask what to do; return the argv for the chosen command, or None to quit."""
    ui.header(t("Technical documentation from your repositories", "Dokumentasi teknis dari repository Anda"))
    try:
        action = _select(t("What do you want to do?", "Mau melakukan apa?"), [
            Choice(t("Scan & generate documentation", "Scan & buat dokumentasi"), "scan"),
            Choice(t("Check scan coverage (doctor)", "Cek cakupan scan (doctor)"), "doctor"),
            Choice(t("Compare two scans (diff)", "Bandingkan dua scan (diff)"), "diff"),
            Choice(t("Re-export documents from scan.json", "Export ulang dokumen dari scan.json"), "export"),
            Choice(t("Create .repolens.yml (init)", "Buat .repolens.yml (init)"), "init"),
            Separator(),
            Choice(t("Quit", "Keluar"), None),
        ])
        if not action:
            return None
        argv = FLOWS[action]()
        ui.out.print()
        ui.hint(t("Same as: ", "Sama dengan: ") + "repolens " + shlex.join(argv), indent="")
        if not _ask(questionary.confirm(t("Run now?", "Jalankan sekarang?"), default=True, style=STYLE)):
            return None
        return argv
    except Cancelled:
        return None
