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


def test_rails_migrations_when_there_is_no_schema_rb(tmp_path):
    from repolens.extractors.database.rails import rails_schema

    migrate = tmp_path / "db" / "migrate"
    migrate.mkdir(parents=True)
    (migrate / "20240101_create_articles.rb").write_text(
        "class CreateArticles < ActiveRecord::Migration[7.1]\n"
        "  def change\n"
        "    create_table :articles do |t|\n"
        "      t.string :title, null: false\n"
        "      t.references :user, foreign_key: true\n"
        "      t.timestamps\n"
        "    end\n"
        "    add_index :articles, :title, unique: true\n"
        "  end\n"
        "end\n"
    )
    [articles] = rails_schema(Repo(tmp_path, use_git=False))
    assert articles["source"] == "Rails migration"
    assert [(c["name"], c["attrs"]) for c in articles["columns"]] == [
        ("id", "PK AUTO"),
        ("title", "NOT NULL unique"),
        ("user_id", "FK→users"),
        ("created_at", "NOT NULL"),
        ("updated_at", "NOT NULL"),
    ]


def test_pnpm_lock_next_to_package_json_and_at_the_workspace_root(tmp_path):
    from repolens.extractors.deps.node import package_json

    lock = (
        "importers:\n"
        "  .:\n"
        "    dependencies:\n"
        "      vue: {specifier: ^3.4.0, version: 3.4.21(typescript@5.4.5)}\n"
        "  web:\n"
        "    dependencies:\n"
        "      vue: {specifier: ^3.4.0, version: 3.5.0}\n"
    )
    (tmp_path / "pnpm-lock.yaml").write_text(lock)
    (tmp_path / "package.json").write_text('{"dependencies": {"vue": "^3.4.0"}}')
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "package.json").write_text('{"dependencies": {"vue": "^3.4.0"}}')
    repo = Repo(tmp_path, use_git=False)
    assert package_json(repo, "package.json")["dependencies"][0]["resolved"] == "3.4.21"
    assert package_json(repo, "web/package.json")["dependencies"][0]["resolved"] == "3.5.0"
