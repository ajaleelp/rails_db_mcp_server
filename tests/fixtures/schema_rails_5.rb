ActiveRecord::Schema.define(version: 2023_11_15_120000) do
  create_table "projects", force: :cascade do |t|
    t.string "name"
    t.bigint "owner_id"
    t.timestamps
  end

  add_index "projects", ["owner_id"], name: "index_projects_on_owner_id"

  create_table "project_memberships", id: false, force: :cascade do |t|
    t.bigint "project_id"
    t.bigint "user_id"
    t.index ["project_id", "user_id"], name: "index_memberships_on_project_and_user"
  end

  add_index "project_memberships", ["user_id", "project_id"], name: "index_memberships_on_user_and_project"
end
