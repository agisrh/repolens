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
from repolens.extractors import config, database, deps, endpoints, overview, stack
from repolens.i18n import get_lang, t
from repolens.repo import Repo, strip_credentials

GIT_URL = re.compile(r"^(https?://|git@|ssh://)")


# Never wait for a username/password prompt: in CI that hangs forever.
GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}


def is_git_url(source: str) -> bool:
    return bool(GIT_URL.match(source))


def _run(args: list[str], cwd: str | None = None) -> str:
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
        origin = source if is_url else str(Path(source).resolve())
        # Remote: skip file contents of old commits (fetched on demand), keeps history for git log/describe.
        clone = (
            ["git", "clone", "--quiet", "--filter=blob:none"]
            if is_url
            else ["git", "clone", "--quiet", "--no-hardlinks"]
        )
        _run(clone + [origin, target])
        if not is_url:
            # Report the project's real remote (e.g. GitHub), not the local folder the temp clone came from.
            try:
                remote = _run(["git", "remote", "get-url", "origin"], cwd=origin)
            except RuntimeError:
                remote = ""
            if remote:
                _run(["git", "remote", "set-url", "origin", remote], cwd=target)
            else:
                _run(["git", "remote", "remove", "origin"], cwd=target)
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


def _quiet(message: str, kind: str = "step") -> None:
    pass


def scan(
    root: Path, source_info: dict, tree_depth: int | None = None, log=_quiet, use_git: bool = True
) -> dict:
    """Run every extractor. `log(message, kind)` reports progress; use_git=False reads the folder as plain files."""
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
    ident = overview.identity(repo)
    if source_info["type"] != "local" and ident["name_source"] == "folder":
        ident["name"] = ident["folder"] = Path(
            source_info["location"].rstrip("/")
        ).name.removesuffix(".git")
    git = overview.git_info(repo) if use_git else {"is_git": False, "disabled": True}
    if source_info["type"] == "git-url" and not git.get("remote"):
        git["remote"] = source_info["location"]

    log(t("Tech stack & dependencies", "Tech stack & dependency"))
    manifests = deps.extract(repo)
    frameworks = stack.frameworks(repo, manifests)
    infra = stack.infrastructure(repo)

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
        "platforms": stack.mobile_platforms(repo),
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
