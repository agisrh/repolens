"""Entry point of the `repolens` command.

  repolens                           interactive menu (in a terminal)
  repolens scan <folder|git-url>     scan and write PDF, Word, and Markdown documents
  repolens doctor <folder>           what was detected and what is probably missing
  repolens init <folder>             create a .repolens.yml template
  repolens export <scan.json>        render the documents again from a previous scan
  repolens diff <old.json> <new.json>
  repolens auth login|status|logout  your own Anthropic API key and model
  repolens update [--check]          install the newest release
  repolens completion bash|zsh|fish  shell completion script

Every command takes --lang en|id (default: REPOLENS_LANG or en) and --debug.

This module only builds the argument parser from repolens/commands/ and turns errors into
short messages and exit codes; each command's work is in its own module there.
"""

from __future__ import annotations

import argparse
import os
import sys

from repolens import __version__, ui
from repolens.commands import COMMANDS
from repolens.commands._common import flag, option
from repolens.i18n import LANGUAGES, set_lang, t


def build_parser() -> argparse.ArgumentParser:
    """The `repolens` argument parser, with one sub-command per module in COMMANDS."""
    common = argparse.ArgumentParser(add_help=False)  # options every command accepts
    option(
        common,
        "--lang",
        "Output language: en or id (default: REPOLENS_LANG or en)",
        "Bahasa output: en atau id (default: REPOLENS_LANG atau en)",
        choices=sorted(LANGUAGES),
    )
    flag(
        common,
        "--debug",
        "Show the full traceback on unexpected errors",
        "Tampilkan traceback lengkap saat error tak terduga",
    )
    parser = argparse.ArgumentParser(
        prog="repolens",
        parents=[common],
        description=t(
            "Generate technical documentation from a repository. "
            "Run without arguments for the interactive menu.",
            "Buat dokumentasi teknis dari repository. "
            "Jalankan tanpa argumen untuk menu interaktif.",
        ),
    )
    parser.add_argument("--version", action="version", version=f"repolens {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    for command in COMMANDS:
        command.register(subparsers, common).set_defaults(func=command.run)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one command and return its exit code (0 ok, 1 failed, 2 bug, 130 cancelled)."""
    argv = list(sys.argv[1:] if argv is None else argv)
    set_lang(_initial_lang(argv))
    debug = "--debug" in argv or bool(
        os.environ.get("REPOLENS_DEBUG") or os.environ.get("DOCGEN_DEBUG")
    )
    ui.set_quiet(False)
    try:
        if not argv:
            argv = _from_menu()
            if not argv:
                return 0
        args = build_parser().parse_args(argv)
        if not getattr(args, "func", None):
            build_parser().print_help()
            return 0
        args.lang_given = args.lang is not None
        if args.lang:
            set_lang(args.lang)
        ui.set_quiet(getattr(args, "json", False))  # keep stdout clean for JSON output
        return args.func(args)
    except (RuntimeError, OSError) as exc:  # expected failures: bad input, git errors, ...
        if debug:
            raise
        ui.error(str(exc))
        return 1
    except KeyboardInterrupt:
        ui.error(t("Cancelled.", "Dibatalkan."))
        return 130
    except Exception as exc:  # a bug in repolens: short message, full traceback with --debug
        if debug:
            raise
        name = type(exc).__name__
        ui.error(
            t(
                f"Unexpected error ({name}): {exc}\n"
                "Run again with --debug for details, and report it to the repolens maintainers.",
                f"Error tak terduga ({name}): {exc}\n"
                "Jalankan ulang dengan --debug untuk detail, lalu laporkan ke pengelola repolens.",
            )
        )
        return 2


def _from_menu() -> list[str]:
    """Without arguments: the interactive menu in a terminal, the help text otherwise."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        build_parser().print_help()
        return []
    from repolens import menu  # imported here: the menu is only needed in this case

    argv = menu.run() or []
    set_lang(_initial_lang(argv))
    return argv


def _initial_lang(argv: list[str]) -> str:
    """The language is needed before argparse runs, because help texts are translated too."""
    lang = os.environ.get("REPOLENS_LANG") or os.environ.get("DOCGEN_LANG") or "en"
    for i, arg in enumerate(argv):
        if arg == "--lang" and i + 1 < len(argv):
            lang = argv[i + 1]
            break
        if arg.startswith("--lang="):
            lang = arg.split("=", 1)[1]
            break
    return lang if lang in LANGUAGES else "en"
