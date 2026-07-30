"""Reading a receipt with Gemini, and deciding what doesn't add up.

Evident verifies everything else about an expense — the recipient name comes
from the bank, the money movement comes from the provider. The amount and the
reason were the last things taken purely on the submitter's word. This closes
that gap.

Two rules this module is built around:

**Flag, never block.** A false positive in a transparency product is expensive:
if the AI wrongly flags a legitimate expense and the committee rejects it, it
has damaged the thing it was meant to protect. Nothing here can stop a payout.
Every failure path — no API key, unreadable file, model error — degrades to
"no opinion", never to "rejected".

**The verdict is published.** Flags are written to the expense and surface on
the public ledger beside the human decision, so members can see "AI flagged a
₦45,000 gap — approved anyway by <name>". The model is held to the same
transparency rule as everyone else rather than being an invisible oracle.

Note this reads an *invoice or quote* at submission time — Evident's flow is
submit → approve → pay, so no money has moved yet and no receipt of payment
exists. The check is "does this document support the amount being requested".
"""
import asyncio
import base64
import json
import logging
from decimal import Decimal

from app.config import settings
from app.services import receipts

logger = logging.getLogger(__name__)

MODEL = "gemini-3.6-flash"

# Gemini accepts these inline; note GIF is absent — it is not a supported image
# type, so a GIF upload falls through to the unsupported-type flag rather than
# erroring at the API.
GEMINI_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/heic", "image/heif"}

# Inline base64 caps the whole request at 20MB. The upload route already rejects
# anything over 10MB, so a receipt can't reach that ceiling — but base64 inflates
# by ~33%, so the headroom is smaller than it looks.
INLINE_LIMIT = 20 * 1024 * 1024

# Constrains the response to exactly these fields, so nothing downstream has to
# parse prose. `null` everywhere is the correct answer for an unreadable image —
# the model is told to use it rather than guess.
EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "vendor": {"type": ["string", "null"], "description": "Merchant or supplier name"},
        "total_amount": {"type": ["number", "null"], "description": "Grand total in naira"},
        "currency": {"type": ["string", "null"], "description": "ISO code, e.g. NGN"},
        "date": {"type": ["string", "null"], "description": "Document date, YYYY-MM-DD"},
        "document_type": {
            "type": ["string", "null"],
            "enum": ["receipt", "invoice", "quote", "other", None],
        },
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "amount": {"type": ["number", "null"]},
                },
                "required": ["description", "amount"],
                "additionalProperties": False,
            },
        },
        "legible": {"type": "boolean", "description": "false if too blurry/dark to read"},
        "notes": {"type": ["string", "null"], "description": "Anything odd about the document"},
    },
    "required": ["vendor", "total_amount", "currency", "date", "document_type",
                 "line_items", "legible", "notes"],
    "additionalProperties": False,
}

PROMPT = (
    "Read this expense document for a Nigerian community group's treasury.\n\n"
    "Extract only what is actually visible. Do not infer, complete, or guess a "
    "value that isn't printed — use null instead. If the image is too blurry, "
    "dark, or cropped to read reliably, set legible to false and return nulls "
    "rather than a best guess.\n\n"
    "Amounts are in naira unless the document says otherwise. Report the grand "
    "total (after tax and discounts), not a subtotal or a single line item.\n\n"
    "Use `notes` for anything a reviewer should know: visible alteration, "
    "mismatched totals, a date far in the past, or a document that isn't an "
    "expense document at all."
)


def _client():
    """None when unconfigured — the caller degrades to no-opinion."""
    if not settings.gemini_api_key:
        return None
    from google import genai

    return genai.Client(api_key=settings.gemini_api_key)


def _input_part(data: bytes, media_type: str) -> dict:
    """Inline base64 part. PDFs use `document`, everything else `image`."""
    encoded = base64.b64encode(data).decode()
    kind = "document" if media_type == "application/pdf" else "image"
    return {"type": kind, "data": encoded, "mime_type": media_type}


async def extract(data: bytes, media_type: str) -> dict | None:
    """Read the document. Returns None if extraction is unavailable or failed."""
    client = _client()
    if client is None:
        logger.info("GEMINI_API_KEY not set — skipping receipt extraction")
        return None

    if len(data) * 4 // 3 > INLINE_LIMIT:
        logger.warning("Receipt too large to send inline (%d bytes)", len(data))
        return None

    def _call():
        # The SDK's interactions API is synchronous. Run it off the event loop so
        # a slow model call can't stall the whole server — this also avoids
        # depending on an async binding whose shape isn't documented here.
        return client.interactions.create(
            model=MODEL,
            input=[_input_part(data, media_type), {"type": "text", "text": PROMPT}],
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": EXTRACTION_SCHEMA,
            },
        )

    try:
        interaction = await asyncio.to_thread(_call)
    except Exception as exc:
        # Never fatal: an expense must remain submittable when the model is down.
        logger.error("Receipt extraction failed: %s", exc, exc_info=True)
        return None

    text = getattr(interaction, "output_text", None)
    if not text:
        logger.warning("Receipt extraction returned no output")
        return None
    try:
        return json.loads(text)
    except ValueError:
        logger.error("Receipt extraction returned non-JSON: %s", str(text)[:200])
        return None


def build_flags(*, claimed_amount: Decimal, claimed_reason: str,
                extraction: dict | None, duplicates: list[dict],
                baseline: dict | None) -> list[dict]:
    """Assemble the advisory findings. Each is {code, severity, message}.

    Ordered cheapest-signal-first: duplicates and arithmetic don't depend on the
    model at all, so they still fire when extraction is unavailable.
    """
    flags: list[dict] = []

    for match in duplicates:
        flags.append({
            "code": "duplicate_receipt",
            "severity": "high",
            "message": (
                f"This receipt was already submitted on expense "
                f"\"{match['reason'][:60]}\" (₦{match['amount']:,.2f}, {match['status']}) "
                f"— {match['match']}."
            ),
        })

    if baseline and claimed_amount > 0:
        # Two independent conditions, both required: well outside the historical
        # spread AND larger than anything the group has ever paid. Either alone
        # fires constantly on a small, lumpy expense history.
        threshold = baseline["mean"] + 3 * baseline["stdev"]
        if float(claimed_amount) > threshold and float(claimed_amount) > baseline["max"]:
            flags.append({
                "code": "unusual_amount",
                "severity": "medium",
                "message": (
                    f"₦{claimed_amount:,.2f} is well above this group's usual spend "
                    f"(average ₦{baseline['mean']:,.2f} across {baseline['count']} expenses, "
                    f"largest so far ₦{baseline['max']:,.2f})."
                ),
            })

    if extraction is None:
        return flags

    if extraction.get("legible") is False:
        flags.append({
            "code": "illegible",
            "severity": "low",
            "message": "The document couldn't be read clearly — verify it by hand.",
        })
        return flags  # nothing below this point is trustworthy on an unreadable doc

    document_total = extraction.get("total_amount")
    if document_total is None:
        flags.append({
            "code": "no_total_found",
            "severity": "low",
            "message": "No total was visible on the document, so the amount is unverified.",
        })
    else:
        document_total = Decimal(str(document_total))
        difference = abs(document_total - claimed_amount)
        # 1% tolerance absorbs rounding and minor fees; below ₦1 is noise.
        if difference > max(Decimal("1"), claimed_amount * Decimal("0.01")):
            direction = "more than" if claimed_amount > document_total else "less than"
            flags.append({
                "code": "amount_mismatch",
                "severity": "high",
                "message": (
                    f"Requested ₦{claimed_amount:,.2f}, but the document totals "
                    f"₦{document_total:,.2f} — ₦{difference:,.2f} {direction} the document."
                ),
            })

    currency = (extraction.get("currency") or "").upper()
    if currency and currency not in ("NGN", "₦", "NAIRA"):
        flags.append({
            "code": "currency_mismatch",
            "severity": "medium",
            "message": f"The document is in {currency}, but the request is in naira.",
        })

    if extraction.get("notes"):
        flags.append({
            "code": "reviewer_note",
            "severity": "low",
            "message": str(extraction["notes"])[:300],
        })

    return flags


def summarise(flags: list[dict]) -> str:
    """One line for the ledger, so the AI's opinion is part of the record."""
    if not flags:
        return "AI receipt check: no discrepancies found"
    high = [f for f in flags if f["severity"] == "high"]
    lead = (high or flags)[0]["message"]
    extra = f" (+{len(flags) - 1} more)" if len(flags) > 1 else ""
    return f"AI receipt check flagged: {lead}{extra}"


async def review(*, data: bytes, media_type: str, sha256: str, collective_id: str,
                 claimed_amount: Decimal, claimed_reason: str, db) -> dict:
    """Full advisory pass over one receipt. Never raises.

    Order matters: the content fingerprint is derived from what the model reads,
    so extraction has to complete before duplicates can be looked up. The
    sha256 check doesn't depend on either, so an exact re-upload is still caught
    when extraction is unavailable.
    """
    if media_type not in receipts.ALLOWED_TYPES:
        return {"status": "error", "extraction": None, "fingerprint": None,
                "flags": [{"code": "unsupported_type", "severity": "low",
                           "message": f"Cannot read {media_type} — verify by hand."}]}

    extraction = await extract(data, media_type)
    fingerprint = receipts.content_fingerprint(extraction)

    duplicates = await receipts.find_duplicates(collective_id, sha256, fingerprint, db)
    baseline = await receipts.amount_baseline(collective_id, db)

    flags = build_flags(
        claimed_amount=claimed_amount,
        claimed_reason=claimed_reason,
        extraction=extraction,
        duplicates=duplicates,
        baseline=baseline,
    )
    if extraction is None and not flags:
        status = "error"  # no opinion at all — don't imply a clean bill of health
    elif flags:
        status = "flagged"
    else:
        status = "clean"
    return {"status": status, "extraction": extraction,
            "fingerprint": fingerprint, "flags": flags}
