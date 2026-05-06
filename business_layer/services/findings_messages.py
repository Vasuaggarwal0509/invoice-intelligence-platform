"""Translate technical validation findings into plain-language messages.

The validation engine emits ``rule_name`` + a terse ``reason`` aimed at
accountants. A small-business owner reading their dashboard doesn't
know what a "GSTIN checksum" is or why CGST and SGST should add up to
18%. This module owns the one-place mapping that turns those terms
into:

  * ``title``       — one short headline ("This bill's GST number looks wrong")
  * ``explanation`` — why the platform flagged it, in everyday words
  * ``suggestion``  — what the user can do next

Every entry leans on three rules:

  * Speak about MONEY consequences, not the rule. Owners care about
    "you may not get GST credit" more than "checksum failed".
  * Tell them WHO to contact (usually the vendor) when an action is
    needed.
  * Never blame the user for a vendor's mistake.

Adding a new rule? Add a key here. Unknown rules fall back to a
generic message so nothing leaks raw text to the UI.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FriendlyMessage:
    title: str
    explanation: str
    suggestion: str


# Keyed by ``validation_findings.rule_name``. Keep titles under ~70
# chars so the UI doesn't wrap awkwardly on a phone.
#
# Two rule families coexist:
#   * GST-flavoured rules (``gstin_format``, ``tax_math`` ...) — emitted
#     by the (planned) Indian validation engine. Used by the seeded demo.
#   * katanaml-flavoured rules (``iban_checksum``, ``invoice_no_format``,
#     ``tax_id_format`` ...) — emitted today by the extraction-layer
#     pipeline that was trained on a European dataset. Real Indian
#     uploads still get scored against them, so we have to translate
#     each one and (where the rule doesn't actually apply to Indian
#     invoices) say so in the suggestion.
_BY_RULE: dict[str, FriendlyMessage] = {
    "gstin_format": FriendlyMessage(
        title="The vendor's GST number looks wrong",
        explanation=(
            "Every Indian GST number has a built-in check digit. The one on this "
            "bill doesn't match — it was probably typed in incorrectly."
        ),
        suggestion=(
            "Ask the vendor for a corrected invoice with the right 15-digit GSTIN. "
            "Until that's fixed, you may not be able to claim GST credit on this bill."
        ),
    ),
    "tax_math": FriendlyMessage(
        title="The tax on this bill doesn't add up",
        explanation=(
            "We re-calculated CGST + SGST (or IGST) from the taxable amount and "
            "the rate the bill claims. The numbers don't match the total tax shown."
        ),
        suggestion=(
            "Double-check the tax breakup with the vendor. If they refuse to "
            "correct it, hold this bill for your CA to review before paying."
        ),
    ),
    "hsn_lookup": FriendlyMessage(
        title="One or more line items are missing an HSN code",
        explanation=(
            "Indian GST law requires the HSN (product/service code) on every line "
            "of a B2B invoice. This bill has at least one line without one."
        ),
        suggestion=(
            "Ask the vendor to reissue the invoice with HSN codes filled in. "
            "It only takes them a minute and protects your input tax credit."
        ),
    ),
    "duplicate_check": FriendlyMessage(
        title="This invoice number was already used",
        explanation=(
            "We've seen this exact invoice number from this vendor before. It "
            "could be a re-sent copy, or it could be an accidental double-bill."
        ),
        suggestion=(
            "Check your records before paying. If it's the same bill resent, "
            "ignore this one. If it's a new bill that re-used a number, ask "
            "for a fresh invoice with a unique number."
        ),
    ),
    "gstr2b_match": FriendlyMessage(
        title="This bill isn't on GSTR-2B yet",
        explanation=(
            "Your GSTR-2B is the government's record of GST you can claim back. "
            "This invoice doesn't appear on it — the vendor may not have filed "
            "their GSTR-1 yet."
        ),
        suggestion=(
            "Wait one filing cycle and re-import your GSTR-2B. If it still "
            "doesn't show up, follow up with the vendor — without a 2B match "
            "you cannot claim ITC on this bill."
        ),
    ),
    "amount_mismatch": FriendlyMessage(
        title="The amount we read doesn't match the printed total",
        explanation=(
            "The total on the bill image and the sum of line items don't agree. "
            "Either we read a number wrong, or there's an arithmetic error on "
            "the bill itself."
        ),
        suggestion=(
            "Open the bill and check the total. If the bill is wrong, ask the "
            "vendor for a corrected copy. If our reading is wrong, your CA can "
            "fix the numbers before you approve."
        ),
    ),
    # ---- katanaml-trained rules (European invoice schema) ----
    # These fire on every uploaded invoice today even when the rule
    # doesn't really apply to the Indian context. We translate the
    # message AND tell the user when to ignore it.
    "iban_checksum": FriendlyMessage(
        title="We couldn't match a European bank-account number on this bill",
        explanation=(
            "The platform tried to validate an IBAN — the international bank-"
            "account number used in Europe and the UK. Either it didn't read "
            "cleanly from the page, or this bill simply doesn't carry one."
        ),
        suggestion=(
            "If you're in India, you can safely ignore this — IBAN doesn't "
            "apply to Indian invoices, which use IFSC + account number instead. "
            "We're working on switching this check off for Indian uploads."
        ),
    ),
    "invoice_no_format": FriendlyMessage(
        title="The invoice number doesn't look like we expected",
        explanation=(
            "We expect a 6–10 digit invoice number (the format the platform "
            "was trained on). The number on this bill is in a different "
            "shape — letters, dashes, or longer/shorter than that range."
        ),
        suggestion=(
            "If the number on the bill is correct, you can ignore this — "
            "many Indian invoices use a longer, mixed format like INV-2526-001. "
            "Otherwise ask the vendor whether the number is right."
        ),
    ),
    "invoice_date_format": FriendlyMessage(
        title="We couldn't read the invoice date confidently",
        explanation=(
            "The date on the bill didn't match the format the platform "
            "expects (US-style mm/dd/yyyy). Indian invoices commonly use "
            "dd/mm/yyyy — both look the same on the page but parse differently."
        ),
        suggestion=(
            "Verify the date on the bill image. Your CA can correct it before "
            "approving so it lands in your books on the right day."
        ),
    ),
    "tax_id_format": FriendlyMessage(
        title="The tax ID on this bill is in a foreign format",
        explanation=(
            "We tried to validate an SSN-style US tax ID (xxx-xx-xxxx). "
            "Indian invoices use a 15-character GSTIN instead, so this rule "
            "doesn't really apply."
        ),
        suggestion=(
            "Safe to ignore on Indian invoices. We'll switch this for a "
            "GSTIN check in the next update."
        ),
    ),
    "item_net_worth_consistency": FriendlyMessage(
        title="A line item's quantity × price doesn't match the line total",
        explanation=(
            "On at least one line, ``quantity × unit price`` doesn't equal "
            "the ``line total`` printed on the bill. Either a number was "
            "read wrong from the image, or there's a typo on the invoice."
        ),
        suggestion=(
            "Open the bill image and compare the row that's wrong. Most of "
            "the time the platform misread a digit — your CA can correct it "
            "before you approve. If the bill itself is wrong, ask the vendor "
            "to reissue."
        ),
    ),
    "item_gross_worth_consistency": FriendlyMessage(
        title="A line item's tax-inclusive total doesn't add up",
        explanation=(
            "On at least one line, ``line total × (1 + tax rate)`` doesn't "
            "equal the ``gross total`` printed on the bill. The arithmetic "
            "doesn't balance."
        ),
        suggestion=(
            "Open the bill image and check the line that's flagged. Often "
            "it's an OCR misread on a single digit. Your CA can correct it "
            "before approving the invoice."
        ),
    ),
    "batch_duplicate": FriendlyMessage(
        title="Looks like a duplicate of another bill in this upload",
        explanation=(
            "Two bills in the same upload share the same invoice number, "
            "vendor and date. Could be a re-sent copy, or two separate bills "
            "that accidentally re-used a number."
        ),
        suggestion=(
            "Compare them side-by-side in your inbox. If they're the same "
            "bill, mark one as not-an-invoice. If they're two different "
            "bills, ask the vendor for a fresh, unique invoice number."
        ),
    ),
}

_FALLBACK = FriendlyMessage(
    title="Something looks off on this bill",
    explanation=(
        "Our checks flagged a problem with this invoice but we can't put it "
        "in plain words automatically. The technical detail is below."
    ),
    suggestion="Forward this bill to your CA — they can tell you whether it's safe to approve.",
)


def for_rule(rule_name: str) -> FriendlyMessage:
    """Return the plain-language message for ``rule_name``.

    Falls back to a generic message if the rule isn't in the table —
    the UI never shows raw ``rule_name`` text to a business user.
    """
    return _BY_RULE.get(rule_name, _FALLBACK)


# ---------- inbox-side: extraction-failure reasons ---------------------
#
# When the pipeline can't extract an invoice at all, the inbox row goes
# to status='failed' and the worker stamps a short ``ignored_reason``.
# These are short slugs the worker emits — translate them here too.

_INBOX_FAILURE_BY_REASON: dict[str, str] = {
    "unsupported_file": "We couldn't read this file. We only accept PDFs and images (PNG/JPG).",
    "blank_pages": "The file we received was blank — please re-upload a scanned copy.",
    "pdf_password_protected": "This PDF is password-protected. Please remove the password and re-upload.",
    "ocr_no_text": "We couldn't find any text on this image. Try a clearer photo or a scanned copy.",
    "extraction_timeout": "Reading this bill took too long. Re-upload it or split it into single pages.",
    "user_marked": "You marked this one as not an invoice. It's been hidden from the bill list.",
}


def inbox_failure_message(ignored_reason: str | None) -> str | None:
    """Return a plain-language message for an inbox row's failure.

    ``None`` if the reason isn't recognised — caller should keep its
    own fallback (e.g. "We couldn't process this file. Try uploading
    again.").
    """
    if not ignored_reason:
        return None
    return _INBOX_FAILURE_BY_REASON.get(ignored_reason)
