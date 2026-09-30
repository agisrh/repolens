"""Tables from ORM models: JPA (Java/Kotlin), Prisma, TypeORM, Drizzle, Django, and Hive (Dart).

Each reader turns one kind of model definition into tables with columns and short flags
(PK, AUTO, NOT NULL, relation type, ...).
"""

from __future__ import annotations

import re

from repolens.extractors._text import JAVA_CLASS_DECL, closing_offset
from repolens.extractors.database._common import column, table, tr
from repolens.repo import Repo, line_of

JPA_FIELD = re.compile(
    r"((?:\s*@\w+(?:\([^)]*\))?\s*)*)"  # annotations
    r"\s*(?:private|protected|public)\s+([\w<>, ?]+?)\s+(\w+)\s*(?:=[^;]*)?;"  # type and name
)
# JPA annotations shown on a column, and how they are shown.
JPA_FLAGS = {
    "Id": "PK",
    "GeneratedValue": "AUTO",
    "ManyToOne": "ManyToOne",
    "OneToMany": "OneToMany",
    "OneToOne": "OneToOne",
    "ManyToMany": "ManyToMany",
    "NotNull": "NotNull",
    "NotEmpty": "NotEmpty",
}
TYPEORM_ENTITY = re.compile(
    r"@Entity\(\s*(?:['\"](\w+)['\"])?[^)]*\)\s*(?:export\s+)?class\s+(\w+)"
)
TYPEORM_COLUMN = re.compile(
    r"@(PrimaryGeneratedColumn|PrimaryColumn|Column|ManyToOne|OneToMany|OneToOne|ManyToMany"
    r"|CreateDateColumn|UpdateDateColumn)\([^)]*\)\s*(\w+)\s*[!?]?\s*:\s*([\w\[\]<>| ]+)"
)
DRIZZLE_TABLE = re.compile(
    r"(?:export\s+)?const\s+(\w+)\s*=\s*(pg|mysql|sqlite)Table\(\s*['\"](\w+)['\"]\s*,\s*\{"
)
DRIZZLE_COLUMN = re.compile(r"^\s*(\w+)\s*:\s*(\w+)\(\s*['\"]?(\w*)['\"]?[^)]*\)([^,\n]*)", re.M)
HIVE_FIELD = re.compile(
    r"@HiveField\((\d+)[^)]*\)\s*(?:final\s+|late\s+)?([\w<>?, ]+?)\s+(\w+)\s*[;=]"
)


def jpa_entities(repo: Repo) -> list[dict]:
    """@Entity classes; the table name comes from @Table(name = "...") or the class name."""
    tables = []
    for path in repo.by_ext(".java", ".kt"):
        text = repo.read(path)
        if not re.search(r"@(Entity|MappedSuperclass)\b", text):
            continue
        declaration = JAVA_CLASS_DECL.search(text)
        if not declaration:
            continue
        table_annotation = re.search(r"@Table\(\s*(?:name\s*=\s*)?\"(\w+)\"", text)
        name = table_annotation.group(1) if table_annotation else declaration.group(2)
        columns = _jpa_columns(text, declaration.end())
        notes = []
        parent = declaration.group(3)
        if parent:
            notes.append(tr(f"inherits columns from {parent}", f"mewarisi kolom dari {parent}"))
        if "@MappedSuperclass" in text:
            notes.append(
                tr(
                    "MappedSuperclass (not a table of its own)",
                    "MappedSuperclass (bukan tabel sendiri)",
                )
            )
        line = line_of(text, declaration.start())
        tables.append(table(name, "JPA entity", path, line, columns, notes))
    return tables


def _jpa_columns(text: str, class_end: int) -> list[dict]:
    """Fields of an entity class; @Column(name=...) renames, @Transient and static are skipped."""
    columns = []
    for field in JPA_FIELD.finditer(text, class_end):
        annotations, type_, name = field.group(1) or "", field.group(2).strip(), field.group(3)
        if "@Transient" in annotations or "static" in type_:
            continue
        column_name = re.search(
            r"@(?:Column|JoinColumn)\(\s*(?:[^)]*?name\s*=\s*)?\"(\w+)\"", annotations
        )
        flags = [shown for key, shown in JPA_FLAGS.items() if f"@{key}" in annotations]
        columns.append(
            column(column_name.group(1) if column_name else name, type_, " ".join(flags))
        )
    return columns


def prisma(repo: Repo) -> list[dict]:
    """model User { id Int @id ... } in schema.prisma; @@map("users") renames the table."""
    tables = []
    for path in repo.by_ext(".prisma"):
        text = repo.read(path)
        for model in re.finditer(r"^model\s+(\w+)\s*\{(.*?)^\}", text, re.S | re.M):
            columns = []
            for line in model.group(2).splitlines():
                words = line.strip().split(None, 2)  # name, type, attributes
                if len(words) >= 2 and not words[0].startswith(("@@", "//")):
                    columns.append(column(words[0], words[1], words[2] if len(words) > 2 else ""))
            mapped = re.search(r"@@map\(\"(\w+)\"\)", model.group(2))
            name = mapped.group(1) if mapped else model.group(1)
            tables.append(table(name, "Prisma model", path, line_of(text, model.start()), columns))
    return tables


def typeorm(repo: Repo) -> list[dict]:
    """@Entity("orders") class Order { @Column() code: string; ... }"""
    tables = []
    for path in repo.by_ext(".ts"):
        text = repo.read(path)
        entity = TYPEORM_ENTITY.search(text)
        if not entity:
            continue
        columns = []
        for match in TYPEORM_COLUMN.finditer(text):
            kind = match.group(1)
            flag = {"PrimaryGeneratedColumn": "PK AUTO", "PrimaryColumn": "PK", "Column": ""}.get(
                kind, kind
            )
            columns.append(column(match.group(2), match.group(3).strip(), flag))
        name = entity.group(1) or entity.group(2)
        tables.append(table(name, "TypeORM entity", path, line_of(text, entity.start()), columns))
    return tables


def drizzle(repo: Repo) -> list[dict]:
    """export const users = pgTable("users", { id: serial("id").primaryKey(), ... })"""
    tables = []
    for path in repo.by_ext(".ts", ".js"):
        text = repo.read(path)
        for match in DRIZZLE_TABLE.finditer(text):
            end = closing_offset(text, match.end(), "{", "}")
            columns = []
            for col in DRIZZLE_COLUMN.finditer(text[match.end() : end - 1]):
                modifiers = col.group(4)
                flags = [
                    flag
                    for flag, key in (
                        ("PK", "primaryKey"),
                        ("NOT NULL", "notNull"),
                        ("unique", "unique"),
                    )
                    if key in modifiers
                ]
                columns.append(column(col.group(3) or col.group(1), col.group(2), " ".join(flags)))
            source = f"Drizzle ({match.group(2)})"
            tables.append(
                table(match.group(3), source, path, line_of(text, match.start()), columns)
            )
    return tables


def django_models(repo: Repo) -> list[dict]:
    """class Product(models.Model): name = models.CharField(...)"""
    tables = []
    for path in repo.by_name("models.py"):
        text = repo.read(path)
        for model in re.finditer(
            r"^class\s+(\w+)\(([\w.]*Model)\):(.*?)(?=^class\s|\Z)", text, re.S | re.M
        ):
            fields = re.finditer(r"^\s+(\w+)\s*=\s*models\.(\w+)", model.group(3), re.M)
            columns = [column(f.group(1), f.group(2)) for f in fields]
            tables.append(
                table(model.group(1), "Django model", path, line_of(text, model.start()), columns)
            )
    return tables


def hive_models(repo: Repo) -> list[dict]:
    """@HiveType(typeId: 1) class Truck { @HiveField(0) String plate; } — on-device storage."""
    tables = []
    for path in repo.by_ext(".dart"):
        text = repo.read(path)
        for match in re.finditer(r"@HiveType\(\s*typeId:\s*(\d+)[^)]*\)\s*class\s+(\w+)", text):
            fields = HIVE_FIELD.finditer(text[match.end() :])
            columns = [
                column(f.group(3), f.group(2).strip(), f"field {f.group(1)}") for f in fields
            ]
            source = f"Hive box type (typeId {match.group(1)})"
            tables.append(
                table(match.group(2), source, path, line_of(text, match.start()), columns)
            )
    return tables
