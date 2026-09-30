"""Tables from framework migrations: Laravel (Schema::create) and CodeIgniter 4 (forge)."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from repolens.extractors._text import block_end
from repolens.extractors.database._common import column, table, tr
from repolens.repo import Repo, line_of

LARAVEL_CREATE = re.compile(r"Schema::(create|table)\(\s*['\"](\w+)['\"]")
LARAVEL_COLUMN = re.compile(
    r"\$table->(\w+)\(\s*(?:['\"](\w+)['\"])?([^;]*?)\)((?:->\w+\([^)]*\))*)\s*;"
)
# Helpers that add fixed columns: $table->id(), $table->timestamps(), ...
LARAVEL_SHORTHAND = {
    "id": [("id", "bigIncrements", "PK AUTO")],
    "timestamps": [
        ("created_at", "timestamp", "nullable"),
        ("updated_at", "timestamp", "nullable"),
    ],
    "timestampsTz": [
        ("created_at", "timestampTz", "nullable"),
        ("updated_at", "timestampTz", "nullable"),
    ],
    "softDeletes": [("deleted_at", "timestamp", "nullable")],
    "rememberToken": [("remember_token", "string(100)", "nullable")],
}
# $table-> calls that do not add a column.
LARAVEL_NOT_COLUMNS = {
    "index",
    "unique",
    "primary",
    "foreign",
    "dropColumn",
    "dropForeign",
    "dropIndex",
    "renameColumn",
    "engine",
    "charset",
    "collation",
    "comment",
}
LARAVEL_KEPT_MODIFIERS = ("nullable", "unique", "index", "unsigned", "primary")

CI4_CREATE = re.compile(r"forge->createTable\(\s*['\"](\w+)['\"]")


def laravel_migrations(repo: Repo) -> list[dict]:
    """One table per Schema::create; later Schema::table calls add columns and a note."""
    tables: dict[str, dict] = {}
    for path in sorted(repo.glob("database/migrations/*.php", "*/database/migrations/*.php")):
        text = repo.read(path)
        for match in LARAVEL_CREATE.finditer(text):
            brace = text.find("{", match.end())
            body = text[brace : block_end(text, brace)]
            name = match.group(2)
            current = tables.get(name)
            if not current:
                current = table(name, "Laravel migration", path, line_of(text, match.start()), [])
                tables[name] = current
            elif match.group(1) == "table":
                file = PurePosixPath(path).name
                current["notes"].append(tr(f"changed by {file}", f"diubah oleh {file}"))
            current["columns"] += _laravel_columns(body)
    return list(tables.values())


def _laravel_columns(body: str) -> list[dict]:
    columns = []
    for match in LARAVEL_COLUMN.finditer(body):
        method, name, args, chain = (
            match.group(1),
            match.group(2),
            match.group(3),
            match.group(4) or "",
        )
        if method in LARAVEL_NOT_COLUMNS:
            continue
        if method in LARAVEL_SHORTHAND and not name:
            columns += [column(n, type_, attrs) for n, type_, attrs in LARAVEL_SHORTHAND[method]]
            continue
        if not name:
            continue
        size = re.findall(r"\d+", args or "")  # string('code', 40) -> string(40)
        type_ = method + (f"({','.join(size)})" if size else "")
        columns.append(column(name, type_, " ".join(_laravel_flags(name, chain))))
    return columns


def _laravel_flags(name: str, chain: str) -> list[str]:
    """Flags from the modifier chain: ->nullable()->constrained('users')->default(0)."""
    flags = []
    for modifier in re.findall(r"->(\w+)\(", chain):
        if modifier in LARAVEL_KEPT_MODIFIERS:
            flags.append(modifier)
        elif modifier == "constrained":
            target = re.search(r"constrained\(\s*['\"](\w+)['\"]", chain)
            # Without an argument Laravel guesses the table: user_id -> users.
            flags.append(f"FK→{target.group(1) if target else name.removesuffix('_id') + 's'}")
        elif modifier == "default":
            default = re.search(r"default\(([^)]*)\)", chain)
            flags.append(f"default {default.group(1).strip()}" if default else "default")
    return flags


def ci4_migrations(repo: Repo) -> list[dict]:
    """$this->forge->addField([...]) + addKey('id', true) + createTable('name')."""
    tables = []
    for path in repo.glob("*app/Database/Migrations/*.php"):
        text = repo.read(path)
        fields = re.search(r"addField\(\s*\[(.*?)\]\s*\)\s*;", text, re.S)
        for match in CI4_CREATE.finditer(text):
            columns = _ci4_columns(fields.group(1)) if fields else []
            for key in re.findall(r"addKey\(\s*['\"](\w+)['\"]\s*,\s*true", text):
                for col in columns:
                    if col["name"] == key:
                        col["attrs"] = ("PK " + col["attrs"]).strip()
            line = line_of(text, match.start())
            tables.append(table(match.group(1), "CodeIgniter migration", path, line, columns))
    return tables


def _ci4_columns(fields: str) -> list[dict]:
    """'title' => ['type' => 'VARCHAR', 'constraint' => 200, 'null' => true] -> VARCHAR(200)."""
    columns = []
    for field in re.finditer(r"['\"](\w+)['\"]\s*=>\s*\[(.*?)\]", fields, re.S):
        spec = field.group(2)
        type_ = re.search(r"['\"]type['\"]\s*=>\s*['\"](\w+)['\"]", spec)
        size = re.search(r"['\"]constraint['\"]\s*=>\s*['\"]?([\w,]+)", spec)
        flags = []
        if re.search(r"auto_increment['\"]\s*=>\s*true", spec, re.I):
            flags.append("AUTO")
        if re.search(r"null['\"]\s*=>\s*true", spec, re.I):
            flags.append("nullable")
        full_type = (type_.group(1) if type_ else "?") + (f"({size.group(1)})" if size else "")
        columns.append(column(field.group(1), full_type, " ".join(flags)))
    return columns
