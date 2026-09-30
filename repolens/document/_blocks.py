"""The block list a document is made of, and small formatting helpers for its sections.

Sections never build block dictionaries by hand; they call the methods of `Blocks`:

    doc.h1("Database")
    doc.table(["Column", "Type"], rows, widths=[2, 2])
    doc.note("Values are masked.", level="warn")
"""

from __future__ import annotations

from repolens.i18n import t


class Blocks(list):
    """A list of blocks with one method per block type (see repolens/document/__init__.py)."""

    def title(self, title: str, subtitle: str, meta: list[tuple[str, str]]) -> None:
        self.append({"t": "title", "title": title, "subtitle": subtitle, "meta": meta})

    def h1(self, text: str) -> None:
        self.append({"t": "h1", "text": text})

    def h2(self, text: str) -> None:
        self.append({"t": "h2", "text": text})

    def h3(self, text: str) -> None:
        self.append({"t": "h3", "text": text})

    def p(self, text: str) -> None:
        """A paragraph; inline `code` and **bold** are supported."""
        self.append({"t": "p", "text": text})

    def paragraphs(self, text: str) -> None:
        """Several paragraphs separated by blank lines (as the AI writes them)."""
        for paragraph in text.split("\n\n"):
            self.p(paragraph.strip())

    def bullets(self, items: list[str]) -> None:
        self.append({"t": "bullets", "items": items})

    def table(self, headers: list[str], rows: list[list[str]], widths: list[float]) -> None:
        """`widths` are relative column weights, e.g. [1, 3] makes the second column 3x wider."""
        self.append({"t": "table", "headers": headers, "rows": rows, "widths": widths})

    def code(self, text: str) -> None:
        self.append({"t": "code", "text": text})

    def note(self, text: str, level: str = "info") -> None:
        """A highlighted remark; level is "info" or "warn"."""
        self.append({"t": "note", "level": level, "text": text})


def value(item) -> str:
    """A fact as table text: None and "" become "-", lists are joined, booleans become yes/no."""
    if item is None or item == "":
        return "-"
    if isinstance(item, bool):
        return t("yes", "ya") if item else t("no", "tidak")
    if isinstance(item, (list, tuple)):
        return ", ".join(map(str, item)) if item else "-"
    return str(item)


def source(file: str, line: int | None) -> str:
    """Where something was found: "routes/api.php:12" (the line is left out when it is 1)."""
    return f"{file}:{line}" if line and line > 1 else file
