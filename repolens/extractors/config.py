"""Environment and config keys (names only, never values), and secret detection."""

from __future__ import annotations

import re

from repolens.i18n import t
from repolens.repo import Repo, line_of

ENV_FILE = re.compile(r"(^|/)(\.env(\.[\w.-]+)?|env|[\w.-]+\.env)$")
ENV_KEY = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_.]*)\s*=", re.M)
TEMPLATE_SUFFIXES = (".example", ".sample", ".dist", ".template", ".defaults")


def env_files(repo: Repo) -> list[dict]:
    """Every .env-style file with its key names; `template` marks .env.example and the like."""
    results = []
    for path in repo.files:
        if not ENV_FILE.search(path) or path.startswith(("android/", "ios/")):
            continue
        text = repo.read(path)
        keys = sorted(dict.fromkeys(ENV_KEY.findall(text)))
        if not keys:
            continue
        filename = path.rsplit("/", 1)[-1].lower()
        is_template = filename == "env" or any(
            suffix.strip(".") in filename.split(".") for suffix in TEMPLATE_SUFFIXES
        )
        results.append(
            {
                "file": path,
                "keys": keys,
                "template": is_template,
                "committed": path in repo.tracked_files if repo.is_git else None,
            }
        )
    return results


def spring_profiles(repo: Repo) -> list[dict]:
    """Top-level keys of Spring application*.properties / *.yml files (not test ones)."""
    out = []
    for path in repo.glob("*application*.properties", "*application*.yml", "*application*.yaml"):
        if "/test/" in path:
            continue
        text = repo.read(path)
        if path.endswith(".properties"):
            keys = sorted(dict.fromkeys(re.findall(r"^\s*([\w.\-\[\]]+)\s*[=:]", text, re.M)))
        else:
            keys = sorted(dict.fromkeys(re.findall(r"^([\w\-]+):", text, re.M)))
        out.append({"file": path, "keys": keys})
    return out


HIGH_SEVERITY = {
    "GitHub token",
    "AWS access key",
    "Slack token",
    "Stripe secret key",
    "Private key",
    "committed_env",
}

SECRET_PATTERNS = [
    ("GitHub token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,})\b")),
    ("AWS access key", re.compile(r"\b(AKIA[0-9A-Z]{16})\b")),
    ("Google API key", re.compile(r"\b(AIza[0-9A-Za-z\-_]{35})\b")),
    ("Slack token", re.compile(r"\b(xox[baprs]-[0-9A-Za-z-]{10,})\b")),
    ("Stripe secret key", re.compile(r"\b(sk_live_[0-9a-zA-Z]{24,})\b")),
    ("Private key", re.compile(r"(-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----)")),
    ("JWT", re.compile(r"\b(eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})\b")),
    (
        "Hardcoded password",
        re.compile(
            r"(?i)\b(?:password|passwd|pwd|secret|api_?key)\b\s*[:=]\s*['\"]([^'\"\s$%{]{8,})['\"]"
        ),
    ),
]
# Test code and fixtures often hold throwaway credentials: still reported, but not at the
# same level as app code.
TEST_PATH = re.compile(
    r"(^|/)(tests?|__tests__|spec|specs|fixtures?|testdata)/|(_test|\.test|\.spec|Test|Tests)\.\w+$"
)
# Firebase client config: the API key is meant to ship inside the app; the risk is a key
# without restrictions.
FIREBASE_CLIENT_CONFIG = {
    "google-services.json",
    "GoogleService-Info.plist",
    "firebase_options.dart",
}
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
# Binary, generated, or lock files: never searched for secrets.
SKIP_SECRET_FILES = tuple(
    ".lock .min.js .map .svg .png .jpg .jpeg .gif .ico .pdf .ttf .woff .woff2 .jar .keystore"
    " .jks".split()
)
# Placeholder values that are not real passwords.
PLACEHOLDERS = ("password", "changeme", "secret")


def secrets(repo: Repo) -> list[dict]:
    """Possible secrets in the current files, most severe first. Values are masked: a token
    shows its first 4 characters, a password none. A committed .env file is a finding too."""
    findings = []
    seen: set[tuple[str, int]] = set()  # one finding per line
    for path in repo.files:
        if path.endswith(SKIP_SECRET_FILES):
            continue
        text = repo.read(path)
        if text:
            findings += _secrets_in_file(repo, path, text, seen)
    for env in env_files(repo):
        if not env["template"] and env["committed"]:
            findings.append(
                {
                    "type": "committed_env",
                    "severity": "high",
                    "file": env["file"],
                    "line": 1,
                    "preview": f"{len(env['keys'])} key",
                    "committed": True,
                    "note": None,
                }
            )
    return sorted(
        findings, key=lambda f: (SEVERITY_ORDER[f["severity"]], f["type"], f["file"], f["line"])
    )


def _secrets_in_file(repo: Repo, path: str, text: str, seen: set) -> list[dict]:
    """Findings in one file; `seen` keeps one finding per line across patterns."""
    findings = []
    for label, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(1)
            line = line_of(text, match.start())
            if (path, line) in seen:
                continue  # already reported by a more specific pattern
            if label == "Hardcoded password" and (value.lower() in PLACEHOLDERS or "env(" in value):
                continue
            seen.add((path, line))
            severity, note = _severity(label, path)
            masked = "••••" if label == "Hardcoded password" else value[:4] + "…"
            findings.append(
                {
                    "type": label,
                    "severity": severity,
                    "file": path,
                    "line": line,
                    "preview": masked + t(f" ({len(value)} chars)", f" ({len(value)} karakter)"),
                    "committed": path in repo.tracked_files if repo.is_git else None,
                    "note": note,
                }
            )
    return findings


def _severity(label: str, path: str) -> tuple[str, str | None]:
    """(severity, note). Firebase client keys and findings in test files are "low"."""
    if label in HIGH_SEVERITY:
        return "high", None
    if label == "Google API key" and path.rsplit("/", 1)[-1] in FIREBASE_CLIENT_CONFIG:
        return "low", t(
            "Firebase client config; make sure the key is restricted "
            "(API restrictions / App Check)",
            "config Firebase klien; pastikan key dibatasi (API restriction / App Check)",
        )
    if TEST_PATH.search(path):
        return "low", t("in a test file", "di file test")
    return "medium", None


def extract(repo: Repo) -> dict:
    return {
        "env_files": env_files(repo),
        "spring_config": spring_profiles(repo),
        "secrets": secrets(repo),
    }
