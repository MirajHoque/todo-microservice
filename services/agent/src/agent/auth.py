"""auth.py — who is calling? Verifies the user's JWT.

The api (Go) issues the token at login. This service never sees
passwords and has no users table — it only checks that the token
is genuine and reads the user id from it:

  Authorization: Bearer <token>
        │
        ▼
  1. signature  — signed with our shared JWT_SECRET?  (not forged/tampered)
  2. algorithm  — HS256 only                           (blocks "alg: none" tricks)
  3. exp        — not expired
  4. iss        — issued by "todo-app"
  5. user_id    — present → that's the caller

Same checks and the same 401 messages as the Go services' middleware
(libs/go/jwtauth), so clients see one behaviour.

Routes use it by declaring a parameter `caller: CurrentUser`.
FastAPI runs `current_user` first; if it raises, the route never runs.
`caller.user_id` says who it is; `caller.token` is kept so the agent
can call the todo service *as this user* (see todo_client.py).
"""

from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agent.config import get_settings
from agent.log import user_id_var

ALGORITHMS = ["HS256"]  # what the auth service signs with — accept nothing else

# Declares "this API uses Bearer tokens" in the OpenAPI contract, so the
# /docs page shows an Authorize button and a lock on protected routes.
# auto_error=False: we do the checks ourselves below, to keep the
# api's exact error messages.
bearer_scheme = HTTPBearer(auto_error=False, description="Paste the JWT from /auth/login")


@dataclass(frozen=True)  # a small read-only record (like a Go struct)
class Caller:
    user_id: str  # from the verified token
    token: str  # the raw JWT, forwarded when the agent calls the todo service


class AuthError(Exception):
    """Token missing or not acceptable. Message is safe to show the client."""


def verify_token(token: str, secret: str, issuer: str) -> str:
    """Return the user id inside a valid token, or raise AuthError."""
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=ALGORITHMS,
            issuer=issuer,
            options={"require": ["exp", "user_id"]},
        )
    except jwt.ExpiredSignatureError:
        raise AuthError("token has expired") from None
    except jwt.InvalidTokenError:
        # Bad signature, wrong algorithm, wrong issuer, malformed, …
        # Don't tell an attacker which check failed.
        raise AuthError("token is invalid") from None

    user_id = claims["user_id"]
    if not isinstance(user_id, str) or not user_id:
        raise AuthError("token is invalid")
    return user_id


async def current_user(
    # The raw header — we parse it ourselves. Hidden from /docs, since the
    # Authorize button (bearer_scheme) already fills it in.
    authorization: Annotated[str | None, Header(include_in_schema=False)] = None,
    _docs: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> Caller:
    """FastAPI dependency: who is calling (user id + token), or a 401.

    `async def` (even though nothing here waits) so it runs in the same
    context as the route: the user_id_var set below is then visible to
    every log line the route writes. A plain `def` dependency runs in a
    worker thread, and a ContextVar set there would not come back.
    """
    # Header(): FastAPI reads the `Authorization` request header for us.
    if not authorization:
        raise HTTPException(401, "missing authorization header")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "authorization header must be: Bearer <token>")

    settings = get_settings()
    try:
        user_id = verify_token(token, settings.jwt_secret, settings.jwt_issuer)
    except AuthError as exc:
        raise HTTPException(401, str(exc)) from None

    user_id_var.set(user_id)  # every log line of this request gets user_id
    return Caller(user_id=user_id, token=token)


# Use in a route:  async def handler(caller: CurrentUser): ...
CurrentUser = Annotated[Caller, Depends(current_user)]
