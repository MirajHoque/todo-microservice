"""db.py — the connection pool to the agent's database.

Opening a database connection is slow (network + login), so we
open a few once at startup and reuse them: a *pool*. A request
borrows a connection, uses it, and gives it back.
Same idea as pgxpool in libs/go/postgres/postgres.go.

The pool is created when the app starts and closed when it stops
(see `lifespan` in main.py). Routes get it by declaring a parameter
of type `Pool` (defined at the bottom).
"""

from typing import Annotated

from fastapi import Depends, Request
from psycopg_pool import AsyncConnectionPool

from agent.config import Settings
from agent.log import get_logger

log = get_logger(__name__)


async def open_pool(settings: Settings) -> AsyncConnectionPool:
    """Open the pool and wait until it really connects.

    If the database is unreachable, startup fails right here with a
    clear error — like the Go services. Better to crash at start than to
    look "up" and fail every request.
    """
    pool = AsyncConnectionPool(
        conninfo=settings.database_url,
        min_size=settings.db_min_conns,
        max_size=settings.db_max_conns,
        # autocommit: every statement is saved immediately. Multi-statement
        # work opts in with `async with conn.transaction():` (migrate.py).
        # Without it, a connection held during a slow LLM call would sit
        # "idle in transaction" the whole time.
        kwargs={"autocommit": True},
        open=False,  # open explicitly below, so we can wait for it
    )
    log.info("connecting to database", extra={"action": "db_connect"})
    await pool.open(wait=True, timeout=10)
    log.info(
        "database connected",
        extra={"action": "db_connected", "min_conns": pool.min_size, "max_conns": pool.max_size},
    )
    return pool


def get_pool(request: Request) -> AsyncConnectionPool:
    """Return the pool that `lifespan` stored on the app at startup."""
    return request.app.state.pool


# A *dependency*: write `pool: Pool` as a route parameter and FastAPI
# calls get_pool(request) for you and passes the result in. The route
# never needs to know where the pool lives — and tests can swap it.
Pool = Annotated[AsyncConnectionPool, Depends(get_pool)]
