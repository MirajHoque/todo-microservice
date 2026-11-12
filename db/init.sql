-- ============================================================
-- db/init.sql — one database + one login user per service.
--
-- Decision (docs/ROADMAP.md): ONE Postgres server, but each service
-- gets its OWN database and its OWN user. A service can only log in
-- to its own database, so it cannot read another service's tables —
-- it has to ask that service over HTTP (rule 3: one owner per table).
--
--   todo     user → todo     database  (the server's ADMIN user and its
--                                        default database, created by the
--                                        image's POSTGRES_* variables in
--                                        `make db`. No service uses it any
--                                        more: it was the monolith's database
--                                        and still holds its old tables.)
--   auth     user → auth_db  database  (+ auth_db_test for its tests)
--   todo_svc user → todo_db  database  (+ todo_db_test for its tests)
--     (the todo service's user can't be called "todo": that name is
--      taken by the server's admin user, see below)
--   agent    user → agent_db database  (+ agent_db_test for its tests)
--
-- Run by `make db` / `make db-init`. Safe to run again and again:
-- every statement checks whether the thing already exists first.
-- Local-only passwords: this server is only reachable from your Mac.
--
-- `\gexec` is a psql feature: run the SELECT, then execute each row
-- it returns as a SQL statement. The WHERE NOT EXISTS makes the
-- SELECT return nothing when the user/database is already there.
-- (CREATE DATABASE has no "IF NOT EXISTS" in Postgres, hence the trick.)
-- ============================================================

-- ── auth service ─────────────────────────────────────────────
SELECT 'CREATE ROLE auth LOGIN PASSWORD ''auth'''
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'auth')\gexec

SELECT 'CREATE DATABASE auth_db OWNER auth'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'auth_db')\gexec

SELECT 'CREATE DATABASE auth_db_test OWNER auth'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'auth_db_test')\gexec

-- ── todo service ─────────────────────────────────────────────
SELECT 'CREATE ROLE todo_svc LOGIN PASSWORD ''todo_svc'''
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'todo_svc')\gexec

SELECT 'CREATE DATABASE todo_db OWNER todo_svc'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'todo_db')\gexec

SELECT 'CREATE DATABASE todo_db_test OWNER todo_svc'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'todo_db_test')\gexec

-- ── agent service ────────────────────────────────────────────
SELECT 'CREATE ROLE agent LOGIN PASSWORD ''agent'''
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'agent')\gexec

SELECT 'CREATE DATABASE agent_db OWNER agent'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'agent_db')\gexec

SELECT 'CREATE DATABASE agent_db_test OWNER agent'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'agent_db_test')\gexec

-- ── who may connect where ────────────────────────────────────
-- By default Postgres lets EVERY user (the PUBLIC group) connect to
-- every database. Take that away, so only the owner gets in:
-- the agent user cannot open the auth or todo database, and so on.
REVOKE CONNECT ON DATABASE todo          FROM PUBLIC;
REVOKE CONNECT ON DATABASE auth_db       FROM PUBLIC;
REVOKE CONNECT ON DATABASE auth_db_test  FROM PUBLIC;
REVOKE CONNECT ON DATABASE todo_db       FROM PUBLIC;
REVOKE CONNECT ON DATABASE todo_db_test  FROM PUBLIC;
REVOKE CONNECT ON DATABASE agent_db      FROM PUBLIC;
REVOKE CONNECT ON DATABASE agent_db_test FROM PUBLIC;
