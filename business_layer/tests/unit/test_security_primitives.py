"""Exercise the security primitives end to end.

Not route-level yet (routes arrive Sprint 1) — just the hash/verify and
constant-time comparison behaviour we rely on.
"""

from __future__ import annotations

import pytest

from business_layer.security.otp import issue_otp, verify_otp
from business_layer.security.passwords import hash_password, needs_rehash, verify_password
from business_layer.security.sessions import hash_token, issue_token, verify_token


class TestPasswordHashing:
    def test_hash_roundtrip(self) -> None:
        h = hash_password("correct horse battery staple")
        assert verify_password(h, "correct horse battery staple")

    def test_wrong_password_rejected(self) -> None:
        h = hash_password("correct horse battery staple")
        assert not verify_password(h, "wrong")

    def test_empty_plaintext_raises(self) -> None:
        with pytest.raises(ValueError):
            hash_password("")

    def test_needs_rehash_is_false_for_current_params(self) -> None:
        h = hash_password("password-of-the-hour")
        # Current parameters → no rehash needed immediately after hashing.
        assert needs_rehash(h) is False

    def test_verify_with_malformed_hash_returns_false(self) -> None:
        # Not a ValueError — verify must tolerate garbage from DB corruption.
        assert verify_password("not-a-real-hash", "password") is False


class TestSessionTokens:
    def test_issue_token_has_distinct_hash_and_plaintext(self) -> None:
        token = issue_token()
        assert token.plaintext
        assert token.token_hash
        assert token.plaintext != token.token_hash

    def test_verify_correct_token(self) -> None:
        token = issue_token()
        assert verify_token(token.plaintext, token.token_hash)

    def test_verify_wrong_token(self) -> None:
        token = issue_token()
        other = issue_token()
        assert not verify_token(other.plaintext, token.token_hash)

    def test_verify_rejects_empties(self) -> None:
        token = issue_token()
        assert not verify_token("", token.token_hash)
        assert not verify_token(token.plaintext, "")

    def test_hash_is_deterministic(self) -> None:
        # Same input → same output; the constant-time compare depends on this.
        assert hash_token("abc") == hash_token("abc")


class TestOtp:
    def test_issue_otp_is_six_digits(self) -> None:
        otp = issue_otp()
        assert len(otp.plaintext) == 6
        assert otp.plaintext.isdigit()

    def test_verify_correct_otp(self) -> None:
        otp = issue_otp()
        assert verify_otp(otp.plaintext, otp.code_hash)

    def test_verify_wrong_otp(self) -> None:
        otp = issue_otp()
        # Flip the last digit (or the first if last was 0).
        wrong = otp.plaintext[:-1] + ("1" if otp.plaintext[-1] == "0" else "0")
        assert not verify_otp(wrong, otp.code_hash)

    def test_verify_non_numeric_rejected(self) -> None:
        otp = issue_otp()
        assert not verify_otp("abcdef", otp.code_hash)

    def test_verify_wrong_length_rejected(self) -> None:
        otp = issue_otp()
        assert not verify_otp("12345", otp.code_hash)
        assert not verify_otp("1234567", otp.code_hash)


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self) -> None:
        from business_layer.security.encryption import decrypt, encrypt

        plaintext = b"sensitive-oauth-refresh-token-xyz"
        blob = encrypt(plaintext)
        assert blob != plaintext
        assert decrypt(blob) == plaintext

    def test_tampered_ciphertext_fails(self) -> None:
        from cryptography.exceptions import InvalidTag

        from business_layer.security.encryption import decrypt, encrypt

        blob = bytearray(encrypt(b"hello"))
        # Flip a byte in the ciphertext body.
        blob[-1] ^= 0x01
        with pytest.raises(InvalidTag):
            decrypt(bytes(blob))

    def test_associated_data_mismatch_fails(self) -> None:
        from cryptography.exceptions import InvalidTag

        from business_layer.security.encryption import decrypt, encrypt

        blob = encrypt(b"hello", associated_data=b"workspace-A")
        with pytest.raises(InvalidTag):
            decrypt(blob, associated_data=b"workspace-B")


class TestRateLimiter:
    def test_capacity_exhausted_raises(self) -> None:
        from business_layer.errors import RateLimitedError
        from business_layer.security.rate_limit import RateLimiter

        lim = RateLimiter()
        # Consume the whole bucket.
        for _ in range(3):
            lim.check("k", capacity=3, per_seconds=60)
        with pytest.raises(RateLimitedError) as excinfo:
            lim.check("k", capacity=3, per_seconds=60)
        assert excinfo.value.retry_after_seconds >= 1

    def test_different_keys_independent(self) -> None:
        from business_layer.security.rate_limit import RateLimiter

        lim = RateLimiter()
        for _ in range(3):
            lim.check("a", capacity=3, per_seconds=60)
        # Different key: fresh bucket, should not raise.
        lim.check("b", capacity=3, per_seconds=60)
