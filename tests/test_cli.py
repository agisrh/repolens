"""CLI behaviour: input validation, error messages, output safety, and git source handling.

These run the real `main()` against fixtures and throwaway git repositories in tmp_path.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from repolens import projectconfig
from repolens.cli import main
from repolens.extractors import config
from repolens.repo import Repo
from repolens.scanner import _run

FIXTURES = Path(__file__).parent / "fixtures"


def git(cwd: Path, *args: str):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                        "HOME": str(cwd)})


def make_repo(tmp_path: Path, fixture: str, name: str, remote: str | None = None) -> Path:
    repo = tmp_path / name
    shutil.copytree(FIXTURES / fixture, repo)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "first")
    git(repo, "tag", "v1.0.0")
    if remote:
        git(repo, "remote", "add", "origin", remote)
    return repo


def scan_args(source, out, *extra):
    return ["scan", str(source), "--no-ai", "--format", "md", "--out", str(out), *extra]


# ---- input validation -------------------------------------------------------

def test_export_rejects_invalid_json(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{bad")
    assert main(["export", str(bad)]) == 1
    assert "is not valid JSON" in capsys.readouterr().err


def test_export_rejects_json_that_is_not_a_scan(tmp_path, capsys):
    other = tmp_path / "other.json"
    other.write_text("{}")
    assert main(["diff", str(other), str(other)]) == 1
    assert "is not a `repolens scan` result" in capsys.readouterr().err


def test_missing_compare_file_fails_before_scanning(tmp_path, capsys):
    assert main(scan_args(FIXTURES / "laravel_groups", tmp_path, "--compare", str(tmp_path / "none.json"))) == 1
    captured = capsys.readouterr()
    assert "File not found" in captured.err
    assert "Reading" not in captured.out


def test_compare_and_compare_ref_are_exclusive(tmp_path):
    with pytest.raises(SystemExit) as exc:
        main(scan_args(FIXTURES / "laravel_groups", tmp_path, "--compare", "a.json", "--compare-ref", "v1"))
    assert exc.value.code == 2


@pytest.mark.parametrize("depth", ["0", "-1", "abc"])
def test_tree_depth_must_be_positive(tmp_path, depth):
    with pytest.raises(SystemExit):
        main(scan_args(FIXTURES / "laravel_groups", tmp_path, "--tree-depth", depth))


def test_init_rejects_git_url(capsys):
    assert main(["init", "https://github.com/example/repo.git"]) == 1
    assert "needs a local folder" in capsys.readouterr().err


def test_init_respects_existing_repolens_yaml(tmp_path, capsys):
    project = tmp_path / "p"
    shutil.copytree(FIXTURES / "laravel_groups", project)
    (project / ".repolens.yaml").write_text("name: x\n")
    assert main(["init", str(project)]) == 1
    assert ".repolens.yaml already exists" in capsys.readouterr().err


# ---- .repolens.yml robustness -------------------------------------------------

def test_malformed_config_is_reported_not_crashing(tmp_path):
    (tmp_path / ".repolens.yml").write_text(
        "version: 1.10\nignore: [123, {a: b}]\nroutes: [/etc/hosts, ../../x.php]\n"
        "frameworks: Laravel\nendpoints: {method: GET}\ntree_depth: true\nname: ''\n")
    cfg = projectconfig.load(tmp_path)
    text = "\n".join(cfg["warnings"])
    assert "as a number" in text
    assert "items must be text, not dict" in text
    assert text.count("stay inside the project folder") == 2
    assert "`frameworks` must be a list" in text
    assert "`endpoints` item needs a `path`" in text
    assert "`tree_depth`" in text
    assert cfg["data"]["ignore"] == ["123"]
    assert "routes" in cfg["data"] and cfg["data"]["routes"] == []
    assert "name" not in cfg["data"]  # empty value from the init template is not an override


def test_glob_outside_project_is_ignored(tmp_path):
    (tmp_path / "inner").mkdir()
    (tmp_path / "secret.sql").write_text("x")
    warnings: list[str] = []
    assert projectconfig.expand(tmp_path / "inner", ["../*.sql"], "schema", warnings) == []


# ---- output safety ----------------------------------------------------------

def test_different_project_with_same_name_and_release_is_not_overwritten(tmp_path, capsys):
    a = make_repo(tmp_path, "flutter_client", "app_a", "git@github.com:org/app-a.git")
    b = make_repo(tmp_path, "flutter_client", "app_b", "git@github.com:org/app-b.git")
    out = tmp_path / "out"
    assert main(scan_args(a, out)) == 0
    assert main(scan_args(b, out)) == 1
    err = capsys.readouterr().err
    assert "Two different projects" in err and "git@github.com:org/app-a" in err and "git@github.com:org/app-b" in err
    assert "`name: app_b`" in err and "--force" in err
    scanned = next(out.glob("*/scan.json"))
    assert json.loads(scanned.read_text())["git"]["remote"] == "git@github.com:org/app-a.git"
    assert main(scan_args(b, out, "--force")) == 0
    assert json.loads(scanned.read_text())["git"]["remote"] == "git@github.com:org/app-b.git"


def test_rescanning_same_project_overwrites(tmp_path):
    a = make_repo(tmp_path, "flutter_client", "app_a", "git@github.com:org/app-a.git")
    out = tmp_path / "out"
    assert main(scan_args(a, out)) == 0
    assert main(scan_args(a, out)) == 0


def test_strict_scan_fails_on_warnings(tmp_path):
    assert main(scan_args(FIXTURES / "ci4_no_vendor", tmp_path, "--strict")) == 1
    assert main(scan_args(FIXTURES / "ci4_no_vendor", tmp_path)) == 0


# ---- git sources ------------------------------------------------------------

def test_local_ref_scan_reports_real_remote_and_no_fake_branch(tmp_path):
    repo = make_repo(tmp_path, "laravel_groups", "api", "https://github.com/org/api.git")
    out = tmp_path / "out"
    assert main(scan_args(repo, out, "--ref", "v1.0.0")) == 0
    facts = json.loads(next(out.glob("*/scan.json")).read_text())
    assert facts["git"]["remote"] == "https://github.com/org/api.git"
    assert facts["git"]["branch"] is None  # detached at the tag, not a branch called "HEAD"
    assert facts["git"]["tags_at_head"] == ["v1.0.0"]


def test_git_errors_never_show_credentials():
    with pytest.raises(RuntimeError) as exc:
        _run(["git", "clone", "--quiet", "https://user:s3cr3t-token@127.0.0.1:9/none.git", "/nonexistent/x"])
    assert "s3cr3t-token" not in str(exc.value)


def test_tracked_files_handles_non_ascii_names(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "café.env").write_text("KEY=1\n")
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "x")
    assert "café.env" in Repo(repo).tracked_files


# ---- security severity ------------------------------------------------------

def test_secret_severity_is_lower_in_tests_and_firebase_client_config(tmp_path):
    (tmp_path / "lib").mkdir()
    (tmp_path / "test").mkdir()
    (tmp_path / "android").mkdir()
    (tmp_path / "lib" / "auth.dart").write_text('const password = "RealPass2024";\n')
    (tmp_path / "test" / "auth_test.dart").write_text('final password = "TestPass2024";\n')
    (tmp_path / "android" / "google-services.json").write_text('{"current_key": "AIzaSyA1234567890abcdefghijklmnopqrstuv"}\n')
    found = {s["file"]: s for s in config.secrets(Repo(tmp_path))}
    assert found["lib/auth.dart"]["severity"] == "medium"
    assert found["test/auth_test.dart"]["severity"] == "low"
    assert found["android/google-services.json"]["severity"] == "low"
    assert [s["severity"] for s in config.secrets(Repo(tmp_path))] == ["medium", "low", "low"]


# ---- plain folder (--no-git), dry run, json -------------------------------

def test_no_git_reads_every_file_on_disk_without_git_info(tmp_path):
    repo = make_repo(tmp_path, "laravel_groups", "api", "https://github.com/org/api.git")
    (repo / ".gitignore").write_text("generated/\n")
    (repo / "generated").mkdir()
    (repo / "generated" / "routes.php").write_text("<?php\n")
    out = tmp_path / "out"
    assert main(scan_args(repo, out, "--no-git")) == 0
    facts = json.loads(next(out.glob("*/scan.json")).read_text())
    assert facts["git"] == {"is_git": False, "disabled": True}
    assert facts["source"]["no_git"] is True
    assert "generated/" in facts["tree"]["text"]  # git-ignored folder is read too
    assert any("--no-git" in c["message"] for c in facts["coverage"])


def test_no_git_rejects_ref_and_url(capsys):
    assert main(["scan", "https://github.com/x/y.git", "--no-git", "--no-ai"]) == 1
    assert main(["scan", ".", "--no-git", "--ref", "v1", "--no-ai"]) == 1
    assert "--no-git" in capsys.readouterr().err


def test_dry_run_writes_nothing(tmp_path):
    out = tmp_path / "out"
    assert main(scan_args(FIXTURES / "laravel_groups", out, "--dry-run")) == 0
    assert not out.exists()


def test_json_output_is_machine_readable(tmp_path, capsys):
    assert main(scan_args(FIXTURES / "laravel_groups", tmp_path, "--json")) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["stats"]["server_endpoints"] > 0 and result["files"]
    assert main(["doctor", str(FIXTURES / "ci4_no_vendor"), "--json"]) == 0
    assert any(c["level"] == "warn" for c in json.loads(capsys.readouterr().out)["coverage"])


def test_lang_id_translates_terminal_and_document(tmp_path, capsys):
    assert main(scan_args(FIXTURES / "laravel_groups", tmp_path, "--lang", "id")) == 0
    assert "Dokumentasi siap" in capsys.readouterr().out
    md = next(tmp_path.glob("*/*.md")).read_text()
    assert "Daftar Isi" in md and "Ringkasan" in md
    facts = json.loads(next(tmp_path.glob("*/scan.json")).read_text())
    assert facts["lang"] == "id"


def test_export_keeps_scan_language_by_default(tmp_path):
    assert main(scan_args(FIXTURES / "laravel_groups", tmp_path, "--lang", "id")) == 0
    scan_file = next(tmp_path.glob("*/scan.json"))
    assert main(["export", str(scan_file), "--format", "md"]) == 0
    assert "Daftar Isi" in next(tmp_path.glob("*/*.md")).read_text()
    assert main(["export", str(scan_file), "--format", "md", "--lang", "en"]) == 0
    assert "Contents" in next(tmp_path.glob("*/*.md")).read_text()


# ---- names from before the rename to repolens -------------------------------

def test_legacy_docgen_yml_is_still_read(tmp_path):
    (tmp_path / ".docgen.yml").write_text("name: legacy-app\n")
    cfg = projectconfig.load(tmp_path)
    assert cfg["file"] == ".docgen.yml" and cfg["data"]["name"] == "legacy-app"


def test_legacy_scan_json_is_accepted(tmp_path, capsys):
    project = tmp_path / "p"
    project.mkdir()
    (project / "main.py").write_text("print('hi')\n")
    assert main(["scan", str(project), "--no-ai", "--format", "md", "--out", str(tmp_path / "out")]) == 0
    scan_json = next((tmp_path / "out").glob("*/scan.json"))
    facts = json.loads(scan_json.read_text())
    facts["docgen_version"] = facts.pop("repolens_version")
    scan_json.write_text(json.dumps(facts))
    assert main(["export", str(scan_json), "--format", "md"]) == 0
