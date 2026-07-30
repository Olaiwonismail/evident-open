"""Receipt upload and verification.

Upload is a separate step from expense submission so the reviewer sees the
verification result *before* committing the expense. The response is advisory
in both directions: flags never prevent submission, and a clean result is not
a guarantee — a forged receipt read correctly still reads as clean.
"""
import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.collective import Collective
from app.services import receipt_ai, receipts

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/collectives", tags=["receipts"])


@router.post("/{collective_id}/receipts")
async def upload_receipt(
    collective_id: str,
    file: UploadFile = File(...),
    amount: float = Form(...),
    reason: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Store a receipt, fingerprint it, and run the advisory checks."""
    exists = (await db.execute(
        select(Collective.id).where(Collective.id == collective_id)
    )).scalar_one_or_none()
    if not exists:
        raise HTTPException(status_code=404, detail="Collective not found")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > receipts.MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Receipt is larger than {receipts.MAX_BYTES // (1024 * 1024)}MB",
        )

    media_type = file.content_type or "application/octet-stream"
    stored = receipts.store(collective_id, file.filename or "receipt", data)

    verdict = await receipt_ai.review(
        data=data,
        media_type=media_type,
        sha256=stored["sha256"],
        collective_id=collective_id,
        claimed_amount=Decimal(str(amount)),
        claimed_reason=reason,
        db=db,
    )

    return {
        "receipt_url": stored["url"],
        "receipt_sha256": stored["sha256"],
        "receipt_fingerprint": verdict["fingerprint"],
        "ai_status": verdict["status"],
        "ai_extraction": verdict["extraction"],
        "ai_flags": verdict["flags"],
        "summary": receipt_ai.summarise(verdict["flags"]),
        # explicit, so the UI never renders a flag as a blocking error
        "blocking": False,
    }


@router.get("/{collective_id}/receipts/{name}")
async def get_receipt(collective_id: str, name: str):
    """Serve a stored receipt. Name is generated server-side at upload, but
    re-validate anyway — never let a caller-supplied path escape the directory."""
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Invalid receipt name")
    path = (receipts.STORAGE_DIR / collective_id / name).resolve()
    root = receipts.STORAGE_DIR.resolve()
    if not str(path).startswith(str(root)) or not path.is_file():
        raise HTTPException(status_code=404, detail="Receipt not found")
    return FileResponse(path)
