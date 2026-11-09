"""conftest.py — shared test setup. pytest loads this file first.

Tests that need a database use the separate `agent_db_test` database
(created by `make db`), never your real `agent_db`. We point
DATABASE_URL (and a test-only JWT_SECRET) at test values *before*
the app is imported, so the app's settings pick them up
(environment variables beat the .env file).

If Postgres isn't running, database tests are skipped with a hint
instead of failing. Token helpers live in helpers.py.
"""

import os

from helpers import TEST_JWT_SECRET

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://agent:agent@localhost:5433/agent_db_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["JWT_SECRET"] = TEST_JWT_SECRET

import psycopg  # noqa: E402  (imports after setting the env vars, on purpose)
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from agent.main import app  # noqa: E402


@pytest.fixture(scope="session")
def database_url() -> str:
    """The test database URL — or skip the test if Postgres isn't up."""
    try:
        psycopg.connect(TEST_DATABASE_URL, connect_timeout=2).close()
    except psycopg.OperationalError:
        pytest.skip("Postgres not reachable — run `make db` from the repo root")
    return TEST_DATABASE_URL


@pytest.fixture
def db_client(database_url: str):
    """A TestClient with the app fully started: pool open, migrations run.

    `with TestClient(app)` runs the lifespan (startup + shutdown);
    a plain TestClient(app) does not. Data is wiped after each test.
    """
    with TestClient(app) as client:
        yield client
    with psycopg.connect(database_url) as conn:
        conn.execute("TRUNCATE conversations, messages")
