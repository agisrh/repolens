ActiveRecord::Schema[7.1].define(version: 2024_01_01_000000) do
  create_table "articles", force: :cascade do |t|
    t.string "title", limit: 200, null: false
    t.string "slug"
    t.bigint "user_id"
    t.boolean "published", default: false
    t.datetime "created_at", null: false
    t.index ["slug"], name: "index_articles_on_slug", unique: true
  end

  create_table "taggings", id: false, force: :cascade do |t|
    t.integer "tag_id"
  end

  add_foreign_key "articles", "users"
end
