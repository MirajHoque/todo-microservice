"""llm.py — the client that talks to the language model.

We use the official OpenRouter SDK. OpenRouter is one API in front of
hundreds of models (Anthropic, OpenAI, Google, Meta, DeepSeek, …), all
in the same "chat completions" format. So the agent isn't tied to any
model or provider: set AGENT_MODEL to e.g. "openai/gpt-5" or
"google/gemini-2.5-pro" and the same code keeps working.

  POST https://openrouter.ai/api/v1/chat/completions
  Authorization: Bearer <OPENROUTER_API_KEY>

We hand the SDK our own httpx.AsyncClient: we decide when it's
closed (shutdown), and tests can plug in a fake transport.
(The SDK is built on `httpx`; our api calls use `httpx2`.)

Retries: the SDK retries 5xx and network errors with backoff. Its
default gives up only after ONE HOUR — far too long for someone
waiting on a chat reply (and the chat holds a lock meanwhile). We
retry for at most LLM_RETRY_SECONDS, then answer "agent failed to
respond".
"""

from typing import Annotated

import httpx
from fastapi import Depends, Request
from openrouter import OpenRouter
from openrouter.utils.retries import BackoffStrategy, RetryConfig

from agent.config import Settings

APP_TITLE = "Todo App"  # shown in your OpenRouter dashboard per request


def create_llm(settings: Settings, http: httpx.AsyncClient) -> OpenRouter:
    retry = RetryConfig(
        "backoff",
        BackoffStrategy(
            initial_interval=500,  # ms before the 1st retry
            max_interval=4000,  # never wait more than 4 s between tries
            exponent=2.0,  # 0.5 s, 1 s, 2 s, 4 s, …
            max_elapsed_time=int(settings.llm_retry_seconds * 1000),  # then give up
        ),
        retry_connection_errors=True,
    )
    return OpenRouter(
        api_key=settings.openrouter_api_key.get_secret_value(),
        x_open_router_title=APP_TITLE,
        async_client=http,
        timeout_ms=int(settings.llm_timeout_seconds * 1000),
        retry_config=retry,
    )


def get_llm(request: Request) -> OpenRouter:
    return request.app.state.llm


# Use in a route:  async def handler(llm: LLM): ...
LLM = Annotated[OpenRouter, Depends(get_llm)]
