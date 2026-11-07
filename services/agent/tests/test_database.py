"""Database tests: readiness, migrations, and the memory tables.

Run against agent_db_test (see conftest.py). Needs `make db`.
"""

import asyncio
from pathlib import Path

import psycopg
from psycopg_pool import AsyncConnectionPool

from agent.migrate import migrate


def test_ready_reports_database(db_client):
    res = db_client.get("/health/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ready"
    assert body["database"]["connected"] is True
    assert "error" not in body  # empty fields are left out


def test_startup_created_tables(db_client, database_url):
    with psycopg.connect(database_url) as conn:
        rows = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        tables = {r[0] for r in rows}
    assert {"conversations", "messages", "schema_migrations"} <= tables


def test_migrate_is_safe_to_rerun(db_client, database_url):
    # The app already migrated at startup; running again applies nothing.
    async def run() -> list[str]:
        async with AsyncConnectionPool(database_url, open=False) as pool:
            return await migrate(pool)

    assert asyncio.run(run()) == []


def test_failed_migration_rolls_back_everything(database_url, tmp_path: Path):
    # 1 good file + 1 broken file: NEITHER may be applied or recorded.
    (tmp_path / "901_good.sql").write_text("CREATE TABLE test_good (id INT);")
    (tmp_path / "902_bad.sql").write_text("THIS IS NOT SQL;")

    async def run() -> None:
        async with AsyncConnectionPool(database_url, open=False) as pool:
            await migrate(pool, tmp_path)

    try:
        asyncio.run(run())
        raise AssertionError("migrate should have failed")
    except psycopg.errors.SyntaxError:
        pass

    with psycopg.connect(database_url) as conn:
        assert conn.execute("SELECT to_regclass('test_good')").fetchone()[0] is None
        recorded = conn.execute(
            "SELECT count(*) FROM schema_migrations WHERE version LIKE '90%'"
        ).fetchone()[0]
        assert recorded == 0


def test_messages_store_full_content_blocks(db_client, database_url):
    # The 1c.6 fix: tool calls are stored as JSON, not thrown away.
    blocks = [{"type": "tool_use", "id": "t1", "name": "create_todo", "input": {"title": "milk"}}]
    with psycopg.connect(database_url) as conn:
        conv_id = conn.execute(
            "INSERT INTO conversations (user_id) VALUES (gen_random_uuid()) RETURNING id"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (%s, 'assistant', %s)",
            (conv_id, psycopg.types.json.Jsonb(blocks)),
        )
        stored = conn.execute("SELECT content FROM messages WHERE conversation_id = %s", (conv_id,))
        assert stored.fetchone()[0] == blocks  # comes back exactly as saved


def test_one_conversation_per_user(db_client, database_url):
    with psycopg.connect(database_url) as conn:
        user = conn.execute("SELECT gen_random_uuid()").fetchone()[0]
        conn.execute("INSERT INTO conversations (user_id) VALUES (%s)", (user,))
        try:
            conn.execute("INSERT INTO conversations (user_id) VALUES (%s)", (user,))
            raise AssertionError("second conversation for the same user should fail")
        except psycopg.errors.UniqueViolation:
            pass
