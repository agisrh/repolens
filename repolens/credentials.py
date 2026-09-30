"""The user's own Anthropic API key and preferred model, set with `repolens auth login`.

Where the key comes from (first match wins):
  1. ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN in the environment (CI, servers)
  2. the key saved by `repolens auth login`: the OS keychain (macOS Keychain, Windows
     Credential Manager, Linux Secret Service), or a 0600 file when no keychain is available
  3. whatever else the Anthropic SDK resolves on its own, such as an `ant auth login` profile

The key is never written to .repolens.yml (that file is committed), never taken as a
command-line flag (shell history, `ps`), and only ever shown masked.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

SERVICE = "repolens"
ACCOUNT = "anthropic-api-key"
ENV_KEYS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


def config_dir() -> Path:
    """REPOLENS_CONFIG_DIR, else %APPDATA%\\repolens on Windows, else $XDG_CONFIG_HOME/repolens or ~/.config/repolens."""
    if os.environ.get("REPOLENS_CONFIG_DIR"):
        return Path(os.environ["REPOLENS_CONFIG_DIR"]).expanduser()
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "repolens"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "repolens"


def _credentials_file() -> Path:
    return config_dir() / "credentials.json"


def _settings_file() -> Path:
    return config_dir() / "settings.json"


def _keyring():
    """The keyring module when a real OS keychain backs it; None otherwise (or when REPOLENS_NO_KEYRING is set)."""
    if os.environ.get("REPOLENS_NO_KEYRING"):
        return None
    try:
        import keyring
        from keyring.backends import fail
    except ImportError:
        return None
    try:
        backend = keyring.get_keyring()
    except Exception:
        return None
    if (
        isinstance(backend, fail.Keyring)
        or "null" in type(backend).__module__
        or backend.priority < 1
    ):
        return None
    return keyring


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_private(path: Path, data: dict) -> None:
    """Write JSON readable only by the current user (created 0600, never world-readable in between)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


# ---- API key ----------------------------------------------------------------


def stored_key() -> tuple[str | None, str | None]:
    """(key, "keychain" | "file") saved by `repolens auth login`, or (None, None)."""
    kr = _keyring()
    if kr:
        try:
            key = kr.get_password(SERVICE, ACCOUNT)
        except Exception:
            key = None
        if key:
            return key, "keychain"
    key = _read_json(_credentials_file()).get("anthropic_api_key")
    return (key, "file") if isinstance(key, str) and key else (None, None)


def save_key(key: str) -> str:
    """Save the key; returns where it went: "keychain" or "file"."""
    kr = _keyring()
    if kr:
        try:
            kr.set_password(SERVICE, ACCOUNT, key)
        except Exception:
            pass
        else:
            _credentials_file().unlink(
                missing_ok=True
            )  # do not leave an older plain-text copy behind
            return "keychain"
    _write_private(_credentials_file(), {"anthropic_api_key": key})
    return "file"


def delete_key() -> list[str]:
    """Remove every saved copy; returns where keys were removed from."""
    removed = []
    kr = _keyring()
    if kr:
        try:
            if kr.get_password(SERVICE, ACCOUNT):
                kr.delete_password(SERVICE, ACCOUNT)
                removed.append("keychain")
        except Exception:
            pass
    if _credentials_file().is_file():
        _credentials_file().unlink()
        removed.append("file")
    return removed


def env_source() -> str | None:
    return next((name for name in ENV_KEYS if os.environ.get(name)), None)


def resolve() -> tuple[str | None, str]:
    """(api_key to pass to the SDK, where it comes from).

    The key is None when the SDK should resolve credentials itself: an environment variable
    (which must keep winning, as it does everywhere else) or an `ant auth login` profile."""
    env = env_source()
    if env:
        return None, env
    key, where = stored_key()
    if key:
        return key, where
    return None, "sdk"


def anthropic_client(api_key: str | None = None):
    """Anthropic client using `api_key`, else the key resolved above."""
    import anthropic

    key = api_key or resolve()[0]
    return anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()


def has_profile() -> bool:
    """Best guess that an `ant auth login` profile exists (the SDK reads it without any env var)."""
    return (
        bool(os.environ.get("ANTHROPIC_PROFILE"))
        or (Path.home() / ".config" / "anthropic").is_dir()
    )


def available() -> bool:
    """True when an AI request has credentials to try with."""
    return bool(env_source() or stored_key()[0] or has_profile())


def mask(key: str) -> str:
    if len(key) <= 12:
        return "…" + key[-2:]
    prefix = "sk-ant-" if key.startswith("sk-ant-") else key[:3]
    return f"{prefix}…{key[-4:]}"


# ---- settings -----------------------------------------------------------------


def load_settings() -> dict:
    return _read_json(_settings_file())


def save_settings(**values) -> None:
    data = load_settings()
    for name, value in values.items():
        if value is None:
            data.pop(name, None)
        else:
            data[name] = value
    _write_private(_settings_file(), data)


def default_model(fallback: str) -> str:
    """REPOLENS_MODEL, else the model chosen in `repolens auth login`, else `fallback`."""
    return os.environ.get("REPOLENS_MODEL") or load_settings().get("model") or fallback
