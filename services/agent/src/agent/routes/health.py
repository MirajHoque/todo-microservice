"""routes/health.py — GET /health (liveness).

Answers "is the process up?" without checking anything else, so a
broken database never makes Kubernetes restart a healthy process.
A /health/ready endpoint that checks the database comes in step 2b.

Same response shape as the Go api's /health.
"""

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from agent.log import SERVICE

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: str


@router.get("/health")
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=SERVICE,
        timestamp=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
