"""
Input and output types for the OCR component.

- :class:`InvoiceInput` is the **service-boundary input contract**: an
  invoice document as image bytes (or a URI to fetch) plus identifying
  metadata. See :meth:`components.ocr.base.BaseOCR.ocr_invoice`.
- :class:`OCRResult` (with :class:`Token`, :class:`Line`,
  :class:`BoundingBox`, :class:`PageSize`) is the **output contract**
  consumed by every downstream stage — extraction, tables, QR cross-check,
  validation.

All types here are ``frozen=True`` Pydantic v2 models — JSON-serialisable
via ``.model_dump_json()`` / ``.model_validate_json()``, schema-extractable
via ``.model_json_schema()``. The component schema files under
``components/ocr/schema/`` are generated from these definitions.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# 4-point polygon in image pixel space, each point as [x, y].
# Kept as a bare alias rather than a BaseModel so RapidOCR's native output
# can be stored without per-point re-validation (and JSON payloads stay flat).
Polygon = list[list[float]]


class BoundingBox(BaseModel):
    """Axis-aligned bounding box in image pixel coordinates.

    Origin is top-left (image convention): x grows right, y grows down.
    """

    model_config = ConfigDict(frozen=True)

    x0: float = Field(..., description="Left edge")
    y0: float = Field(..., description="Top edge")
    x1: float = Field(..., description="Right edge")
    y1: float = Field(..., description="Bottom edge")

    @model_validator(mode="after")
    def _check_bbox_order(self) -> "BoundingBox":
        if self.x1 < self.x0:
            raise ValueError(f"x1 ({self.x1}) must be >= x0 ({self.x0})")
        if self.y1 < self.y0:
            raise ValueError(f"y1 ({self.y1}) must be >= y0 ({self.y0})")
        return self

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)


class Token(BaseModel):
    """A single word-level detection.

    For OCR engines that only emit line-level detections (like RapidOCR /
    PaddleOCR), tokens are derived from lines by splitting on whitespace and
    interpolating each word's bbox proportionally along the line. That
    derivation is the responsibility of the backend; consumers of Token do
    not need to care where it came from.
    """

    model_config = ConfigDict(frozen=True)

    text: str = Field(..., min_length=1)
    bbox: BoundingBox
    polygon: Polygon | None = Field(
        default=None,
        description="4-point polygon; preserves rotation when the OCR backend supports it.",
    )
    confidence: float = Field(..., ge=0.0, le=1.0)


class Line(BaseModel):
    """A line-level detection as emitted natively by most OCR engines."""

    model_config = ConfigDict(frozen=True)

    text: str
    bbox: BoundingBox
    polygon: Polygon | None = None
    tokens: list[Token] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)


class PageSize(BaseModel):
    """Source image dimensions in pixels."""

    model_config = ConfigDict(frozen=True)

    width: int = Field(..., gt=0)
    height: int = Field(..., gt=0)


class OCRResult(BaseModel):
    """Everything the OCR stage produces for one image.

    Consumed downstream by:
      - components/extraction (entity extraction from tokens + layout)
      - components/tables     (line-item extraction)
      - components/qr         (cross-check against QR-decoded IRP fields)
    """

    model_config = ConfigDict(frozen=True)

    tokens: list[Token] = Field(default_factory=list)
    lines: list[Line] = Field(default_factory=list)
    page: PageSize
    backend: str = Field(
        ...,
        min_length=1,
        description="Backend identifier, e.g. 'rapidocr', 'tesseract'.",
    )
    duration_ms: float = Field(..., ge=0.0)


# Supported MIME content types for :class:`InvoiceInput`. Listed explicitly
# so a service-boundary consumer can validate input before the OCR backend
# has to sniff bytes. Extend by adding here; backends may still reject
# types they cannot handle at runtime.
ContentType = Literal[
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/tiff",
    "image/webp",
]


class InvoiceInput(BaseModel):
    """Service-boundary input for OCR (and any component consuming an image).

    One of ``image_bytes`` or ``image_uri`` is required. ``image_bytes`` is
    the default for local / single-process invocation; ``image_uri`` is for
    distributed deployments (S3, GCS, HTTP) where the bytes should not be
    copied over the wire.

    Carrying ``id``, ``filename``, and ``content_type`` next to the bytes
    means a downstream service can log, cache, and route without parsing
    the bytes themselves — this is the shape AWS Textract and Google
    Document AI use for their batch submit APIs.
    """

    # ``ser_json_bytes="base64"`` makes ``image_bytes`` round-trip safely through
    # JSON (raw binary bytes are not valid UTF-8). ``val_json_bytes="base64"``
    # matches on the way back so ``model_validate_json`` reconstructs the bytes.
    model_config = ConfigDict(
        frozen=True,
        ser_json_bytes="base64",
        val_json_bytes="base64",
    )

    id: str = Field(..., min_length=1, description="Stable identifier, e.g. dataset sample id or UUID.")
    content_type: ContentType = Field(
        ...,
        description="MIME type of the referenced bytes / URI target.",
    )
    image_bytes: bytes | None = Field(
        default=None,
        description="Inline image bytes. Mutually exclusive with `image_uri`.",
    )
    image_uri: str | None = Field(
        default=None,
        description=(
            "URI (s3://, gs://, https://, file://) pointing at the image. "
            "Backends must fetch if they honour this branch. Mutually exclusive with `image_bytes`."
        ),
    )
    filename: str | None = Field(
        default=None,
        description="Original filename, for logs / provenance; not used for OCR.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form bag for upstream metadata (email sender, WhatsApp number, dataset split, ...).",
    )

    @model_validator(mode="after")
    def _exactly_one_source(self) -> "InvoiceInput":
        has_bytes = self.image_bytes is not None and len(self.image_bytes) > 0
        has_uri = self.image_uri is not None and self.image_uri.strip() != ""
        if has_bytes and has_uri:
            raise ValueError(
                "InvoiceInput: provide exactly one of `image_bytes` or `image_uri`, not both."
            )
        if not has_bytes and not has_uri:
            raise ValueError(
                "InvoiceInput: one of `image_bytes` or `image_uri` is required."
            )
        return self
