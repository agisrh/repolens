"""Regression tests on small synthetic projects that reproduce real-world variants.

When a real project exposes a new variant, add a minimal fixture under tests/fixtures/
that reproduces it, plus a test here, before fixing the extractor.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from repolens import document
from repolens.i18n import set_lang
from repolens.render import docx_out, markdown, pdf_out
from repolens.scanner import scan

FIXTURES = Path(__file__).parent / "fixtures"


def run(name: str) -> dict:
    root = FIXTURES / name
    return scan(root, {"type": "local", "location": str(root), "ref": None}, log=lambda *_: None)


def endpoints(facts, kind="server"):
    return {(e["method"], e["path"]) for e in facts["endpoints"][kind]}


def table(facts, name):
    return next(t for t in facts["database"]["tables"] if t["name"] == name)


def columns(facts, name):
    return {c["name"] for c in table(facts, name)["columns"]}


def warnings(facts):
    return [c for c in facts["coverage"] if c["level"] == "warn"]


# ---- CodeIgniter 4 without vendor/ (web-portal variant) --------------------

def test_ci4_skeleton_composer_name_is_not_used_as_project_name():
    f = run("ci4_no_vendor")
    assert f["project"]["name"] == "ci4_no_vendor"


def test_ci4_detected_from_layout_without_vendor():
    f = run("ci4_no_vendor")
    ci = next(x for x in f["frameworks"] if x["name"] == "CodeIgniter 4")
    assert ci["version"] is None
    assert any("CodeIgniter 4 version unknown" in w["message"] and "composer install" in w["hint"] for w in warnings(f))


def test_ci4_routes_groups_and_resource():
    eps = endpoints(run("ci4_no_vendor"))
    assert ("GET", "/admin/dashboard") in eps
    assert ("POST", "/admin/berita/simpan") in eps
    assert ("GET", "/berita/(:segment)") in eps
    assert ("DELETE", "/photos/(:segment)") in eps


def test_ci4_auto_route_env_is_reported():
    f = run("ci4_no_vendor")
    assert any("AUTO_ROUTE" in n for n in f["endpoints"]["notes"])


def test_ci4_unrouted_controller_is_flagged():
    f = run("ci4_no_vendor")
    msg = next(w["message"] for w in warnings(f) if "do not appear in any route" in w["message"])
    assert "Legacy" in msg and "Home" not in msg and "Berita," not in msg


def test_model_tables_resolve_aliases_and_joins():
    f = run("ci4_no_vendor")
    assert {"id_berita", "status_berita", "tanggal_publish", "id_kategori", "id_user"} <= columns(f, "cp_berita")
    assert "nama_kategori" not in columns(f, "cp_berita")
    assert {"nama_kategori", "id_kategori"} <= columns(f, "kategori")
    assert {"nama", "id_user"} <= columns(f, "users")
    assert "is_active" in columns(f, "cp_kip")
    assert table(f, "cp_berita")["inferred"] and "inferred" in table(f, "cp_berita")["source"]


def test_test_support_models_are_ignored():
    names = {t["name"] for t in run("ci4_no_vendor")["database"]["tables"]}
    assert "factories" not in names


def test_inferred_only_schema_is_flagged():
    assert any("only inferred from queries" in w["message"] for w in warnings(run("ci4_no_vendor")))


# ---- .repolens.yml ------------------------------------------------------------

def test_config_overrides_metadata_and_framework_version():
    f = run("ci4_with_config")
    assert f["project"]["name"] == "Web Portal Contoh"
    assert f["project"]["version"] == "2.1.0"
    ci = next(x for x in f["frameworks"] if x["name"] == "CodeIgniter 4")
    assert ci["version"] == "4.1.3" and ci["source"] == ".repolens.yml"


def test_config_extra_routes_and_manual_endpoints():
    eps = endpoints(run("ci4_with_config"))
    assert ("GET", "/laporan/bulanan") in eps
    assert ("GET", "/legacy/export") in eps


def test_config_schema_file_with_any_extension_replaces_inferred_table():
    f = run("ci4_with_config")
    t = table(f, "cp_berita")
    assert t["source"] == "SQL"
    assert {"id_berita", "judul"} <= columns(f, "cp_berita")


def test_config_ignore_excludes_files():
    f = run("ci4_with_config")
    assert all(not e["file"].startswith("public/assets/vendor") for e in f["endpoints"]["client"])
    assert "/should/not/appear" not in {e["path"] for e in f["endpoints"]["client"]}


def test_config_unknown_key_and_notes():
    f = run("ci4_with_config")
    assert any("unknown_key" in w["message"] for w in warnings(f))
    assert f["project_config"]["notes"] == ["Auto-routing aktif di production."]
    assert not any("CodeIgniter 4 version unknown" in w["message"] for w in warnings(f))


# ---- Laravel ----------------------------------------------------------------

def test_laravel_prefix_group_and_api_resource():
    f = run("laravel_groups")
    eps = endpoints(f)
    assert ("GET", "/api/v1/orders/{order}/track") in eps
    assert ("GET", "/api/v1/orders") in eps
    assert ("DELETE", "/api/v1/orders/{order}") in eps
    assert ("GET", "/api/v1/orders/create") not in eps  # apiResource has no create/edit
    assert ("POST", "/api/login") in eps
    fw = next(x for x in f["frameworks"] if x["name"] == "Laravel")
    assert fw["version"] == "11.9.2"
    assert f["project"]["name"] == "laravel_groups"


def test_laravel_migration_columns():
    f = run("laravel_groups")
    cols = {c["name"]: c for c in table(f, "orders")["columns"]}
    assert {"id", "customer_id", "awb", "weight", "created_at", "updated_at"} <= set(cols)
    assert "FK→customers" in cols["customer_id"]["attrs"]


# ---- Spring -----------------------------------------------------------------

def test_spring_class_prefix_and_request_mapping_methods():
    f = run("spring_basic")
    eps = endpoints(f)
    assert {("GET", "/api/shipments"), ("GET", "/api/shipments/{awb}"), ("POST", "/api/shipments/{awb}/cancel"),
            ("PUT", "/api/shipments/sync"), ("PATCH", "/api/shipments/sync")} <= eps
    fw = {x["name"]: x["version"] for x in f["frameworks"]}
    assert fw["Spring Boot"] == "3.3.2" and fw["Java"] == "21"
    assert f["project"]["name"] == "shipment-api" and f["project"]["version"] == "1.4.0"


def test_spring_entities_ignore_javadoc_and_transient():
    f = run("spring_basic")
    names = {t["name"] for t in f["database"]["tables"]}
    assert "shipments" in names and "BaseEntity" in names
    assert not names & {"for", "public", "class"}
    assert columns(f, "shipments") == {"awb_number", "customer_id"}
    assert any(e["engine"] == "PostgreSQL" for e in f["database"]["engines"])


# ---- Flutter ----------------------------------------------------------------

def test_flutter_client_paths_resolve_variables_and_interpolation():
    f = run("flutter_client")
    eps = endpoints(f, "client")
    assert ("GET", "trucks") in eps
    assert ("GET", "agen/{outletId}/profile/{id}") in eps
    assert ("PUT", "assign-truck/assignment") in eps
    assert {e["group"] for e in f["endpoints"]["client"]} == {"Env.baseUrlCoins()"}
    fw = {x["name"]: x["version"] for x in f["frameworks"]}
    assert fw["Flutter"] == "3.35.0"


# ---- Next.js ----------------------------------------------------------------

def test_next_app_router_groups_and_drizzle():
    f = run("next_app_router")
    assert {("GET", "/api/shipments"), ("POST", "/api/shipments")} <= endpoints(f)
    assert {("VIEW", "/"), ("VIEW", "/shipments/[awb]")} <= endpoints(f, "pages")
    assert {"id", "awb", "status"} <= columns(f, "shipments")
    assert any(e["engine"] == "PostgreSQL" for e in f["database"]["engines"])


# ---- Unknown stack ----------------------------------------------------------

def test_unknown_stack_is_flagged_not_silently_empty():
    f = run("unknown_stack")
    assert any("Main framework not recognised" in w["message"] for w in warnings(f))


# ---- Rendering --------------------------------------------------------------

@pytest.mark.parametrize("name", ["ci4_with_config", "spring_basic", "unknown_stack"])
def test_all_formats_render(tmp_path, name):
    blocks = document.build(run(name))
    for render, ext in ((markdown.render, ".md"), (docx_out.render, ".docx"), (pdf_out.render, ".pdf")):
        out = render(blocks, tmp_path / f"doc{ext}")
        assert out.stat().st_size > 1000
    md = (tmp_path / "doc.md").read_text()
    assert "Scan Coverage" in md


def test_old_scan_json_without_new_keys_still_renders(tmp_path):
    facts = run("spring_basic")
    facts.pop("coverage")
    facts.pop("project_config")
    markdown.render(document.build(facts), tmp_path / "old.md")


def test_indonesian_output_and_legacy_values(tmp_path):
    """--lang id renders Indonesian; values from scans made by 0.1 (Indonesian text) still render."""
    set_lang("id")
    try:
        facts = run("ci4_no_vendor")
        assert any("tidak diketahui" in w["message"] for w in warnings(facts))
        facts["security"]["secrets"] = [{"type": "File env ikut di-commit", "severity": "tinggi", "file": ".env", "line": 1,
                                         "preview": "3 key", "committed": True}]
        md = markdown.render(document.build(facts), tmp_path / "id.md").read_text()
        assert "Cakupan Pemindaian" in md and "Daftar Isi" in md
        assert "| tinggi | File env ikut di-commit |" in md
        set_lang("en")
        md = markdown.render(document.build(facts), tmp_path / "en.md").read_text()
        assert "| high | Env file committed |" in md
    finally:
        set_lang("en")
