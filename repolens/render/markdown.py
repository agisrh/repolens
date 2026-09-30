"""Markdown renderer."""

from __future__ import annotations

import re
from pathlib import Path
from repolens.i18n import t as tr  # `t` is the block type in render()


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", "<br>")


def _anchor(text: str) -> str:
    return re.sub(r"[^\w\- ]", "", text.lower()).strip().replace(" ", "-")


def render(blocks: list[dict], path: Path) -> Path:
    lines: list[str] = []
    h1_index = 0
    headings = [blk["text"] for blk in blocks if blk["t"] == "h1"]
    for blk in blocks:
        t = blk["t"]
        if t == "title":
            lines += [f"# {blk['title']}", "", f"**{blk['subtitle']}**", "", "| | |", "|:--|:--|"]
            lines += [f"| {_cell(k)} | {_cell(v)} |" for k, v in blk["meta"]]
            lines += ["", "## " + tr("Contents", "Daftar Isi"), ""]
            lines += [f"{i}. [{h}](#{_anchor(f'{i}. {h}')})" for i, h in enumerate(headings, 1)]
            lines.append("")
        elif t == "h1":
            h1_index += 1
            lines += ["", "---", "", f"## {h1_index}. {blk['text']}", ""]
        elif t == "h2":
            lines += [f"### {blk['text']}", ""]
        elif t == "h3":
            lines += [f"#### {blk['text']}", ""]
        elif t == "p":
            lines += [blk["text"], ""]
        elif t == "bullets":
            lines += [f"- {item}" for item in blk["items"]] + [""]
        elif t == "table":
            lines.append("| " + " | ".join(_cell(h) for h in blk["headers"]) + " |")
            lines.append("|" + "|".join(":--" for _ in blk["headers"]) + "|")
            for row in blk["rows"]:
                lines.append("| " + " | ".join(_cell(c) for c in row) + " |")
            lines.append("")
        elif t == "code":
            lines += ["```text", blk["text"], "```", ""]
        elif t == "note":
            label = tr("Warning", "Perhatian") if blk.get("level") == "warn" else tr("Note", "Catatan")
            lines += [f"> **{label}:** {blk['text']}", ""]
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path
