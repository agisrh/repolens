"""Tables inferred from PHP models and controllers (CodeIgniter 3/4, Laravel Eloquent).

Many PHP projects have no migrations or schema file, so the schema is pieced together
from code instead:
  - table names from `protected $table = 'news'`, `$this->db->table('news')`, joins, and
    the Eloquent convention (class Post -> table posts)
  - column names from $allowedFields / $fillable and from where(), select(), orderBy(), ...
The result is a partial schema (only columns that appear in code), marked as inferred.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from repolens.extractors.database._common import column, table, tr
from repolens.repo import Repo, line_of

TABLE_PROPERTY = re.compile(
    r"(?:protected|public|private|var)\s+\$(\w*table\w*)\s*=\s*['\"]([\w.]+)['\"]", re.I
)
# $this->db->table($this->table . ' n') and ->from($this->table)
TABLE_FROM_PROPERTY = re.compile(
    r"(?:db->table|->from)\(\s*\$this->(\w+)\s*(?:\.\s*['\"]\s+(\w+)['\"])?"
)
QUERY_BUILDER = r"(?:db->table|DB::table|db->get|db->from|->from|db->get_where|db->insert|db->update|db->delete)"
# db->table('news n') / DB::table('news as n')
TABLE_FROM_STRING = re.compile(QUERY_BUILDER + r"\(\s*['\"]([\w.]+)(?:\s+(?:as\s+)?(\w+))?['\"]")
JOIN = re.compile(r"->join\(\s*['\"](\w+)(?:\s+(?:as\s+)?(\w+))?['\"]\s*,\s*['\"]([^'\"]+)['\"]")
JOIN_CONDITION = re.compile(r"->join\(\s*['\"][^'\"]+['\"]\s*,\s*['\"]([^'\"]+)['\"]")
COLUMN_CALL = re.compile(
    r"->(?:where|orWhere|whereIn|like|orLike|orderBy|order_by|groupBy|group_by|having"
    r"|select_sum|selectMax|selectSum|selectCount)\(\s*['\"]([\w.]+)"
)
SELECT = re.compile(r"->select\(\s*['\"]([^'\"]+)['\"]")
METHOD_SPLIT = re.compile(r"\n\s*(?:public|protected|private)?\s*function\s+")


def php_models(repo: Repo) -> list[dict]:
    found: dict[str, dict] = {}  # table name -> what is known about it
    for path in _candidate_files(repo):
        _read_file(path, repo.read(path), found)
    return _as_tables(found)


def _candidate_files(repo: Repo) -> list[str]:
    """Models and controllers, without tests."""
    files = [
        f
        for f in repo.by_ext(".php")
        if re.search(r"(^|/)(app|application)/(Models|models|Controllers|controllers)/", f)
        or "/Models/" in f
    ]
    return [f for f in files if not re.search(r"(^|/)(tests?|spec)/", f)]


def _entry(found: dict, name: str, file: str, line: int) -> dict:
    return found.setdefault(
        name, {"file": file, "line": line, "columns": {}, "pk": None, "models": set()}
    )


def _read_file(path: str, text: str, found: dict) -> None:
    properties = {m.group(1): m.group(2) for m in TABLE_PROPERTY.finditer(text)}
    # Split into methods, so query columns are attributed to the table that method queries.
    for method in METHOD_SPLIT.split(text):
        _read_method(method, path, properties, found)
    _add_declared_tables(path, text, properties, found)
    _add_eloquent_table(path, text, properties, found)


def _read_method(chunk: str, path: str, properties: dict, found: dict) -> None:
    """Tables a method queries (with their aliases), and the columns it uses."""
    aliases: dict[str, str] = {}  # alias or name -> table
    main: list[str] = []  # tables queried directly
    for match in TABLE_FROM_PROPERTY.finditer(chunk):
        if match.group(1) in properties:
            name = properties[match.group(1)]
            main.append(name)
            aliases[name] = name
            if match.group(2):
                aliases[match.group(2)] = name
    for match in TABLE_FROM_STRING.finditer(chunk):
        name = match.group(1).split(".")[-1]
        main.append(name)
        aliases[name] = name
        if match.group(2):
            aliases[match.group(2)] = name
    joined = []
    for match in JOIN.finditer(chunk):
        name = match.group(1)
        joined.append(name)
        aliases[name] = name
        if match.group(2):
            aliases[match.group(2)] = name
    if not main and len(properties) == 1 and "$this->" in chunk:
        main = list(properties.values())  # a model with one table queries that table
        aliases.update({name: name for name in main})

    for name in dict.fromkeys(main + joined):
        _entry(found, name, path, 1)["models"].add(PurePosixPath(path).stem)
    for ref in _column_references(chunk):
        if ref.endswith("*"):
            continue
        if "." in ref:  # alias.column
            prefix, name = ref.split(".", 1)
            target = aliases.get(prefix)
        else:  # a bare column only belongs to a table when just one is queried
            name = ref
            target = main[0] if len(set(main)) == 1 and not joined else None
        if target and re.fullmatch(r"[A-Za-z_]\w*", name):
            found[target]["columns"].setdefault(name, tr("used in queries", "dipakai di query"))


def _column_references(chunk: str) -> list[str]:
    """Column names ("col" or "alias.col") used in where/select/order/join calls."""
    refs = COLUMN_CALL.findall(chunk)
    if re.search(r"->(?:where|orWhere|like)\(\s*\[", chunk):  # where(['col' => value])
        refs += re.findall(r"['\"]([\w]+\.[\w]+|\w+)['\"]\s*=>", chunk)
    for selected in SELECT.findall(chunk):
        refs += [c.strip().split(" ")[0] for c in selected.split(",") if c.strip() and "(" not in c]
    for condition in JOIN_CONDITION.findall(chunk):
        refs += re.findall(r"(\w+\.\w+)", condition)
    return refs


def _add_declared_tables(path: str, text: str, properties: dict, found: dict) -> None:
    """Tables named in $table properties, with $primaryKey and $allowedFields / $fillable."""
    primary_key = re.search(r"\$primaryKey\s*=\s*['\"](\w+)['\"]", text)
    allowed = re.search(r"\$allowedFields\s*=\s*\[(.*?)\]", text, re.S)
    fillable = re.search(r"\$fillable\s*=\s*\[(.*?)\]", text, re.S)
    for variable, name in properties.items():
        line = line_of(text, text.find(name))
        entry = _entry(found, name, path, line)
        entry["file"], entry["line"] = path, line
        entry["models"].add(PurePosixPath(path).stem)
        if variable.lower() != "table":
            continue
        if primary_key:
            entry["pk"] = primary_key.group(1)
        for block, label in ((allowed, "allowedFields"), (fillable, "fillable")):
            if block:
                for field in re.findall(r"['\"](\w+)['\"]", block.group(1)):
                    entry["columns"][field] = label


def _add_eloquent_table(path: str, text: str, properties: dict, found: dict) -> None:
    """Laravel convention for models without $table: class OrderItem -> table order_items."""
    eloquent = re.search(r"class\s+(\w+)\s+extends\s+(?:Model|Authenticatable)\b", text)
    if not eloquent or properties or "/Models/" not in path or "extends Model" not in text:
        return
    name = re.sub(r"(?<!^)(?=[A-Z])", "_", eloquent.group(1)).lower() + "s"
    entry = _entry(found, name, path, line_of(text, eloquent.start()))
    entry["models"].add(eloquent.group(1))
    fillable = re.search(r"\$fillable\s*=\s*\[(.*?)\]", text, re.S)
    if fillable:
        for field in re.findall(r"['\"](\w+)['\"]", fillable.group(1)):
            entry["columns"][field] = "fillable"


def _as_tables(found: dict) -> list[dict]:
    tables = []
    for name, entry in sorted(found.items()):
        columns = [column(entry["pk"], "?", "PK")] if entry["pk"] else []
        columns += [column(c, "?", how) for c, how in entry["columns"].items() if c != entry["pk"]]
        models = ", ".join(sorted(entry["models"]))
        notes = [
            tr(f"used by {models}", f"dipakai oleh {models}"),
            tr(
                "partial schema: only columns that appear in code",
                "skema parsial: hanya kolom yang muncul di kode",
            ),
        ]
        source = tr("PHP model (inferred from queries)", "Model PHP (disimpulkan dari query)")
        tables.append(
            table(name, source, entry["file"], entry["line"], columns, notes, inferred=True)
        )
    return tables
