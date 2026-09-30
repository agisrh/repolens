"""Focused checks of single extractors, for cases the fixtures do not cover."""

from __future__ import annotations

from repolens.extractors.database.migrations import laravel_migrations
from repolens.extractors.overview import folder_tree
from repolens.i18n import set_lang
from repolens.repo import Repo


def test_laravel_schema_table_note_follows_the_output_language(tmp_path):
    migrations = tmp_path / "database" / "migrations"
    migrations.mkdir(parents=True)
    (migrations / "2024_01_01_create_carts.php").write_text(
        "<?php Schema::create('carts', function (Blueprint $table) { $table->id(); });"
    )
    (migrations / "2024_02_01_add_token.php").write_text(
        "<?php Schema::table('carts', function (Blueprint $table) { $table->string('token'); });"
    )
    repo = Repo(tmp_path, use_git=False)
    [carts] = laravel_migrations(repo)
    assert [c["name"] for c in carts["columns"]] == ["id", "token"]
    assert carts["notes"] == ["changed by 2024_02_01_add_token.php"]
    set_lang("id")
    assert laravel_migrations(repo)[0]["notes"] == ["diubah oleh 2024_02_01_add_token.php"]


def test_folder_tree_text_follows_the_output_language(tmp_path):
    for i in range(25):  # more folders than a tree level shows
        (tmp_path / f"module{i:02}").mkdir()
        (tmp_path / f"module{i:02}" / "a.py").write_text("x = 1\n")
    tree = folder_tree(Repo(tmp_path, use_git=False))["text"]
    assert "module00/  (1 file)" in tree and "(+5 more)" in tree
    assert f"{tmp_path.name}/" in tree
    set_lang("id")
    tree = folder_tree(Repo(tmp_path, use_git=False))["text"]
    assert "module00/  (1 file)" in tree and "(+5 lainnya)" in tree
