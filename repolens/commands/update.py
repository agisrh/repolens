"""`repolens update`: install the newest release from the repository RepoLens came from.

Releases are git tags (v0.3.0, v0.4.0, ...). The installer is detected from the running
environment: pipx (reinstalled with --force), a regular pip environment (pip install -U),
or an editable source checkout, where the right move is `git pull`, not an install.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path

from repolens import __version__, ui
from repolens.commands._common import add_command, flag
from repolens.i18n import t

NAME = "update"
DEFAULT_REPO = "git@github.com:agisrh/repolens.git"
TAG = re.compile(r"refs/tags/(v(\d+)\.(\d+)\.(\d+))$")


def register(subparsers, common):
    p = add_command(
        subparsers,
        NAME,
        common,
        "Install the newest RepoLens release",
        "Pasang rilis RepoLens terbaru",
    )
    flag(
        p,
        "--check",
        "Only report whether a newer release exists",
        "Hanya cek apakah ada rilis yang lebih baru",
    )
    return p


def run(args) -> int:
    return update(check_only=args.check)


def repo_url() -> str:
    """Repository to update from: REPOLENS_REPO, else the official one."""
    return os.environ.get("REPOLENS_REPO") or DEFAULT_REPO


def version_tuple(version: str) -> tuple[int, ...]:
    """ "v0.10.2" -> (0, 10, 2), so versions compare as numbers and not as text."""
    return tuple(int(n) for n in re.findall(r"\d+", version)[:3])


def pip_url(repo: str, tag: str) -> str:
    """The pip requirement for a tag of the repository.

    git@github.com:org/repo.git -> git+ssh://git@github.com/org/repo.git@tag
    https://github.com/org/repo.git -> git+https://github.com/org/repo.git@tag"""
    scp = re.match(r"^([\w.-]+@[\w.-]+):(.+)$", repo)
    if scp:
        repo = f"ssh://{scp.group(1)}/{scp.group(2)}"
    return f"git+{repo}@{tag}"


def latest_tag(repo: str) -> str | None:
    """Newest vX.Y.Z tag in the repository, or None when it cannot be read."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--tags", "--refs", repo],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    tags = [m.group(1) for line in result.stdout.splitlines() if (m := TAG.search(line.strip()))]
    return max(tags, key=version_tuple, default=None)


def install_kind() -> tuple[str, str | None]:
    """("editable", source folder) | ("pipx", None) | ("pip", None)."""
    try:
        raw = metadata.distribution("repolens").read_text("direct_url.json")
        direct = json.loads(raw) if raw else {}
    except (metadata.PackageNotFoundError, ValueError):
        direct = {}
    if (direct.get("dir_info") or {}).get("editable"):
        return "editable", re.sub(r"^file://", "", direct.get("url", ""))
    if "pipx" in Path(sys.prefix).parts:
        return "pipx", None
    return "pip", None


def install_command(kind: str, url: str) -> list[str]:
    """The command that installs `url` with the same installer RepoLens was installed with."""
    if kind == "pipx":
        return ["pipx", "install", "--force", url]
    return [sys.executable, "-m", "pip", "install", "--upgrade", url]


def update(check_only: bool = False) -> int:
    """Find the newest vX.Y.Z tag and install it, unless it is already installed."""
    repo = repo_url()
    ui.header("Update", repo)
    with ui.out.status(t("Looking for the newest release…", "Mencari rilis terbaru…")):
        tag = latest_tag(repo)
    if not tag:
        ui.error(
            t(
                f"Cannot read the releases of {repo}. Check your network and your access to "
                "the repository (set REPOLENS_REPO when installed from another location).",
                f"Tidak bisa membaca rilis dari {repo}. Cek jaringan dan akses Anda ke repository "
                "(set REPOLENS_REPO jika dipasang dari lokasi lain).",
            )
        )
        return 1
    if version_tuple(tag) <= version_tuple(__version__):
        ui.ok(
            t(
                f"RepoLens {__version__} is the newest release.",
                f"RepoLens {__version__} sudah versi terbaru.",
            )
        )
        return 0
    ui.info(
        t(
            f"New release: {__version__} → {tag.lstrip('v')}",
            f"Rilis baru: {__version__} → {tag.lstrip('v')}",
        )
    )
    kind, source = install_kind()
    if kind == "editable":
        ui.warn(
            t(
                "RepoLens runs from a source folder (editable install); update it with git "
                "instead:",
                "RepoLens berjalan dari folder source (editable install); update lewat git:",
            )
        )
        ui.hint(
            f"git -C {source or '<folder>'} pull && git -C {source or '<folder>'} checkout {tag}"
        )
        return 0 if check_only else 1
    if check_only:
        ui.hint(
            t("Install it with: repolens update", "Pasang dengan: repolens update"), indent="  "
        )
        return 0
    _install(kind, pip_url(repo, tag), tag)
    return 0


def _install(kind: str, url: str, tag: str) -> None:
    """Install `url` with pipx or pip; a failure shows the last lines of the installer output."""
    command = install_command(kind, url)
    with ui.task(
        t(f"Installing {tag} with {kind}", f"Memasang {tag} dengan {kind}"),
        t(f"Updated to {tag}", f"Diperbarui ke {tag}"),
    ):
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:  # raised inside the task, so no "✓ Updated" line is shown
            output = (result.stderr or result.stdout).strip().splitlines()[-8:]
            failed = t("Update failed: ", "Update gagal: ") + " ".join(command)
            raise RuntimeError(failed + "\n" + "\n".join(output))
