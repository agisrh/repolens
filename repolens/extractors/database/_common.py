"""Shapes shared by the schema readers: a table and a column."""

from __future__ import annotations

from repolens.i18n import t as tr  # `t` is a common name for a table in this package


def table(name, source, file, line, columns, notes=None, inferred=False) -> dict:
    """One table (or model) of the schema. `source` says what defined it, e.g. "SQL"."""
    result = {
        "name": name,
        "source": source,
        "file": file,
        "line": line,
        "columns": columns,
        "notes": notes or [],
    }
    if inferred:
        result["inferred"] = True  # guessed from queries in code, not from a schema definition
    return result


def column(name, type_, attrs="") -> dict:
    """One column. `attrs` holds short flags such as "PK AUTO" or "NOT NULL FK→users"."""
    return {"name": name, "type": type_, "attrs": attrs.strip()}


def mark_primary_key(columns: list[dict], name: str) -> None:
    """Put "PK" in front of the attributes of the column called `name`."""
    for col in columns:
        if col["name"] == name and "PK" not in col["attrs"]:
            col["attrs"] = ("PK " + col["attrs"]).strip()


def also_defined(file: str) -> str:
    return tr(f"also defined in {file}", f"juga didefinisikan di {file}")


def split_top_level(body: str) -> list[str]:
    """Split on commas that are not inside parentheses: "a int, b decimal(8,2)" -> 2 parts."""
    parts, depth, current = [], 0, []
    for char in body:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]
