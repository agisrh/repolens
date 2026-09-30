"""Per-project overrides from `.repolens.yml` in the scanned repository.

The file lives in the project itself, so it is versioned with the code and applies
to every release that is scanned (including `--ref` scans of older tags that have it).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from repolens.i18n import t

FILENAMES = (".repolens.yml", ".repolens.yaml")
LEGACY_FILENAMES = (".docgen.yml", ".docgen.yaml")  # before the rename to repolens; still read

KNOWN_KEYS = {
    "name": "Project name shown in the document",
    "description": "Short project description",
    "version": "Version, when no manifest records it",
    "frameworks": "List of {name, version, category} to add to or correct the tech stack",
    "routes": "Extra route files (glob). Laravel, CodeIgniter 3 and CodeIgniter 4 syntax "
    "is recognised",
    "schema": "SQL schema dump files (glob, any extension). May be git-ignored",
    "ignore": "Folders/files excluded from the scan (glob)",
    "endpoints": "Endpoints that cannot be detected: {method, path, handler, note}",
    "notes": "Project owner notes shown in the document",
    "tree_depth": "Folder structure depth",
}


def load(root: Path) -> dict:
    """{"file", "data", "warnings"}; data is {} when the project has no config file.

    Invalid values are dropped with a warning instead of failing the scan, so a typo in
    .repolens.yml never blocks documentation; `doctor` shows the warnings."""
    name = next((n for n in FILENAMES + LEGACY_FILENAMES if (root / n).is_file()), None)
    if name is None:
        return {"file": None, "data": {}, "warnings": []}
    try:
        data = yaml.safe_load((root / name).read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        problem = t(
            f"{name} cannot be read (invalid YAML): {exc}",
            f"{name} tidak bisa dibaca (YAML tidak valid): {exc}",
        )
        return {"file": name, "data": {}, "warnings": [problem]}
    if not isinstance(data, dict):
        problem = t(
            f"{name} must contain key: value pairs at the top level.",
            f"{name} harus berisi key: value di tingkat atas.",
        )
        return {"file": name, "data": {}, "warnings": [problem]}
    warnings: list[str] = []
    for validate in VALIDATORS:
        validate(name, data, warnings)
    return {"file": name, "data": data, "warnings": warnings}


# ---- validators: each fixes or drops invalid values in `data` and explains why -----------


def _unknown_keys(name: str, data: dict, warnings: list[str]) -> None:
    """Drop keys that are not in KNOWN_KEYS (a typo would otherwise do nothing silently)."""
    for key in [k for k in data if k not in KNOWN_KEYS]:
        keys = ", ".join(KNOWN_KEYS)
        warnings.append(
            t(
                f"{name}: unknown key `{key}` ignored. Available keys: {keys}.",
                f"{name}: key `{key}` tidak dikenal dan diabaikan. Key yang tersedia: {keys}.",
            )
        )
        data.pop(key)


def _text_keys(name: str, data: dict, warnings: list[str]) -> None:
    """name, description, version: text. Empty means not filled in yet (as `init` leaves it)."""
    for key in ("name", "description", "version"):
        if key not in data:
            continue
        value = data[key]
        if value is None or value == "":
            data.pop(key)
        elif isinstance(value, float):
            # YAML reads `version: 1.10` as the number 1.1, silently losing the trailing zero.
            warnings.append(
                t(
                    f"{name}: YAML reads `{key}: {value}` as a number. "
                    f'Quote it, e.g. `{key}: "{value}"`.',
                    f"{name}: `{key}: {value}` dibaca YAML sebagai angka. "
                    f'Beri tanda kutip, misalnya `{key}: "{value}"`.',
                )
            )
        elif not isinstance(value, (str, int)):
            warnings.append(
                t(f"{name}: `{key}` must be text.", f"{name}: `{key}` harus berupa teks.")
            )
            data.pop(key)


def _list_keys(name: str, data: dict, warnings: list[str]) -> None:
    """routes, schema, ignore, notes: lists of text; a single string becomes a list of one."""
    for key in ("routes", "schema", "ignore", "notes"):
        if key not in data:
            continue
        if isinstance(data[key], str):
            data[key] = [data[key]]
        if not isinstance(data[key], list):
            warnings.append(
                t(f"{name}: `{key}` must be a list.", f"{name}: `{key}` harus berupa daftar.")
            )
            data.pop(key)
            continue
        items = (_list_item(name, key, item, warnings) for item in data[key])
        data[key] = [item for item in items if item is not None]


def _list_item(name: str, key: str, item, warnings: list[str]) -> str | None:
    """The item as text, or None (with a warning) when it is not text or leaves the project."""
    if not isinstance(item, (str, int, float)) or isinstance(item, bool):
        kind = type(item).__name__
        warnings.append(
            t(
                f"{name}: `{key}` items must be text, not {kind}.",
                f"{name}: item `{key}` harus berupa teks, bukan {kind}.",
            )
        )
        return None
    item = str(item)
    outside = item.startswith(("/", "~")) or ".." in item.split("/") or ":" in item[:3]
    if key != "notes" and outside:  # notes are free text; the others are paths
        warnings.append(
            t(
                f"{name}: `{key}` pattern `{item}` must be relative to the project root "
                "and stay inside the project folder.",
                f"{name}: `{key}` pola `{item}` harus relatif terhadap root proyek dan "
                "tidak boleh keluar dari folder proyek.",
            )
        )
        return None
    return item


def _as_list(name: str, key: str, value, example: str, warnings: list[str]) -> list:
    """A mapping becomes a list of one; anything else that is not a list becomes []."""
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return value
    warnings.append(
        t(
            f"{name}: `{key}` must be a list{example}.",
            f"{name}: `{key}` harus berupa daftar{example.replace('e.g.', 'misalnya')}.",
        )
    )
    return []


def _frameworks(name: str, data: dict, warnings: list[str]) -> None:
    """frameworks: [{name, version, category}]; `name` is required."""
    if "frameworks" not in data:
        return
    example = ", e.g. `[{name: Laravel, version: 10.48.2}]`"
    valid = []
    for item in _as_list(name, "frameworks", data["frameworks"], example, warnings):
        if not (isinstance(item, dict) and item.get("name")):
            warnings.append(
                t(
                    f"{name}: every `frameworks` item needs a `name`.",
                    f"{name}: setiap item `frameworks` butuh `name`.",
                )
            )
            continue
        version = item.get("version")
        if isinstance(version, float):
            framework = item["name"]
            warnings.append(
                t(
                    f"{name}: YAML reads the `{framework}` version as a number ({version}). "
                    f'Quote it, e.g. `version: "{version}"`.',
                    f"{name}: versi `{framework}` dibaca YAML sebagai angka ({version}). "
                    f'Beri tanda kutip, misalnya `version: "{version}"`.',
                )
            )
        valid.append(
            {
                "name": str(item["name"]),
                "version": None if version is None else str(version),
                "category": item.get("category"),
            }
        )
    data["frameworks"] = valid


def _endpoints(name: str, data: dict, warnings: list[str]) -> None:
    """endpoints: [{method, path, handler, note}]; `path` is required."""
    if "endpoints" not in data:
        return
    valid = []
    for item in _as_list(name, "endpoints", data["endpoints"], "", warnings):
        if isinstance(item, dict) and item.get("path"):
            valid.append(item)
        else:
            warnings.append(
                t(
                    f"{name}: every `endpoints` item needs a `path`.",
                    f"{name}: setiap item `endpoints` butuh `path`.",
                )
            )
    data["endpoints"] = valid


def _tree_depth(name: str, data: dict, warnings: list[str]) -> None:
    """tree_depth must be a whole number of 1 or more."""
    depth = data.get("tree_depth")
    if "tree_depth" in data and (
        not isinstance(depth, int) or isinstance(depth, bool) or depth < 1
    ):
        warnings.append(
            t(
                f"{name}: `tree_depth` must be a whole number of 1 or more.",
                f"{name}: `tree_depth` harus bilangan bulat 1 atau lebih.",
            )
        )
        data.pop("tree_depth")


VALIDATORS = [_unknown_keys, _text_keys, _list_keys, _frameworks, _endpoints, _tree_depth]


def expand(root: Path, patterns: list[str], label: str, warnings: list[str]) -> list[str]:
    """Resolve globs against the filesystem (so git-ignored dumps still work)."""
    found: list[str] = []
    for pattern in patterns:
        try:
            matches = sorted(
                p.relative_to(root).as_posix()
                for p in root.glob(pattern)
                if p.is_file() and p.resolve().is_relative_to(root.resolve())
            )
        except (ValueError, OSError) as exc:
            warnings.append(
                t(
                    f".repolens.yml: `{label}` pattern `{pattern}` is invalid: {exc}",
                    f".repolens.yml: `{label}` pola `{pattern}` tidak valid: {exc}",
                )
            )
            continue
        if not matches:
            warnings.append(
                t(
                    f".repolens.yml: `{label}` pattern `{pattern}` matches no file.",
                    f".repolens.yml: `{label}` pola `{pattern}` tidak cocok dengan file apa pun.",
                )
            )
        found += matches
    return list(dict.fromkeys(found))


def _apply_framework(facts: dict, framework: dict, file: str) -> str:
    """Correct a detected framework, or add one that was not detected."""
    name = framework["name"]
    existing = next((f for f in facts["frameworks"] if f["name"].lower() == name.lower()), None)
    if not existing:
        facts["frameworks"].append(
            {
                "name": name,
                "category": framework.get("category") or "Framework",
                "version": framework["version"],
                "source": file,
            }
        )
        return t(f"framework {name} added", f"framework {name} ditambahkan")
    if framework["version"]:
        existing["version"] = framework["version"]
    if framework.get("category"):
        existing["category"] = framework["category"]
    existing["source"] = file
    version = framework["version"] or t("version unchanged", "versi tetap")
    return t(f"framework {name} corrected ({version})", f"framework {name} dikoreksi ({version})")


def apply_overrides(facts: dict, cfg: dict) -> list[str]:
    """Apply the metadata overrides after extraction.

    Returns a readable description of each change, shown by `doctor` and in the document."""
    data, applied = cfg["data"], []
    project = facts["project"]
    for key in ("name", "description", "version"):
        if data.get(key):
            project[key] = str(data[key])
            if key == "name":
                project["name_source"] = cfg["file"]
            applied.append(f"{key} = {data[key]}")
    for framework in data.get("frameworks", []):
        applied.append(_apply_framework(facts, framework, cfg["file"]))
    for ep in data.get("endpoints", []):
        facts["endpoints"]["server"].append(
            {
                "kind": "server",
                "method": str(ep.get("method", "ANY")).upper(),
                "path": str(ep["path"]),
                "handler": ep.get("handler"),
                "file": cfg["file"],
                "line": None,
                "group": t("Defined manually", "Didefinisikan manual"),
                "framework": "manual",
                "note": ep.get("note"),
            }
        )
    if data.get("endpoints"):
        n = len(data["endpoints"])
        applied.append(t(f"{n} manual endpoints", f"{n} endpoint manual"))
    return applied
