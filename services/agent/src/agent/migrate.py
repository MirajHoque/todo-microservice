"""migrate.py — applies the SQL files in migrations/ at startup.

How it works (same idea as services/api/internal/db/migrate.go):
  1. a table `schema_migrations` remembers which files already ran
  2. files are applied in name order: 001_..., 002_..., ...
  3. the whole run is ONE transaction: if any file fails, everything
     from this run is rolled back (nothing half-applied, nothing
     recorded) and startup stops with the error
  4. files already recorded are skipped, so running this on every
     start is safe

The advisory lock: on Kubernetes several copies of this service may
start at once. pg_advisory_xact_lock makes them take turns, so two
copies never run the same migration at the same time.

Never edit a migration that has run somewhere — add a new file.
"""

from pathlib import Path

from psycopg_pool import AsyncConnectionPool

from agent.log import get_logger

log = get_logger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
LOCK_ID = 727_001  # any fixed number, shared by all copies of this service


async def migrate(pool: AsyncConnectionPool, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations. Returns the names of the files applied."""
    files = sorted(directory.glob("*.sql"))
    applied_now: list[str] = []

    async with pool.connection() as conn:
        # `conn.transaction()` = BEGIN … COMMIT (or ROLLBACK on error).
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version    TEXT        PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur = await conn.execute("SELECT version FROM schema_migrations")
            done = {row[0] for row in await cur.fetchall()}

            for file in files:
                if file.name in done:
                    continue
                await conn.execute(file.read_text())
                await conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)", (file.name,)
                )
                log.info("migration applied", extra={"version": file.name})
                applied_now.append(file.name)

    if not applied_now:
        log.info("database schema is up to date")
    return applied_now
