import pytest

from repolens.i18n import set_lang


@pytest.fixture(autouse=True)
def english_output():
    """The output language is module state: start every test from the default."""
    set_lang("en")
    yield
    set_lang("en")
