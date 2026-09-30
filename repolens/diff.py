"""Compare two scans (e.g. the previous release and this one) into a list of changes per area.

Used by `scan --compare-ref` / `--compare` (the Changes section of the document) and by
`repolens diff`. Change kinds are language-neutral codes; i18n.label() shows them.
"""

from __future__ import annotations

from repolens.i18n import t


def _label(facts: dict) -> str:
    """Name of the release a scan describes (like document.release_label)."""
    git = facts.get("git") or {}
    return (
        (facts.get("source") or {}).get("ref")
        or (git.get("tags_at_head") or [None])[0]
        or facts["project"].get("version")
        or git.get("commit_short")
        or t("previous", "sebelumnya")
    )


def _flatten(d, prefix=""):
    """{"android": {"min_sdk": 21}} -> {"android.min_sdk": 21}; lists become text."""
    out = {}
    for k, v in (d or {}).items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        elif isinstance(v, list):
            out[key] = ", ".join(map(str, v))
        else:
            out[key] = v
    return out


def compare(old: dict, new: dict) -> dict:
    """What changed from the `old` scan to the `new` one, per area."""
    changes = {
        "from": _label(old),
        "to": _label(new),
        "frameworks": _frameworks(old, new),
        "dependencies": _dependencies(old, new),
        "endpoints": _endpoints(old, new),
        "database": _tables(old, new),
        "env": _env_keys(old, new),
        "platforms": _platforms(old, new),
        "stats": {
            "files": (old["tree"]["total_files"], new["tree"]["total_files"]),
            "lines": (_lines(old), _lines(new)),
        },
    }
    if old.get("git", {}).get("commit") and new.get("git", {}).get("commit"):
        changes["commits"] = {"from": old["git"]["commit_short"], "to": new["git"]["commit_short"]}
    return changes


def _changes(old: dict, new: dict, with_changed: bool = True) -> list[tuple]:
    """(key, "added" | "removed" | "changed", old value, new value) between two mappings:
    added keys in `new` order, then removed keys in `old` order, then changed values."""
    result = [(key, "added", None, new[key]) for key in new if key not in old]
    result += [(key, "removed", old[key], None) for key in old if key not in new]
    if with_changed:
        result += [
            (key, "changed", old[key], new[key])
            for key in new
            if key in old and old[key] != new[key]
        ]
    return result


def _frameworks(old: dict, new: dict) -> list[dict]:
    before = {f["name"]: f["version"] for f in old["frameworks"]}
    after = {f["name"]: f["version"] for f in new["frameworks"]}
    return [
        {"name": name, "change": change, "old": was, "new": now}
        for name, change, was, now in _changes(before, after)
    ]


def _dependencies(old: dict, new: dict) -> list[dict]:
    """Per (ecosystem, package): the installed version, else the declared one."""

    def versions(facts: dict) -> dict:
        return {
            (m["ecosystem"], d["name"]): d.get("resolved") or d.get("declared") or d.get("source")
            for m in facts["dependencies"]
            for d in m["dependencies"]
        }

    items = [
        {"ecosystem": key[0], "name": key[1], "change": change, "old": was, "new": now}
        for key, change, was, now in _changes(versions(old), versions(new))
    ]
    return sorted(items, key=lambda c: (c["change"], c["name"]))


def _endpoints(old: dict, new: dict) -> list[dict]:
    """Endpoints added or removed, by (kind, method, path); moving to another file is no change."""

    def by_key(facts: dict) -> dict:
        return {
            (kind, e["method"], e["path"]): e
            for kind in ("server", "client", "pages")
            for e in facts["endpoints"][kind]
        }

    items = [
        {
            "kind": key[0],
            "method": key[1],
            "path": key[2],
            "change": change,
            "file": (now or was)["file"],
        }
        for key, change, was, now in _changes(by_key(old), by_key(new), with_changed=False)
    ]
    return sorted(items, key=lambda c: (c["kind"], c["change"], c["path"]))


def _tables(old: dict, new: dict) -> list[dict]:
    """Tables added or removed, and columns added or removed in tables that stayed."""
    before = {x["name"]: {c["name"] for c in x["columns"]} for x in old["database"]["tables"]}
    after = {x["name"]: {c["name"] for c in x["columns"]} for x in new["database"]["tables"]}
    items = [
        {"table": name, "change": "table_added", "detail": ", ".join(sorted(after[name]))}
        for name in after
        if name not in before
    ]
    items += [
        {"table": name, "change": "table_removed", "detail": ""}
        for name in before
        if name not in after
    ]
    for name in after:
        if name not in before:
            continue
        added, removed = after[name] - before[name], before[name] - after[name]
        if added:
            items.append(
                {"table": name, "change": "columns_added", "detail": ", ".join(sorted(added))}
            )
        if removed:
            items.append(
                {"table": name, "change": "columns_removed", "detail": ", ".join(sorted(removed))}
            )
    return items


def _env_keys(old: dict, new: dict) -> list[dict]:
    """Env key names added or removed across all .env files."""

    def keys(facts: dict) -> set:
        return {key for env in facts["config"]["env_files"] for key in env["keys"]}

    before, after = keys(old), keys(new)
    return [{"key": k, "change": "added"} for k in sorted(after - before)] + [
        {"key": k, "change": "removed"} for k in sorted(before - after)
    ]


def _platforms(old: dict, new: dict) -> list[dict]:
    """Changed platform settings such as android.min_sdk (file paths are not settings)."""
    before, after = _flatten(old.get("platforms")), _flatten(new.get("platforms"))
    return [
        {"setting": key, "old": before.get(key), "new": after.get(key)}
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key) and not key.endswith(".file")
    ]


def _lines(facts: dict) -> int:
    return sum(language["lines"] for language in facts["languages"])


def is_empty(changes: dict) -> bool:
    """True when nothing in any area changed (file and line counts do not count)."""
    return not any(
        changes.get(k)
        for k in ("frameworks", "dependencies", "endpoints", "database", "env", "platforms")
    )
