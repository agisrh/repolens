"""Tables from Ruby on Rails: db/schema.rb, or the migrations in db/migrate when there is none.

schema.rb is generated from the real database, so it is preferred. Both use the same
syntax: `create_table "articles" do |t| t.string "title", null: false ... end`, plus
`add_index` / `t.index` (unique) and `add_foreign_key`. Every table gets an `id` primary
key unless it says `id: false`.
"""

from __future__ import annotations

import re

from repolens.extractors.database._common import column, table
from repolens.repo import Repo, line_of

CREATE = re.compile(r"create_table\s*\(?\s*[:\"'](\w+)[\"']?(.*?)\bdo\s*\|\s*(\w+)\s*\|", re.S)
# t.string "title", limit: 128, null: false   /   t.references :user, foreign_key: true
COLUMN = re.compile(r"^\s*(\w+)\.(\w+)\s+[:\"'](\w+)[\"']?(.*)$", re.M)
INDEX = re.compile(
    r"add_index\s*\(?\s*[:\"'](\w+)[\"']?,\s*(\[[^\]]*\]|[:\"']\w+[\"']?)(.*)$", re.M
)
BLOCK_INDEX = re.compile(r"^\s*\w+\.index\s+(\[[^\]]*\]|[:\"']\w+[\"']?)(.*)$", re.M)
FOREIGN_KEY = re.compile(
    r"add_foreign_key\s*\(?\s*[:\"'](\w+)[\"']?,\s*[:\"'](\w+)[\"']?(?:.*?column:\s*[:\"'](\w+))?",
)
# Column helpers that are not one column of that name.
NOT_COLUMNS = {"index", "timestamps", "check_constraint"}


def rails_schema(repo: Repo) -> list[dict]:
    files = repo.glob("db/schema.rb", "*/db/schema.rb")
    source = "Rails schema.rb"
    if not files:
        files = sorted(repo.glob("db/migrate/*.rb", "*/db/migrate/*.rb"))
        source = "Rails migration"
    tables: dict[str, dict] = {}
    for path in files:
        text = repo.read(path)
        for match in CREATE.finditer(text):
            body_end = _block_end(text, match.end())
            columns = _columns(match.group(2), match.group(3), text[match.end() : body_end])
            name = match.group(1)
            if name in tables:  # a later migration redefines the table
                tables[name]["columns"] = columns
            else:
                tables[name] = table(name, source, path, line_of(text, match.start()), columns)
        _apply_indexes(text, tables)
        _apply_foreign_keys(text, tables)
    return list(tables.values())


def _block_end(text: str, start: int) -> int:
    """Offset of the `end` that closes the block opened just before `start`."""
    depth = 1
    for match in re.finditer(r"\bdo\b|^\s*end\b", text[start:], re.M):
        depth += 1 if match.group(0) == "do" else -1
        if depth == 0:
            return start + match.start()
    return len(text)


def _columns(options: str, var: str, body: str) -> list[dict]:
    columns = []
    if not re.search(r"\bid:\s*false", options):
        id_type = re.search(r"\bid:\s*:(\w+)", options)
        columns.append(column("id", id_type.group(1) if id_type else "bigint", "PK AUTO"))
    for match in COLUMN.finditer(body):
        if match.group(1) != var:
            continue
        kind, name, rest = match.group(2), match.group(3), match.group(4)
        if kind in NOT_COLUMNS:
            if kind == "timestamps":  # t.timestamps -> created_at, updated_at
                flags = "NOT NULL" if re.search(r"null:\s*false", rest) else ""
                columns += [column(c, "datetime", flags) for c in ("created_at", "updated_at")]
            continue
        if kind in ("references", "belongs_to"):
            target = _plural(name)
            flags = "FK→" + target if re.search(r"foreign_key:\s*true", rest) else ""
            columns.append(column(f"{name}_id", "bigint", flags))
            continue
        columns.append(column(name, _type(kind, rest), " ".join(_flags(rest))))
    # t.timestamps without arguments is not matched by COLUMN (no column name follows it).
    if re.search(rf"^\s*{re.escape(var)}\.timestamps\s*$", body, re.M):
        columns += [column(c, "datetime", "NOT NULL") for c in ("created_at", "updated_at")]
    return columns


def _type(kind: str, rest: str) -> str:
    size = re.search(r"limit:\s*(\d+)", rest)
    return kind + (f"({size.group(1)})" if size else "")


def _flags(rest: str) -> list[str]:
    flags = []
    if re.search(r"null:\s*false", rest):
        flags.append("NOT NULL")
    default = re.search(r"default:\s*([^,]+?)(?:,|$)", rest)
    if default:
        flags.append(f"default {default.group(1).strip()}")
    return flags


def _apply_indexes(text: str, tables: dict) -> None:
    """Mark single-column unique indexes as `unique` on that column."""
    for match in INDEX.finditer(text):
        _mark_unique(tables.get(match.group(1)), match.group(2), match.group(3))
    for match in CREATE.finditer(text):
        body = text[match.end() : _block_end(text, match.end())]
        for index in BLOCK_INDEX.finditer(body):
            _mark_unique(tables.get(match.group(1)), index.group(1), index.group(2))


def _mark_unique(found: dict | None, columns: str, options: str) -> None:
    names = re.findall(r"\w+", columns)
    if not found or len(names) != 1 or not re.search(r"unique:\s*true", options):
        return
    for col in found["columns"]:
        if col["name"] == names[0] and "unique" not in col["attrs"]:
            col["attrs"] = (col["attrs"] + " unique").strip()


def _apply_foreign_keys(text: str, tables: dict) -> None:
    """add_foreign_key "comments", "articles" -> comments.article_id is FK→articles."""
    for match in FOREIGN_KEY.finditer(text):
        found = tables.get(match.group(1))
        target = match.group(2)
        name = match.group(3) or f"{_singular(target)}_id"
        for col in found["columns"] if found else []:
            if col["name"] == name and "FK→" not in col["attrs"]:
                col["attrs"] = (col["attrs"] + f" FK→{target}").strip()


def _plural(word: str) -> str:
    if re.search(r"[^aeiou]y$", word):
        return word[:-1] + "ies"
    if re.search(r"(s|x|z|ch|sh)$", word):
        return word + "es"
    return word + "s"


def _singular(word: str) -> str:
    if word.endswith("ies"):
        return word[:-3] + "y"
    if re.search(r"(s|x|z|ch|sh)es$", word):
        return word[:-2]
    return word[:-1] if word.endswith("s") else word
