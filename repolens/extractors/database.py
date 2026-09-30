"""Database engine and schema from SQL files, migrations, ORM entities, and local-storage models."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from repolens.i18n import t as tr  # `t` is used as a table variable throughout this module
from repolens.repo import Repo, line_of


def _also_defined(file: str) -> str:
    return tr(f"also defined in {file}", f"juga didefinisikan di {file}")


def _table(name, source, file, line, columns, notes=None, inferred=False):
    table = {
        "name": name,
        "source": source,
        "file": file,
        "line": line,
        "columns": columns,
        "notes": notes or [],
    }
    if inferred:
        table["inferred"] = True  # guessed from queries in code, not from a schema definition
    return table


def _col(name, type_, attrs=""):
    return {"name": name, "type": type_, "attrs": attrs.strip()}


def _split_top_level(body: str) -> list[str]:
    parts, depth, cur = [], 0, []
    for c in body:
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        if c == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    if cur:
        parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?(?:\w+[`\"\]]?\.[`\"\[]?)?(\w+)[`\"\]]?\s*\(",
    re.I,
)
SQL_CONSTRAINT = re.compile(
    r"^(PRIMARY|FOREIGN|CONSTRAINT|KEY|INDEX|UNIQUE|CHECK|FULLTEXT)\b", re.I
)


def sql_files(repo: Repo, extra: list[str] = ()) -> list[dict]:
    tables = []
    for path in dict.fromkeys(repo.by_ext(".sql") + list(extra)):
        text = repo.read(path)
        for m in CREATE_TABLE.finditer(text):
            depth, i = 1, m.end()
            while i < len(text) and depth:
                depth += (text[i] == "(") - (text[i] == ")")
                i += 1
            cols = []
            for part in _split_top_level(text[m.end() : i - 1]):
                if SQL_CONSTRAINT.match(part):
                    if part.upper().startswith("PRIMARY"):
                        for pk in re.findall(r"[`\"]?(\w+)[`\"]?", part.split("(", 1)[-1]):
                            for c in cols:
                                if c["name"] == pk and "PK" not in c["attrs"]:
                                    c["attrs"] = ("PK " + c["attrs"]).strip()
                    continue
                bits = part.split(None, 2)
                if len(bits) >= 2:
                    attrs = bits[2] if len(bits) > 2 else ""
                    flags = []
                    if re.search(r"primary\s+key", attrs, re.I):
                        flags.append("PK")
                    if re.search(r"not\s+null", attrs, re.I):
                        flags.append("NOT NULL")
                    if re.search(r"auto_increment|serial|identity", part, re.I):
                        flags.append("AUTO")
                    ref = re.search(r"references\s+[`\"]?(\w+)", attrs, re.I)
                    if ref:
                        flags.append(f"FK→{ref.group(1)}")
                    cols.append(_col(bits[0].strip('`"[]'), bits[1], " ".join(flags)))
            tables.append(_table(m.group(1), "SQL", path, line_of(text, m.start()), cols))
    return tables


LARAVEL_CREATE = re.compile(r"Schema::(create|table)\(\s*['\"](\w+)['\"]")
LARAVEL_COL = re.compile(
    r"\$table->(\w+)\(\s*(?:['\"](\w+)['\"])?([^;]*?)\)((?:->\w+\([^)]*\))*)\s*;"
)
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
LARAVEL_SKIP = {
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


def laravel_migrations(repo: Repo) -> list[dict]:
    tables: dict[str, dict] = {}
    for path in sorted(repo.glob("database/migrations/*.php", "*/database/migrations/*.php")):
        text = repo.read(path)
        for m in LARAVEL_CREATE.finditer(text):
            brace = text.find("{", m.end())
            depth, i = 0, brace
            while i < len(text):
                depth += (text[i] == "{") - (text[i] == "}")
                if depth == 0:
                    break
                i += 1
            body = text[brace:i]
            name = m.group(2)
            table = tables.get(name)
            if not table:
                table = _table(name, "Laravel migration", path, line_of(text, m.start()), [])
                tables[name] = table
            elif m.group(1) == "table":
                table["notes"].append(f"diubah oleh {PurePosixPath(path).name}")
            for c in LARAVEL_COL.finditer(body):
                method, col, args, chain = c.group(1), c.group(2), c.group(3), c.group(4) or ""
                if method in LARAVEL_SKIP:
                    continue
                if method in LARAVEL_SHORTHAND and not col:
                    for n, t, a in LARAVEL_SHORTHAND[method]:
                        table["columns"].append(_col(n, t, a))
                    continue
                if not col:
                    continue
                flags = []
                for mod in re.findall(r"->(\w+)\(", chain):
                    if mod in ("nullable", "unique", "index", "unsigned", "primary"):
                        flags.append(mod)
                    elif mod == "constrained":
                        target = re.search(r"constrained\(\s*['\"](\w+)['\"]", chain)
                        flags.append(
                            f"FK→{target.group(1) if target else col.removesuffix('_id') + 's'}"
                        )
                    elif mod == "default":
                        d = re.search(r"default\(([^)]*)\)", chain)
                        flags.append(f"default {d.group(1).strip()}" if d else "default")
                size = re.findall(r"\d+", args or "")
                type_ = method + (f"({','.join(size)})" if size else "")
                table["columns"].append(_col(col, type_, " ".join(flags)))
    return list(tables.values())


CI4_CREATE = re.compile(r"forge->createTable\(\s*['\"](\w+)['\"]")


def ci4_migrations(repo: Repo) -> list[dict]:
    tables = []
    for path in repo.glob("*app/Database/Migrations/*.php"):
        text = repo.read(path)
        fields_block = re.search(r"addField\(\s*\[(.*?)\]\s*\)\s*;", text, re.S)
        for m in CI4_CREATE.finditer(text):
            cols = []
            if fields_block:
                for f in re.finditer(
                    r"['\"](\w+)['\"]\s*=>\s*\[(.*?)\]", fields_block.group(1), re.S
                ):
                    spec = f.group(2)
                    t = re.search(r"['\"]type['\"]\s*=>\s*['\"](\w+)['\"]", spec)
                    size = re.search(r"['\"]constraint['\"]\s*=>\s*['\"]?([\w,]+)", spec)
                    flags = []
                    if re.search(r"auto_increment['\"]\s*=>\s*true", spec, re.I):
                        flags.append("AUTO")
                    if re.search(r"null['\"]\s*=>\s*true", spec, re.I):
                        flags.append("nullable")
                    cols.append(
                        _col(
                            f.group(1),
                            (t.group(1) if t else "?") + (f"({size.group(1)})" if size else ""),
                            " ".join(flags),
                        )
                    )
            for key in re.findall(r"addKey\(\s*['\"](\w+)['\"]\s*,\s*true", text):
                for c in cols:
                    if c["name"] == key:
                        c["attrs"] = ("PK " + c["attrs"]).strip()
            tables.append(
                _table(m.group(1), "CodeIgniter migration", path, line_of(text, m.start()), cols)
            )
    return tables


CLASS_DECL = re.compile(
    r"^[ \t]*(?:@\w+(?:\([^)]*\))?\s+)*(?:(?:public|protected|private|abstract|final|open|data|sealed|internal)\s+)*(class|interface)\s+(\w+)(?:<[^>]*>)?(?:\s+extends\s+(\w+))?",
    re.M,
)
JPA_FIELD = re.compile(
    r"((?:\s*@\w+(?:\([^)]*\))?\s*)*)\s*(?:private|protected|public)\s+([\w<>, ?]+?)\s+(\w+)\s*(?:=[^;]*)?;"
)


def jpa_entities(repo: Repo) -> list[dict]:
    tables = []
    for path in repo.by_ext(".java", ".kt"):
        text = repo.read(path)
        if not re.search(r"@(Entity|MappedSuperclass)\b", text):
            continue
        cls = CLASS_DECL.search(text)
        if not cls:
            continue
        table_ann = re.search(r"@Table\(\s*(?:name\s*=\s*)?\"(\w+)\"", text)
        name = table_ann.group(1) if table_ann else cls.group(2)
        cols = []
        for f in JPA_FIELD.finditer(text, cls.end()):
            anns, type_, field = f.group(1) or "", f.group(2).strip(), f.group(3)
            if "@Transient" in anns or "static" in type_:
                continue
            col_name = re.search(
                r"@(?:Column|JoinColumn)\(\s*(?:[^)]*?name\s*=\s*)?\"(\w+)\"", anns
            )
            flags = [
                a
                for a in (
                    "Id",
                    "GeneratedValue",
                    "ManyToOne",
                    "OneToMany",
                    "OneToOne",
                    "ManyToMany",
                    "NotNull",
                    "NotEmpty",
                )
                if f"@{a}" in anns
            ]
            flags = ["PK" if a == "Id" else ("AUTO" if a == "GeneratedValue" else a) for a in flags]
            cols.append(_col(col_name.group(1) if col_name else field, type_, " ".join(flags)))
        notes = []
        if cls.group(3):
            notes.append(
                tr(f"inherits columns from {cls.group(3)}", f"mewarisi kolom dari {cls.group(3)}")
            )
        if "@MappedSuperclass" in text:
            notes.append(
                tr(
                    "MappedSuperclass (not a table of its own)",
                    "MappedSuperclass (bukan tabel sendiri)",
                )
            )
        tables.append(_table(name, "JPA entity", path, line_of(text, cls.start()), cols, notes))
    return tables


def prisma(repo: Repo) -> list[dict]:
    tables = []
    for path in repo.by_ext(".prisma"):
        text = repo.read(path)
        for m in re.finditer(r"^model\s+(\w+)\s*\{(.*?)^\}", text, re.S | re.M):
            cols = []
            for line in m.group(2).splitlines():
                bits = line.strip().split(None, 2)
                if len(bits) >= 2 and not bits[0].startswith(("@@", "//")):
                    cols.append(_col(bits[0], bits[1], bits[2] if len(bits) > 2 else ""))
            mapped = re.search(r"@@map\(\"(\w+)\"\)", m.group(2))
            tables.append(
                _table(
                    mapped.group(1) if mapped else m.group(1),
                    "Prisma model",
                    path,
                    line_of(text, m.start()),
                    cols,
                )
            )
    return tables


def typeorm(repo: Repo) -> list[dict]:
    tables = []
    for path in repo.by_ext(".ts"):
        text = repo.read(path)
        ent = re.search(
            r"@Entity\(\s*(?:['\"](\w+)['\"])?[^)]*\)\s*(?:export\s+)?class\s+(\w+)", text
        )
        if not ent:
            continue
        cols = []
        for c in re.finditer(
            r"@(PrimaryGeneratedColumn|PrimaryColumn|Column|ManyToOne|OneToMany|OneToOne|ManyToMany|CreateDateColumn|UpdateDateColumn)\([^)]*\)\s*(\w+)\s*[!?]?\s*:\s*([\w\[\]<>| ]+)",
            text,
        ):
            flag = {"PrimaryGeneratedColumn": "PK AUTO", "PrimaryColumn": "PK"}.get(
                c.group(1), c.group(1) if c.group(1) != "Column" else ""
            )
            cols.append(_col(c.group(2), c.group(3).strip(), flag))
        tables.append(
            _table(
                ent.group(1) or ent.group(2),
                "TypeORM entity",
                path,
                line_of(text, ent.start()),
                cols,
            )
        )
    return tables


DRIZZLE_TABLE = re.compile(
    r"(?:export\s+)?const\s+(\w+)\s*=\s*(pg|mysql|sqlite)Table\(\s*['\"](\w+)['\"]\s*,\s*\{"
)


def drizzle(repo: Repo) -> list[dict]:
    tables = []
    for path in repo.by_ext(".ts", ".js"):
        text = repo.read(path)
        for m in DRIZZLE_TABLE.finditer(text):
            depth, i = 1, m.end()
            while i < len(text) and depth:
                depth += (text[i] == "{") - (text[i] == "}")
                i += 1
            cols = []
            for c in re.finditer(
                r"^\s*(\w+)\s*:\s*(\w+)\(\s*['\"]?(\w*)['\"]?[^)]*\)([^,\n]*)",
                text[m.end() : i - 1],
                re.M,
            ):
                flags = " ".join(
                    f
                    for f, k in (
                        ("PK", "primaryKey"),
                        ("NOT NULL", "notNull"),
                        ("unique", "unique"),
                    )
                    if k in c.group(4)
                )
                cols.append(_col(c.group(3) or c.group(1), c.group(2), flags))
            tables.append(
                _table(m.group(3), f"Drizzle ({m.group(2)})", path, line_of(text, m.start()), cols)
            )
    return tables


def _dedupe_tables(tables: list[dict]) -> list[dict]:
    """Same table defined in several files (e.g. one schema.sql per SQL dialect): keep the richest, note the rest."""
    by_key: dict[str, dict] = {}
    for t in tables:
        key = t["name"].lower()
        if key not in by_key:
            by_key[key] = t
            continue
        keep = by_key[key]
        if t["source"] == keep["source"]:
            if len(t["columns"]) > len(keep["columns"]):
                t["notes"] = keep["notes"] + [_also_defined(keep["file"])]
                by_key[key] = t
            else:
                keep["notes"].append(_also_defined(t["file"]))
        else:
            by_key[key + "::" + t["source"]] = t
    return list(by_key.values())


PHP_TABLE_PROP = re.compile(
    r"(?:protected|public|private|var)\s+\$(\w*table\w*)\s*=\s*['\"]([\w.]+)['\"]", re.I
)
PHP_TABLE_CALL = re.compile(
    r"(?:db->table|DB::table|db->get|db->from|->from|db->get_where|db->insert|db->update|db->delete)\(\s*['\"]([\w.]+)(?:\s+\w+)?['\"]"
)
PHP_TABLE_VAR = re.compile(r"(?:db->table|->from)\(\s*\$this->(\w+)")
PHP_COLUMN = re.compile(
    r"->(?:where|orWhere|whereIn|like|orLike|orderBy|order_by|groupBy|group_by|having|select_sum|selectMax|selectSum|selectCount)\(\s*['\"]([\w.]+)"
)
PHP_SELECT = re.compile(r"->select\(\s*['\"]([^'\"]+)['\"]")


def php_models(repo: Repo) -> list[dict]:
    """Tables referenced by PHP models/controllers (CodeIgniter 3/4, Laravel Eloquent / query builder).

    Only column names used in queries are known, so the result is a partial schema.
    """
    found: dict[str, dict] = {}
    candidates = [
        f
        for f in repo.by_ext(".php")
        if re.search(r"(^|/)(app|application)/(Models|models|Controllers|controllers)/", f)
        or "/Models/" in f
    ]
    candidates = [f for f in candidates if not re.search(r"(^|/)(tests?|spec)/", f)]
    for path in candidates:
        text = repo.read(path)
        props = {m.group(1): m.group(2) for m in PHP_TABLE_PROP.finditer(text)}
        pk = re.search(r"\$primaryKey\s*=\s*['\"](\w+)['\"]", text)
        allowed = re.search(r"\$allowedFields\s*=\s*\[(.*?)\]", text, re.S)
        fillable = re.search(r"\$fillable\s*=\s*\[(.*?)\]", text, re.S)
        eloquent = re.search(r"class\s+(\w+)\s+extends\s+(?:Model|Authenticatable)\b", text)

        # Split the file into methods so query columns are attributed to the right table,
        # resolving aliases (`table($this->table . ' berita')`, `join('kategori k', ...)`).
        chunks = re.split(r"\n\s*(?:public|protected|private)?\s*function\s+", text)
        for chunk in chunks:
            aliases: dict[str, str] = {}
            main: list[str] = []
            for m in re.finditer(
                r"(?:db->table|->from)\(\s*\$this->(\w+)\s*(?:\.\s*['\"]\s+(\w+)['\"])?", chunk
            ):
                if m.group(1) in props:
                    t = props[m.group(1)]
                    main.append(t)
                    aliases[t] = t
                    if m.group(2):
                        aliases[m.group(2)] = t
            for m in re.finditer(
                r"(?:db->table|DB::table|db->get|db->from|->from|db->get_where|db->insert|db->update|db->delete)\(\s*['\"]([\w.]+)(?:\s+(?:as\s+)?(\w+))?['\"]",
                chunk,
            ):
                t = m.group(1).split(".")[-1]
                main.append(t)
                aliases[t] = t
                if m.group(2):
                    aliases[m.group(2)] = t
            joined = []
            for m in re.finditer(
                r"->join\(\s*['\"](\w+)(?:\s+(?:as\s+)?(\w+))?['\"]\s*,\s*['\"]([^'\"]+)['\"]",
                chunk,
            ):
                t = m.group(1)
                joined.append(t)
                aliases[t] = t
                if m.group(2):
                    aliases[m.group(2)] = t
            if not main and len(props) == 1 and "$this->" in chunk:
                main = list(props.values())
                aliases.update({t: t for t in main})

            refs = PHP_COLUMN.findall(chunk)
            refs += (
                re.findall(r"['\"]([\w]+\.[\w]+|\w+)['\"]\s*=>", chunk)
                if re.search(r"->(?:where|orWhere|like)\(\s*\[", chunk)
                else []
            )
            for sel in PHP_SELECT.findall(chunk):
                refs += [
                    c.strip().split(" ")[0] for c in sel.split(",") if c.strip() and "(" not in c
                ]
            for cond in re.findall(
                r"->join\(\s*['\"][^'\"]+['\"]\s*,\s*['\"]([^'\"]+)['\"]", chunk
            ):
                refs += re.findall(r"(\w+\.\w+)", cond)

            for t in dict.fromkeys(main + joined):
                entry = found.setdefault(
                    t, {"file": path, "line": 1, "columns": {}, "pk": None, "models": set()}
                )
                entry["models"].add(PurePosixPath(path).stem)
            for ref in refs:
                if ref.endswith("*"):
                    continue
                if "." in ref:
                    prefix, col = ref.split(".", 1)
                    table = aliases.get(prefix)
                else:
                    col = ref
                    table = main[0] if len(set(main)) == 1 and not joined else None
                if table and re.fullmatch(r"[A-Za-z_]\w*", col):
                    found[table]["columns"].setdefault(
                        col, tr("used in queries", "dipakai di query")
                    )
        for var, table in props.items():
            entry = found.setdefault(
                table,
                {
                    "file": path,
                    "line": line_of(text, text.find(table)),
                    "columns": {},
                    "pk": None,
                    "models": set(),
                },
            )
            entry["file"], entry["line"] = path, line_of(text, text.find(table))
            entry["models"].add(PurePosixPath(path).stem)
            if pk and var.lower() == "table":
                entry["pk"] = pk.group(1)
            for block in (allowed, fillable):
                if block and var.lower() == "table":
                    for f in re.findall(r"['\"](\w+)['\"]", block.group(1)):
                        entry["columns"][f] = "allowedFields" if block is allowed else "fillable"
        if eloquent and not props and "/Models/" in path and "extends Model" in text:
            # Laravel convention: class Post -> table posts
            name = re.sub(r"(?<!^)(?=[A-Z])", "_", eloquent.group(1)).lower() + "s"
            entry = found.setdefault(
                name,
                {
                    "file": path,
                    "line": line_of(text, eloquent.start()),
                    "columns": {},
                    "pk": None,
                    "models": set(),
                },
            )
            entry["models"].add(eloquent.group(1))
            if fillable:
                for f in re.findall(r"['\"](\w+)['\"]", fillable.group(1)):
                    entry["columns"][f] = "fillable"

    tables = []
    for name, e in sorted(found.items()):
        cols = []
        if e["pk"]:
            cols.append(_col(e["pk"], "?", "PK"))
        cols += [_col(c, "?", how) for c, how in e["columns"].items() if c != e["pk"]]
        models = ", ".join(sorted(e["models"]))
        tables.append(
            _table(
                name,
                tr("PHP model (inferred from queries)", "Model PHP (disimpulkan dari query)"),
                e["file"],
                e["line"],
                cols,
                [
                    tr(f"used by {models}", f"dipakai oleh {models}"),
                    tr(
                        "partial schema: only columns that appear in code",
                        "skema parsial: hanya kolom yang muncul di kode",
                    ),
                ],
                inferred=True,
            )
        )
    return tables


def django_models(repo: Repo) -> list[dict]:
    tables = []
    for path in repo.by_name("models.py"):
        text = repo.read(path)
        for m in re.finditer(
            r"^class\s+(\w+)\(([\w.]*Model)\):(.*?)(?=^class\s|\Z)", text, re.S | re.M
        ):
            cols = [
                _col(c.group(1), c.group(2))
                for c in re.finditer(r"^\s+(\w+)\s*=\s*models\.(\w+)", m.group(3), re.M)
            ]
            tables.append(_table(m.group(1), "Django model", path, line_of(text, m.start()), cols))
    return tables


def hive_models(repo: Repo) -> list[dict]:
    tables = []
    for path in repo.by_ext(".dart"):
        text = repo.read(path)
        for m in re.finditer(r"@HiveType\(\s*typeId:\s*(\d+)[^)]*\)\s*class\s+(\w+)", text):
            cols = [
                _col(f.group(3), f.group(2).strip(), f"field {f.group(1)}")
                for f in re.finditer(
                    r"@HiveField\((\d+)[^)]*\)\s*(?:final\s+|late\s+)?([\w<>?, ]+?)\s+(\w+)\s*[;=]",
                    text[m.end() :],
                )
            ]
            tables.append(
                _table(
                    m.group(2),
                    f"Hive box type (typeId {m.group(1)})",
                    path,
                    line_of(text, m.start()),
                    cols,
                )
            )
    return tables


ENGINE_HINTS = [
    (r"jdbc:(\w+):", "properties"),
    (r"DB_CONNECTION\s*=\s*(\w+)", "env"),
    (r"DBDriver['\"]?\s*=>?\s*['\"]?(\w+)", "config"),
    (r"database\.default\.DBDriver\s*=\s*(\w+)", "env"),
    (r"DATABASE_URL\s*=\s*['\"]?(\w+)://", "env"),
    (r"datasource\s+\w+\s*\{[^}]*?provider\s*=\s*\"(\w+)\"", "prisma"),
    (r"ENGINE['\"]\s*:\s*['\"]django\.db\.backends\.(\w+)", "settings"),
]
DEP_ENGINES = {
    "mysql": "MySQL",
    "mysql2": "MySQL",
    "com.mysql:mysql-connector-j": "MySQL",
    "mysql:mysql-connector-java": "MySQL",
    "pg": "PostgreSQL",
    "org.postgresql:postgresql": "PostgreSQL",
    "psycopg2": "PostgreSQL",
    "psycopg2-binary": "PostgreSQL",
    "com.h2database:h2": "H2",
    "mongoose": "MongoDB",
    "mongodb": "MongoDB",
    "sqlite3": "SQLite",
    "better-sqlite3": "SQLite",
    "redis": "Redis",
    "ioredis": "Redis",
    "com.oracle.database.jdbc:ojdbc11": "Oracle",
    "com.microsoft.sqlserver:mssql-jdbc": "SQL Server",
    "hive": "Hive (local)",
    "hive_flutter": "Hive (local)",
    "sqflite": "SQLite (local)",
    "drift": "SQLite via Drift (local)",
    "shared_preferences": "SharedPreferences (local)",
    "postgres": "PostgreSQL",
    "@vercel/postgres": "PostgreSQL",
    "@neondatabase/serverless": "PostgreSQL",
    "@planetscale/database": "MySQL",
}


def engines(repo: Repo, manifests: list[dict], compose: list[dict]) -> list[dict]:
    found: dict[str, str] = {}
    config_files = repo.glob(
        "*application*.properties",
        "*application*.yml",
        "*application*.yaml",
        ".env.example",
        ".env.sample",
        "env",
        "*app/Config/Database.php",
        "*config/database.php",
        "*.prisma",
        "*settings.py",
    )
    for path in config_files:
        text = "\n".join(
            l
            for l in repo.read(path).splitlines()
            if not l.lstrip().startswith(("#", "//", "*", "/*"))
        )
        for pattern, _ in ENGINE_HINTS:
            m = re.search(pattern, text)
            if m:
                found.setdefault(m.group(1).lower(), path)
    for m in manifests:
        for d in m["dependencies"]:
            if d["name"] in DEP_ENGINES:
                found.setdefault(DEP_ENGINES[d["name"]], f"{m['manifest']} ({d['name']})")
    for svc in compose:
        image = (svc.get("image") or "").lower()
        for key, label in (
            ("postgres", "PostgreSQL"),
            ("mysql", "MySQL"),
            ("mariadb", "MariaDB"),
            ("mongo", "MongoDB"),
            ("redis", "Redis"),
            ("mssql", "SQL Server"),
        ):
            if key in image:
                found.setdefault(label, f"{svc['file']} (service {svc['service']})")
    pretty = {
        "mysql": "MySQL",
        "mysqli": "MySQL",
        "pgsql": "PostgreSQL",
        "postgres": "PostgreSQL",
        "postgresql": "PostgreSQL",
        "sqlite": "SQLite",
        "sqlite3": "SQLite",
        "h2": "H2",
        "sqlsrv": "SQL Server",
        "sqlserver": "SQL Server",
        "mongodb": "MongoDB",
        "oracle": "Oracle",
        "hsqldb": "HSQLDB",
        "mariadb": "MariaDB",
    }
    merged: dict[str, str] = {}
    for k, src in found.items():
        merged.setdefault(pretty.get(k, k), src)
    result = []
    for k, v in merged.items():
        engine = {"engine": k.replace("(local)", tr("(local)", "(lokal)")), "evidence": v}
        if "(local)" in k:
            engine["local"] = True  # on-device storage, not a server database
        result.append(engine)
    return result


def extract(
    repo: Repo, manifests: list[dict], compose: list[dict], extra_schema: list[str] = ()
) -> dict:
    """extra_schema: SQL dump files declared in .repolens.yml (any extension)."""
    schema_tables = (
        sql_files(repo, extra_schema)
        + laravel_migrations(repo)
        + ci4_migrations(repo)
        + jpa_entities(repo)
        + prisma(repo)
        + typeorm(repo)
        + drizzle(repo)
        + django_models(repo)
        + hive_models(repo)
    )
    # Query-inferred tables only fill gaps: skip names already defined by a real schema source.
    known = {t["name"].lower() for t in schema_tables}
    inferred = [t for t in php_models(repo) if t["name"].lower() not in known]
    return {
        "engines": engines(repo, manifests, compose),
        "tables": _dedupe_tables(schema_tables) + inferred,
    }
