"""Which database engines a project uses, and the evidence for each.

Three kinds of evidence, in this order (the first one found for an engine is kept):
  1. connection settings in config files (.env.example, application.properties, ...)
  2. driver packages in the dependency manifests (pg, mysql2, psycopg2, hive, ...)
  3. database images in docker-compose (postgres, mysql, redis, ...)
"""

from __future__ import annotations

import re

from repolens.extractors.database._common import tr
from repolens.repo import Repo

CONFIG_FILES = (
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
# Each pattern captures a driver or scheme name, e.g. "mysql" in jdbc:mysql://...
CONFIG_PATTERNS = (
    r"jdbc:(\w+):",
    r"DB_CONNECTION\s*=\s*(\w+)",
    r"DBDriver['\"]?\s*=>?\s*['\"]?(\w+)",
    r"database\.default\.DBDriver\s*=\s*(\w+)",
    r"DATABASE_URL\s*=\s*['\"]?(\w+)://",
    r"datasource\s+\w+\s*\{[^}]*?provider\s*=\s*\"(\w+)\"",
    r"ENGINE['\"]\s*:\s*['\"]django\.db\.backends\.(\w+)",
)
# package name -> engine
DRIVER_PACKAGES = {
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
# docker image name part -> engine
IMAGES = (
    ("postgres", "PostgreSQL"),
    ("mysql", "MySQL"),
    ("mariadb", "MariaDB"),
    ("mongo", "MongoDB"),
    ("redis", "Redis"),
    ("mssql", "SQL Server"),
)
# driver name found in config -> display name
DISPLAY_NAMES = {
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


def engines(repo: Repo, manifests: list[dict], compose: list[dict]) -> list[dict]:
    """[{"engine", "evidence", "local"?}]; "local" marks on-device storage, not a server."""
    found: dict[str, str] = {}  # engine or driver name -> evidence
    for path in repo.glob(*CONFIG_FILES):
        lines = repo.read(path).splitlines()
        text = "\n".join(
            line for line in lines if not line.lstrip().startswith(("#", "//", "*", "/*"))
        )
        for pattern in CONFIG_PATTERNS:
            match = re.search(pattern, text)
            if match:
                found.setdefault(match.group(1).lower(), path)
    for manifest in manifests:
        for dependency in manifest["dependencies"]:
            engine = DRIVER_PACKAGES.get(dependency["name"])
            if engine:
                found.setdefault(engine, f"{manifest['manifest']} ({dependency['name']})")
    for service in compose:
        image = (service.get("image") or "").lower()
        for key, engine in IMAGES:
            if key in image:
                found.setdefault(engine, f"{service['file']} (service {service['service']})")

    merged: dict[str, str] = {}
    for name, evidence in found.items():
        merged.setdefault(DISPLAY_NAMES.get(name, name), evidence)
    result = []
    for name, evidence in merged.items():
        engine = {"engine": name.replace("(local)", tr("(local)", "(lokal)")), "evidence": evidence}
        if "(local)" in name:
            engine["local"] = True
        result.append(engine)
    return result
