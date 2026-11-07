"""config.py — all settings, read once at startup.

pydantic-settings reads each field from an environment variable of
the same name (case-insensitive), falling back to the .env file,
then to the default here. Wrong types fail at startup, not later:
PORT=abc stops the service with a clear error.

Same idea as services/api/internal/config/config.go.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Server
    host: str = "0.0.0.0"
    port: int = 8083  # api is 8080; auth/todo will get 8081/8082 in step 3
    env: Literal["development", "production"] = "development"

    # Database — the agent's OWN database (agent_db), as its own user.
    # It can't connect to the api's `todo` database (see db/init.sql).
    database_url: str = "postgresql://agent:agent@localhost:5433/agent_db"
    db_min_conns: int = 1
    db_max_conns: int = 5

    # Logging
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    log_format: Literal["json", "text"] = "json"


@lru_cache  # read the environment once, then reuse the same object
def get_settings() -> Settings:
    return Settings()
