"""Tables from CREATE TABLE statements in .sql files (and schema dumps listed in .repolens.yml)."""

from __future__ import annotations

import re

from repolens.extractors._text import closing_offset
from repolens.extractors.database._common import (
    column,
    mark_primary_key,
    split_top_level,
    table,
)
from repolens.repo import Repo, line_of

CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"[`\"\[]?(?:\w+[`\"\]]?\.[`\"\[]?)?(\w+)[`\"\]]?\s*\(",  # optional schema. prefix, quotes
    re.I,
)
CONSTRAINT = re.compile(r"^(PRIMARY|FOREIGN|CONSTRAINT|KEY|INDEX|UNIQUE|CHECK|FULLTEXT)\b", re.I)


def sql_files(repo: Repo, extra: list[str] = ()) -> list[dict]:
    tables = []
    for path in dict.fromkeys(repo.by_ext(".sql") + list(extra)):
        text = repo.read(path)
        for match in CREATE_TABLE.finditer(text):
            end = closing_offset(text, match.end(), "(", ")")
            columns = _columns(text[match.end() : end - 1])
            tables.append(table(match.group(1), "SQL", path, line_of(text, match.start()), columns))
    return tables


def _columns(body: str) -> list[dict]:
    """Column definitions of one CREATE TABLE body; table constraints mark primary keys."""
    columns = []
    for part in split_top_level(body):
        if CONSTRAINT.match(part):
            if part.upper().startswith("PRIMARY"):  # PRIMARY KEY (`id`, `code`)
                for name in re.findall(r"[`\"]?(\w+)[`\"]?", part.split("(", 1)[-1]):
                    mark_primary_key(columns, name)
            continue
        words = part.split(None, 2)  # name, type, the rest
        if len(words) < 2:
            continue
        rest = words[2] if len(words) > 2 else ""
        flags = []
        if re.search(r"primary\s+key", rest, re.I):
            flags.append("PK")
        if re.search(r"not\s+null", rest, re.I):
            flags.append("NOT NULL")
        if re.search(r"auto_increment|serial|identity", part, re.I):
            flags.append("AUTO")
        reference = re.search(r"references\s+[`\"]?(\w+)", rest, re.I)
        if reference:
            flags.append(f"FK→{reference.group(1)}")
        columns.append(column(words[0].strip('`"[]'), words[1], " ".join(flags)))
    return columns
