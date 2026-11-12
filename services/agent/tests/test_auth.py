"""Auth tests: every way a token can be wrong must give a 401.

Messages match the Go services' middleware exactly, so clients see the
same behaviour from every service.
"""

import uuid

import jwt
import psycopg
import pytest
from helpers import TEST_JWT_SECRET, auth, make_token
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from agent.auth import AuthError, verify_token
from agent.config import Settings

URL = "/api/v1/agent/conversation"


# ── verify_token on its own (no HTTP, no database) ───────────


def test_valid_token_gives_user_id():
    user = str(uuid.uuid4())
    assert verify_token(make_token(user), TEST_JWT_SECRET, "todo-app") == user


@pytest.mark.parametrize(
    ("token", "message"),
    [
        (make_token(expires_in=-10), "token has expired"),
        (make_token(secret="someone-elses-secret-" + "y" * 40), "token is invalid"),  # forged
        (make_token(algorithm="HS512"), "token is invalid"),  # only HS256 accepted
        (make_token(issuer="evil-app"), "token is invalid"),
        (jwt.encode({"exp": 9999999999, "iss": "todo-app"}, TEST_JWT_SECRET), "token is invalid"),
        ("not.a.token", "token is invalid"),
    ],
    ids=["expired", "wrong-secret", "wrong-algorithm", "wrong-issuer", "no-user_id", "garbage"],
)
def test_bad_tokens_are_rejected(token, message):
    with pytest.raises(AuthError, match=message):
        verify_token(token, TEST_JWT_SECRET, "todo-app")


def test_alg_none_is_rejected():
    # The classic attack: an unsigned token claiming "no signature needed".
    header = jwt.utils.base64url_encode(b'{"alg":"none","typ":"JWT"}').decode()
    body = jwt.utils.base64url_encode(b'{"user_id":"x","exp":9999999999,"iss":"todo-app"}').decode()
    with pytest.raises(AuthError, match="token is invalid"):
        verify_token(f"{header}.{body}.", TEST_JWT_SECRET, "todo-app")


# ── over HTTP: the header checks + the shared error shape ────


@pytest.mark.parametrize(
    ("headers", "message"),
    [
        ({}, "missing authorization header"),
        ({"Authorization": "Token abc"}, "authorization header must be: Bearer <token>"),
        ({"Authorization": "Bearer"}, "authorization header must be: Bearer <token>"),
        ({"Authorization": "Bearer nope"}, "token is invalid"),
    ],
    ids=["missing", "wrong-scheme", "empty-token", "garbage-token"],
)
def test_protected_route_returns_401(db_client, headers, message):
    res = db_client.get(URL, headers=headers)
    assert res.status_code == 401
    assert res.json()["error"] == message
    assert res.json()["request_id"]


def test_valid_token_reaches_the_route(db_client):
    res = db_client.get(URL, headers=auth(make_token()))
    assert res.status_code == 200
    assert res.json() == {"messages": []}


# ── each user only sees their own conversation ───────────────


def _seed_conversation(database_url: str, user_id: str, text: str) -> None:
    with psycopg.connect(database_url) as conn:
        conv = conn.execute(
            "INSERT INTO conversations (user_id) VALUES (%s) RETURNING id", (user_id,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO messages (conversation_id, role, message) VALUES (%s, 'user', %s)",
            (conv, Jsonb({"role": "user", "content": text})),
        )


def test_users_are_isolated(db_client, database_url):
    alice, bob = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_conversation(database_url, alice, "alice's secret plan")

    alice_view = db_client.get(URL, headers=auth(make_token(alice))).json()
    bob_view = db_client.get(URL, headers=auth(make_token(bob))).json()
    assert alice_view["messages"][0]["message"]["content"] == "alice's secret plan"
    assert bob_view == {"messages": []}

    # Bob deleting "his" conversation must not touch Alice's.
    assert db_client.delete(URL, headers=auth(make_token(bob))).status_code == 204
    assert len(db_client.get(URL, headers=auth(make_token(alice))).json()["messages"]) == 1

    # Alice can delete hers.
    assert db_client.delete(URL, headers=auth(make_token(alice))).status_code == 204
    assert db_client.get(URL, headers=auth(make_token(alice))).json() == {"messages": []}


# ── config: a weak or missing secret stops the service ───────


@pytest.mark.parametrize("secret", ["change-me", ""], ids=["too-short", "empty"])
def test_weak_secret_is_refused_at_startup(secret):
    with pytest.raises(ValidationError, match="jwt_secret"):
        Settings(jwt_secret=secret)
