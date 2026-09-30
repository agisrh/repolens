"""The interactive menu only builds argv for regular commands: drive it with scripted answers."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from repolens import menu

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def answers(monkeypatch):
    """Replace every prompt with the next scripted answer."""
    queue: list = []

    class Prompt:
        def __init__(self, *args, **kwargs):
            pass

    for name in ("select", "path", "text", "checkbox", "confirm"):
        monkeypatch.setattr(menu.questionary, name, Prompt)
    monkeypatch.setattr(menu, "_ask", lambda prompt: queue.pop(0))
    return queue


def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "app"
    shutil.copytree(FIXTURES / "laravel_groups", repo)
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": str(tmp_path)}
    for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "x"], ["tag", "v1.0.0"],
                ["commit", "-q", "--allow-empty", "-m", "y"], ["tag", "v1.1.0"]):
        subprocess.run(["git", *cmd], cwd=repo, check=True, capture_output=True, env=env)
    return repo


def test_scan_local_folder_as_plain_files(answers, tmp_path):
    repo = git_repo(tmp_path)
    answers += ["scan", "local", str(repo), "plain", ["pdf", "docx", "md"], False, "en", "docs-output", True]
    assert menu.run() == ["scan", str(repo), "--no-git", "--no-ai", "--lang", "en"]


def test_scan_release_tag_compared_with_previous(answers, tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    repo = git_repo(tmp_path)
    answers += ["scan", "local", str(repo), "ref", "v1.1.0", "v1.0.0", ["pdf"], True, "id", "out", True]
    assert menu.run() == ["scan", str(repo), "--ref", "v1.1.0", "--compare-ref", "v1.0.0", "--format", "pdf",
                          "--lang", "id", "--out", "out"]


def test_scan_folder_that_is_not_a_git_repo_skips_git_questions(answers, tmp_path):
    folder = tmp_path / "plain"
    shutil.copytree(FIXTURES / "laravel_groups", folder)
    answers += ["scan", "local", str(folder), ["md"], False, "en", "docs-output", True]
    assert menu.run() == ["scan", str(folder), "--format", "md", "--no-ai", "--lang", "en"]


def test_scan_git_url(answers):
    answers += ["scan", "url", "git@github.com:org/app.git", "v2.0.0", "", ["pdf", "docx", "md"], False, "en", "docs-output", True]
    assert menu.run() == ["scan", "git@github.com:org/app.git", "--ref", "v2.0.0", "--no-ai", "--lang", "en"]


def test_ai_without_a_key_offers_setup_and_falls_back_to_no_ai(answers, tmp_path):
    folder = tmp_path / "plain"
    shutil.copytree(FIXTURES / "laravel_groups", folder)
    # AI? yes -> set up a key now? no -> scanned without AI
    answers += ["scan", "local", str(folder), ["md"], True, False, "en", "docs-output", True]
    assert menu.run() == ["scan", str(folder), "--format", "md", "--no-ai", "--lang", "en"]


def test_auth_entry(answers):
    answers += ["auth", "status", True]
    assert menu.run() == ["auth", "status"]


def test_quit_and_decline_return_nothing(answers):
    answers += [None]
    assert menu.run() is None
    answers += ["doctor", ".", False]
    assert menu.run() is None


def test_ctrl_c_cancels(monkeypatch):
    def cancelled(prompt):
        raise menu.Cancelled
    monkeypatch.setattr(menu, "_ask", cancelled)
    for name in ("select", "path", "text", "checkbox", "confirm"):
        monkeypatch.setattr(menu.questionary, name, lambda *a, **k: None)
    assert menu.run() is None
