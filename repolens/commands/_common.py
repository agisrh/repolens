"""Small helpers shared by the command modules.

Argument helpers keep each command's `register()` short: every option is one call with its
English and Indonesian help text side by side. Source checks and the JSON printer are used
by more than one command, so they live here instead of being copied.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from repolens.i18n import t
from repolens.output import RENDERERS
from repolens.scanner import is_git_url

ALL_FORMATS = ["pdf", "docx", "md"]


# ---- defining arguments ----------------------------------------------------------------


def flag(parser, name: str, en: str, id: str) -> None:
    """An on/off switch such as --json."""
    parser.add_argument(name, action="store_true", help=t(en, id))


def option(parser, name: str, en: str, id: str, **kwargs) -> None:
    """An option that takes a value, such as --ref v1.2.0."""
    parser.add_argument(name, help=t(en, id), **kwargs)


def add_command(subparsers, name: str, common, en: str, id: str) -> argparse.ArgumentParser:
    """A sub-command that also accepts the options every command has (--lang, --debug)."""
    return subparsers.add_parser(name, parents=[common], help=t(en, id))


def formats(value: str) -> list[str]:
    """argparse type for --format: "pdf,md" -> ["pdf", "md"], with unknown names rejected."""
    names = [f.strip().lower() for f in value.split(",") if f.strip()]
    unknown = ", ".join(f for f in names if f not in RENDERERS) or "-"
    if unknown != "-" or not names:
        raise argparse.ArgumentTypeError(
            t(
                f"unknown format: {unknown} (choose: pdf, docx, md)",
                f"format tidak dikenal: {unknown} (pilihan: pdf, docx, md)",
            )
        )
    return list(dict.fromkeys(names))  # drop duplicates, keep order


def positive_int(value: str) -> int:
    """argparse type for counts that must be 1 or more."""
    try:
        number = int(value)
    except ValueError:
        number = 0
    if number < 1:
        raise argparse.ArgumentTypeError(
            t(
                f"must be a whole number of 1 or more, not `{value}`",
                f"harus bilangan bulat 1 atau lebih, bukan `{value}`",
            )
        )
    return number


# ---- checking the source ----------------------------------------------------------------


def check_source_options(args) -> None:
    """Fail early, before any output, when the source or its options cannot work together."""
    if not is_git_url(args.source) and not Path(args.source).expanduser().is_dir():
        raise FileNotFoundError(t("Folder not found: ", "Folder tidak ditemukan: ") + args.source)
    if not getattr(args, "no_git", False):
        return
    if is_git_url(args.source):
        raise RuntimeError(
            t(
                "--no-git only works with a local folder; a git URL has to be cloned with git.",
                "--no-git hanya untuk folder lokal; URL git harus di-clone dengan git.",
            )
        )
    if getattr(args, "ref", None) or getattr(args, "compare_ref", None):
        raise RuntimeError(
            t(
                "--no-git cannot be combined with --ref or --compare-ref, "
                "which read from git history.",
                "--no-git tidak bisa digabung dengan --ref atau --compare-ref, "
                "yang membaca riwayat git.",
            )
        )


def source_detail(args) -> str:
    """How the source is read, for the header line: "app @ v1.0", "app (working tree)", ..."""
    source = args.source
    if args.ref:
        return source + f" @ {args.ref}"
    if getattr(args, "no_git", False):
        return source + t(" (plain folder, no git)", " (folder biasa, tanpa git)")
    if not is_git_url(args.source):
        return source + " (working tree)"
    return source


# ---- output -------------------------------------------------------------------------------


def emit_json(data: dict) -> None:
    """Print a machine-readable result on stdout (used by --json)."""
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def count_warnings(checks: list[dict]) -> int:
    """Number of coverage findings that need attention (what --strict fails on)."""
    return sum(1 for check in checks if check["level"] == "warn")
