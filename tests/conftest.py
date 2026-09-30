import pytest

from repolens import credentials
from repolens.i18n import set_lang


@pytest.fixture(autouse=True)
def english_output():
    """The output language is module state: start every test from the default."""
    set_lang("en")
    yield
    set_lang("en")


@pytest.fixture(autouse=True)
def isolated_credentials(tmp_path, monkeypatch):
    """Never read or write the developer's real keychain, config folder, or API key."""
    monkeypatch.setenv("REPOLENS_CONFIG_DIR", str(tmp_path / "repolens-config"))
    monkeypatch.setenv("REPOLENS_NO_KEYRING", "1")
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE", "REPOLENS_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(credentials, "has_profile", lambda: False)
