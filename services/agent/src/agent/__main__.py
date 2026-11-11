"""__main__.py — runs when you type `python -m agent`.

Starts uvicorn (the HTTP server) with host/port from config, so the
port lives in one place (.env) instead of on the command line.
In development it watches src/ and restarts on every save.
"""

import uvicorn

from agent.config import get_settings


def main() -> None:
    settings = get_settings()
    dev = settings.env == "development"
    uvicorn.run(
        "agent.main:app",  # import path, so --reload can re-import it
        host=settings.host,
        port=settings.port,
        reload=dev,
        reload_dirs=["src"] if dev else None,
        log_config=None,  # keep our JSON logging (log.py)
        access_log=False,  # our middleware logs requests
    )


if __name__ == "__main__":
    main()
