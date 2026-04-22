"""Shared types used across request/response DTOs.

Keep this small — anything domain-specific belongs in its own
``*_request.py`` / ``*_response.py`` module.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import StringConstraints

# E.164 phone number. Loose upper bound (8..16 chars) accommodates
# most international formats; a strict validator on specific country
# codes is applied at the signup-service layer, not here.
Phone = Annotated[
    str,
    StringConstraints(
        pattern=r"^\+?[1-9]\d{7,14}$",
        min_length=8,
        max_length=16,
    ),
]

# GSTIN format regex. 15 chars: state(2) + PAN(10) + entity(1) + Z + check(1).
# Full checksum validation is in the extraction_layer validation rules;
# here we only gatekeep shape.
Gstin = Annotated[
    str,
    StringConstraints(
        pattern=r"^\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z0-9]Z[A-Z0-9]$",
        min_length=15,
        max_length=15,
    ),
]

# Display name for a user or workspace. Reasonable bounds to prevent
# buffer-abuse-adjacent input; no content restrictions beyond length.
DisplayName = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=120,
        strip_whitespace=True,
    ),
]

# 6-digit OTP. Digit-only at the type layer so malformed inputs fail
# validation before they reach the constant-time compare.
OtpCode = Annotated[
    str,
    StringConstraints(
        pattern=r"^\d{6}$",
        min_length=6,
        max_length=6,
    ),
]
