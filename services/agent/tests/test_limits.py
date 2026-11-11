"""Guardrail tests (step 2i.2): rate limit and daily cost cap.

The fake model charges $0.0001 per call (see fakes.py). Limits are
lowered per test with monkeypatch, on the app's own settings object.
"""

import psycopg
import pytest
from fakes import answer, call
from helpers import auth, make_token

from agent.config import get_settings
from agent.usage import money

USAGE = "/api/v1/agent/usage"


@pytest.fixture
def limits(monkeypatch):
    """limits(per_hour=…, cost=…) — lower the limits for one test."""

    def set_limits(per_hour: int = 30, cost: float = 0.50) -> None:
        settings = get_settings()  # the cached object the app uses
        monkeypatch.setattr(settings, "chat_messages_per_hour", per_hour)
        monkeypatch.setattr(settings, "daily_cost_limit_usd", cost)

    return set_limits


def test_too_many_messages_is_429_without_calling_the_model(chat, limits):
    limits(per_hour=2)
    send, _, model, _ = chat(orchestrator=[answer("one"), answer("two"), answer("three")])

    assert send("1").status_code == 200
    assert send("2").status_code == 200
    res = send("3")

    assert res.status_code == 429
    assert res.json()["error"].startswith("too many messages: the limit is 2 per hour")
    assert 0 < int(res.headers["Retry-After"]) <= 3601  # seconds until the next hour
    assert len(model.requests) == 2  # the 3rd message cost nothing


def test_daily_cost_cap(chat, limits):
    limits(cost=0.0003)  # = 3 fake LLM calls
    task = call("o1", "delegate_to_todo_agent", task="List todos")
    send, _, model, _ = chat(
        orchestrator=[answer(tool_calls=[task]), answer("Nothing on your list.")],
        todo=[answer("The list is empty.")],
    )

    # One message, but 3 LLM calls (orchestrator → todo → orchestrator):
    # the cap counts EVERY agent's calls, not just messages.
    assert send("what's on my list?").status_code == 200
    res = send("and now?")

    assert res.status_code == 429
    assert res.json()["error"] == "daily AI budget used up ($0.0003); try again tomorrow"
    assert len(model.requests) == 3


def test_usage_endpoint_shows_messages_and_cost(db_client, chat):
    token = make_token()
    send, _, _, _ = chat(token=token, orchestrator=[answer("hi"), answer("hello")])
    send("hi")
    send("hello")

    body = db_client.get(USAGE, headers=auth(token)).json()
    assert body["messages_this_hour"] == 2
    assert body["cost_today_usd"] == pytest.approx(0.0002)
    assert body["messages_per_hour"] == get_settings().chat_messages_per_hour


def test_logout_does_not_reset_the_limits(db_client, chat, limits):
    limits(per_hour=1)
    token = make_token()
    send, _, _, _ = chat(token=token, orchestrator=[answer("hi")])
    send("hi")

    db_client.delete("/api/v1/agent/conversation", headers=auth(token))  # "log out"
    assert send("hi again").status_code == 429


def test_limits_are_per_user(db_client, chat, limits):
    limits(per_hour=1)
    send, _, _, _ = chat(orchestrator=[answer("hi"), answer("hi")])
    assert send("hi").status_code == 200
    assert send("again").status_code == 429

    other = auth(make_token())  # another user still has their full allowance
    res = db_client.post("/api/v1/agent/chat", json={"message": "hi"}, headers=other)
    assert res.status_code == 200


def test_a_new_hour_resets_the_message_count(chat, limits, database_url):
    limits(per_hour=1)
    send, _, _, _ = chat(orchestrator=[answer("hi"), answer("hi again")])
    send("hi")
    assert send("again").status_code == 429

    # Pretend that message was sent in the previous hour.
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("UPDATE usage SET hour = hour - interval '1 hour'")
    assert send("again").status_code == 200


def test_failed_messages_still_count(chat, limits):
    limits(per_hour=1)
    send, _, _, _ = chat(fail={"orchestrator": 500})
    assert send("hello?").status_code == 502  # the model was down …
    assert send("hello??").status_code == 429  # … but the attempt counted


def test_money_format():
    assert [money(x) for x in (0.5, 2, 0.006, 0.0003)] == ["$0.50", "$2.00", "$0.006", "$0.0003"]


def test_bad_requests_are_not_counted(chat, limits):
    limits(per_hour=1)
    send, _, _, _ = chat(orchestrator=[answer("hi")])
    assert send("   ").status_code == 400  # rejected before the limit check
    assert send("hi").status_code == 200
