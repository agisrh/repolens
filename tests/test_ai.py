"""The AI narrative: request, answer parsing, and every way it can be skipped.

The Anthropic client is replaced by a fake, so no request leaves the machine.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from repolens import ai, credentials
from repolens.scanner import prepared_source, scan

FIXTURES = Path(__file__).parent / "fixtures"

ANSWER = {
    "summary": "A demo.",
    "architecture": "Layers.",
    "folder_descriptions": [],
    "modules": [],
    "setup_steps": [],
    "observations": [],
}
REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def response(text=None, stop_reason="end_turn"):
    """A model response whose text is `text` (the valid ANSWER by default)."""
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=json.dumps(ANSWER) if text is None else text)],
        model="claude-test",
        usage=SimpleNamespace(input_tokens=10, output_tokens=20),
    )


class FakeClient:
    """Answers with `result`, or raises it when it is an exception. Records the request."""

    def __init__(self, result):
        self.result, self.request = result, None
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **request):
        self.request = request
        client = self

        class Stream:
            def __enter__(self):
                if isinstance(client.result, Exception):
                    raise client.result
                return SimpleNamespace(get_final_message=lambda: client.result)

            def __exit__(self, *exc):
                return False

        return Stream()


@pytest.fixture
def facts():
    with prepared_source(str(FIXTURES / "laravel_groups"), None) as (root, info):
        return scan(root, info, use_git=False)


def run(monkeypatch, facts, result):
    client = FakeClient(result)
    monkeypatch.setattr(credentials, "anthropic_client", lambda api_key=None: client)
    warnings = []
    output = ai.generate(
        facts, model="claude-test", log=lambda msg, kind="step": warnings.append(msg)
    )
    return output, warnings, client


def test_answer_is_parsed_with_model_and_usage(monkeypatch, facts):
    output, warnings, client = run(monkeypatch, facts, response())
    assert warnings == []
    assert output["summary"] == "A demo." and output["model"] == "claude-test"
    assert output["usage"] == {"input_tokens": 10, "output_tokens": 20}
    assert client.request["model"] == "claude-test"
    assert client.request["output_config"]["format"]["schema"] == ai.SCHEMA
    assert "English" in client.request["system"]


def status_error(cls, code):
    return cls("error", response=httpx2.Response(code, request=REQUEST), body=None)


@pytest.mark.parametrize(
    "result, reason",
    [
        (response(stop_reason="refusal"), "declined"),
        (response(stop_reason="max_tokens"), "cut off"),
        (response(text="not json"), "not valid JSON"),
        (status_error(anthropic.AuthenticationError, 401), "invalid"),
        (status_error(anthropic.RateLimitError, 429), "rate limited"),
        (status_error(anthropic.InternalServerError, 500), "API error 500"),
        (anthropic.APIConnectionError(request=REQUEST), "cannot connect"),
        (TypeError("no credentials"), "no Anthropic API key"),
    ],
)
def test_problems_skip_the_ai_part_with_a_reason(monkeypatch, facts, result, reason):
    output, warnings, _ = run(monkeypatch, facts, result)
    assert output is None
    assert len(warnings) == 1 and warnings[0].startswith("AI skipped: ") and reason in warnings[0]


def test_missing_client_credentials(monkeypatch, facts):
    def no_client(api_key=None):
        raise anthropic.AnthropicError("no key")

    monkeypatch.setattr(credentials, "anthropic_client", no_client)
    warnings = []
    assert ai.generate(facts, log=lambda msg, kind="step": warnings.append(msg)) is None
    assert "no Anthropic API key" in warnings[0]


def test_payload_holds_facts_but_no_env_values_or_secrets(tmp_path):
    project = tmp_path / "p"
    project.mkdir()
    (project / ".env").write_text("DB_PASSWORD=supersecret123\n")
    (project / "config.py").write_text('password = "hunter2hunter2"\n')
    with prepared_source(str(project), None) as (root, info):
        facts = scan(root, info, use_git=False)
    payload = json.dumps(ai._compact(facts))
    assert "supersecret123" not in payload and "hunter2hunter2" not in payload
