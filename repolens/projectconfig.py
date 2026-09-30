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
    "routes": "Extra route files (glob). Laravel, CodeIgniter 3 and CodeIgniter 4 syntax is recognised",
    "schema": "SQL schema dump files (glob, any extension). May be git-ignored",
    "ignore": "Folders/files excluded from the scan (glob)",
    "endpoints": "Endpoints that cannot be detected: {method, path, handler, note}",
    "notes": "Project owner notes shown in the document",
    "tree_depth": "Folder structure depth",
}


def load(root: Path) -> dict:
    """Return {'file', 'data', 'warnings'}; data is {} when the project has no config."""
    for name in FILENAMES + LEGACY_FILENAMES:
        path = root / name
        if path.is_file():
            break
    else:
        return {"file": None, "data": {}, "warnings": []}

    warnings = []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        return {
            "file": name,
            "data": {},
            "warnings": [
                t(
                    f"{name} cannot be read (invalid YAML): {exc}",
                    f"{name} tidak bisa dibaca (YAML tidak valid): {exc}",
                )
            ],
        }
    if not isinstance(data, dict):
        return {
            "file": name,
            "data": {},
            "warnings": [
                t(
                    f"{name} must contain key: value pairs at the top level.",
                    f"{name} harus berisi key: value di tingkat atas.",
                )
            ],
        }

    for key in list(data):
        if key not in KNOWN_KEYS:
            keys = ", ".join(KNOWN_KEYS)
            warnings.append(
                t(
                    f"{name}: unknown key `{key}` ignored. Available keys: {keys}.",
                    f"{name}: key `{key}` tidak dikenal dan diabaikan. Key yang tersedia: {keys}.",
                )
            )
            data.pop(key)
    for key in ("name", "description", "version"):
        if key not in data:
            continue
        if data[key] is None or data[key] == "":
            data.pop(
                key
            )  # left empty in the `repolens init` template: not an error, just not filled in yet
        elif isinstance(data[key], float):
            # YAML reads `version: 1.10` as the number 1.1, silently losing the trailing zero.
            warnings.append(
                t(
                    f'{name}: YAML reads `{key}: {data[key]}` as a number. Quote it, e.g. `{key}: "{data[key]}"`.',
                    f'{name}: `{key}: {data[key]}` dibaca YAML sebagai angka. Beri tanda kutip, misalnya `{key}: "{data[key]}"`.',
                )
            )
        elif not isinstance(data[key], (str, int)):
            warnings.append(
                t(f"{name}: `{key}` must be text.", f"{name}: `{key}` harus berupa teks.")
            )
            data.pop(key)
    for key in ("routes", "schema", "ignore", "notes"):
        if key in data and isinstance(data[key], str):
            data[key] = [data[key]]
        if key in data and not isinstance(data[key], list):
            warnings.append(
                t(f"{name}: `{key}` must be a list.", f"{name}: `{key}` harus berupa daftar.")
            )
            data.pop(key)
            continue
        if key in data:
            items = []
            for item in data[key]:
                if not isinstance(item, (str, int, float)) or isinstance(item, bool):
                    kind = type(item).__name__
                    warnings.append(
                        t(
                            f"{name}: `{key}` items must be text, not {kind}.",
                            f"{name}: item `{key}` harus berupa teks, bukan {kind}.",
                        )
                    )
                    continue
                item = str(item)
                if key != "notes" and (
                    item.startswith(("/", "~")) or ".." in item.split("/") or ":" in item[:3]
                ):
                    warnings.append(
                        t(
                            f"{name}: `{key}` pattern `{item}` must be relative to the project root and stay inside the project folder.",
                            f"{name}: `{key}` pola `{item}` harus relatif terhadap root proyek dan tidak boleh keluar dari folder proyek.",
                        )
                    )
                    continue
                items.append(item)
            data[key] = items
    if "frameworks" in data:
        fws = data["frameworks"]
        if isinstance(fws, dict):
            fws = [fws]
        if not isinstance(fws, list):
            warnings.append(
                t(
                    f"{name}: `frameworks` must be a list, e.g. `[{{name: Laravel, version: 10.48.2}}]`.",
                    f"{name}: `frameworks` harus berupa daftar, misalnya `[{{name: Laravel, version: 10.48.2}}]`.",
                )
            )
            fws = []
        valid = []
        for fw in fws:
            if isinstance(fw, dict) and fw.get("name"):
                if isinstance(fw.get("version"), float):
                    fwn, fwv = fw["name"], fw["version"]
                    warnings.append(
                        t(
                            f'{name}: YAML reads the `{fwn}` version as a number ({fwv}). Quote it, e.g. `version: "{fwv}"`.',
                            f'{name}: versi `{fwn}` dibaca YAML sebagai angka ({fwv}). Beri tanda kutip, misalnya `version: "{fwv}"`.',
                        )
                    )
                valid.append(
                    {
                        "name": str(fw["name"]),
                        "version": None if fw.get("version") is None else str(fw["version"]),
                        "category": fw.get("category"),
                    }
                )
            else:
                warnings.append(
                    t(
                        f"{name}: every `frameworks` item needs a `name`.",
                        f"{name}: setiap item `frameworks` butuh `name`.",
                    )
                )
        data["frameworks"] = valid
    if "endpoints" in data:
        eps = data["endpoints"]
        if isinstance(eps, dict):
            eps = [eps]
        if not isinstance(eps, list):
            warnings.append(
                t(
                    f"{name}: `endpoints` must be a list.",
                    f"{name}: `endpoints` harus berupa daftar.",
                )
            )
            eps = []
        valid = []
        for ep in eps:
            if isinstance(ep, dict) and ep.get("path"):
                valid.append(ep)
            else:
                warnings.append(
                    t(
                        f"{name}: every `endpoints` item needs a `path`.",
                        f"{name}: setiap item `endpoints` butuh `path`.",
                    )
                )
        data["endpoints"] = valid
    if "tree_depth" in data and (
        not isinstance(data["tree_depth"], int)
        or isinstance(data["tree_depth"], bool)
        or data["tree_depth"] < 1
    ):
        warnings.append(
            t(
                f"{name}: `tree_depth` must be a whole number of 1 or more.",
                f"{name}: `tree_depth` harus bilangan bulat 1 atau lebih.",
            )
        )
        data.pop("tree_depth")
    return {"file": name, "data": data, "warnings": warnings}


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


def apply_overrides(facts: dict, cfg: dict) -> list[str]:
    """Apply metadata overrides after extraction. Returns human-readable descriptions of what changed."""
    data, applied = cfg["data"], []
    project = facts["project"]
    for key in ("name", "description", "version"):
        if data.get(key):
            project[key] = str(data[key])
            if key == "name":
                project["name_source"] = cfg["file"]
            applied.append(f"{key} = {data[key]}")
    for fw in data.get("frameworks", []):
        existing = next(
            (f for f in facts["frameworks"] if f["name"].lower() == fw["name"].lower()), None
        )
        if existing:
            if fw["version"]:
                existing["version"] = fw["version"]
            if fw.get("category"):
                existing["category"] = fw["category"]
            existing["source"] = cfg["file"]
            version = fw["version"] or t("version unchanged", "versi tetap")
            applied.append(
                t(
                    f"framework {fw['name']} corrected ({version})",
                    f"framework {fw['name']} dikoreksi ({version})",
                )
            )
        else:
            facts["frameworks"].append(
                {
                    "name": fw["name"],
                    "category": fw.get("category") or "Framework",
                    "version": fw["version"],
                    "source": cfg["file"],
                }
            )
            applied.append(
                t(f"framework {fw['name']} added", f"framework {fw['name']} ditambahkan")
            )
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
