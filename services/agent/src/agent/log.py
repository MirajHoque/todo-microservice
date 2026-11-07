"""log.py — structured JSON logs, one line per event.

Field names match the Go api (services/api/internal/logger):
service, env, request_id, user_id, method, path, status,
duration_ms, error, agent, action. Same names in every service
means one log query (Loki/Grafana, step 6) can follow a request
across services.

request_id is kept in a ContextVar: a variable whose value belongs
to the current request, even when many requests run at once. The
request middleware (main.py) sets it; every log line picks it up.
Python's version of passing ctx around in Go.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

SERVICE = "agent"

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Attributes every LogRecord has. Anything else came from extra={...}.
_STANDARD = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "taskName"}


class JSONFormatter(logging.Formatter):
    def __init__(self, env: str) -> None:
        super().__init__()
        self.env = env

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "msg": record.getMessage(),
            "service": SERVICE,
            "env": self.env,
        }
        if request_id := request_id_var.get():
            entry["request_id"] = request_id
        # Fields passed as log.info("...", extra={"user_id": ...})
        entry.update({k: v for k, v in record.__dict__.items() if k not in _STANDARD})
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def setup_logging(level: str, fmt: str, env: str) -> None:
    """Send all logs (ours, uvicorn's, fastapi's) to stdout in one format."""
    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JSONFormatter(env))
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # uvicorn has its own access log; our middleware logs requests instead.
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
