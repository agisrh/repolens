"""`repolens auth login | status | logout`: each user sets their own Anthropic API key and model.

Where keys are stored and in which order they are used is decided in repolens/credentials.py;
this module is the conversation with the user around it:
  login   ask for the key (or read it from stdin), check it with Anthropic, then save it
  status  show which key and model a scan would use, and check that they work
  logout  remove the saved key
"""

from __future__ import annotations

import json
import os
import sys

from repolens import ai, credentials, ui
from repolens.commands._common import add_command, flag, option
from repolens.i18n import t

NAME = "auth"


def register(subparsers, common):
    p = add_command(
        subparsers,
        NAME,
        common,
        "Set your own Anthropic API key and model for the AI summary",
        "Atur API key Anthropic dan model Anda sendiri untuk ringkasan AI",
    )
    actions = p.add_subparsers(dest="action")
    login_parser = add_command(
        actions,
        "login",
        common,
        "Save an API key (asked for, or read from stdin), after checking it",
        "Simpan API key (ditanyakan, atau dibaca dari stdin) setelah dicek",
    )
    models = ", ".join(ai.MODELS)
    option(
        login_parser,
        "--model",
        f"Default model for scans (e.g. {models})",
        f"Model default untuk scan (mis. {models})",
    )
    flag(
        login_parser,
        "--no-verify",
        "Save without checking the key with Anthropic",
        "Simpan tanpa mengecek key ke Anthropic",
    )
    status_parser = add_command(
        actions,
        "status",
        common,
        "Show which key and model are used, and check them",
        "Tampilkan key dan model yang dipakai, lalu cek",
    )
    flag(status_parser, "--offline", "Do not contact Anthropic", "Tanpa menghubungi Anthropic")
    flag(status_parser, "--json", "Print a JSON result", "Cetak hasil JSON")
    add_command(actions, "logout", common, "Remove the saved key", "Hapus key yang disimpan")
    # `repolens auth` on its own means `repolens auth status`.
    p.set_defaults(action="status", offline=False, json=False)
    return p


def run(args) -> int:
    if args.action == "login":
        return login(model=args.model, verify=not args.no_verify)
    if args.action == "logout":
        return logout()
    return status(as_json=args.json, verify=not args.offline)


# ---- login --------------------------------------------------------------------------------


def login(model: str | None = None, verify: bool = True) -> int:
    """Ask for (or read) a key, check it, and save it with the chosen model.

    Also used by the menu when AI is chosen without a key."""
    interactive = sys.stdin.isatty()
    ui.header("Auth", t("Save your Anthropic API key", "Simpan API key Anthropic Anda"))
    env = credentials.env_source()
    if env:
        ui.warn(
            t(
                f"{env} is set in this environment and is used before the saved key.",
                f"{env} ter-set di environment ini dan dipakai lebih dulu daripada key "
                "yang disimpan.",
            )
        )
    key = _read_key(interactive)
    if not key:
        ui.error(t("No key given.", "Key tidak diisi."))
        return 1
    if model is None and interactive:
        model = _pick_model()
    model_in_use = model or credentials.default_model(ai.DEFAULT_MODEL)
    if verify and not _verify(key, model_in_use):
        return 1

    where = credentials.save_key(key)
    if model:
        credentials.save_settings(model=model)
    if where == "file":
        ui.warn(
            t(
                "No OS keychain available: the key is stored in a file readable only by you.",
                "Keychain OS tidak tersedia: key disimpan di file yang hanya bisa dibaca "
                "oleh Anda.",
            )
        )
    ui.summary(
        t("API key saved", "API key tersimpan"),
        [
            ("Key", credentials.mask(key)),
            (t("Stored in", "Disimpan di"), _where(where)),
            ("Model", model_in_use),
        ],
    )
    return 0


def _read_key(interactive: bool) -> str:
    """Hidden prompt in a terminal; otherwise one line from stdin.

    Reading stdin allows `pass show anthropic | repolens auth login`, so the key never
    appears in shell history."""
    if not interactive:
        return sys.stdin.readline().strip()
    import questionary

    from repolens import menu

    prompt = questionary.password(
        t("Anthropic API key (sk-ant-…)", "API key Anthropic (sk-ant-…)"),
        style=menu.STYLE,
        validate=lambda value: bool(value.strip()) or t("Required", "Wajib diisi"),
    )
    return menu.ask(prompt).strip()


def _pick_model() -> str:
    """Choose the default model for scans; the current one is preselected."""
    from questionary import Choice

    from repolens import menu

    current = credentials.default_model(ai.DEFAULT_MODEL)
    choices = [Choice(f"{model}  ({t(*desc)})", model) for model, desc in ai.MODELS.items()]
    if current not in ai.MODELS:
        choices.append(Choice(f"{current}  ({t('current', 'saat ini')})", current))
    question = t("Model for the AI summary", "Model untuk ringkasan AI")
    return menu.select(question, choices, default=current)


def _verify(key: str, model: str) -> bool:
    """Check the key with Anthropic. False (and nothing saved) when it is rejected.

    When Anthropic cannot be reached the key may still be fine, so it is saved with a warning."""
    with ui.out.status(t("Checking the key with Anthropic…", "Mengecek key ke Anthropic…")):
        result, message = ai.check(model, api_key=key)
    if result == "invalid":
        ui.error(message + t(" Nothing was saved.", " Tidak ada yang disimpan."))
        return False
    if result == "model":
        ui.error(
            message
            + t(
                " Nothing was saved. Pick another model with --model.",
                " Tidak ada yang disimpan. Pilih model lain dengan --model.",
            )
        )
        return False
    if result == "unknown":
        ui.warn(
            message
            + t(
                " Saved anyway; check later with `repolens auth status`.",
                " Tetap disimpan; cek nanti dengan `repolens auth status`.",
            )
        )
    else:
        ui.ok(t(f"Key works with {message}", f"Key berfungsi dengan {message}"))
    return True


# ---- status and logout --------------------------------------------------------------------

STATUS_TEXT = {
    "ok": ("✓ valid", "✓ valid"),
    "invalid": ("✗ rejected", "✗ ditolak"),
    "model": ("✗ model not available", "✗ model tidak tersedia"),
    "unknown": ("? not checked (offline)", "? belum dicek (offline)"),
    None: ("not checked", "tidak dicek"),
}


def status(as_json: bool = False, verify: bool = True) -> int:
    """Which key and model a scan would use. Exit code 1 when there is none or it is rejected."""
    key, source = credentials.resolve()
    if source in credentials.ENV_KEYS:
        key = os.environ[source]
    found = bool(key) or (source == "sdk" and credentials.has_profile())
    model = credentials.default_model(ai.DEFAULT_MODEL)
    check, message = ai.check(model) if found and verify else (None, None)
    exit_code = 1 if not found or check in ("invalid", "model") else 0
    if as_json:
        result = {
            "configured": found,
            "source": source if found else None,
            "key": credentials.mask(key) if key else None,
            "model": model,
            "model_source": _model_source(),
            "check": check,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return exit_code

    ui.header("Auth", t("AI credentials", "Kredensial AI"))
    if not found:
        ui.warn(t("No Anthropic API key.", "Belum ada API key Anthropic."), indent="")
        ui.hint(
            t(
                "Run `repolens auth login`, or set ANTHROPIC_API_KEY.",
                "Jalankan `repolens auth login`, atau set ANTHROPIC_API_KEY.",
            ),
            indent="  ",
        )
        return exit_code
    rows = [
        ("Key", credentials.mask(key) if key else "-"),
        (t("Source", "Sumber"), _where(source)),
        ("Model", f"{model}  ({_model_source()})"),
        ("Status", t(*STATUS_TEXT[check])),
    ]
    ui.summary(t("AI credentials", "Kredensial AI"), rows)
    if check in ("invalid", "model", "unknown"):
        ui.hint(message, indent="")
    return exit_code


def logout() -> int:
    """Remove every saved copy of the key. An environment variable, if set, still applies."""
    ui.header("Auth", t("Remove the saved API key", "Hapus API key yang disimpan"))
    removed = credentials.delete_key()
    if removed:
        ui.ok(t("Removed from ", "Dihapus dari ") + ", ".join(_where(w) for w in removed))
    else:
        ui.skip(t("No saved key.", "Tidak ada key yang disimpan."))
    env = credentials.env_source()
    if env:
        ui.info(
            t(
                f"{env} is still set in this environment and will keep being used.",
                f"{env} masih ter-set di environment ini dan akan tetap dipakai.",
            )
        )
    return 0


# ---- display helpers ----------------------------------------------------------------------


def _where(source: str) -> str:
    """Human name of a key source ("keychain", "file", "sdk", or an environment variable)."""
    names = {
        "keychain": t("OS keychain", "keychain OS"),
        "file": str(credentials.config_dir() / "credentials.json"),
        "sdk": t("`ant auth login` profile", "profil `ant auth login`"),
    }
    return names.get(source, f"environment variable {source}")


def _model_source() -> str:
    if os.environ.get("REPOLENS_MODEL"):
        return "REPOLENS_MODEL"
    if credentials.load_settings().get("model"):
        return t("saved setting", "pengaturan tersimpan")
    return "default"
