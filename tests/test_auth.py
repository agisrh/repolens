"""`repolens auth` and where the API key and model come from. The Anthropic API is never called."""

from __future__ import annotations

import io
import json
import os
import stat

import pytest

from repolens import ai, credentials
from repolens.cli import main

KEY = "sk-ant-api03-abcdefghijklmnop-WXYZ"


@pytest.fixture
def api(monkeypatch):
    """Stand-in for ai.check: records calls and answers with `api.result`."""
    class Api:
        result = ("ok", "Claude Opus 5.5")
        calls: list = []
    def check(model, api_key=None):
        Api.calls.append((model, api_key))
        return Api.result
    monkeypatch.setattr(ai, "check", check)
    return Api


def login(monkeypatch, *args, key=KEY):
    monkeypatch.setattr("sys.stdin", io.StringIO(key + "\n"))
    return main(["auth", "login", *args])


class FakeKeyring:
    def __init__(self):
        self.store = {}
    def get_password(self, service, account):
        return self.store.get((service, account))
    def set_password(self, service, account, value):
        self.store[(service, account)] = value
    def delete_password(self, service, account):
        del self.store[(service, account)]


def test_login_checks_then_saves_to_a_private_file(monkeypatch, api):
    assert login(monkeypatch, "--model", "claude-sonnet-5-5") == 0
    assert api.calls[-1] == ("claude-sonnet-5-5", KEY)
    assert credentials.stored_key() == (KEY, "file")
    path = credentials.config_dir() / "credentials.json"
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert credentials.default_model(ai.DEFAULT_MODEL) == "claude-sonnet-5-5"


def test_login_prefers_the_os_keychain(monkeypatch, api):
    fake = FakeKeyring()
    monkeypatch.setattr(credentials, "_keyring", lambda: fake)
    assert login(monkeypatch) == 0
    assert credentials.stored_key() == (KEY, "keychain")
    assert not (credentials.config_dir() / "credentials.json").exists()
    assert credentials.delete_key() == ["keychain"] and credentials.stored_key() == (None, None)


@pytest.mark.parametrize("status", ["invalid", "model"])
def test_login_saves_nothing_when_the_check_fails(monkeypatch, api, capsys, status):
    api.result = (status, "rejected")
    assert login(monkeypatch) == 1
    assert credentials.stored_key() == (None, None)
    assert "Nothing was saved" in capsys.readouterr().err


def test_login_offline_still_saves_with_a_warning(monkeypatch, api, capsys):
    api.result = ("unknown", "Cannot reach the Anthropic API")
    assert login(monkeypatch) == 0
    assert credentials.stored_key()[0] == KEY
    assert "Saved anyway" in capsys.readouterr().out


def test_login_no_verify_and_empty_key(monkeypatch, api):
    api.calls = []
    assert login(monkeypatch, "--no-verify") == 0
    assert api.calls == [] and credentials.stored_key()[0] == KEY
    assert login(monkeypatch, key="") == 1


def test_environment_variable_wins_over_the_saved_key(monkeypatch, api):
    login(monkeypatch)
    assert credentials.resolve() == (KEY, "file")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-env-0000")
    assert credentials.resolve() == (None, "ANTHROPIC_API_KEY")  # the SDK reads the env var itself


def test_model_precedence(monkeypatch):
    assert credentials.default_model(ai.DEFAULT_MODEL) == ai.DEFAULT_MODEL
    credentials.save_settings(model="claude-sonnet-5-5")
    assert credentials.default_model(ai.DEFAULT_MODEL) == "claude-sonnet-5-5"
    monkeypatch.setenv("REPOLENS_MODEL", "claude-opus-5")
    assert credentials.default_model(ai.DEFAULT_MODEL) == "claude-opus-5"


def test_status_and_logout(monkeypatch, api, capsys):
    assert main(["auth", "status"]) == 1
    assert "No Anthropic API key" in capsys.readouterr().out
    login(monkeypatch)
    capsys.readouterr()
    assert main(["auth", "status", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == {"configured": True, "source": "file", "key": "sk-ant-…WXYZ", "model": ai.DEFAULT_MODEL,
                      "model_source": "default", "check": "ok"}
    assert KEY not in json.dumps(result)
    api.result = ("invalid", "rejected")
    assert main(["auth", "status"]) == 1
    assert main(["auth", "logout"]) == 0
    assert credentials.stored_key() == (None, None)


def test_mask_never_shows_the_whole_key():
    assert credentials.mask(KEY) == "sk-ant-…WXYZ"
    assert credentials.mask("short") == "…rt"
