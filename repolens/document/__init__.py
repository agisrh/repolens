"""Turn scan facts into a format-neutral list of blocks that every renderer understands.

Block types (built with the methods of _blocks.Blocks):
  title      {title, subtitle, meta: [(label, value)]}
  h1/h2/h3   {text}
  p          {text}            inline `code` and **bold** are supported
  bullets    {items}
  table      {headers, rows, widths}   widths are relative column weights
  code       {text}
  note       {text, level: info|warn}

Each section of the document is a function `(doc, facts) -> None` that appends its blocks;
SECTIONS below lists them in document order. To add a section, write such a function in
the module it fits (or a new one) and put it in SECTIONS.

Text follows the current output language (repolens.i18n). Strings produced during the scan
(coverage messages, extractor notes) keep the language the scan ran in.
"""

from __future__ import annotations

from repolens.document import changes, closing, environment, interfaces, overview, project
from repolens.document._blocks import Blocks
from repolens.document.overview import release_label

__all__ = ["build", "release_label"]

SECTIONS = [
    overview.title,
    overview.summary,  # 1
    changes.changes,  # 2, only when compared with an earlier release
    project.release,  # 3
    project.tech_stack,  # 4
    project.folders,  # 5
    interfaces.endpoints,  # 6
    interfaces.database,  # 7
    environment.configuration,  # 8
    environment.platforms,  # 9, only when there is something to show
    environment.dependencies,  # 10
    closing.security,  # 11
    closing.recommendations,  # 12, only with the AI summary
    closing.coverage,  # 13
    closing.about,  # 14
]


def build(facts: dict) -> list[dict]:
    """All blocks of the document for these scan facts."""
    doc = Blocks()
    for section in SECTIONS:
        section(doc, facts)
    return list(doc)
