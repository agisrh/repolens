"""Database engines and schema, from SQL files, migrations, ORM models, and PHP queries.

Each reader returns tables in the same shape (see _common.table):
  sql.py         CREATE TABLE statements
  migrations.py  Laravel and CodeIgniter 4 migrations
  orm.py         JPA, Prisma, TypeORM, Drizzle, Django, Hive
  gorm.py        GORM models (Go)
  rails.py       Ruby on Rails schema.rb or migrations
  php_models.py  tables inferred from PHP models and queries (partial, marked "inferred")
  engines.py     which database engines are used

To support another schema source, add a reader `(repo) -> list[dict]` and call it in
`extract()` below.
"""

from __future__ import annotations

from repolens.extractors.database._common import also_defined
from repolens.extractors.database.engines import engines
from repolens.extractors.database.gorm import gorm_models
from repolens.extractors.database.migrations import ci4_migrations, laravel_migrations
from repolens.extractors.database.orm import (
    django_models,
    drizzle,
    hive_models,
    jpa_entities,
    prisma,
    typeorm,
)
from repolens.extractors.database.php_models import php_models
from repolens.extractors.database.rails import rails_schema
from repolens.extractors.database.sql import sql_files
from repolens.repo import Repo


def extract(
    repo: Repo, manifests: list[dict], compose: list[dict], extra_schema: list[str] = ()
) -> dict:
    """{"engines", "tables"}. extra_schema: SQL dumps listed in .repolens.yml (any extension)."""
    defined = (
        sql_files(repo, extra_schema)
        + laravel_migrations(repo)
        + ci4_migrations(repo)
        + jpa_entities(repo)
        + prisma(repo)
        + typeorm(repo)
        + drizzle(repo)
        + django_models(repo)
        + hive_models(repo)
        + gorm_models(repo)
        + rails_schema(repo)
    )
    # Tables inferred from queries only fill gaps: skip names a real schema source defines.
    known = {t["name"].lower() for t in defined}
    inferred = [t for t in php_models(repo) if t["name"].lower() not in known]
    return {
        "engines": engines(repo, manifests, compose),
        "tables": _merge_duplicates(defined) + inferred,
    }


def _merge_duplicates(tables: list[dict]) -> list[dict]:
    """The same table defined by one kind of source in several files (e.g. one schema.sql
    per SQL dialect): keep the one with the most columns and note where the others are.
    Definitions from different kinds of sources are all kept."""
    by_key: dict[str, dict] = {}
    for item in tables:
        key = item["name"].lower()
        if key not in by_key:
            by_key[key] = item
            continue
        kept = by_key[key]
        if item["source"] != kept["source"]:
            by_key[key + "::" + item["source"]] = item
        elif len(item["columns"]) > len(kept["columns"]):
            item["notes"] = kept["notes"] + [also_defined(kept["file"])]
            by_key[key] = item
        else:
            kept["notes"].append(also_defined(item["file"]))
    return list(by_key.values())
