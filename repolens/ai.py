"""Optional AI narrative: summary, architecture, folder and module descriptions.

Only extracted facts are sent (names, versions, paths, column names, README
excerpt) - never full source files, and never env values or secret previews.
"""

from __future__ import annotations

import json

import anthropic

from repolens import credentials
from repolens.i18n import LANGUAGES, get_lang, t

DEFAULT_MODEL = "claude-opus-5-5"
# Offered by `repolens auth login`; any other model id still works through --model.
MODELS = {
    "claude-opus-5-5": ("most thorough (default)", "paling teliti (default)"),
    "claude-sonnet-5-5": (
        "faster and about half the cost",
        "lebih cepat, biaya sekitar setengahnya",
    ),
}

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "2-3 paragraphs: what the project is, who uses it, main capabilities.",
        },
        "architecture": {
            "type": "string",
            "description": "1-2 paragraphs on architecture, layering, and how the parts interact.",
        },
        "folder_descriptions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "description": {"type": "string"}},
                "required": ["path", "description"],
                "additionalProperties": False,
            },
        },
        "modules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "description": {"type": "string"}},
                "required": ["name", "description"],
                "additionalProperties": False,
            },
        },
        "setup_steps": {"type": "array", "items": {"type": "string"}},
        "observations": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "summary",
        "architecture",
        "folder_descriptions",
        "modules",
        "setup_steps",
        "observations",
    ],
    "additionalProperties": False,
}

# The instructions for the model. {language} is filled in per request.
SYSTEM = (
    "You are a senior technical writer documenting a software repository for developers "
    "and product owners.\n"
    "You receive facts that a static scanner extracted from the repository. Write the "
    "requested JSON in {language}.\n"
    "\n"
    "Rules:\n"
    "- Use only the provided facts. Never invent endpoints, versions, tables, env keys, "
    "or features.\n"
    "- When a fact is missing or ambiguous, say plainly that it cannot be determined from"
    " the repository.\n"
    '- folder_descriptions: describe each path listed under "directories" that matters to'
    " a reader (skip generated or platform boilerplate folders unless notable). Keep each"
    " description to one sentence.\n"
    "- modules: the functional modules/features of the application, inferred from folder "
    "names, routes, and endpoints.\n"
    "- setup_steps: concrete steps to run the project locally, based on the detected "
    "stack, manifests, scripts, and env files.\n"
    "- observations: risks or notable points supported by the facts (outdated or "
    "mismatched versions, committed env files, secrets, missing lock files, missing "
    "tests, etc.). Each item is one sentence."
)


def _compact(facts: dict) -> dict:
    """The facts sent to the model: trimmed lists, no file contents, no env values or secrets."""
    eps = facts["endpoints"]
    manifests = [
        {
            "manifest": m["manifest"],
            "ecosystem": m["ecosystem"],
            "runtime": m.get("runtime"),
            "scripts": list((m.get("scripts") or {}).keys())[:20],
            "dependencies": [_dependency_line(d) for d in m["dependencies"][:80]],
        }
        for m in facts["dependencies"]
    ]
    return {
        "project": facts["project"],
        "git": {
            k: facts["git"].get(k)
            for k in (
                "commit_short",
                "commit_date",
                "branch",
                "tags_at_head",
                "describe",
                "commit_count",
            )
        },
        "frameworks": facts["frameworks"],
        "languages": facts["languages"][:8],
        "manifests": manifests,
        "directories": facts["tree"]["directories"][:120],
        "tree": facts["tree"]["text"][:6000],
        "endpoints": {
            "server_count": len(eps["server"]),
            "client_count": len(eps["client"]),
            "page_count": len(eps["pages"]),
            "server": _endpoint_lines(eps["server"], 80),
            "client": _endpoint_lines(eps["client"], 80),
            "pages": _endpoint_lines(eps["pages"], 40),
            "notes": eps["notes"],
        },
        "database": {
            "engines": facts["database"]["engines"],
            "tables": [
                {
                    "name": tbl["name"],
                    "source": tbl["source"],
                    "columns": [c["name"] for c in tbl["columns"]][:30],
                }
                for tbl in facts["database"]["tables"][:60]
            ],
        },
        "env_keys": [
            {"file": e["file"], "keys": e["keys"], "committed": e["committed"]}
            for e in facts["config"]["env_files"]
        ],
        "platforms": facts["platforms"],
        "infrastructure": facts["infrastructure"],
        "security_findings": [
            {"type": s["type"], "file": s["file"], "severity": s.get("severity")}
            for s in facts["security"]["secrets"][:30]
        ],
        "readme_excerpt": facts["readme_excerpt"][:4000],
    }


def _dependency_line(dependency: dict) -> str:
    """ "dio 5.4.0 (runtime)": the installed version when known, else the declared one."""
    d = dependency
    version = d.get("resolved") or d.get("declared") or d.get("source") or ""
    return f"{d['name']} {version} ({d['scope']})"


def _endpoint_lines(items: list[dict], limit: int) -> list[str]:
    """ "GET /users -> UserController@index [api.php]" for the first `limit` endpoints."""
    return [
        f"{e['method']} {e['path']} -> {e.get('handler') or ''} [{e.get('group') or ''}]"
        for e in items[:limit]
    ]


def _quiet(message: str, kind: str = "step") -> None:
    pass


class _Skipped(Exception):
    """The AI part cannot be produced; the message says why (shown as a warning)."""


def generate(
    facts: dict, language: str | None = None, model: str = DEFAULT_MODEL, log=_quiet
) -> dict | None:
    """The AI narrative for these facts, or None when it cannot be produced.

    The reason for a None is sent to `log(message, "warn")`, so the scan can go on without it."""
    try:
        response = _request(_client(), facts, model, language or LANGUAGES[get_lang()])
        return _parse(response)
    except _Skipped as reason:
        log(t("AI skipped: ", "AI dilewati: ") + str(reason), "warn")
        return None


def _no_key() -> _Skipped:
    return _Skipped(
        t(
            "no Anthropic API key. Run `repolens auth login`, or set ANTHROPIC_API_KEY.",
            "belum ada API key Anthropic. Jalankan `repolens auth login`, atau set "
            "ANTHROPIC_API_KEY.",
        )
    )


def _client():
    try:
        return credentials.anthropic_client()
    except Exception:  # missing credentials surface here in some SDK versions
        raise _no_key() from None


def _request(client, facts: dict, model: str, language: str):
    """Ask the model for the narrative as JSON that follows SCHEMA."""
    payload = json.dumps(_compact(facts), ensure_ascii=False, indent=1)
    try:
        # Streaming: thinking tokens count toward max_tokens, and a large repo needs a large
        # JSON answer. A non-streaming request that big would risk the SDK's HTTP timeout.
        with client.beta.messages.stream(
            model=model,
            max_tokens=64000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM.format(language=language),
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": f"Repository facts:\n```json\n{payload}\n```"}],
        ) as stream:
            return stream.get_final_message()
    except anthropic.AuthenticationError:
        reason = t(
            "the Anthropic API key is invalid. Check it with `repolens auth status`.",
            "API key Anthropic tidak valid. Cek dengan `repolens auth status`.",
        )
    except anthropic.RateLimitError:
        reason = t(
            "rate limited. Try again in a moment, or run with --no-ai.",
            "kena rate limit. Coba lagi beberapa saat, atau jalankan dengan --no-ai.",
        )
    except anthropic.APIStatusError as exc:
        reason = f"API error {exc.status_code}: {exc.message}"
    except anthropic.APIConnectionError:
        reason = t("cannot connect to the Anthropic API.", "tidak bisa terhubung ke Anthropic API.")
    except anthropic.APIError as exc:
        reason = str(exc)
    except TypeError:  # raised by the SDK when no credential source can be resolved
        raise _no_key() from None
    raise _Skipped(reason)


def _parse(response) -> dict:
    """The JSON answer, with the model and token usage added."""
    if response.stop_reason == "refusal":
        raise _Skipped(t("the model declined the request.", "permintaan ditolak oleh model."))
    if response.stop_reason == "max_tokens":
        raise _Skipped(t("the answer was cut off (max_tokens).", "jawaban terpotong (max_tokens)."))
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        raise _Skipped(
            t("the answer is not valid JSON.", "jawaban bukan JSON yang valid.")
        ) from None
    result["model"] = response.model
    result["usage"] = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    return result


def check(model: str, api_key: str | None = None) -> tuple[str, str]:
    """Check that the key works and can use `model`, without spending tokens (Models API).

    Returns (status, message) with status "ok", "invalid" (key rejected), "model" (model
    not available to this key), or "unknown" (could not reach the API; the key may be fine)."""
    try:
        client = credentials.anthropic_client(api_key)
        info = client.models.retrieve(model)
    except anthropic.AuthenticationError:
        return "invalid", t(
            "The API key was rejected by Anthropic.", "API key ditolak oleh Anthropic."
        )
    except anthropic.PermissionDeniedError:
        return "invalid", t(
            "This API key is not allowed to use the API.",
            "API key ini tidak diizinkan memakai API.",
        )
    except anthropic.NotFoundError:
        return "model", t(
            f"Model `{model}` is not available for this key.",
            f"Model `{model}` tidak tersedia untuk key ini.",
        )
    except anthropic.APIConnectionError:
        return "unknown", t(
            "Cannot reach the Anthropic API, so the key was not checked.",
            "Tidak bisa terhubung ke Anthropic API, jadi key belum dicek.",
        )
    except anthropic.APIStatusError as exc:
        return "unknown", f"API error {exc.status_code}: {exc.message}"
    except TypeError:  # no credential source at all
        return "invalid", t("No API key found.", "API key tidak ditemukan.")
    return "ok", getattr(info, "display_name", None) or model
