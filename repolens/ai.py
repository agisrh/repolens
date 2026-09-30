"""Optional AI narrative: summary, architecture, folder and module descriptions.

Only extracted facts are sent (names, versions, paths, column names, README
excerpt) - never full source files, and never env values or secret previews.
"""

from __future__ import annotations

import json

import anthropic

from repolens.i18n import LANGUAGES, get_lang, t

DEFAULT_MODEL = "claude-opus-5"

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "2-3 paragraphs: what the project is, who uses it, main capabilities."},
        "architecture": {"type": "string", "description": "1-2 paragraphs on architecture, layering, and how the parts interact."},
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
    "required": ["summary", "architecture", "folder_descriptions", "modules", "setup_steps", "observations"],
    "additionalProperties": False,
}

SYSTEM = """You are a senior technical writer documenting a software repository for developers and product owners.
You receive facts that a static scanner extracted from the repository. Write the requested JSON in {language}.

Rules:
- Use only the provided facts. Never invent endpoints, versions, tables, env keys, or features.
- When a fact is missing or ambiguous, say plainly that it cannot be determined from the repository.
- folder_descriptions: describe each path listed under "directories" that matters to a reader (skip generated or platform boilerplate folders unless notable). Keep each description to one sentence.
- modules: the functional modules/features of the application, inferred from folder names, routes, and endpoints.
- setup_steps: concrete steps to run the project locally, based on the detected stack, manifests, scripts, and env files.
- observations: risks or notable points supported by the facts (outdated or mismatched versions, committed env files, secrets, missing lock files, missing tests, etc.). Each item is one sentence."""


def _compact(facts: dict) -> dict:
    eps = facts["endpoints"]

    def ep_list(items, limit):
        return [f"{e['method']} {e['path']} -> {e.get('handler') or ''} [{e.get('group') or ''}]" for e in items[:limit]]

    manifests = []
    for m in facts["dependencies"]:
        manifests.append({
            "manifest": m["manifest"], "ecosystem": m["ecosystem"], "runtime": m.get("runtime"),
            "scripts": list((m.get("scripts") or {}).keys())[:20],
            "dependencies": [f"{d['name']} {d.get('resolved') or d.get('declared') or d.get('source') or ''} ({d['scope']})"
                             for d in m["dependencies"][:80]],
        })
    return {
        "project": facts["project"],
        "git": {k: facts["git"].get(k) for k in ("commit_short", "commit_date", "branch", "tags_at_head", "describe", "commit_count")},
        "frameworks": facts["frameworks"],
        "languages": facts["languages"][:8],
        "manifests": manifests,
        "directories": facts["tree"]["directories"][:120],
        "tree": facts["tree"]["text"][:6000],
        "endpoints": {
            "server_count": len(eps["server"]), "client_count": len(eps["client"]), "page_count": len(eps["pages"]),
            "server": ep_list(eps["server"], 80), "client": ep_list(eps["client"], 80), "pages": ep_list(eps["pages"], 40),
            "notes": eps["notes"],
        },
        "database": {
            "engines": facts["database"]["engines"],
            "tables": [{"name": tbl["name"], "source": tbl["source"], "columns": [c["name"] for c in tbl["columns"]][:30]}
                       for tbl in facts["database"]["tables"][:60]],
        },
        "env_keys": [{"file": e["file"], "keys": e["keys"], "committed": e["committed"]} for e in facts["config"]["env_files"]],
        "platforms": facts["platforms"],
        "infrastructure": facts["infrastructure"],
        "security_findings": [{"type": s["type"], "file": s["file"], "severity": s.get("severity")} for s in facts["security"]["secrets"][:30]],
        "readme_excerpt": facts["readme_excerpt"][:4000],
    }


def _quiet(message: str, kind: str = "step") -> None:
    pass


def generate(facts: dict, language: str | None = None, model: str = DEFAULT_MODEL, log=_quiet) -> dict | None:
    """Return the AI narrative, or None (with the reason sent to `log(message, "warn")`) when it cannot be produced."""
    language = language or LANGUAGES[get_lang()]
    skipped = t("AI skipped: ", "AI dilewati: ")
    no_creds = skipped + t("Anthropic credentials are not set. Set ANTHROPIC_API_KEY or run `ant auth login`.",
                           "kredensial Anthropic belum diatur. Set ANTHROPIC_API_KEY atau jalankan `ant auth login`.")
    try:
        client = anthropic.Anthropic()
    except Exception:  # missing credentials surface here in some SDK versions
        log(no_creds, "warn")
        return None
    payload = json.dumps(_compact(facts), ensure_ascii=False, indent=1)
    try:
        # Streaming: thinking tokens count toward max_tokens, and a large repo needs a large JSON answer.
        # A non-streaming request that big would risk the SDK's HTTP timeout.
        with client.beta.messages.stream(
            model=model,
            max_tokens=64000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM.format(language=language),
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": f"Repository facts:\n```json\n{payload}\n```"}],
        ) as stream:
            response = stream.get_final_message()
    except anthropic.AuthenticationError:
        log(skipped + t("Anthropic credentials are invalid or not set (ANTHROPIC_API_KEY / `ant auth login`).",
                        "kredensial Anthropic tidak valid atau belum diatur (ANTHROPIC_API_KEY / `ant auth login`)."), "warn")
        return None
    except anthropic.RateLimitError:
        log(skipped + t("rate limited. Try again in a moment, or run with --no-ai.",
                        "kena rate limit. Coba lagi beberapa saat, atau jalankan dengan --no-ai."), "warn")
        return None
    except anthropic.APIStatusError as exc:
        log(skipped + f"API error {exc.status_code}: {exc.message}", "warn")
        return None
    except anthropic.APIConnectionError:
        log(skipped + t("cannot connect to the Anthropic API.", "tidak bisa terhubung ke Anthropic API."), "warn")
        return None
    except anthropic.APIError as exc:
        log(skipped + str(exc), "warn")
        return None
    except TypeError:
        # Raised by the SDK when no credential source can be resolved.
        log(no_creds, "warn")
        return None

    if response.stop_reason == "refusal":
        log(skipped + t("the model declined the request.", "permintaan ditolak oleh model."), "warn")
        return None
    if response.stop_reason == "max_tokens":
        log(skipped + t("the answer was cut off (max_tokens).", "jawaban terpotong (max_tokens)."), "warn")
        return None
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        log(skipped + t("the answer is not valid JSON.", "jawaban bukan JSON yang valid."), "warn")
        return None
    result["model"] = response.model
    result["usage"] = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
    return result
