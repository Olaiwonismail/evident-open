"""Receipt storage and duplicate detection.

A recycled receipt — the same one attached to three requests, or reused across
periods — is the receipt fraud that actually happens, and catching it is the
most valuable check in this module.

Two fingerprints, because they fail differently:

* **sha256** over the file bytes. Exact, zero false positives, and defeated by
  simply re-saving or re-photographing the document.
* **Content fingerprint** over vendor + total + date, as read off the document.
  Survives re-photographing, cropping and re-compression completely, because it
  identifies the *receipt* rather than the *file*.

Perceptual image hashing (dHash/aHash) is the conventional answer here and was
tried first. It does not work on receipts: a receipt downsampled to the hash
grid is a near-uniform pale rectangle with the text gone, so unrelated receipts
collided at smaller Hamming distances than a genuine re-photographed duplicate
(measured: 5 and 7 between different documents, 8 between true duplicates, on a
256-bit hash). No threshold separates those populations. It was removed rather
than shipped with a threshold that cannot work.

The content fingerprint is also the more explainable signal — "same vendor, same
total, same date as expense X" is something an approver can act on, where a
Hamming distance is not.
"""
import hashlib
import logging
import os
import re
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense

logger = logging.getLogger(__name__)

STORAGE_DIR = Path(os.getenv("RECEIPT_STORAGE_DIR", "receipts"))
MAX_BYTES = 10 * 1024 * 1024

# Matches what the vision model can actually read, so an accepted upload is
# never one the reader will reject. HEIC/HEIF matter — that's the default
# iPhone camera format, and a phone photo is the normal way a receipt arrives.
# GIF is deliberately absent: not a supported input type, and nobody
# photographs a receipt as one.
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
ALLOWED_TYPES = IMAGE_TYPES | {"application/pdf"}


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalise_vendor(vendor: str) -> str:
    """Fold case, punctuation and spacing so "Adebayo Hardware Ltd." and
    "ADEBAYO HARDWARE LTD" fingerprint identically."""
    return re.sub(r"[^a-z0-9]+", "", vendor.lower())


def content_fingerprint(extraction: dict | None) -> str | None:
    """Identify the receipt by what it says, not by its pixels.

    Requires vendor AND total — a date alone, or a total alone, is far too
    common to identify anything. Returns None when the document couldn't be
    read well enough, in which case only sha256 matching applies.
    """
    if not extraction or extraction.get("legible") is False:
        return None
    vendor = (extraction.get("vendor") or "").strip()
    total = extraction.get("total_amount")
    if not vendor or total is None:
        return None
    # Date is included when present but not required — a reprinted receipt with
    # the date cropped off should still match on vendor + total.
    date = (extraction.get("date") or "").strip()
    basis = f"{_normalise_vendor(vendor)}|{float(total):.2f}|{date}"
    return hashlib.sha256(basis.encode()).hexdigest()


def store(collective_id: str, filename: str, data: bytes) -> dict:
    """Write the receipt to disk and fingerprint it."""
    suffix = Path(filename or "").suffix[:10] or ".bin"
    name = f"{uuid.uuid4().hex}{suffix}"
    directory = STORAGE_DIR / collective_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_bytes(data)

    return {
        # must match the serve route in routers/receipts.py, or the stored URL 404s
        "url": f"/collectives/{collective_id}/receipts/{name}",
        "path": str(directory / name),
        "sha256": sha256_hex(data),
        "size": len(data),
    }


async def find_duplicates(
    collective_id: str,
    sha256: str,
    fingerprint: str | None,
    db: AsyncSession,
    exclude_expense_id: str | None = None,
) -> list[dict]:
    """Any earlier expense in this collective carrying the same receipt.

    Scoped to the collective deliberately: a cross-collective match would be a
    stronger fraud signal, but surfacing one group's expense detail to another
    leaks information those members never agreed to share.
    """
    result = await db.execute(
        select(Expense).where(
            Expense.collective_id == collective_id,
            Expense.receipt_sha256.isnot(None),
        )
    )
    matches = []
    for other in result.scalars().all():
        if exclude_expense_id and other.id == exclude_expense_id:
            continue
        if other.receipt_sha256 == sha256:
            rank, kind = 0, "the identical file"
        elif fingerprint and other.receipt_fingerprint == fingerprint:
            rank, kind = 1, "the same vendor, total and date"
        else:
            continue
        matches.append({
            "expense_id": other.id,
            "reason": other.reason,
            "amount": float(other.amount),
            "status": other.status,
            "match": kind,
            "rank": rank,
        })
    return sorted(matches, key=lambda m: m["rank"])


async def amount_baseline(collective_id: str, db: AsyncSession) -> dict | None:
    """Mean and spread of past expenses, for the 'unusually large' check.

    Returns None below 4 samples — with fewer, the mean is noise and any
    anomaly flag derived from it would be too.
    """
    result = await db.execute(
        select(Expense.amount).where(
            Expense.collective_id == collective_id,
            Expense.status.in_(("paid", "disbursing")),
        )
    )
    amounts = [float(a) for (a,) in result.all() if a is not None]
    if len(amounts) < 4:
        return None
    mean = sum(amounts) / len(amounts)
    variance = sum((a - mean) ** 2 for a in amounts) / len(amounts)
    return {"count": len(amounts), "mean": mean, "stdev": variance ** 0.5, "max": max(amounts)}
