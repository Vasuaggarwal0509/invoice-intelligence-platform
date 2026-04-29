"""OTP generation and verification.

6-digit numeric code, 5-minute TTL (configurable), max 5 attempts.
Only the SHA-256 hash is stored; the plaintext is dispatched once via
the SMS provider (stubbed to stdout in dev) and never logged.

Why not TOTP: business-owner signup uses SMS OTP as a phone-verification
step, not an MFA second factor. TOTP (authenticator apps) is a later
concern.

Sprint 0 exposes the primitives; Sprint 1 wires them through the auth
service and phone-verify route.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

_OTP_DIGITS = 6


@dataclass(frozen=True)
class IssuedOTP:
    """Result of :func:`issue_otp`.

    Attributes:
        plaintext: The 6-digit string to send to the user via SMS. Never
            persist; never log.
        code_hash: Value to write to ``otp_challenges.code_hash``.
    """

    plaintext: str
    code_hash: str


def _generate_digits() -> str:
    """Return a uniformly random 6-digit numeric string (leading zeros allowed).

    :func:`secrets.randbelow` ensures no modulo bias. Leading zeros are
    preserved via :meth:`str.zfill`.
    """
    value = secrets.randbelow(10**_OTP_DIGITS)
    return str(value).zfill(_OTP_DIGITS)


def issue_otp() -> IssuedOTP:
    """Generate a fresh OTP + its storage hash.

    Caller persists ``code_hash`` with ``expires_at`` and dispatches
    ``plaintext`` to the user's phone.
    """
    plaintext = _generate_digits()
    return IssuedOTP(plaintext=plaintext, code_hash=_hash(plaintext))


def verify_otp(plaintext: str, stored_hash: str) -> bool:
    """Constant-time compare of a user-submitted OTP against its stored hash.

    Returns False on any empty/malformed input — callers shouldn't need
    to care about the difference between "wrong code" and "malformed
    submission" (both → auth failure).
    """
    if not plaintext or not stored_hash:
        return False
    if len(plaintext) != _OTP_DIGITS or not plaintext.isdigit():
        return False
    return hmac.compare_digest(_hash(plaintext), stored_hash)


def _hash(plaintext: str) -> str:
    """SHA-256 hash of the numeric code for DB storage.

    No salt: the code is only 6 digits. A precomputation table across
    all 10^6 codes is trivial for an attacker WITH the DB, so the real
    defences are (1) short TTL, (2) attempt cap, (3) rate limit on the
    submit endpoint. The hash is purely "don't store live codes".
    """
    return hashlib.sha256(plaintext.encode("ascii")).hexdigest()
