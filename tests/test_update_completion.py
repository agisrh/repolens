"""`repolens update` (git and pip are replaced by fakes) and the generated completion scripts."""

from __future__ import annotations

import shutil
import subprocess
from types import SimpleNamespace

import pytest

from repolens.cli import build_parser, main
from repolens.commands import update as selfupdate

LS_REMOTE = "\n".join(
    [
        "aaa\trefs/tags/v0.2.0",
        "bbb\trefs/tags/v0.10.0",
        "ccc\trefs/tags/v0.3.0",
        "ddd\trefs/tags/nightly",
    ]
)


@pytest.fixture
def fake_run(monkeypatch):
    """Record subprocess calls; `git ls-remote` answers with LS_REMOTE, everything else succeeds."""
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        out = LS_REMOTE if cmd[:2] == ["git", "ls-remote"] else ""
        return SimpleNamespace(returncode=0, stdout=out, stderr="")

    monkeypatch.setattr(selfupdate.subprocess, "run", run)
    return calls


def test_pip_url_from_ssh_and_https():
    assert (
        selfupdate.pip_url("git@github.com:agisrh/repolens.git", "v1.0.0")
        == "git+ssh://git@github.com/agisrh/repolens.git@v1.0.0"
    )
    assert (
        selfupdate.pip_url("https://github.com/agisrh/repolens.git", "v1.0.0")
        == "git+https://github.com/agisrh/repolens.git@v1.0.0"
    )


def test_latest_tag_compares_versions_not_text(fake_run):
    assert selfupdate.latest_tag("repo") == "v0.10.0"


def test_update_installs_with_pip(fake_run, monkeypatch):
    monkeypatch.setattr(selfupdate, "install_kind", lambda: ("pip", None))
    assert main(["update"]) == 0
    assert fake_run[-1][-3:] == [
        "install",
        "--upgrade",
        "git+ssh://git@github.com/agisrh/repolens.git@v0.10.0",
    ]


def test_update_reinstalls_with_pipx(fake_run, monkeypatch):
    monkeypatch.setattr(selfupdate, "install_kind", lambda: ("pipx", None))
    assert main(["update"]) == 0
    assert fake_run[-1][:3] == ["pipx", "install", "--force"]


def test_update_check_and_editable_do_not_install(fake_run, monkeypatch, capsys):
    monkeypatch.setattr(selfupdate, "install_kind", lambda: ("editable", "/src/repolens"))
    assert main(["update", "--check"]) == 0
    assert main(["update"]) == 1
    assert "git -C /src/repolens pull" in capsys.readouterr().out
    assert all(cmd[:2] == ["git", "ls-remote"] for cmd in fake_run)


def test_update_when_already_newest(fake_run, monkeypatch, capsys):
    monkeypatch.setattr(selfupdate, "__version__", "0.10.0")
    assert main(["update"]) == 0
    assert "newest release" in capsys.readouterr().out


def test_update_reports_unreachable_repository(monkeypatch, capsys):
    monkeypatch.setattr(
        selfupdate.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=128, stdout="", stderr="denied"),
    )
    assert main(["update"]) == 1
    assert "Cannot read the releases" in capsys.readouterr().err


# ---- completion ---------------------------------------------------------------


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_completion_scripts_list_every_command(shell, capsys):
    assert main(["completion", shell]) == 0
    script = capsys.readouterr().out
    for command in (
        "scan",
        "doctor",
        "init",
        "export",
        "diff",
        "auth",
        "update",
        "completion",
        "no-ai",
        "compare-ref",
    ):
        assert command in script


@pytest.mark.skipif(not shutil.which("bash"), reason="needs bash")
def test_bash_completion_answers(tmp_path):
    script = tmp_path / "repolens.bash"
    from repolens.commands import completion

    script.write_text(completion.bash(build_parser()))
    probe = f"""source {script}
t() {{ COMP_WORDS=("$@"); COMP_CWORD=$((${{#COMP_WORDS[@]}}-1)); COMPREPLY=(); _repolens_completion; echo "${{COMPREPLY[*]}}"; }}
t repolens au
t repolens scan . --lang ""
t repolens auth ""
t repolens completion f
"""
    out = subprocess.run(
        ["bash", "-c", probe], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    assert out == ["auth", "en id", "login status logout", "fish"]
