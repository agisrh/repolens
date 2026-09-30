"""Output language: English (default) or Indonesian.

Strings are written side by side at the call site, `t("English", "Indonesia")`, so a
translation can never drift away from the code that uses it.

Values stored in scan.json that code compares against (severity, change kind, security
type) are language-neutral codes; `label()` turns them into display text. Older scan.json
files written in Indonesian keep working because their values are recognised too.
"""

from __future__ import annotations

LANGUAGES = {"en": "English", "id": "Bahasa Indonesia"}

_lang = "en"


def set_lang(code: str) -> None:
    global _lang
    if code not in LANGUAGES:
        raise ValueError(f"unknown language: {code} (choose: {', '.join(LANGUAGES)})")
    _lang = code


def get_lang() -> str:
    return _lang


def t(en: str, id: str) -> str:
    return id if _lang == "id" else en


# code -> (English, Indonesian). Indonesian values from older scans map back to the same code.
LABELS = {
    "high": ("high", "tinggi"),
    "medium": ("medium", "sedang"),
    "low": ("low", "rendah"),
    "added": ("added", "baru"),
    "removed": ("removed", "dihapus"),
    "changed": ("changed", "berubah"),
    "table_added": ("new table", "tabel baru"),
    "table_removed": ("table removed", "tabel dihapus"),
    "columns_added": ("new columns", "kolom baru"),
    "columns_removed": ("columns removed", "kolom dihapus"),
    "committed_env": ("Env file committed", "File env ikut di-commit"),
    "warn": ("check", "perlu dicek"),
    "info": ("info", "info"),
}
_LEGACY = {id_: code for code, (_, id_) in LABELS.items()}


def code_of(value: str) -> str:
    """Normalise a stored value (new code or legacy Indonesian text) to its code."""
    return value if value in LABELS else _LEGACY.get(value, value)


def label(value: str | None) -> str:
    if value is None:
        return "-"
    pair = LABELS.get(code_of(value))
    return t(*pair) if pair else value


MONTHS = {
    "en": (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ),
    "id": (
        "Januari",
        "Februari",
        "Maret",
        "April",
        "Mei",
        "Juni",
        "Juli",
        "Agustus",
        "September",
        "Oktober",
        "November",
        "Desember",
    ),
}


def date_time(dt) -> str:
    return f"{dt.day:02d} {MONTHS[_lang][dt.month - 1]} {dt.year} {dt:%H:%M}"


def number(n: int) -> str:
    """1234567 -> 1,234,567 (en) or 1.234.567 (id)."""
    text = f"{n:,}"
    return text.replace(",", ".") if _lang == "id" else text


def signed(n: int) -> str:
    text = f"{n:+,}"
    return text.replace(",", ".") if _lang == "id" else text
