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

    # Logging
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    log_format: Literal["json", "text"] = "json"


@lru_cache  # read the environment once, then reuse the same object
def get_settings() -> Settings:
    return Settings()
