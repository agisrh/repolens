"""Prepare the source (local folder, git URL, specific ref) and run every extractor."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from repolens import __version__, coverage, projectconfig
from repolens.extractors import config, database, deps, endpoints, overview, platforms, stack
from repolens.i18n import get_lang, t
from repolens.repo import Repo, strip_credentials

GIT_URL = re.compile(r"^(https?://|git@|ssh://)")


# Never wait for a username/password prompt: in CI that hangs forever.
GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}


def is_git_url(source: str) -> bool:
    """True for https://, ssh:// and git@host: sources (anything else is a local folder)."""
    return bool(GIT_URL.match(source))


def _run(args: list[str], cwd: str | None = None) -> str:
    """Run a command (git) and return its output; failures become a readable RuntimeError
    with any credentials in URLs removed."""
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=GIT_ENV,
        )
    except FileNotFoundError:
        raise RuntimeError(
            t(
                f"`{args[0]}` not found. Install {args[0]} and try again.",
                f"`{args[0]}` tidak ditemukan. Pasang {args[0]} lalu coba lagi.",
            )
        ) from None
    if result.returncode != 0:
        # Both the command line and git's own message can contain the URL, including a token in it.
        command = strip_credentials(" ".join(args))
        raise RuntimeError(
            t("Command failed: ", "Perintah gagal: ")
            + f"{command}\n{strip_credentials(result.stderr.strip())}"
        )
    return result.stdout.strip()


@contextmanager
def prepared_source(source: str, ref: str | None):
    """Yield a folder to scan.

    A remote URL is cloned to a temp folder. A local repo scanned at a specific
    ref is cloned too, so the user's working tree is never touched.
    """
    is_url = is_git_url(source)
    if not is_url and not ref:
        yield (
            Path(source).resolve(),
            {"type": "local", "location": str(Path(source).resolve()), "ref": None},
        )
        return
    if not is_url and not Path(source).is_dir():
        raise FileNotFoundError(
            t("Folder not found: ", "Folder tidak ditemukan: ") + str(Path(source).resolve())
        )
    tmp = tempfile.mkdtemp(prefix="repolens-")
    target = str(Path(tmp) / "repo")
    try:
        _clone(source, is_url, target)
        if ref:
            _run(["git", "-c", "advice.detachedHead=false", "checkout", "--quiet", ref], cwd=target)
        yield (
            Path(target),
            {
                "type": "git-url" if is_url else "local@ref",
                "location": strip_credentials(source),
                "ref": ref,
            },
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _clone(source: str, is_url: bool, target: str) -> None:
    """Clone `source` into `target`, keeping the remote the project really uses."""
    origin = source if is_url else str(Path(source).resolve())
    if is_url:
        # Skip file contents of old commits (fetched on demand), but keep the history for
        # git log / describe.
        _run(["git", "clone", "--quiet", "--filter=blob:none", origin, target])
        return
    _run(["git", "clone", "--quiet", "--no-hardlinks", origin, target])
    # Report the project's real remote (e.g. GitHub), not the local folder the temporary
    # clone came from.
    try:
        remote = _run(["git", "remote", "get-url", "origin"], cwd=origin)
    except RuntimeError:
        remote = ""
    if remote:
        _run(["git", "remote", "set-url", "origin", remote], cwd=target)
    else:
        _run(["git", "remote", "remove", "origin"], cwd=target)


def _quiet(message: str, kind: str = "step") -> None:
    pass


def _identity(repo: Repo, source_info: dict) -> dict:
    """Project name and version. A clone lives in a temporary folder, so when the name would
    come from the folder, the repository name from the URL or path is used instead."""
    ident = overview.identity(repo)
    if source_info["type"] != "local" and ident["name_source"] == "folder":
        name = Path(source_info["location"].rstrip("/")).name.removesuffix(".git")
        ident["name"] = ident["folder"] = name
    return ident


def _git(repo: Repo, source_info: dict, use_git: bool) -> dict:
    if not use_git:
        return {"is_git": False, "disabled": True}
    git = overview.git_info(repo)
    if source_info["type"] == "git-url" and not git.get("remote"):
        git["remote"] = source_info["location"]
    return git


def scan(
    root: Path, source_info: dict, tree_depth: int | None = None, log=_quiet, use_git: bool = True
) -> dict:
    """Run every extractor and return the scan facts.

    `log(message, kind)` reports progress; use_git=False reads the folder as plain files."""
    if not Path(root).is_dir():
        raise FileNotFoundError(
            t("Folder not found: ", "Folder tidak ditemukan: ") + str(Path(root).resolve())
        )
    project_cfg = projectconfig.load(root)
    data, cfg_warnings = project_cfg["data"], list(project_cfg["warnings"])
    if project_cfg["file"]:
        log(t(f"Using {project_cfg['file']}", f"Memakai {project_cfg['file']}"))
    repo = Repo(root, ignore=data.get("ignore", []), use_git=use_git)
    extra_routes = projectconfig.expand(root, data.get("routes", []), "routes", cfg_warnings)
    extra_schema = projectconfig.expand(root, data.get("schema", []), "schema", cfg_warnings)
    depth = tree_depth or data.get("tree_depth") or 3

    log(
        t(f"Reading {len(repo.files)} files", f"Membaca {len(repo.files)} file")
        + ("" if use_git else t(" (plain folder, git not used)", " (folder biasa, tanpa git)"))
    )
    ident = _identity(repo, source_info)
    git = _git(repo, source_info, use_git)

    log(t("Tech stack & dependencies", "Tech stack & dependency"))
    manifests = deps.extract(repo)
    frameworks = stack.frameworks(repo, manifests)
    infra = platforms.infrastructure(repo)

    log(t("Endpoints & routes", "Endpoint & route"))
    eps = endpoints.extract(repo, extra_routes)

    log(t("Database & configuration", "Database & konfigurasi"))
    db = database.extract(repo, manifests, infra["compose_services"], extra_schema)
    cfg = config.extract(repo)

    facts = {
        "repolens_version": __version__,
        "lang": get_lang(),
        "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source_info,
        "project": ident,
        "git": git,
        "readme_excerpt": overview.readme_excerpt(repo),
        "tree": overview.folder_tree(repo, max_depth=depth),
        "languages": overview.languages(repo),
        "frameworks": frameworks,
        "dependencies": manifests,
        "platforms": platforms.mobile_platforms(repo),
        "infrastructure": infra,
        "endpoints": eps,
        "database": db,
        "config": {"env_files": cfg["env_files"], "spring_config": cfg["spring_config"]},
        "security": {"secrets": cfg["secrets"]},
        "project_config": {
            "file": project_cfg["file"],
            "applied": [],
            "warnings": cfg_warnings,
            "routes": extra_routes,
            "schema": extra_schema,
            "ignore": data.get("ignore", []),
            "notes": data.get("notes", []),
        },
        "ai": None,
        "changes": None,
    }
    if project_cfg["file"]:
        facts["project_config"]["applied"] = projectconfig.apply_overrides(facts, project_cfg)
    facts["coverage"] = coverage.check(repo, facts)
    return facts
