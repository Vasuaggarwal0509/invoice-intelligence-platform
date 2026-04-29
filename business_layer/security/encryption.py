"""Column-level encryption for secrets at rest (AES-256-GCM).

Primary use case: encrypting OAuth refresh tokens in
``sources.credentials_encrypted`` so a DB read alone doesn't unlock the
user's Gmail. Keyed by :attr:`Settings.secret_key`; a rotation procedure
(out of scope for Sprint 0) would re-encrypt with a new key.

AEAD choice rationale:
  * AES-GCM provides confidentiality + integrity in one primitive; a
    truncated/tampered ciphertext fails to decrypt, never returns
    corrupted plaintext.
  * 12-byte nonce chosen randomly per encrypt — safe for up to ~2^32
    messages per key (we will rotate far sooner).
  * Nonce is prefixed to the ciphertext so decrypt is self-describing.

Format on disk: ``nonce || ciphertext || tag`` (cryptography packs the
tag at the end of ciphertext in its output, so just ``nonce || output``).
"""

from __future__ import annotations

import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from business_layer.config import get_settings

_NONCE_BYTES = 12  # AES-GCM standard
_KEY_BYTES = 32  # AES-256


def _derive_key() -> bytes:
    """Derive a 32-byte AES-256 key from the configured master secret.

    SHA-256 is used purely as a uniformiser; the secret is required to
    be >= 32 characters of entropy by :class:`Settings` validators.
    A proper KDF (HKDF) would be appropriate if we started splitting
    one secret across multiple purposes — not needed yet.
    """
    raw = get_settings().secret_key.get_secret_value().encode("utf-8")
    return hashlib.sha256(raw).digest()[:_KEY_BYTES]


def encrypt(plaintext: bytes, *, associated_data: bytes | None = None) -> bytes:
    """Encrypt and authenticate ``plaintext``, returning ``nonce || ct_with_tag``.

    Args:
        plaintext: Bytes to encrypt. Empty is allowed (encrypts to just
            the authentication tag).
        associated_data: Optional AAD bound to this ciphertext — e.g.
            the workspace_id, so a ciphertext from one workspace can't
            be relocated into another. NOT stored by this function; the
            caller must pass the same AAD on decrypt.
    """
    aesgcm = AESGCM(_derive_key())
    nonce = os.urandom(_NONCE_BYTES)
    ct = aesgcm.encrypt(nonce, plaintext, associated_data)
    return nonce + ct


def decrypt(blob: bytes, *, associated_data: bytes | None = None) -> bytes:
    """Decrypt a blob produced by :func:`encrypt`.

    Raises:
        cryptography.exceptions.InvalidTag: On tamper/wrong-key/
            wrong-AAD. Callers should treat this as a hard failure and
            not leak which parameter was wrong.
    """
    if len(blob) < _NONCE_BYTES + 16:  # GCM tag is 16 bytes
        # Shorter than this means the blob is structurally invalid. We
        # raise the same InvalidTag-style error the aesgcm library would,
        # to keep the failure modes uniform for callers.
        from cryptography.exceptions import InvalidTag

        raise InvalidTag("ciphertext is shorter than nonce + tag")

    nonce, ct = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    aesgcm = AESGCM(_derive_key())
    return aesgcm.decrypt(nonce, ct, associated_data)
