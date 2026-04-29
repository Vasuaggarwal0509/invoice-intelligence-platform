"""CA-persona DTOs: signup, login, client list, client detail.

Password fields are :class:`SecretStr` on request types so the raw
value never survives an unintentional ``repr()`` or structured log
dump. Services call ``.get_secret_value()`` only at the hash/verify
boundary.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr

from .common import DisplayName, Gstin


class CaSignupRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    email: EmailStr
    password: SecretStr = Field(min_length=12, max_length=128)
    display_name: DisplayName
    gstin: Gstin


class CaLoginRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=128)


class CaWorkspacePublic(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    gstin: str | None
    role: Literal["ca"]


class CaSessionResponse(BaseModel):
    """Body returned from CA signup or login. Session token is in the cookie."""

    model_config = ConfigDict(frozen=True)

    user_id: str
    display_name: str
    email: str
    workspace: CaWorkspacePublic


class CaClientPublic(BaseModel):
    """One row in the CA dashboard's client list."""

    model_config = ConfigDict(frozen=True)

    workspace_id: str
    name: str
    gstin: str | None
    invoice_count: int
    total_spend_minor: int
    open_flags: int


class CaClientListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[CaClientPublic]


class CaClientInvoicePublic(BaseModel):
    """Summary row for CA → one-client → invoice list."""

    model_config = ConfigDict(frozen=True)

    invoice_id: str
    vendor_name: str | None
    invoice_no: str | None
    invoice_date: str | None
    total_amount_minor: int | None
    currency: str
    status: str
    failing_rules: int
    created_at: int


class CaClientInvoiceListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[CaClientInvoicePublic]


# ---------- Business-side DTOs for CA linking --------------------------


class BusinessLinkCaRequest(BaseModel):
    """Body of POST /api/business/ca-link (business-persona authenticated)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ca_gstin: Gstin


class LinkedCaPublic(BaseModel):
    model_config = ConfigDict(frozen=True)

    ca_workspace_id: str
    ca_name: str
    ca_gstin: str
