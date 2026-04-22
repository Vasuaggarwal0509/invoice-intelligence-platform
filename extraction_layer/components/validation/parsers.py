"""
Numeric parsing for European-format decimal strings.

Katanaml (and much of Europe) writes numbers like `1 319,97` or
`1.319,97`:

- space or `.` is the **thousand separator**
- `,` is the **decimal separator**

Most Python code assumes US format (`1,319.97` — reversed). Using
`float(s)` or `Decimal(s)` on European input silently wrecks amount
arithmetic. This module does the conversion correctly.

Decimal (not float) is used throughout validation so that comparing
`Decimal("1319.97") == Decimal("1319.97")` is exact; float would
risk `1319.9700000001` from intermediate arithmetic.
"""

from decimal import Decimal, InvalidOperation


def parse_european_decimal(value: str | None) -> Decimal | None:
    """Parse a string like ``2,00`` / ``1 319,97`` / ``1.319,97`` into a Decimal.

    Returns None on empty input or if parsing fails.

    Examples:
        >>> parse_european_decimal("2,00")
        Decimal('2.00')
        >>> parse_european_decimal("1 319,97")
        Decimal('1319.97')
        >>> parse_european_decimal("1.319,97")
        Decimal('1319.97')
        >>> parse_european_decimal("") is None
        True
        >>> parse_european_decimal(None) is None
        True
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    # Remove all whitespace (thousand separators).
    text = "".join(text.split())
    if "," in text:
        # Comma is decimal; any remaining '.' characters are thousand separators.
        text = text.replace(".", "").replace(",", ".")
    # else: no comma, nothing European to translate — accept US-format or plain int.
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def parse_percent(value: str | None) -> Decimal | None:
    """Parse a percent value like ``10%`` / ``10 %`` / ``10,5%`` into a Decimal.

    Returns the numeric portion (percent points, not a fraction). Use
    ``parse_percent("10%") / Decimal(100)`` for the fraction.
    """
    if value is None:
        return None
    text = str(value).strip().rstrip("%").strip()
    return parse_european_decimal(text)
