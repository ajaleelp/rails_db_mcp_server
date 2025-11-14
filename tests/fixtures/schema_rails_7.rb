ActiveRecord::Schema[7.1].define(version: 2024_01_01_000000) do
  create_table "users", force: :cascade do |t|
    t.string "email", null: false
    t.string "name"
    t.integer "company_id"
    t.datetime "created_at", null: false
    t.datetime "updated_at", null: false
    t.index ["email"], name: "index_users_on_email", unique: true
  end

  add_index "users", ["company_id", "created_at"], name: "index_users_on_company_and_created"

  create_table "events", id: :uuid, default: -> { "gen_random_uuid()" }, force: :cascade do |t|
    t.uuid "user_id"
    t.integer "company_id"
    t.string "event_type"
    t.datetime "timestamp"
  end

  add_index "events", ["company_id", "timestamp"], name: "index_events_on_company_and_timestamp"
  add_index "events", ["company_id", "event_type"], name: "index_events_on_company_and_type"

  create_table "api_keys", primary_key: "token", id: :string, force: :cascade do |t|
    t.string "token", null: false
    t.integer "user_id"
  end

  add_index "api_keys", ["user_id"], name: "index_api_keys_on_user_id"
  add_foreign_key "events", "users"
  add_foreign_key "api_keys", "users", column: "user_id", name: "fk_api_keys_users"
end
