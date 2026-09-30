"""Compare two scans (e.g. previous release vs current) into a structured change list."""

from __future__ import annotations

from repolens.i18n import t


def _label(facts: dict) -> str:
    git = facts.get("git") or {}
    return (facts.get("source") or {}).get("ref") or (git.get("tags_at_head") or [None])[0] \
        or facts["project"].get("version") or git.get("commit_short") or t("previous", "sebelumnya")


def _flatten(d, prefix=""):
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
    changes: dict = {"from": _label(old), "to": _label(new)}

    of = {f["name"]: f["version"] for f in old["frameworks"]}
    nf = {f["name"]: f["version"] for f in new["frameworks"]}
    changes["frameworks"] = (
        [{"name": n, "change": "added", "old": None, "new": nf[n]} for n in nf if n not in of]
        + [{"name": n, "change": "removed", "old": of[n], "new": None} for n in of if n not in nf]
        + [{"name": n, "change": "changed", "old": of[n], "new": nf[n]} for n in nf if n in of and of[n] != nf[n]]
    )

    def dep_map(facts):
        result = {}
        for m in facts["dependencies"]:
            for d in m["dependencies"]:
                result[(m["ecosystem"], d["name"])] = d.get("resolved") or d.get("declared") or d.get("source")
        return result

    od, nd = dep_map(old), dep_map(new)
    changes["dependencies"] = sorted(
        [{"ecosystem": k[0], "name": k[1], "change": "added", "old": None, "new": nd[k]} for k in nd if k not in od]
        + [{"ecosystem": k[0], "name": k[1], "change": "removed", "old": od[k], "new": None} for k in od if k not in nd]
        + [{"ecosystem": k[0], "name": k[1], "change": "changed", "old": od[k], "new": nd[k]} for k in nd if k in od and od[k] != nd[k]],
        key=lambda c: (c["change"], c["name"]),
    )

    def ep_set(facts):
        result = {}
        for kind in ("server", "client", "pages"):
            for e in facts["endpoints"][kind]:
                result[(kind, e["method"], e["path"])] = e
        return result

    oe, ne = ep_set(old), ep_set(new)
    changes["endpoints"] = sorted(
        [{"kind": k[0], "method": k[1], "path": k[2], "change": "added", "file": ne[k]["file"]} for k in ne if k not in oe]
        + [{"kind": k[0], "method": k[1], "path": k[2], "change": "removed", "file": oe[k]["file"]} for k in oe if k not in ne],
        key=lambda c: (c["kind"], c["change"], c["path"]),
    )

    ot = {tbl["name"]: {c["name"] for c in tbl["columns"]} for tbl in old["database"]["tables"]}
    nt = {tbl["name"]: {c["name"] for c in tbl["columns"]} for tbl in new["database"]["tables"]}
    tables = [{"table": n, "change": "table_added", "detail": ", ".join(sorted(nt[n]))} for n in nt if n not in ot]
    tables += [{"table": n, "change": "table_removed", "detail": ""} for n in ot if n not in nt]
    for n in nt:
        if n in ot:
            added, removed = nt[n] - ot[n], ot[n] - nt[n]
            if added:
                tables.append({"table": n, "change": "columns_added", "detail": ", ".join(sorted(added))})
            if removed:
                tables.append({"table": n, "change": "columns_removed", "detail": ", ".join(sorted(removed))})
    changes["database"] = tables

    def env_keys(facts):
        return {k for e in facts["config"]["env_files"] for k in e["keys"]}

    ok, nk = env_keys(old), env_keys(new)
    changes["env"] = [{"key": k, "change": "added"} for k in sorted(nk - ok)] + [{"key": k, "change": "removed"} for k in sorted(ok - nk)]

    op, np_ = _flatten(old.get("platforms")), _flatten(new.get("platforms"))
    changes["platforms"] = [{"setting": k, "old": op.get(k), "new": np_.get(k)} for k in sorted(set(op) | set(np_))
                            if op.get(k) != np_.get(k) and not k.endswith(".file")]

    changes["stats"] = {
        "files": (old["tree"]["total_files"], new["tree"]["total_files"]),
        "lines": (sum(l["lines"] for l in old["languages"]), sum(l["lines"] for l in new["languages"])),
    }
    if old.get("git", {}).get("commit") and new.get("git", {}).get("commit"):
        changes["commits"] = {"from": old["git"]["commit_short"], "to": new["git"]["commit_short"]}
    return changes


def is_empty(changes: dict) -> bool:
    return not any(changes.get(k) for k in ("frameworks", "dependencies", "endpoints", "database", "env", "platforms"))
