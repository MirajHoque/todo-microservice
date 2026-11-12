"""config.py — all settings, read once at startup.

pydantic-settings reads each field from an environment variable of
the same name (case-insensitive), falling back to the .env file,
then to the default here. Wrong types fail at startup, not later:
PORT=abc stops the service with a clear error.

Same idea as services/todo/internal/config/config.go.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Server
    host: str = "0.0.0.0"
    port: int = 8083  # auth is 8081, todo is 8082
    env: Literal["development", "production"] = "development"

    # Database — the agent's OWN database (agent_db), as its own user.
    # It can't connect to the todo service's `todo_db` database (see db/init.sql).
    database_url: str = "postgresql://agent:agent@localhost:5433/agent_db"
    db_min_conns: int = 1
    db_max_conns: int = 10  # a chat holds one connection while it runs (see routes/chat.py)

    # Auth — the SAME secret the auth service signs tokens with (HS256, shared
    # secret; see ROADMAP "Auth"). No default on purpose: without it the
    # service refuses to start instead of accepting forged tokens.
    # At least 32 characters: a short secret can be brute-forced, and
    # then anyone can forge tokens. (`openssl rand -base64 32` → 44.)
    jwt_secret: str = Field(min_length=32)
    jwt_issuer: str = "todo-app"  # the auth service sets iss="todo-app"

    # The api service that owns todos. The agent never touches the
    # todos table — its tools call this over HTTP, as the user.
    todo_url: str = "http://localhost:8082"
    api_timeout_seconds: float = 10.0

    # The LLM — via OpenRouter's unified API, so ANY model from any
    # provider works: change AGENT_MODEL, nothing else.
    # Model ids: https://openrouter.ai/models  ("provider/model")
    # SecretStr: never printed in logs or error messages.
    openrouter_api_key: SecretStr = Field(min_length=1)
    agent_model: str = "anthropic/claude-sonnet-5.5"
    llm_max_tokens: int = 16000  # room for reasoning + reply; hitting it cuts the answer off
    llm_timeout_seconds: float = 60.0
    # The SDK retries 5xx/network errors by itself; its default keeps
    # trying for up to ONE HOUR. A chat should give up much sooner.
    llm_retry_seconds: float = 10.0
    # Max LLM calls per chat message, by ALL agents together (orchestrator +
    # sub-agents). Stops runaway loops; planning + adding 7 todos takes
    # 6–13 depending on the model. If it runs out, the orchestrator gets
    # one extra call to tell the user what was done.
    agent_max_steps: int = 20

    # Guardrails (step 2i.2) — per user, checked before any model is called.
    chat_messages_per_hour: int = Field(default=30, ge=1)
    daily_cost_limit_usd: float = Field(default=0.50, gt=0)  # midnight to midnight, UTC

    # Logging
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    log_format: Literal["json", "text"] = "json"


@lru_cache  # read the environment once, then reuse the same object
def get_settings() -> Settings:
    return Settings()
