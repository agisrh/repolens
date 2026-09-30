"""Terminal output: headers, step markers, spinners, and the final summary.

Visual vocabulary (shared by every command):
  ➤ step in progress / neutral step     ✓ done      ◎ skipped
  ⚠ needs attention                     ℹ info      ✗ error      → hint

Colours and spinners switch off automatically when output is not a terminal, and when
NO_COLOR is set. `--json` makes the human output silent so stdout stays machine-readable.
"""

from __future__ import annotations

import time
from contextlib import contextmanager

from rich.console import Console
from rich.markup import escape
from rich.padding import Padding
from rich.table import Table

from repolens import __version__

BRAND = "#8B5CF6"
WIDTH = 70

out = Console(highlight=False, soft_wrap=True)
err = Console(stderr=True, highlight=False, soft_wrap=True)


def set_quiet(quiet: bool) -> None:
    out.quiet = quiet


def header(title: str, detail: str | None = None) -> None:
    out.print()
    out.print(f"[bold {BRAND}]repolens[/] [dim]{__version__}[/]  [bold]{escape(title)}[/]")
    if detail:
        out.print(f"[dim]⚙[/] {escape(detail)}")
    out.print()


def section(title: str) -> None:
    out.print()
    out.print(f"[bold]{escape(title)}[/]")


def step(message: str) -> None:
    out.print(f"  [{BRAND}]➤[/] {escape(message)}")


def ok(message: str) -> None:
    out.print(f"  [green]✓[/] {escape(message)}")


def skip(message: str) -> None:
    out.print(f"  [dim]◎ {escape(message)}[/]")


def warn(message: str, indent: str = "  ") -> None:
    out.print(f"{indent}[yellow]⚠[/] {escape(message)}")


def info(message: str, indent: str = "  ") -> None:
    out.print(f"{indent}[blue]ℹ[/] {escape(message)}")


def hint(message: str, indent: str = "    ") -> None:
    out.print(f"{indent}[dim]→ {escape(message)}[/]")


def error(message: str) -> None:
    err.print(f"[red]✗[/] {escape(message)}")


def log(message: str, kind: str = "step") -> None:
    """Progress callback handed to scanner/ai: log(message, kind)."""
    {"warn": warn, "skip": skip, "ok": ok}.get(kind, step)(message)


@contextmanager
def task(message: str, done: str | None = None):
    """Spinner while a slow step runs (clone, AI, render), then a ✓ line with the elapsed time."""
    started = time.monotonic()
    with out.status(f"[{BRAND}]{escape(message)}…[/]", spinner="dots"):
        yield
    ok(f"{done or message} [{time.monotonic() - started:.1f}s]")


def summary(title: str, rows: list[tuple[str, str]], subtitle: str | None = None) -> None:
    """Bordered block at the end of a command, like:

    ======================================================================
    Documentation ready  ·  web-portal 0be74e3  ·  0.5s
    Stack      CodeIgniter 4
    ======================================================================
    """
    rule = f"[{BRAND}]" + "=" * WIDTH + "[/]"
    out.print()
    out.print(rule)
    out.print(f"[bold]{escape(title)}[/]" + (f"  [dim]·  {escape(subtitle)}[/]" if subtitle else ""))
    width = max((len(label) for label, _ in rows), default=0)
    for label, value in rows:
        # Plain lines rather than a table: long paths wrap instead of being cut off with "…".
        out.print(f"[dim]{escape(label.ljust(width))}[/]  {escape(value)}")
    out.print(rule)


def table(headers: list[str], rows: list[list[str]], indent: int = 2) -> None:
    """Borderless aligned columns for listings (doctor, diff)."""
    grid = Table(box=None, show_header=bool(headers), header_style="dim", padding=(0, 2, 0, 0), pad_edge=False)
    for _ in headers or rows[0]:
        grid.add_column()
    for row in rows:
        grid.add_row(*[escape(str(c)) for c in row])
    out.print(Padding(grid, (0, 0, 0, indent), expand=False))
