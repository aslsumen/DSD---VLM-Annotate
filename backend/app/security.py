"""Password and session-token primitives.

Only the standard library is used: no new runtime dependency and no secret is
ever stored in clear text.  Passwords use PBKDF2-HMAC-SHA256 with a per-user
salt; session tokens are random 256-bit values whose SHA-256 hash is stored, so
a database leak does not expose usable tokens.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 260_000
_TOKEN_BYTES = 32


def hash_password(password: str) -> str:
    """Return ``pbkdf2_sha256$iterations$salt_hex$digest_hex``."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_ALGORITHM}${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time check; malformed hashes are treated as a mismatch."""
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$")
        if algorithm != _ALGORITHM:
            return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# Used to keep the failed-login path roughly constant-time when the email does
# not exist.  Computed once at import.
DUMMY_PASSWORD_HASH = hash_password("not-a-real-password")
