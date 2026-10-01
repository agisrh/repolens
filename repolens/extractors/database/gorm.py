"""Tables from GORM models (Go).

A struct is a model when it embeds gorm.Model or has a field with a `gorm:"..."` tag. The
table name follows GORM's default naming (UserModel -> user_models) unless the model has a
TableName() method. Fields whose type is another model are relations, not columns; their
foreign key field (Author + AuthorID) is marked FK to that model's table.
"""

from __future__ import annotations

import re

from repolens.extractors.database._common import column, table
from repolens.repo import Repo, line_of

STRUCT = re.compile(r"^type\s+(\w+)\s+struct\s*\{(.*?)^\}", re.S | re.M)
# One field per line: name, type, optional `tag` ([ \t] so a match never runs into the next line).
FIELD = re.compile(r"^[ \t]*(\w+)[ \t]+([\w.*\[\]]+)[ \t]*(?:`([^`]*)`)?", re.M)
TABLE_NAME = re.compile(
    r"func\s*\(\s*\w*\s*\*?(\w+)\s*\)\s*TableName\(\)\s*string\s*\{\s*return\s*\"(\w+)\"", re.S
)
# Columns that gorm.Model adds to every model embedding it.
GORM_MODEL_COLUMNS = [
    ("id", "uint", "PK AUTO"),
    ("created_at", "time.Time", ""),
    ("updated_at", "time.Time", ""),
    ("deleted_at", "gorm.DeletedAt", "nullable"),
]


def gorm_models(repo: Repo) -> list[dict]:
    files = [
        path
        for path in repo.by_ext(".go")
        if not path.endswith("_test.go") and "gorm" in repo.read(path)
    ]
    structs = {}  # name -> (file, text, body, offset)
    names = {}  # struct name -> table name from TableName()
    for path in files:
        text = repo.read(path)
        names.update(dict(TABLE_NAME.findall(text)))
        for match in STRUCT.finditer(text):
            structs[match.group(1)] = (path, text, match.group(2), match.start())
    models = {name: body for name, (_, _, body, _) in structs.items() if _is_model(body)}
    tables = {name: names.get(name) or table_name(name) for name in models}
    result = []
    for name in models:
        path, text, body, offset = structs[name]
        columns, notes = _columns(body, tables)
        result.append(
            table(tables[name], "GORM model", path, line_of(text, offset), columns, notes)
        )
    return result


def _is_model(body: str) -> bool:
    return bool(re.search(r"^\s*gorm\.Model\s*$", body, re.M)) or 'gorm:"' in body


def _columns(body: str, tables: dict) -> tuple[list[dict], list[str]]:
    """(columns, notes) of one model; `tables` maps model names to table names."""
    columns, notes = [], []
    if re.search(r"^\s*gorm\.Model\s*$", body, re.M):
        columns += [column(*spec) for spec in GORM_MODEL_COLUMNS]
    fields = [(m.group(1), m.group(2), m.group(3) or "") for m in FIELD.finditer(body)]
    # Relation fields point at another model: `Author ArticleUserModel`, `Tags []TagModel`.
    relations = {
        name: tables[_base_type(type_)] for name, type_, _ in fields if _base_type(type_) in tables
    }
    for name, type_, tag in fields:
        settings = _gorm_settings(tag)
        join_table = settings.get("many2many")
        if join_table:
            notes.append(f"many2many: {join_table}")
        if name in relations or type_ == "gorm.Model" or settings.get("-") is not None:
            continue
        column_name = settings.get("column") or snake_case(name)
        flags = _flags(name, type_, settings)
        target = relations.get(name[:-2]) if name.endswith("ID") else None
        if target:
            flags.append(f"FK→{target}")
        size = settings.get("size")
        type_text = type_.lstrip("*") + (f"({size})" if size else "")
        columns.append(column(column_name, type_text, " ".join(flags)))
    return columns, notes


def _flags(name: str, type_: str, settings: dict) -> list[str]:
    flags = []
    if "primarykey" in settings or name == "ID":  # GORM treats ID as the primary key
        flags.append("PK")
    if "autoincrement" in settings:
        flags.append("AUTO")
    if "not null" in settings:
        flags.append("NOT NULL")
    if "uniqueindex" in settings or "unique" in settings:
        flags.append("unique")
    if type_.startswith("*"):
        flags.append("nullable")
    return flags


def _gorm_settings(tag: str) -> dict:
    """`gorm:"column:email;uniqueIndex;size:255"` -> {"column": "email", "uniqueindex": "",
    "size": "255"}; keys are lowercased like GORM does."""
    match = re.search(r'gorm:"([^"]*)"', tag)
    settings = {}
    for part in match.group(1).split(";") if match else []:
        key, _, value = part.partition(":")
        if key.strip():
            settings[key.strip().lower()] = value.strip()
    return settings


def _base_type(type_: str) -> str:
    """[]*articles.TagModel -> TagModel."""
    return type_.lstrip("[]*").split(".")[-1]


def snake_case(name: str) -> str:
    """GORM's column naming: UserID -> user_id, PasswordHash -> password_hash."""
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z\d])([A-Z])", r"\1_\2", name).lower()


def table_name(model: str) -> str:
    """GORM's default table name: snake_case, plural (UserModel -> user_models)."""
    name = snake_case(model)
    if re.search(r"[^aeiou]y$", name):
        return name[:-1] + "ies"
    if re.search(r"(s|x|z|ch|sh)$", name):
        return name + "es"
    return name + "s"
