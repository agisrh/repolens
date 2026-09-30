"""`repolens auth login | status | logout`: let each user set their own Anthropic API key and model."""

from __future__ import annotations

import json
import os
import sys

from repolens import ai, credentials, ui
from repolens.i18n import t


def _where(source: str) -> str:
    return {
        "keychain": t("OS keychain", "keychain OS"),
        "file": str(credentials.config_dir() / "credentials.json"),
        "sdk": t("`ant auth login` profile", "profil `ant auth login`"),
    }.get(source, t(f"environment variable {source}", f"environment variable {source}"))


def _model_source() -> str:
    if os.environ.get("REPOLENS_MODEL"):
        return "REPOLENS_MODEL"
    return t("saved setting", "pengaturan tersimpan") if credentials.load_settings().get("model") else "default"


def _read_key(interactive: bool) -> str:
    if not interactive:  # e.g. `pass show anthropic | repolens auth login`: the key never touches shell history
        return sys.stdin.readline().strip()
    import questionary

    from repolens import menu
    return menu._ask(questionary.password(t("Anthropic API key (sk-ant-…)", "API key Anthropic (sk-ant-…)"), style=menu.STYLE,
                                          validate=lambda v: bool(v.strip()) or t("Required", "Wajib diisi"))).strip()


def _pick_model() -> str:
    from questionary import Choice

    from repolens import menu
    current = credentials.default_model(ai.DEFAULT_MODEL)
    choices = [Choice(f"{model}  ({t(*desc)})", model) for model, desc in ai.MODELS.items()]
    if current not in ai.MODELS:
        choices.append(Choice(f"{current}  ({t('current', 'saat ini')})", current))
    return menu._select(t("Model for the AI summary", "Model untuk ringkasan AI"), choices, default=current)


def login(model: str | None = None, verify: bool = True) -> int:
    interactive = sys.stdin.isatty()
    ui.header("Auth", t("Save your Anthropic API key", "Simpan API key Anthropic Anda"))
    env = credentials.env_source()
    if env:
        ui.warn(t(f"{env} is set in this environment and is used before the saved key.",
                  f"{env} ter-set di environment ini dan dipakai lebih dulu daripada key yang disimpan."))
    key = _read_key(interactive)
    if not key:
        ui.error(t("No key given.", "Key tidak diisi."))
        return 1
    if model is None and interactive:
        model = _pick_model()
    check_model = model or credentials.default_model(ai.DEFAULT_MODEL)

    if verify:
        with ui.out.status(t("Checking the key with Anthropic…", "Mengecek key ke Anthropic…")):
            status, message = ai.check(check_model, api_key=key)
        if status == "invalid":
            ui.error(message + t(" Nothing was saved.", " Tidak ada yang disimpan."))
            return 1
        if status == "model":
            ui.error(message + t(" Nothing was saved. Pick another model with --model.",
                                 " Tidak ada yang disimpan. Pilih model lain dengan --model."))
            return 1
        if status == "unknown":
            ui.warn(message + t(" Saved anyway; check later with `repolens auth status`.",
                                " Tetap disimpan; cek nanti dengan `repolens auth status`."))
        else:
            ui.ok(t(f"Key works with {message}", f"Key berfungsi dengan {message}"))

    where = credentials.save_key(key)
    if model:
        credentials.save_settings(model=model)
    if where == "file":
        ui.warn(t("No OS keychain available: the key is stored in a file readable only by you.",
                  "Keychain OS tidak tersedia: key disimpan di file yang hanya bisa dibaca oleh Anda."))
    ui.summary(t("API key saved", "API key tersimpan"), [
        ("Key", credentials.mask(key)),
        (t("Stored in", "Disimpan di"), _where(where)),
        ("Model", check_model),
    ])
    return 0


def status(as_json: bool = False, verify: bool = True) -> int:
    key, source = credentials.resolve()
    if source in credentials.ENV_KEYS:
        key = os.environ[source]
    found = bool(key) or (source == "sdk" and credentials.has_profile())
    model = credentials.default_model(ai.DEFAULT_MODEL)
    check = ai.check(model) if found and verify else (None, None)
    result = {"configured": found, "source": source if found else None, "key": credentials.mask(key) if key else None,
              "model": model, "model_source": _model_source(), "check": check[0]}
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        ui.header("Auth", t("AI credentials", "Kredensial AI"))
        if not found:
            ui.warn(t("No Anthropic API key.", "Belum ada API key Anthropic."), indent="")
            ui.hint(t("Run `repolens auth login`, or set ANTHROPIC_API_KEY.",
                      "Jalankan `repolens auth login`, atau set ANTHROPIC_API_KEY."), indent="  ")
            return 1
        state = {"ok": "✓ " + t("valid", "valid"), "invalid": "✗ " + t("rejected", "ditolak"),
                 "model": "✗ " + t("model not available", "model tidak tersedia"),
                 "unknown": "? " + t("not checked (offline)", "belum dicek (offline)"), None: t("not checked", "tidak dicek")}[check[0]]
        rows = [("Key", credentials.mask(key) if key else "-"), (t("Source", "Sumber"), _where(source)),
                ("Model", f"{model}  ({result['model_source']})"), ("Status", state)]
        ui.summary(t("AI credentials", "Kredensial AI"), rows)
        if check[0] in ("invalid", "model", "unknown"):
            ui.hint(check[1], indent="")
    return 1 if not found or check[0] in ("invalid", "model") else 0


def logout() -> int:
    ui.header("Auth", t("Remove the saved API key", "Hapus API key yang disimpan"))
    removed = credentials.delete_key()
    if removed:
        ui.ok(t("Removed from ", "Dihapus dari ") + ", ".join(_where(w) for w in removed))
    else:
        ui.skip(t("No saved key.", "Tidak ada key yang disimpan."))
    env = credentials.env_source()
    if env:
        ui.info(t(f"{env} is still set in this environment and will keep being used.",
                  f"{env} masih ter-set di environment ini dan akan tetap dipakai."))
    return 0
