"""Regression tests on real repositories pinned to a commit (see corpus.yml). Run: pytest -m corpus"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from repolens.scanner import prepared_source, scan

CORPUS = yaml.safe_load((Path(__file__).parent / "corpus.yml").read_text())
CACHE = Path.home() / ".cache" / "repolens" / "corpus"


def _git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def _checkout_public(entry) -> Path:
    target = CACHE / entry["name"]
    head = _git("rev-parse", "HEAD", cwd=target).stdout.strip() if (target / ".git").exists() else ""
    if head != entry["commit"]:
        target.mkdir(parents=True, exist_ok=True)
        _git("init", "-q", cwd=target)
        _git("remote", "remove", "origin", cwd=target)
        _git("remote", "add", "origin", entry["url"], cwd=target)
        fetched = _git("fetch", "-q", "--depth", "1", "origin", entry["commit"], cwd=target)
        if fetched.returncode != 0:
            pytest.skip(f"tidak bisa mengambil {entry['url']}: {fetched.stderr.strip()}")
        _git("-c", "advice.detachedHead=false", "checkout", "-q", "--force", "FETCH_HEAD", cwd=target)
    return target


def _verify(facts: dict, expect: dict):
    fws = {f["name"]: f["version"] for f in facts["frameworks"]}
    for name, version in (expect.get("framework") or {}).items():
        assert name in fws, f"framework {name} tidak terdeteksi (terdeteksi: {sorted(fws)})"
        if version is not None:
            assert fws[name] == str(version), f"{name}: versi {fws[name]!r}, diharapkan {version!r}"

    eps = facts["endpoints"]
    counts = {"server": len(eps["server"]), "client": len(eps["client"]), "pages": len(eps["pages"]),
              "tables": len(facts["database"]["tables"])}
    for key, minimum in (expect.get("min") or {}).items():
        assert counts[key] >= minimum, f"{key}: {counts[key]} < minimum {minimum}"

    for kind in ("server", "client", "pages"):
        found = {f"{e['method']} {e['path']}" for e in eps[kind]}
        missing = [e for e in expect.get(kind, []) if e not in found]
        assert not missing, f"{kind} tidak ditemukan: {missing}"

    # A table can be described by several sources (e.g. schema.sql and a JPA entity): union their columns.
    tables: dict[str, set] = {}
    for t in facts["database"]["tables"]:
        tables.setdefault(t["name"], set()).update(c["name"] for c in t["columns"])
    for name, cols in (expect.get("tables") or {}).items():
        assert name in tables, f"tabel {name} tidak ditemukan"
        missing = set(cols) - tables[name]
        assert not missing, f"tabel {name}: kolom tidak ditemukan {sorted(missing)}"


@pytest.mark.corpus
@pytest.mark.parametrize("entry", CORPUS.get("public", []), ids=lambda e: e["name"])
def test_public_repo(entry):
    root = _checkout_public(entry)
    facts = scan(root, {"type": "local", "location": entry["url"], "ref": entry["commit"]}, log=lambda *_: None)
    _verify(facts, entry["expect"])


@pytest.mark.corpus
@pytest.mark.parametrize("entry", CORPUS.get("local", []), ids=lambda e: e["name"])
def test_local_repo(entry):
    path = Path(entry["path"]).expanduser()
    if not path.exists():
        pytest.skip(f"{path} tidak ada di mesin ini")
    with prepared_source(str(path), entry["ref"]) as (root, info):
        facts = scan(root, info, log=lambda *_: None)
    _verify(facts, entry["expect"])
