"""routes/health.py — health checks, for humans and Kubernetes.

GET /health        liveness:  "is the process up?" Checks nothing else,
                   so a database outage never makes Kubernetes restart
                   a healthy process.
GET /health/ready  readiness: "can I serve requests right now?" Runs a
                   real query on the database. 503 while it can't, so
                   traffic is sent elsewhere until it recovers.

Same response shapes as the Go api's /health and /health/ready.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Response
from pydantic import BaseModel

from agent.db import Pool
from agent.log import SERVICE

router = APIRouter()


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: str


@router.get("/health")
def health() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE, timestamp=_now())


class DatabaseStatus(BaseModel):
    connected: bool
    stats: dict[str, int] | None = None
    error: str | None = None


class ReadyResponse(BaseModel):
    status: str  # "ready" | "not_ready"
    timestamp: str
    database: DatabaseStatus


# response_model_exclude_none: leave out empty fields (like `omitempty` in Go)
@router.get(
    "/health/ready",
    responses={503: {"model": ReadyResponse}},
    response_model_exclude_none=True,
)
async def ready(pool: Pool, response: Response) -> ReadyResponse:
    # `pool: Pool` — FastAPI hands us the database pool (see db.py).
    # `response: Response` — lets us change the status code to 503.
    try:
        # Borrow a connection, run the cheapest possible query, give it back.
        async with pool.connection(timeout=2) as conn:
            await conn.execute("SELECT 1")
    except Exception as exc:
        response.status_code = 503
        return ReadyResponse(
            status="not_ready",
            timestamp=_now(),
            database=DatabaseStatus(connected=False, error=type(exc).__name__),
        )

    s = pool.get_stats()
    return ReadyResponse(
        status="ready",
        timestamp=_now(),
        database=DatabaseStatus(
            connected=True,
            stats={
                "pool_size": s.get("pool_size", 0),  # connections open right now
                "idle_conns": s.get("pool_available", 0),  # open and free to borrow
                "max_conns": pool.max_size,
            },
        ),
    )
