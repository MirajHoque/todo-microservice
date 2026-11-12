"""helpers.py — small tools shared by the tests.

Import as `from helpers import ...` (pytest adds tests/ to the import
path, see [tool.pytest.ini_options] in pyproject.toml).
"""

import time
import uuid

import jwt

# conftest.py sets JWT_SECRET to this. 64+ chars: long enough even for the
# HS512 test (the service itself only accepts HS256).
TEST_JWT_SECRET = "test-secret-only-for-tests-" + "x" * 40


def make_token(
    user_id: str | None = None,
    *,
    secret: str = TEST_JWT_SECRET,
    algorithm: str = "HS256",
    expires_in: int = 3600,
    issuer: str = "todo-app",
) -> str:
    """Build a token like the auth service does (override parts to make bad ones)."""
    now = int(time.time())
    claims = {
        "user_id": user_id or str(uuid.uuid4()),
        "iat": now,
        "exp": now + expires_in,
        "iss": issuer,
    }
    return jwt.encode(claims, secret, algorithm=algorithm)


def auth(token: str) -> dict[str, str]:
    """Headers for a request carrying this token."""
    return {"Authorization": f"Bearer {token}"}
