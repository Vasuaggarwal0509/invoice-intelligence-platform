"""Opaque session tokens — issued by us, verified by us, revocable.

Design:
  * The token we hand to the client is 32 bytes of random base64url.
  * What we persist is SHA-256(token), so a DB read doesn't reveal live
    session credentials.
  * Verification is constant-time (``hmac.compare_digest``) against the
    hash we stored.
  * Server-side state lives in ``sessions`` (see ``db/schema.sql``);
    revocation is a column update, immediate.

We deliberately do NOT use JWT:
  * JWT revocation requires either a token list or very short TTLs.
  * Our front-end is server-rendered; no cross-origin fetch that needs
    a bearer token.
  * A cookie-transported opaque token is simpler and fails safer.

Cookie attributes (set by the FastAPI route, not here): HttpOnly,
Secure, SameSite=Lax, Path=/ — read from :class:`Settings`.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

# 32 bytes → 43 base64url chars; plenty of entropy (256 bits).
_TOKEN_BYTES = 32


@dataclass(frozen=True)
class IssuedToken:
    """Result of :func:`issue_token`.

    Attributes:
        plaintext: The value to set in the response cookie. Hand to the
            client; NEVER store.
        token_hash: The value to write to ``sessions.token_hash``. Use
            this for DB lookups + constant-time equality checks.
    """

    plaintext: str
    token_hash: str


def issue_token() -> IssuedToken:
    """Generate a fresh session token + its storage hash.

    Caller is responsible for persisting ``token_hash`` alongside the
    user id, expiry, IP, and user-agent.
    """
    plaintext = secrets.token_urlsafe(_TOKEN_BYTES)
    return IssuedToken(plaintext=plaintext, token_hash=hash_token(plaintext))


def hash_token(plaintext: str) -> str:
    """Hash a token for DB storage and equality comparison.

    SHA-256 is sufficient: tokens are 256-bit random values already,
    hashing is for "don't store what attackers can replay," not for
    slowing down guessing (which is pointless against 256-bit random
    anyway).
    """
    return hashlib.sha256(plaintext.encode("ascii")).hexdigest()


def verify_token(plaintext: str, stored_hash: str) -> bool:
    """Constant-time check that ``plaintext`` hashes to ``stored_hash``.

    Protects against timing oracles on the hash comparison. Callers
    must still check ``expires_at`` and ``revoked_at`` separately.
    """
    if not plaintext or not stored_hash:
        return False
    candidate = hash_token(plaintext)
    return hmac.compare_digest(candidate, stored_hash)
