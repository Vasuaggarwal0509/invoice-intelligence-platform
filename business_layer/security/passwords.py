"""Password hashing — argon2id only.

Wraps :mod:`argon2.PasswordHasher` with parameters pinned in code so an
env tweak cannot downgrade crypto strength. Callers never touch the
underlying library directly.

Argon2id parameters (memory=64 MiB, time=3, parallelism=4) follow the
OWASP 2024 baseline for interactive auth. Bump ``time_cost`` as
hardware improves — old hashes re-verify correctly; the
:meth:`PasswordHasher.check_needs_rehash` method tells us when to
rotate on next successful login.

Never store bcrypt, MD5, SHA-x, or plain passwords. Never transport the
plaintext through logs or structured output; callers must pass a
:class:`pydantic.SecretStr` in from the request model and call
``.get_secret_value()`` only at the hash boundary.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError, VerifyMismatchError

# Single shared hasher — argon2-cffi's PasswordHasher is thread-safe.
# Parameters chosen to complete in ~100-300ms on a modern server;
# balance between user-visible login latency and attacker cost.
_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,  # KiB → 64 MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(plaintext: str) -> str:
    """Hash a plaintext password and return the argon2id encoded string.

    The returned string contains the salt + parameters + hash, so no
    separate salt column is needed in the DB.

    Raises:
        ValueError: If ``plaintext`` is empty. Reject at the API layer
            too — this is a defensive belt.
    """
    if not plaintext:
        # Not a ValueError of the Pydantic kind — this is defensive
        # against a caller that forgot to validate upstream.
        raise ValueError("password must not be empty")
    return _HASHER.hash(plaintext)


def verify_password(stored_hash: str, plaintext: str) -> bool:
    """Check a plaintext against a stored argon2id hash.

    Constant-time by design (argon2's verify doesn't short-circuit).
    Returns False on any mismatch, malformed hash, or verification
    error — callers shouldn't need to distinguish "wrong password"
    from "malformed hash" at the response boundary (both → 401).

    Rehash-on-success: if :meth:`check_needs_rehash` returns True
    (parameters have been bumped since the original hash), the caller
    should recompute and persist a new hash. This module returns only
    the boolean; the auth service orchestrates the rehash.
    """
    try:
        _HASHER.verify(stored_hash, plaintext)
    except (VerifyMismatchError, VerificationError, InvalidHash):
        return False
    return True


def needs_rehash(stored_hash: str) -> bool:
    """Return True if the stored hash uses weaker parameters than the current policy.

    Call after a successful :func:`verify_password`; if True, hash the
    just-verified plaintext again with :func:`hash_password` and
    overwrite the DB row.
    """
    return _HASHER.check_needs_rehash(stored_hash)
